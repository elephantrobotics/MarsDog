"""Reduce confirmed face identities into presence lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

from marsdog_vision_interaction.messages.visual_event_types import (
    EVT_VISION_FAMILY_PRESENT,
    EVT_VISION_MASTER,
    EVT_VISION_STRANGER,
)


_FAMILY_IDENTITIES = {
    "family_member_1",
    "family_member_2",
    "family_member_3",
    "family_member_4",
}
_EVENT_NAMES = {
    EVT_VISION_MASTER,
    EVT_VISION_FAMILY_PRESENT,
    EVT_VISION_STRANGER,
}
_DEFAULTS = {
    "t_enter_sec": 1.0,
    "t_exit_sec": 2.0,
    "t_retrigger_sec": 3.0,
}
_MAX_DURATION_SEC = 60.0


@dataclass
class _PresenceState:
    active: bool = False
    pending_since: float | None = None
    missing_since: float | None = None
    cooldown_until: float = 0.0


class FacePresenceEventTracker:
    """Track independent ENTER/HOLD/EXIT lifecycles for confirmed face tracks.

    Face track IDs describe geometric tracks, not people. They are therefore
    used only with the event name to scope a lifecycle, as required by the
    visual event contract.
    """

    def __init__(self, config: Any = None) -> None:
        values = config if isinstance(config, dict) else {}
        self.t_enter_sec = self._duration(values, "t_enter_sec")
        self.t_exit_sec = self._duration(values, "t_exit_sec")
        self.t_retrigger_sec = self._duration(values, "t_retrigger_sec")
        self._states: dict[tuple[str, int], _PresenceState] = {}

    @staticmethod
    def _duration(config: dict[str, Any], key: str) -> float:
        value = config.get(key, _DEFAULTS[key])
        if isinstance(value, bool):
            return _DEFAULTS[key]
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return _DEFAULTS[key]
        if (
            not math.isfinite(duration)
            or duration <= 0.0
            or duration > _MAX_DURATION_SEC
        ):
            return _DEFAULTS[key]
        return duration

    @staticmethod
    def _event_key(face: Any) -> tuple[str, int] | None:
        if not isinstance(face, dict):
            return None
        raw_track_id = face.get("track_id")
        if isinstance(raw_track_id, bool):
            return None
        try:
            track_id = int(raw_track_id)
        except (TypeError, ValueError, OverflowError):
            return None
        if track_id <= 0:
            return None
        if isinstance(raw_track_id, float) and not raw_track_id.is_integer():
            return None

        identity_state = str(face.get("identity_state", ""))
        event_name = ""
        if identity_state == "confirmed_known":
            identity = str(face.get("recognized_user", "")).strip()
            if identity == "owner":
                event_name = EVT_VISION_MASTER
            elif identity in _FAMILY_IDENTITIES:
                event_name = EVT_VISION_FAMILY_PRESENT
        elif identity_state == "confirmed_unknown":
            event_name = EVT_VISION_STRANGER

        if event_name not in _EVENT_NAMES:
            return None
        return event_name, track_id

    def update(
        self,
        faces: Any,
        *,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Return lifecycle declarations for one visual state snapshot.

        ``now`` is injectable for callers that need a shared monotonic sample;
        production callers omit it and use ``time.monotonic()``.
        """
        try:
            current_time = time.monotonic() if now is None else float(now)
        except (TypeError, ValueError, OverflowError):
            current_time = time.monotonic()
        if not math.isfinite(current_time):
            current_time = time.monotonic()

        eligible: set[tuple[str, int]] = set()
        if isinstance(faces, list):
            for face in faces:
                key = self._event_key(face)
                if key is not None:
                    eligible.add(key)

        output: list[dict[str, Any]] = []
        for key in sorted(eligible | self._states.keys()):
            state = self._states.setdefault(key, _PresenceState())
            present = key in eligible
            event_name, track_id = key

            if state.active:
                if present:
                    if (
                        state.missing_since is not None
                        and current_time - state.missing_since >= self.t_exit_sec
                    ):
                        state.active = False
                        state.pending_since = current_time
                        state.missing_since = None
                        state.cooldown_until = current_time + self.t_retrigger_sec
                        output.append(self._record(event_name, "EXIT", track_id))
                        continue
                    state.missing_since = None
                    output.append(self._record(event_name, "HOLD", track_id))
                    continue

                if state.missing_since is None:
                    state.missing_since = current_time
                if current_time - state.missing_since >= self.t_exit_sec:
                    state.active = False
                    state.pending_since = None
                    state.missing_since = None
                    state.cooldown_until = current_time + self.t_retrigger_sec
                    output.append(self._record(event_name, "EXIT", track_id))
                else:
                    output.append(self._record(event_name, "HOLD", track_id))
                continue

            if present:
                if state.pending_since is None:
                    state.pending_since = current_time
                if (
                    current_time - state.pending_since >= self.t_enter_sec
                    and current_time >= state.cooldown_until
                ):
                    state.active = True
                    state.pending_since = None
                    output.append(self._record(event_name, "ENTER", track_id))
                continue

            state.pending_since = None
            if current_time >= state.cooldown_until:
                del self._states[key]

        return output

    @staticmethod
    def _record(event_name: str, state: str, track_id: int) -> dict[str, Any]:
        return {
            "event_name": event_name,
            "state": state,
            "track_id": track_id,
        }
