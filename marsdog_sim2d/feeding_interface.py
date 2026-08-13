"""Thread-safe ROS2 handshake state for UI-controlled feeding."""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from typing import Any


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
        self._food_available = False
        self._dog_at_bowl = False
        self._waiting_for_food = False
        self._eating_authorized = False
        self._active_goal_id: str | None = None
        self._updated_at = time.time()

    def update_from_ui(
        self,
        *,
        food_available: bool,
        dog_at_bowl: bool,
        waiting_for_food: bool,
        eating_authorized: bool,
        active_goal_id: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            reported_goal_id = (
                str(active_goal_id) if active_goal_id else None
            )
            reported_authorized = bool(eating_authorized)
            if (
                self._eating_authorized
                and not reported_authorized
                and bool(food_available)
                and bool(waiting_for_food)
                and reported_goal_id == self._active_goal_id
            ):
                # The ROS service callback can run just after an Arcade frame
                # copied the old state. Preserve its successful authorization
                # until the queued event reaches the next UI frame.
                reported_authorized = True
            values = (
                bool(food_available),
                bool(dog_at_bowl),
                bool(waiting_for_food),
                reported_authorized,
                reported_goal_id,
            )
            previous = (
                self._food_available,
                self._dog_at_bowl,
                self._waiting_for_food,
                self._eating_authorized,
                self._active_goal_id,
            )
            if values != previous:
                (
                    self._food_available,
                    self._dog_at_bowl,
                    self._waiting_for_food,
                    self._eating_authorized,
                    self._active_goal_id,
                ) = values
                self._sequence += 1
                self._updated_at = time.time()
            return self._snapshot_locked()

    def try_start_eating(self) -> FeedingDecision:
        """Authorize eating only when the rendered dog is at a supplied bowl."""

        with self._lock:
            if not self._dog_at_bowl:
                return FeedingDecision(
                    False,
                    "DOG_NOT_AT_BOWL",
                    self._snapshot_locked(),
                )
            if not self._food_available:
                return FeedingDecision(
                    False,
                    "NO_FOOD",
                    self._snapshot_locked(),
                )

            if not self._eating_authorized:
                self._eating_authorized = True
                self._sequence += 1
                self._updated_at = time.time()
            return FeedingDecision(
                True,
                "EATING_AUTHORIZED",
                self._snapshot_locked(),
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def state_json(self) -> str:
        return json.dumps(
            self.snapshot(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "event_type": "FEEDING_STATE",
            "sequence": self._sequence,
            "phase": self._phase_locked(),
            "foodAvailable": self._food_available,
            "dogAtBowl": self._dog_at_bowl,
            "waitingForFood": self._waiting_for_food,
            "waitingForAuthorization": (
                self._waiting_for_food
                and self._food_available
                and not self._eating_authorized
            ),
            "eatingAuthorized": self._eating_authorized,
            "activeGoalId": self._active_goal_id,
            "timestamp": self._updated_at,
        }

    def _phase_locked(self) -> str:
        if self._eating_authorized:
            return "EATING_AUTHORIZED"
        if self._dog_at_bowl and self._food_available:
            return "READY_TO_EAT"
        if self._waiting_for_food:
            return "WAITING_FOR_FOOD"
        if self._food_available:
            return "FOOD_AVAILABLE"
        return "EMPTY_BOWL"
