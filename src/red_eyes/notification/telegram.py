"""Telegram notification with rate limiting and deduplication."""

import time
from collections import defaultdict
from datetime import datetime
from io import BytesIO

import numpy as np
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from PIL import Image

from red_eyes.core.config import TelegramConfig
from red_eyes.core.models import Event
from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    def __init__(self, config: TelegramConfig):
        self.config = config
        self._bot = Bot(token=config.bot_token)
        self._last_sent: dict[str, float] = defaultdict(float)
        self._dedup_window: dict[str, float] = {}

    async def send_alert(
        self,
        event: Event,
        summary: str,
        frames: list[np.ndarray],
    ) -> None:
        if not self._check_rate_limit(event):
            logger.info("alert_rate_limited", event_type=event.type.value)
            return

        if self._is_duplicate(event):
            logger.info("alert_deduplicated", event_type=event.type.value)
            return

        message = self._build_message(event, summary)

        try:
            await self._bot.send_message(
                chat_id=self.config.chat_id,
                text=message,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("telegram_text_send_failed", error=str(e))
            return

        for i, frame in enumerate(frames[: self.config.max_images_per_alert]):
            try:
                await self._bot.send_photo(
                    chat_id=self.config.chat_id,
                    photo=self._frame_to_bytes(frame),
                    caption=f"[{event.camera_id}] Keyframe {i + 1}",
                )
            except TelegramRetryAfter as e:
                logger.warning(
                    "telegram_rate_limit_retry_after",
                    seconds=e.retry_after,
                )
                await self._bot.session.close()
                self._bot = Bot(token=self.config.bot_token)
            except Exception as e:
                logger.error("telegram_image_send_failed", error=str(e))

        self._last_sent[event.type.value] = time.time()
        self._dedup_window[f"{event.type.value}:{event.camera_id}"] = time.time()

    def _check_rate_limit(self, event: Event) -> bool:
        last = self._last_sent.get(event.type.value, 0)
        return (time.time() - last) >= self.config.rate_limit

    def _is_duplicate(self, event: Event) -> bool:
        key = f"{event.type.value}:{event.camera_id}"
        last = self._dedup_window.get(key, 0)
        return (time.time() - last) < 60

    def _build_message(self, event: Event, summary: str) -> str:
        icons = {
            "person_entered": "🚨",
            "approaching": "⚠️",
            "loitering": "👁️",
            "delivery": "📦",
            "patrolling": "🔄",
            "person_left": "✅",
            "night_movement": "🌙",
        }
        icon = icons.get(event.type.value, "🔴")
        ts = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")

        return (
            f"{icon} <b>RED EYES ALERT</b>\n\n"
            f"📌 <b>유형:</b> {event.type.value}\n"
            f"📍 <b>카메라:</b> {event.camera_id}\n"
            f"⏰ <b>시간:</b> {ts}\n"
            f"⏱️ <b>체류:</b> {event.duration:.0f}초\n\n"
            f"📝 <b>분석:</b>\n{summary}"
        )

    def _frame_to_bytes(self, frame: np.ndarray) -> bytes:
        img = Image.fromarray(frame)
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        buffer.seek(0)
        return buffer.getvalue()

    async def close(self) -> None:
        await self._bot.session.close()
