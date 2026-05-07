"""YOLOv8n person detector with adaptive frame skipping for M1."""

import time

import numpy as np
from ultralytics import YOLO

from red_eyes.core.config import DetectionConfig
from red_eyes.core.models import DetectionResult, TrackedPerson
from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


class PersonDetector:
    PERSON_CLASS = 0

    def __init__(self, config: DetectionConfig):
        self.config = config
        self._model: YOLO | None = None
        self._last_detection_time = 0.0
        self._current_interval = config.adaptive.idle_interval
        self._person_detected = False

    def load_model(self) -> None:
        logger.info(
            "loading_detection_model",
            model=self.config.model,
            device=self.config.device,
        )
        self._model = YOLO(self.config.model)

        if self.config.device == "mps":
            import torch
            if not torch.backends.mps.is_available():
                logger.warning("mps_not_available_falling_back_to_cpu")
                self.config.device = "cpu"
            else:
                logger.info("mps_acceleration_enabled")

    def should_process_frame(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last_detection_time
        return elapsed >= self._current_interval

    def detect(self, frame: np.ndarray) -> DetectionResult:
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        start = time.monotonic()

        results = self._model(
            frame,
            classes=[self.PERSON_CLASS],
            conf=self.config.confidence,
            verbose=False,
            device=self.config.device,
        )

        persons = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu())
                persons.append(
                    TrackedPerson(
                        track_id=i,
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        confidence=conf,
                        center=(int((x1 + x2) / 2), int((y1 + y2) / 2)),
                    )
                )

        latency = (time.monotonic() - start) * 1000
        self._last_detection_time = time.monotonic()
        self._person_detected = len(persons) > 0
        self._adjust_interval()

        logger.debug(
            "detection_complete",
            persons=len(persons),
            latency_ms=round(latency, 1),
            interval=self._current_interval,
        )

        return DetectionResult(
            persons=persons,
            timestamp=time.time(),
            frame_shape=frame.shape,
        )

    def _adjust_interval(self) -> None:
        if self._person_detected:
            self._current_interval = self.config.adaptive.active_interval
        else:
            self._current_interval = min(
                self._current_interval * 1.2,
                self.config.adaptive.max_interval,
            )

    @property
    def current_interval(self) -> float:
        return self._current_interval
