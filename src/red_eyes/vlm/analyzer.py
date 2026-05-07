"""VLM analysis via Ollama API for behavior summarization."""

import asyncio
import base64
from io import BytesIO

import httpx
import numpy as np
from PIL import Image

from red_eyes.core.config import VLMConfig
from red_eyes.core.models import Event
from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


class VLMAnalyzer:
    def __init__(self, config: VLMConfig):
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
        )

    async def analyze(self, frames: list[np.ndarray], event: Event) -> str:
        encoded_frames = []
        for frame in frames[: self.config.max_images]:
            encoded = self._encode_frame(frame)
            if encoded:
                encoded_frames.append(encoded)

        if not encoded_frames:
            return self._fallback_summary(event)

        prompt = self._build_prompt(event)

        try:
            summary = await asyncio.wait_for(
                self._call_ollama(prompt, encoded_frames),
                timeout=self.config.timeout,
            )
            logger.info("vlm_analysis_complete", event_type=event.type.value)
            return summary
        except asyncio.TimeoutError:
            logger.error("vlm_timeout", event_type=event.type.value)
            return self._fallback_summary(event)
        except Exception as e:
            logger.error("vlm_error", error=str(e))
            return self._fallback_summary(event)

    async def _call_ollama(self, prompt: str, images: list[str]) -> str:
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "images": images,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256,
            },
        }

        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json()["response"].strip()

    def _encode_frame(self, frame: np.ndarray) -> str | None:
        try:
            img = Image.fromarray(frame)
            img.thumbnail((800, 600))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=75)
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception as e:
            logger.error("frame_encode_failed", error=str(e))
            return None

    def _build_prompt(self, event: Event) -> str:
        return (
            f"{self.config.prompt}\n\n"
            f"Event type: {event.type.value}\n"
            f"Duration: {event.duration:.0f} seconds\n\n"
            f"Describe what is happening in these CCTV frames. "
            f"Respond in Korean, 1-2 sentences."
        )

    def _fallback_summary(self, event: Event) -> str:
        templates = {
            "person_entered": "사람이 카메라 영역에 진입했습니다.",
            "approaching": "사람이 카메라 쪽으로 접근하고 있습니다.",
            "loitering": f"사람이 {event.duration:.0f}초간 머물고 있습니다.",
            "delivery": "택배 배달 행위가 감지되었습니다.",
            "patrolling": "사람이 카메라 주변을 배회하고 있습니다.",
            "person_left": "사람이 카메라 영역을 떠났습니다.",
            "night_movement": "야간 시간대에 움직임이 감지되었습니다.",
        }
        return templates.get(event.type.value, "이벤트가 감지되었습니다.")

    async def close(self) -> None:
        await self._client.aclose()
