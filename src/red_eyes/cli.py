"""Main application entry point and orchestrator."""

import asyncio
import gc
import signal
import sys

import cv2
import numpy as np

from red_eyes.core.config import Settings
from red_eyes.core.models import Event, EventType
from red_eyes.core.queue import BoundedAsyncQueue
from red_eyes.capture.rtsp import RTSPCaptureManager
from red_eyes.detection.person import PersonDetector
from red_eyes.events.tracker import EventTracker
from red_eyes.vlm.analyzer import VLMAnalyzer
from red_eyes.notification.telegram import TelegramNotifier
from red_eyes.storage.manager import StorageManager
from red_eyes.utils.logger import setup_logging, get_logger
from red_eyes.utils.memory import check_memory_limit, get_memory_usage_gb

logger = get_logger(__name__)


class RedEyesApp:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.settings = Settings.from_yaml(config_path)
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._event_cooldowns: dict[str, float] = {}

        self.queue = BoundedAsyncQueue(
            maxsize=self.settings.rtsp.frame.max_queue_size
        )
        self.capture = RTSPCaptureManager(self.settings.rtsp)
        self.detector = PersonDetector(self.settings.detection)
        self.tracker = EventTracker(self.settings)
        self.vlm = VLMAnalyzer(self.settings.vlm)
        self.telegram = TelegramNotifier(self.settings.telegram)
        self.storage = StorageManager(self.settings.storage)

    async def run(self) -> None:
        setup_logging(
            self.settings.system.log_level,
            self.settings.system.log_file,
        )
        logger.info("red_eyes_starting", version="0.1.0")

        self._running = True

        self.detector.load_model()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig, lambda: asyncio.create_task(self.shutdown())
            )

        for camera in self.settings.rtsp.cameras:
            if camera.enabled:
                await self.capture.start(camera)

        tasks = [
            asyncio.create_task(self._capture_loop()),
            asyncio.create_task(self._detection_loop()),
            asyncio.create_task(self._storage_cleanup_loop()),
            asyncio.create_task(self._memory_monitor_loop()),
        ]

        logger.info("all_components_started")
        await self._shutdown_event.wait()

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._cleanup()

    async def _capture_loop(self) -> None:
        while self._running:
            for camera in self.settings.rtsp.cameras:
                if not camera.enabled:
                    continue

                frame = await self.capture.read_frame(camera)
                if frame is None:
                    continue

                frame = cv2.resize(
                    frame,
                    (
                        self.settings.rtsp.frame.target_width,
                        self.settings.rtsp.frame.target_height,
                    ),
                )

                await self.queue.put((camera, frame))

            await asyncio.sleep(0.033)

    async def _detection_loop(self) -> None:
        while self._running:
            item = await self.queue.get(timeout=1.0)
            if item is None:
                continue

            camera, frame = item

            if not self.detector.should_process_frame():
                continue

            try:
                detection = self.detector.detect(frame)
                detection.camera_id = camera.id

                events = self.tracker.process(detection)

                for event in events:
                    if self._should_process_event(event):
                        await self._handle_event(event, camera, frame)

            except Exception as e:
                logger.error("detection_error", error=str(e))

    def _should_process_event(self, event: Event) -> bool:
        key = f"{event.type.value}:{event.camera_id}"
        now = event.timestamp

        cooldown_map = {
            EventType.PERSON_ENTERED: 120,
            EventType.APPROACHING: 60,
            EventType.LOITERING: 180,
            EventType.DELIVERY: 300,
            EventType.PATROLLING: 300,
            EventType.PERSON_LEFT: 60,
            EventType.NIGHT_MOVEMENT: 300,
        }

        cooldown = cooldown_map.get(event.type, 120)
        last = self._event_cooldowns.get(key, 0)

        if now - last < cooldown:
            return False

        self._event_cooldowns[key] = now
        return True

    async def _handle_event(
        self, event: Event, camera, frame: np.ndarray
    ) -> None:
        keyframes = [frame.copy()]

        try:
            summary = await self.vlm.analyze(keyframes, event)

            await self.storage.save_event(event, keyframes, summary)

            await self.telegram.send_alert(event, summary, keyframes)

        except Exception as e:
            logger.error("event_handling_error", error=str(e))
        finally:
            for kf in keyframes:
                del kf
            gc.collect()

    async def _storage_cleanup_loop(self) -> None:
        while self._running:
            try:
                await self.storage.cleanup_old()
                await self.storage.check_and_enforce_limit()
            except Exception as e:
                logger.error("cleanup_error", error=str(e))

            await asyncio.sleep(self.settings.storage.cleanup_interval)

    async def _memory_monitor_loop(self) -> None:
        while self._running:
            mem_gb = get_memory_usage_gb()
            within_limit = check_memory_limit(self.settings.system.max_memory_gb)

            logger.info(
                "memory_status",
                usage_gb=round(mem_gb, 2),
                limit_gb=self.settings.system.max_memory_gb,
                within_limit=within_limit,
            )

            if not within_limit:
                logger.warning("memory_limit_exceeded_triggering_gc")
                gc.collect()

            await asyncio.sleep(60)

    async def shutdown(self) -> None:
        logger.info("shutting_down")
        self._running = False
        self._shutdown_event.set()

    async def _cleanup(self) -> None:
        await self.capture.stop_all()
        await self.vlm.close()
        await self.telegram.close()
        gc.collect()
        logger.info("red_eyes_stopped")


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/settings.yaml"
    app = RedEyesApp(config_path)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
