"""Pydantic-based configuration with YAML and env var support."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ReconnectConfig(BaseModel):
    initial_delay: float = 1.0
    max_delay: float = 300.0
    max_attempts: int = 100


class FrameConfig(BaseModel):
    target_width: int = 640
    target_height: int = 640
    max_queue_size: int = 3


class RTSPConfig(BaseModel):
    cameras: list["CameraConfig"] = Field(default_factory=list)
    reconnect: ReconnectConfig = Field(default_factory=ReconnectConfig)
    frame: FrameConfig = Field(default_factory=FrameConfig)


class CameraConfig(BaseModel):
    id: str
    name: str
    url: str
    enabled: bool = True


class AdaptiveConfig(BaseModel):
    idle_interval: float = 3.0
    active_interval: float = 0.5
    max_interval: float = 5.0
    cpu_threshold: float = 0.7


class DetectionConfig(BaseModel):
    model: str = "yolov8n.pt"
    confidence: float = 0.5
    device: Literal["mps", "cpu"] = "mps"
    adaptive: AdaptiveConfig = Field(default_factory=AdaptiveConfig)


class VLMConfig(BaseModel):
    provider: str = "ollama"
    model: str = "qwen2-vl:2b"
    base_url: str = "http://localhost:11434"
    timeout: int = 30
    max_images: int = 2
    prompt: str = (
        "CCTV 영상을 분석하여 사람의 행동을 설명하세요. "
        "무엇을 했는지, 얼마나 머물렀는지, 물건 관련 행동이 있었는지 중점으로 설명하세요. "
        "한국어로 1-2 문장만 응답하세요. "
        "사람이 보이지 않으면 '사람이 확인되지 않습니다.'라고 응답하세요."
    )


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
    rate_limit: int = 300
    max_images_per_alert: int = 2


class StorageConfig(BaseModel):
    base_dir: str = "data/events"
    max_disk_gb: float = 1.0
    retention_days: int = 7
    keyframes_per_event: int = 2
    cleanup_interval: int = 3600


class SystemConfig(BaseModel):
    device: Literal["mps", "cpu"] = "mps"
    max_memory_gb: float = 5.0
    log_level: str = "INFO"
    log_file: str = "data/logs/red_eyes.log"


class EventsConfig(BaseModel):
    approach_threshold: float = 3.0
    loitering_threshold: int = 30
    delivery_threshold: int = 10
    patrol_min_moves: int = 3
    night_mode_start: str = "22:00"
    night_mode_end: str = "06:00"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RED_EYES_",
        extra="ignore",
    )

    system: SystemConfig = Field(default_factory=SystemConfig)
    rtsp: RTSPConfig = Field(default_factory=RTSPConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @classmethod
    def from_yaml(cls, path: str = "config/settings.yaml") -> "Settings":
        yaml_path = Path(path)
        if not yaml_path.exists():
            return cls()

        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

        data.setdefault("telegram", {})["bot_token"] = os.getenv(
            "TELEGRAM_BOT_TOKEN",
            data.get("telegram", {}).get("bot_token", ""),
        )
        data.setdefault("telegram", {})["chat_id"] = os.getenv(
            "TELEGRAM_CHAT_ID",
            data.get("telegram", {}).get("chat_id", ""),
        )

        if "rtsp" in data and "cameras" in data["rtsp"]:
            data["rtsp"]["cameras"] = [
                CameraConfig(**c) for c in data["rtsp"]["cameras"]
            ]

        return cls(**data)
