"""Core data models for the CCTV analysis system."""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    PERSON_ENTERED = "person_entered"
    APPROACHING = "approaching"
    LOITERING = "loitering"
    DELIVERY = "delivery"
    PATROLLING = "patrolling"
    PERSON_LEFT = "person_left"
    NIGHT_MOVEMENT = "night_movement"


class EventState(Enum):
    NEW = "new"
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass
class TrackedPerson:
    track_id: int
    bbox: tuple[int, int, int, int]
    confidence: float
    center: tuple[int, int]
    area: int = 0

    def __post_init__(self):
        x1, y1, x2, y2 = self.bbox
        self.area = (x2 - x1) * (y2 - y1)


@dataclass
class DetectionResult:
    persons: list[TrackedPerson]
    timestamp: float
    frame_shape: tuple
    camera_id: str = ""


@dataclass
class Event:
    type: EventType
    camera_id: str
    timestamp: float
    state: EventState
    persons: list[TrackedPerson]
    message: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    keyframes: list = field(default_factory=list)
    _first_seen: float = field(default_factory=time.time)

    @property
    def duration(self) -> float:
        return time.time() - self._first_seen
