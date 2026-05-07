"""Event storage with automatic cleanup and disk usage limits."""

import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from red_eyes.core.config import StorageConfig
from red_eyes.core.models import Event
from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


class StorageManager:
    def __init__(self, config: StorageConfig):
        self.config = config
        self.base_dir = Path(config.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_event(
        self,
        event: Event,
        frames: list[np.ndarray],
        summary: str,
    ) -> Path | None:
        date_str = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d")
        event_dir = self.base_dir / date_str / event.id
        event_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for i, frame in enumerate(frames[: self.config.keyframes_per_event]):
            path = event_dir / f"frame_{i + 1:03d}.jpg"
            img = Image.fromarray(frame)
            img.save(path, format="JPEG", quality=80)
            saved_paths.append(str(path.relative_to(self.base_dir)))

        metadata = {
            "id": event.id,
            "type": event.type.value,
            "camera_id": event.camera_id,
            "timestamp": event.timestamp,
            "duration": event.duration,
            "summary": summary,
            "frames": saved_paths,
        }
        metadata_path = event_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        logger.info(
            "event_saved",
            event_id=event.id,
            path=str(event_dir),
            frames=len(saved_paths),
        )
        return event_dir

    async def cleanup_old(self) -> int:
        deleted = 0
        cutoff = time.time() - (self.config.retention_days * 86400)

        for date_dir in sorted(self.base_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            for event_dir in date_dir.iterdir():
                metadata = event_dir / "metadata.json"
                if metadata.exists():
                    data = json.loads(metadata.read_text())
                    if data.get("timestamp", 0) < cutoff:
                        shutil.rmtree(event_dir)
                        deleted += 1

        for date_dir in sorted(self.base_dir.iterdir()):
            if date_dir.is_dir() and not any(date_dir.iterdir()):
                date_dir.rmdir()

        if deleted:
            logger.info("cleanup_completed", deleted=deleted)
        return deleted

    async def check_and_enforce_limit(self) -> int:
        total = self._get_disk_usage()
        limit_bytes = self.config.max_disk_gb * 1024**3

        if total <= limit_bytes:
            return 0

        deleted = 0
        events = self._list_events()
        events.sort(key=lambda e: e.get("timestamp", 0))

        for event_data in events:
            if self._get_disk_usage() <= limit_bytes:
                break
            event_path = Path(event_data["_path"])
            shutil.rmtree(event_path.parent, ignore_errors=True)
            deleted += 1

        if deleted:
            logger.warning(
                "disk_limit_enforced",
                deleted=deleted,
                usage_gb=self._get_disk_usage() / 1024**3,
            )
        return deleted

    def _get_disk_usage(self) -> int:
        total = 0
        for path in self.base_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def _list_events(self) -> list[dict]:
        events = []
        for metadata_path in self.base_dir.rglob("metadata.json"):
            data = json.loads(metadata_path.read_text())
            data["_path"] = str(metadata_path)
            events.append(data)
        return events
