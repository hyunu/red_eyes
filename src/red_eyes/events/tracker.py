"""Event tracking with state machine for behavior analysis."""

import time
from enum import Enum

from red_eyes.core.config import EventsConfig, Settings
from red_eyes.core.models import DetectionResult, Event, EventType, EventState, TrackedPerson
from red_eyes.utils.logger import get_logger

logger = get_logger(__name__)


class PersonState(Enum):
    IDLE = "idle"
    APPROACHING = "approaching"
    LOITERING = "loitering"
    DELIVERY = "delivery"
    PATROLLING = "patrolling"
    LEAVING = "leaving"


class TrackedPersonState:
    def __init__(self, person: TrackedPerson, config: EventsConfig):
        self.person = person
        self.state = PersonState.IDLE
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.positions: list[tuple[int, int]] = [person.center]
        self.config = config
        self._prev_center = person.center

    def update(self, person: TrackedPerson) -> None:
        self.person = person
        self.last_seen = time.time()
        self.positions.append(person.center)

        dx = person.center[0] - self._prev_center[0]
        dy = person.center[1] - self._prev_center[1]
        distance = (dx**2 + dy**2) ** 0.5
        self._prev_center = person.center

        self._transition_state(distance)

    def _transition_state(self, distance: float) -> None:
        now = time.time()
        duration = now - self.first_seen
        old_state = self.state

        if self.state == PersonState.IDLE:
            if distance > 5:
                self.state = PersonState.APPROACHING

        elif self.state == PersonState.APPROACHING:
            if duration >= self.config.loitering_threshold:
                self.state = PersonState.LOITERING

        elif self.state == PersonState.LOITERING:
            if distance < 3 and duration > self.config.delivery_threshold:
                self.state = PersonState.DELIVERY
            elif self._count_direction_changes() >= self.config.patrol_min_moves:
                self.state = PersonState.PATROLLING

        elif self.state == PersonState.DELIVERY:
            if distance > 10:
                self.state = PersonState.LEAVING

        elif self.state == PersonState.PATROLLING:
            if distance < 2:
                self.state = PersonState.LOITERING

        if old_state != self.state:
            logger.info(
                "person_state_changed",
                state=f"{old_state.value}->{self.state.value}",
                duration=round(duration, 1),
            )

    def _count_direction_changes(self) -> int:
        if len(self.positions) < 4:
            return 0
        changes = 0
        for i in range(2, len(self.positions) - 1):
            dx1 = self.positions[i][0] - self.positions[i - 1][0]
            dx2 = self.positions[i + 1][0] - self.positions[i][0]
            if dx1 * dx2 < 0:
                changes += 1
        return changes

    @property
    def duration(self) -> float:
        return self.last_seen - self.first_seen

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > 5.0


class EventTracker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._tracked: dict[int, TrackedPersonState] = {}
        self._next_id = 0

    def process(self, detection: DetectionResult) -> list[Event]:
        events = []
        current_ids = set()

        for person in detection.persons:
            if person.track_id in self._tracked:
                self._tracked[person.track_id].update(person)
            else:
                tracked = TrackedPersonState(person, self.settings.events)
                self._tracked[person.track_id] = tracked
                events.append(
                    Event(
                        type=EventType.PERSON_ENTERED,
                        camera_id=detection.camera_id,
                        timestamp=time.time(),
                        state=EventState.NEW,
                        persons=[person],
                        message="사람이 카메라 영역에 진입했습니다.",
                    )
                )
            current_ids.add(person.track_id)

        for tid, tracked in self._tracked.items():
            if tid not in current_ids:
                continue
            event = self._check_state_event(tracked, detection.camera_id)
            if event:
                events.append(event)

        stale_ids = [
            tid for tid, tracked in self._tracked.items() if tracked.is_stale
        ]
        for tid in stale_ids:
            tracked = self._tracked.pop(tid)
            if tracked.duration > 5:
                events.append(
                    Event(
                        type=EventType.PERSON_LEFT,
                        camera_id=detection.camera_id,
                        timestamp=time.time(),
                        state=EventState.COMPLETED,
                        persons=[tracked.person],
                        message=f"사람이 카메라 영역을 떠났습니다. (체류: {tracked.duration:.0f}초)",
                    )
                )

        if self._is_night():
            for tid in current_ids:
                tracked = self._tracked.get(tid)
                if tracked and tracked.duration < 10:
                    events.append(
                        Event(
                            type=EventType.NIGHT_MOVEMENT,
                            camera_id=detection.camera_id,
                            timestamp=time.time(),
                            state=EventState.NEW,
                            persons=[tracked.person],
                            message="야간 시간대에 움직임이 감지되었습니다.",
                        )
                    )

        return events

    def _check_state_event(
        self, tracked: TrackedPersonState, camera_id: str
    ) -> Event | None:
        state = tracked.state
        duration = tracked.duration

        if state == PersonState.APPROACHING and duration >= self.settings.events.approach_threshold:
            return Event(
                type=EventType.APPROACHING,
                camera_id=camera_id,
                timestamp=time.time(),
                state=EventState.ACTIVE,
                persons=[tracked.person],
                message="사람이 카메라 쪽으로 접근하고 있습니다.",
            )

        if state == PersonState.LOITERING:
            return Event(
                type=EventType.LOITERING,
                camera_id=camera_id,
                timestamp=time.time(),
                state=EventState.ACTIVE,
                persons=[tracked.person],
                message=f"사람이 {duration:.0f}초간 머물고 있습니다.",
            )

        if state == PersonState.DELIVERY:
            return Event(
                type=EventType.DELIVERY,
                camera_id=camera_id,
                timestamp=time.time(),
                state=EventState.ACTIVE,
                persons=[tracked.person],
                message="택배 배달 행위가 감지되었습니다.",
            )

        if state == PersonState.PATROLLING:
            return Event(
                type=EventType.PATROLLING,
                camera_id=camera_id,
                timestamp=time.time(),
                state=EventState.ACTIVE,
                persons=[tracked.person],
                message="사람이 카메라 주변을 배회하고 있습니다.",
            )

        return None

    def _is_night(self) -> bool:
        from datetime import datetime
        now = datetime.now().time()
        start = datetime.strptime(self.settings.events.night_mode_start, "%H:%M").time()
        end = datetime.strptime(self.settings.events.night_mode_end, "%H:%M").time()
        if start > end:
            return now >= start or now <= end
        return start <= now <= end
