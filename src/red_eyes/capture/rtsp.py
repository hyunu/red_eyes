"""RTSP stream capture with exponential backoff reconnection."""

import asyncio

import cv2
import numpy as np

from red_eyes.core.config import RTSPConfig, CameraConfig
from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


class RTSPCaptureManager:
    def __init__(self, config: RTSPConfig):
        self.config = config
        self._caps: dict[str, cv2.VideoCapture] = {}
        self._reconnect_counts: dict[str, int] = {}
        self._last_frame_time: dict[str, float] = {}

    async def start(self, camera: CameraConfig) -> None:
        if camera.id in self._caps:
            return
        self._reconnect_counts[camera.id] = 0
        await self._connect(camera)
        logger.info("rtsp_capture_started", camera_id=camera.id)

    async def _connect(self, camera: CameraConfig) -> bool:
        cap = cv2.VideoCapture(camera.url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MILLIS, 5000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MILLIS, 3000)

        if not cap.isOpened():
            logger.error("rtsp_open_failed", camera_id=camera.id)
            return False

        self._caps[camera.id] = cap
        self._reconnect_counts[camera.id] = 0
        self._last_frame_time[camera.id] = cv2.getTickCount()
        return True

    async def read_frame(self, camera: CameraConfig) -> np.ndarray | None:
        cap = self._caps.get(camera.id)
        if cap is None:
            return None

        ret, frame = cap.read()
        if not ret or frame is None:
            await self._handle_disconnect(camera)
            return None

        self._last_frame_time[camera.id] = cv2.getTickCount()
        return frame

    async def _handle_disconnect(self, camera: CameraConfig) -> None:
        count = self._reconnect_counts.get(camera.id, 0)
        if count >= self.config.reconnect.max_attempts:
            logger.error(
                "max_reconnect_attempts_reached",
                camera_id=camera.id,
                attempts=count,
            )
            return

        delay = min(
            self.config.reconnect.initial_delay * (2**count),
            self.config.reconnect.max_delay,
        )

        logger.warning(
            "rtsp_reconnecting",
            camera_id=camera.id,
            attempt=count + 1,
            delay=round(delay, 1),
        )

        if camera.id in self._caps:
            self._caps[camera.id].release()
            del self._caps[camera.id]

        await asyncio.sleep(delay)

        success = await self._connect(camera)
        if success:
            logger.info("rtsp_reconnected", camera_id=camera.id)
        else:
            self._reconnect_counts[camera.id] = count + 1
            await self._handle_disconnect(camera)

    async def stop(self, camera_id: str) -> None:
        cap = self._caps.pop(camera_id, None)
        if cap:
            cap.release()
        self._last_frame_time.pop(camera_id, None)
        logger.info("rtsp_capture_stopped", camera_id=camera_id)

    async def stop_all(self) -> None:
        for camera_id in list(self._caps.keys()):
            await self.stop(camera_id)
