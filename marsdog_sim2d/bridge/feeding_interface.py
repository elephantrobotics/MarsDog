"""Thread-safe ROS2 handshake state for UI-controlled feeding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import threading
import time
from typing import Any


class FeedingPhase(str, Enum):
    """Handshake states reported to ROS2."""

    EMPTY_BOWL = "EMPTY_BOWL"
    FOOD_AVAILABLE = "FOOD_AVAILABLE"
    WAITING_FOR_FOOD = "WAITING_FOR_FOOD"
    READY_TO_EAT = "READY_TO_EAT"
    EATING_AUTHORIZED = "EATING_AUTHORIZED"


@dataclass(frozen=True, slots=True)
class FeedingDecision:
    accepted: bool
    reason: str
    state: dict[str, Any]

    def response_message(self) -> str:
        return json.dumps(
            {
                "accepted": self.accepted,
                "reason": self.reason,
                "state": self.state,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


class FeedingCoordinator:
    """Share the Arcade-owned bowl state with ROS callbacks safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._phase = FeedingPhase.EMPTY_BOWL
        self._food_available = False
        self._dog_at_bowl = False
        self._waiting_for_food = False
        self._active_goal_id: str | None = None
        self._updated_at = time.time()

    def update_from_ui(self, *, food_available: bool, dog_at_bowl: bool, waiting_for_food: bool, eating_authorized: bool, active_goal_id: str) -> dict[str, Any]:
        with self._lock:
            next_phase = self._phase_after_ui_update_locked(
                food_available=food_available,
                dog_at_bowl=dog_at_bowl,
                waiting_for_food=waiting_for_food,
                eating_authorized=eating_authorized,
                active_goal_id=active_goal_id,
            )
            values = food_available, dog_at_bowl, waiting_for_food, next_phase, active_goal_id

            previous = (
                self._food_available,
                self._dog_at_bowl,
                self._waiting_for_food,
                self._phase,
                self._active_goal_id,
            )
            if values != previous:
                (
                    self._food_available,
                    self._dog_at_bowl,
                    self._waiting_for_food,
                    self._phase,
                    self._active_goal_id,
                ) = values
                self._sequence += 1
                self._updated_at = time.time()

            return self._snapshot_locked()

    def try_start_eating(self) -> FeedingDecision:
        """Authorize eating only when the rendered dog is at a supplied bowl."""
        with self._lock:
            if not self._dog_at_bowl:
                return FeedingDecision(False, "DOG_NOT_AT_BOWL", self._snapshot_locked())

            if not self._food_available:
                return FeedingDecision(False, "NO_FOOD", self._snapshot_locked())

            if self._phase is not FeedingPhase.EATING_AUTHORIZED:
                self._phase = FeedingPhase.EATING_AUTHORIZED
                self._sequence += 1
                self._updated_at = time.time()

            return FeedingDecision(True, "EATING_AUTHORIZED", self._snapshot_locked())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def state_json(self) -> str:
        return json.dumps(
            self.snapshot(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _phase_after_ui_update_locked(
        self,
        *,
        food_available: bool,
        dog_at_bowl: bool,
        waiting_for_food: bool,
        eating_authorized: bool,
        active_goal_id: str | None,
    ) -> FeedingPhase:
        if eating_authorized:
            return FeedingPhase.EATING_AUTHORIZED

        if (
            self._phase is FeedingPhase.EATING_AUTHORIZED
            and food_available
            and waiting_for_food
            and active_goal_id == self._active_goal_id
        ):
            # The service can authorize eating before its event reaches the UI.
            # A stale UI frame for the same goal must not undo that transition.
            return FeedingPhase.EATING_AUTHORIZED

        if dog_at_bowl and food_available:
            return FeedingPhase.READY_TO_EAT
        if waiting_for_food:
            return FeedingPhase.WAITING_FOR_FOOD
        if food_available:
            return FeedingPhase.FOOD_AVAILABLE
        return FeedingPhase.EMPTY_BOWL

    def _snapshot_locked(self) -> dict[str, Any]:
        authorized = self._phase is FeedingPhase.EATING_AUTHORIZED
        return {
            "event_type": "FEEDING_STATE",
            "sequence": self._sequence,
            "phase": self._phase.value,
            "foodAvailable": self._food_available,
            "dogAtBowl": self._dog_at_bowl,
            "waitingForFood": self._waiting_for_food,
            "waitingForAuthorization": (
                self._waiting_for_food
                and self._food_available
                and not authorized
            ),
            "eatingAuthorized": authorized,
            "activeGoalId": self._active_goal_id,
            "timestamp": self._updated_at,
        }
