"""State owned and updated by the Arcade rendering thread."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
from queue import Empty, Queue
import re
import time
from typing import Any

from . import config


@dataclass(slots=True)
class SimEvent:
    """Normalized event passed from ROS callbacks to the Arcade thread."""

    kind: str
    topic: str
    payload: dict[str, Any]
    summary: str
    received_at: float = field(default_factory=time.time)
    format_hint: str | None = None


@dataclass(slots=True)
class TopicStats:
    """Runtime receive stats for one subscribed topic."""

    count: int = 0
    last_received_at: float | None = None
    last_summary: str = ""
    recent_received_at: deque[float] = field(default_factory=lambda: deque(maxlen=64))


@dataclass
class SimState:
    """Mutable page state. Keep this on the Arcade/main thread only."""

    dog_x: float = config.DEFAULT_DOG_X
    dog_y: float = config.DEFAULT_DOG_Y
    dog_heading: float = config.DEFAULT_DOG_HEADING
    user_x: float = config.DEFAULT_USER_X
    user_y: float = config.DEFAULT_USER_Y
    room_objects: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            name: dict(item) for name, item in config.DEFAULT_ROOM_OBJECTS.items()
        }
    )

    active_target: dict[str, Any] | None = None
    latest_visual_event: dict[str, Any] | None = None
    latest_audio_event: dict[str, Any] | None = None

    emotion_state: dict[str, Any] | None = None
    emotion_signal_event: dict[str, Any] | None = None
    internal_need_state: dict[str, Any] | None = None
    internal_need_signal_event: dict[str, Any] | None = None
    personality_state: dict[str, Any] | None = None

    behavior_result_event: dict[str, Any] | None = None
    recent_behavior_results: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=config.MAX_BEHAVIOR_RESULTS)
    )

    active_behavior: str | None = None
    action_status: str = "waiting"
    action_goal_id: str | None = None
    action_behavior_id: str | None = None
    action_progress: float = 0.0
    action_current_action: str = "-"
    action_unit_type: str = "-"
    action_message: str = "-"
    action_safe_to_interrupt: bool | None = None
    action_result: str = "-"
    action_reason: str = "-"
    action_reward: float | None = None
    action_priority_level: int | None = None
    action_params: dict[str, Any] = field(default_factory=dict)
    action_stage_index: int = 0
    action_stage_total: int = 0
    action_stage_label: str = "-"
    action_stage_estimated: bool = True
    action_phase: str = "idle"
    action_target_label: str = "-"
    action_trigger_reason: str = "-"
    action_transition: str = "-"
    action_source: str = "-"
    action_intent: str = "-"
    action_level: str = "-"
    action_interaction_mode: str = "-"
    action_completed_stages: list[str] = field(default_factory=list)
    action_executed_units: list[str] = field(default_factory=list)
    action_started_at: float | None = None
    action_updated_at: float | None = None
    action_result_at: float | None = None
    action_server_available: bool = False
    action_server_message: str = "not initialized"
    recent_action_steps: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=8)
    )
    recent_action_events: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=12)
    )
    manual_injection_count: int = 0
    last_manual_injection: dict[str, Any] | None = None
    event_injector_open: bool = False
    event_injector_group: str = "Audio"
    event_injector_fields: dict[str, str] = field(default_factory=dict)
    event_injector_focused_field: str | None = None
    audio_wake_angle: float | None = None

    # UI-only state. These fields never alter ROS topic names, message fields,
    # or the state values received from ROS2.
    ui_left_collapsed: bool = False
    ui_left_scroll: float = 0.0
    ui_input_tab: str = "Event"
    ui_open_select: str | None = None
    ui_payload_preview: str = ""
    ui_preview_topics: list[str] = field(default_factory=list)
    ui_selected_scenario: str = "high_hunger"
    ui_pending_placement: dict[str, Any] | None = None
    ui_selected_object: str | None = None
    ui_show_fov: bool = True
    ui_collapsed_cards: set[str] = field(default_factory=set)
    ui_right_scroll: float = 0.0
    ui_log_filters: set[str] = field(
        default_factory=lambda: {"VIS", "AUD", "NEED", "EMO", "BEH", "EXEC", "RESULT", "SYS"}
    )
    ui_log_search: str = ""
    ui_log_paused: bool = False
    ui_log_pause_snapshot: list[dict[str, Any]] = field(default_factory=list)
    ui_log_auto_scroll: bool = True
    ui_log_scroll: int = 0
    ui_selected_event_id: int | None = None
    ui_behavior_context_expanded: bool = False
    ui_pending_confirmation: dict[str, Any] | None = None
    ui_log_height: float | None = None
    ui_dragging_log: bool = False
    ui_text_focus: str | None = None

    event_log: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=config.MAX_EVENT_LOG)
    )
    event_records: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=config.MAX_STRUCTURED_EVENTS)
    )
    processed_events: int = 0
    queue_depth: int = 0
    started_at: float = field(default_factory=time.time)
    topic_stats: dict[str, TopicStats] = field(
        default_factory=lambda: {
            topic: TopicStats()
            for topic in (
                *config.TOPICS.values(),
                config.ACTION_NAME,
                config.ACTION_GOAL_TOPIC,
                config.ACTION_FEEDBACK_TOPIC,
                config.ACTION_RESULT_TOPIC,
            )
        }
    )

    def drain_queue(self, event_queue: Queue[SimEvent]) -> int:
        """Apply queued ROS events on the Arcade thread."""

        drained = 0
        while drained < config.QUEUE_DRAIN_LIMIT:
            try:
                event = event_queue.get_nowait()
            except Empty:
                break
            self.apply_event(event)
            drained += 1
        self.queue_depth = _queue_size(event_queue)
        return drained

    def apply_event(self, event: SimEvent) -> None:
        self.processed_events += 1
        self.event_log.append((event.received_at, event.summary))
        self._record_ui_event(event)
        topic_stats = self.topic_stats.setdefault(event.topic, TopicStats())
        topic_stats.count += 1
        topic_stats.last_received_at = event.received_at
        topic_stats.last_summary = event.summary
        topic_stats.recent_received_at.append(event.received_at)

        if event.kind == "visual_event":
            self.latest_visual_event = event.payload
            active_target = event.payload.get("active_target")
            if isinstance(active_target, dict):
                self.active_target = active_target
            return

        if event.kind == "audio_event":
            self.latest_audio_event = event.payload
            self.audio_wake_angle = None
            if (
                event.payload.get("event_type") == "EVT_VOICE_CALL_NAME"
                and event.payload.get("wake_angle") is not None
            ):
                self.audio_wake_angle = _to_float(event.payload.get("wake_angle"))
            return

        if event.kind == "manual_injection":
            self.manual_injection_count += 1
            self.last_manual_injection = {
                **event.payload,
                "received_at": event.received_at,
            }
            return

        if event.kind == "internal_need_state":
            self.internal_need_state = event.payload
            return

        if event.kind == "internal_need_signal_event":
            self.internal_need_signal_event = {
                **event.payload,
                "received_at": event.received_at,
            }
            return

        if event.kind == "emotion_state":
            self.emotion_state = event.payload
            return

        if event.kind == "emotion_signal_event":
            self.emotion_signal_event = {
                **event.payload,
                "received_at": event.received_at,
            }
            return

        if event.kind == "personality_state":
            self.personality_state = event.payload
            return

        if event.kind == "behavior_result_event":
            self.behavior_result_event = event.payload
            self.recent_behavior_results.appendleft(event.payload)
            behavior_name = event.payload.get("behavior_name")
            action_type = event.payload.get("action_type")
            self.active_behavior = _first_text(behavior_name, action_type)
            self.action_status = _derive_action_status(event.payload)
            self.action_trigger_reason = _behavior_result_reason(event.payload)
            self._append_action_event(event, "behavior_result", self.action_trigger_reason)

        if event.kind == "action_server_state":
            self.action_server_available = bool(event.payload.get("available"))
            self.action_server_message = str(event.payload.get("message") or "-")
            return

        if event.kind == "action_goal":
            previous_goal = self.action_goal_id
            previous_behavior = self.active_behavior
            if self.action_status == "running" and previous_goal and previous_goal != _first_text(event.payload.get("goal_id")):
                self.action_transition = f"preempt {previous_behavior or '-'}"
                self._append_action_event(event, "preempt", self.action_transition)
            else:
                self.action_transition = "started"
            self.action_goal_id = _first_text(event.payload.get("goal_id"))
            self.action_behavior_id = _first_text(event.payload.get("behavior_id"))
            self.active_behavior = _first_text(event.payload.get("behavior_name"))
            self.action_status = "running"
            self.action_progress = 0.0
            self.action_current_action = _first_text(event.payload.get("current_action")) or "-"
            self.action_unit_type = _infer_unit_type(self.action_current_action)
            self.action_message = "goal accepted"
            self.action_result = "-"
            self.action_reason = "-"
            self.action_reward = None
            self.action_priority_level = _to_int(event.payload.get("priority_level"))
            self.action_params = _dict(event.payload.get("params"))
            if not self.action_params:
                self.action_params = _json_dict(event.payload.get("params_json"))
            self._apply_action_context()
            self.action_completed_stages = []
            self.action_executed_units = []
            self.action_started_at = event.received_at
            self.action_updated_at = event.received_at
            self.action_result_at = None
            self.action_phase = "start"
            self.action_target_label = _infer_target_label(self.active_behavior, self.action_current_action)
            self.action_trigger_reason = _infer_trigger_reason(self, event.payload)
            self.action_stage_index, self.action_stage_total, self.action_stage_label = _extract_stage(
                event.payload,
                self.action_progress,
                self.action_current_action,
            )
            self.action_stage_estimated = not _has_explicit_stage(event.payload)
            self.recent_action_steps.clear()
            if self.action_current_action != "-":
                self.recent_action_steps.append((event.received_at, self.action_current_action))
            self._append_action_event(event, "goal", f"{self.active_behavior or '-'} <- {self.action_trigger_reason}")
            return

        if event.kind == "action_feedback":
            self._apply_virtual_motion(event.payload)
            self.action_goal_id = _first_text(event.payload.get("goal_id"), self.action_goal_id)
            self.action_behavior_id = _first_text(
                event.payload.get("behavior_id"), self.action_behavior_id
            )
            self.active_behavior = _first_text(
                event.payload.get("behavior_name"), self.active_behavior
            )
            self.action_status = str(event.payload.get("status") or "running").lower()
            self.action_progress = _normalized_progress(event.payload.get("progress"))
            current_action = _first_text(
                event.payload.get("current_action"), self.action_current_action
            ) or "-"
            if current_action != "-" and current_action != self.action_current_action:
                self.recent_action_steps.append((event.received_at, current_action))
                self._append_action_event(event, "stage", current_action)
            self.action_current_action = current_action
            self.action_unit_type = _infer_unit_type(current_action)
            self.action_message = _first_text(event.payload.get("message")) or "-"
            safe_to_interrupt = event.payload.get("safe_to_interrupt")
            self.action_safe_to_interrupt = (
                _to_bool(safe_to_interrupt) if safe_to_interrupt is not None else None
            )
            self.action_updated_at = event.received_at
            self.action_stage_index, self.action_stage_total, self.action_stage_label = _extract_stage(
                event.payload,
                self.action_progress,
                self.action_current_action,
            )
            self.action_stage_estimated = not _has_explicit_stage(event.payload)
            self.action_phase = _first_text(event.payload.get("phase")) or _phase_label(
                self.action_progress,
                self.action_current_action,
            )
            self.action_target_label = (
                _first_text(event.payload.get("target_label"))
                or _infer_target_label(self.active_behavior, self.action_current_action)
            )
            if not self.action_trigger_reason or self.action_trigger_reason == "-":
                self.action_trigger_reason = _infer_trigger_reason(self, event.payload)
            return

        if event.kind == "action_result":
            self._apply_virtual_motion(event.payload)
            self.action_goal_id = _first_text(event.payload.get("goal_id"), self.action_goal_id)
            self.action_behavior_id = _first_text(
                event.payload.get("behavior_id"), self.action_behavior_id
            )
            self.active_behavior = _first_text(
                event.payload.get("behavior_name"), self.active_behavior
            )
            status = str(event.payload.get("status") or "").upper()
            result = str(event.payload.get("result") or status or "").lower()
            self.action_status = _result_status(status, result)
            self.action_result = result or "-"
            self.action_reason = _first_text(event.payload.get("reason")) or "-"
            self.action_reward = _to_float(event.payload.get("reward"))
            self.action_progress = 1.0 if self.action_status == "success" else self.action_progress
            self.action_result_at = event.received_at
            self.action_updated_at = event.received_at
            self.action_phase = _result_phase(status, result)
            self.action_transition = _result_transition(status, result)
            self.action_completed_stages = _string_list(event.payload.get("completed_stages"))
            self.action_executed_units = _string_list(event.payload.get("executed_units"))
            if self.action_status == "success" and self.action_stage_total:
                self.action_stage_index = self.action_stage_total
            self.action_stage_label = self.action_result or self.action_phase
            self._append_action_event(event, self.action_phase, self.action_reason)
            for room_object in self.room_objects.values():
                room_object["active"] = False
            return

    def _apply_action_context(self) -> None:
        self.action_source = _first_text(self.action_params.get("source")) or "-"
        self.action_intent = _first_text(self.action_params.get("intent")) or "-"
        self.action_level = _first_text(
            self.action_params.get("level"), self.action_params.get("variant")
        ) or "-"
        mode = _first_text(self.action_params.get("interaction_mode"))
        if mode is None and self.action_params.get("interactive") is not None:
            mode = "interactive" if _to_bool(self.action_params.get("interactive")) else "solo"
        self.action_interaction_mode = mode or "-"

    def _apply_virtual_motion(self, payload: dict[str, Any]) -> None:
        dog_pose = payload.get("dog_pose")
        if isinstance(dog_pose, dict):
            self.dog_x = _float_or_default(dog_pose.get("x"), self.dog_x)
            self.dog_y = _float_or_default(dog_pose.get("y"), self.dog_y)
            self.dog_heading = _float_or_default(dog_pose.get("heading"), self.dog_heading)

        objects = payload.get("objects")
        if isinstance(objects, dict):
            self.room_objects = {
                str(name): dict(value)
                for name, value in objects.items()
                if isinstance(value, dict)
            }

    def _append_action_event(self, event: SimEvent, kind: str, label: str) -> None:
        self.recent_action_events.appendleft(
            {
                "at": event.received_at,
                "kind": kind,
                "label": label or "-",
                "goal_id": self.action_goal_id or event.payload.get("goal_id"),
                "behavior": self.active_behavior or event.payload.get("behavior_name"),
            }
        )

    def _record_ui_event(self, event: SimEvent) -> None:
        """Maintain a compact presentation cache for the structured event table."""

        source = _ui_event_source(event)
        level = _ui_event_level(event)
        collapse_key = f"{source}|{event.kind}|{event.summary}"
        if self.event_records:
            previous = self.event_records[-1]
            if previous.get("collapse_key") == collapse_key:
                previous["count"] = int(previous.get("count") or 1) + 1
                previous["at"] = event.received_at
                previous["payload"] = event.payload.get("raw", event.payload)
                return

        self.event_records.append(
            {
                "id": self.processed_events,
                "at": event.received_at,
                "first_at": event.received_at,
                "source": source,
                "event": event.kind,
                "level": level,
                "summary": event.summary,
                "topic": event.topic,
                "payload": event.payload.get("raw", event.payload),
                "count": 1,
                "collapse_key": collapse_key,
            }
        )


def _derive_action_status(payload: dict[str, Any]) -> str:
    result_type = _upper_or_none(payload.get("result_type"))
    status = _upper_or_none(payload.get("status"))
    result = _upper_or_none(payload.get("result"))

    if result_type == "STARTED":
        return "running"
    if result_type in {"COMPLETED"} or status == "SUCCESS" or result == "COMPLETED":
        return "success"
    if result_type == "TIMEOUT" or status == "TIMEOUT":
        return "timeout"
    if result_type == "INTERRUPTED":
        return "interrupted"
    if result_type in {"CANCELLED", "CANCELED"} or status in {"CANCELED", "CANCELLED"}:
        return "canceled"
    if result_type == "FAILED" or status == "FAILURE":
        return "failed"
    return "waiting"


def _upper_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).upper()


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_or_default(value: Any, default: float) -> float:
    parsed = _to_float(value)
    return default if parsed is None else parsed


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalized_progress(value: Any) -> float:
    progress = _to_float(value) or 0.0
    if progress > 1.0:
        progress /= 100.0
    return _clamp01(progress)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _extract_stage(
    payload: dict[str, Any],
    progress: float,
    current_action: str,
) -> tuple[int, int, str]:
    for key in ("stage_index", "step_index"):
        stage_index = _to_int(payload.get(key))
        stage_total = _to_int(payload.get("stage_total") or payload.get("step_total"))
        if stage_index is not None and stage_total:
            return max(1, stage_index), max(1, stage_total), _stage_label(payload, current_action)

    text = " ".join(
        str(value)
        for value in (
            payload.get("message"),
            payload.get("current_action"),
        )
        if value is not None
    )
    match = re.search(r"(?:step|stage)?\s*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE)
    if match:
        index = max(1, int(match.group(1)))
        total = max(index, int(match.group(2)))
        return index, total, _stage_label(payload, current_action)

    reported_stage = _first_text(payload.get("current_stage"))
    if progress <= 0:
        return 1, 3, reported_stage or "start"
    if progress >= 0.98:
        return 3, 3, reported_stage or "settle"
    if progress < 0.34:
        return 1, 3, reported_stage or "approach"
    if progress < 0.76:
        return 2, 3, reported_stage or _compact_action_label(current_action)
    return 3, 3, reported_stage or "settle"


def _has_explicit_stage(payload: dict[str, Any]) -> bool:
    for index_key, total_key in (("stage_index", "stage_total"), ("step_index", "step_total")):
        if payload.get(index_key) is not None and payload.get(total_key) is not None:
            return True
    text = str(payload.get("message") or "")
    return re.search(r"(?:step|stage)?\s*\d+\s*/\s*\d+", text, re.IGNORECASE) is not None


def _stage_label(payload: dict[str, Any], current_action: str) -> str:
    explicit = _first_text(
        payload.get("current_stage"),
        payload.get("stage_label"),
        payload.get("step_label"),
    )
    if explicit:
        return explicit
    message = str(payload.get("message") or "")
    match = re.search(
        r"(?:stage|step)\s+(?:\d+\s*/\s*\d+\s*[:=-]?\s*)?([A-Za-z][A-Za-z0-9_-]+)",
        message,
        re.IGNORECASE,
    )
    if match and not match.group(1).upper().startswith("ACT_"):
        return match.group(1).lower().replace("_", " ")
    return _compact_action_label(current_action) or "-"


def _phase_label(progress: float, current_action: str) -> str:
    action = str(current_action or "").upper()
    if any(key in action for key in ("LOCO", "NAV", "WALK", "RUN", "APPROACH", "FOLLOW", "FLEE")):
        return "moving" if progress < 0.78 else "arriving"
    if any(key in action for key in ("MOUTH", "PAW", "POSTURE", "TAIL", "HEAD", "VOCAL", "GROOM")):
        return "interacting"
    if progress < 0.34:
        return "approach"
    if progress < 0.82:
        return "execute"
    return "settle"


def _infer_target_label(behavior: Any, current_action: Any) -> str:
    text = f"{behavior or ''} {current_action or ''}".upper()
    rules = (
        ("food bowl", ("FOOD", "BOWL", "EAT", "WATER")),
        ("toilet pad", ("PAD", "TOILET", "PEE", "POOP", "EXCRETION")),
        ("sleep mat", ("BED", "SLEEP", "NAP", "CURLED")),
        ("toy ball", ("TOY", "BALL", "FETCH", "POUNCE", "OBJECT", "CARRY")),
        ("charger", ("CHARGE", "RECHARGE", "DOCK")),
        ("groom mat", ("GROOM", "CLEAN", "LICK")),
        ("owner", ("OWNER", "USER", "PERSON", "HUMAN", "ANIMAL", "SOCIAL", "INTERACTION", "RESOURCE", "GREET", "INVITE", "HAND", "FOLLOW", "COME", "CUDDLE", "NUDGE")),
        ("safe zone", ("FLEE", "HIDE", "AVOID", "DANGER", "STOP")),
    )
    for label, needles in rules:
        if any(needle in text for needle in needles):
            return label
    return "room"


def _infer_trigger_reason(state: SimState, payload: dict[str, Any]) -> str:
    params = _dict(payload.get("params")) or _json_dict(payload.get("params_json"))
    for key in ("source_event", "trigger_event", "command_id", "intent", "category"):
        value = _first_text(params.get(key), payload.get(key))
        if value:
            return str(value)
    if state.internal_need_signal_event:
        return str(state.internal_need_signal_event.get("event_type") or "need signal")
    if state.emotion_signal_event:
        return str(state.emotion_signal_event.get("event_type") or "emotion signal")
    if state.latest_audio_event:
        return str(state.latest_audio_event.get("command_id") or state.latest_audio_event.get("event_type") or "audio")
    latest_visual = state.latest_visual_event or {}
    events = latest_visual.get("events")
    if isinstance(events, list) and events:
        return ",".join(str(item) for item in events[:2])
    if state.behavior_result_event:
        return _behavior_result_reason(state.behavior_result_event)
    return "-"


def _behavior_result_reason(payload: dict[str, Any]) -> str:
    return (
        _first_text(
            payload.get("source_event"),
            payload.get("action_type"),
            payload.get("demand_type"),
            payload.get("result_type"),
            payload.get("reason"),
        )
        or "-"
    )


def _result_phase(status: str, result: str) -> str:
    text = f"{status} {result}".upper()
    if "CANCEL" in text:
        return "canceled"
    if "INTERRUPT" in text or "PREEMPT" in text:
        return "interrupted"
    if "TIMEOUT" in text:
        return "timeout"
    if "SUCCESS" in text or "COMPLETED" in text:
        return "completed"
    return "failed"


def _result_transition(status: str, result: str) -> str:
    phase = _result_phase(status, result)
    if phase in {"canceled", "interrupted", "timeout", "failed"}:
        return phase
    return "completed"


def _result_status(status: str, result: str) -> str:
    phase = _result_phase(status, result)
    if phase == "completed":
        return "success"
    return phase


def _infer_unit_type(action: str) -> str:
    key = str(action or "").upper()
    if not key or key == "-":
        return "-"
    if any(token in key for token in ("IGNORE_", "POLICY", "NO_MOTION", "COMPLETE_STAGE")):
        return "policy"
    if any(
        token in key
        for token in (
            "MODIFIER",
            "SPEED_SCALE",
            "SLOW_MOVEMENT",
            "ACCELERATION_SCALE",
            "AMPLITUDE_SCALE",
            "DURATION_SCALE",
        )
    ):
        return "modifier"
    if any(
        token in key
        for token in (
            "RETURN_TO_",
            "NAV_",
            "NAVIGATE",
            "SEARCH_",
            "EXPLORE_",
            "FOLLOW_",
            "RETRIEVE_",
            "SEEK_",
            "CHARGE",
        )
    ):
        return "task"
    if "COMPOSITE" in key or "SEQUENCE" in key:
        return "composite"
    return "atomic"


def _compact_action_label(action: str) -> str:
    label = str(action or "-")
    for prefix in ("ACT_POSTURE_", "ACT_LOCO_", "ACT_HEAD_", "ACT_TAIL_", "ACT_MOUTH_", "ACT_PAW_", "ACT_NAV_", "ACT_"):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    return label.lower().replace("_", " ")


def _queue_size(event_queue: Queue[SimEvent]) -> int:
    try:
        return event_queue.qsize()
    except NotImplementedError:
        return 0


def _ui_event_source(event: SimEvent) -> str:
    if event.kind == "visual_event":
        return "VIS"
    if event.kind == "audio_event":
        return "AUD"
    if event.kind.startswith("internal_need"):
        return "NEED"
    if event.kind.startswith("emotion"):
        return "EMO"
    if event.kind == "behavior_result_event":
        return "RESULT"
    if event.kind.startswith("action_"):
        return "EXEC"
    if event.kind == "manual_injection":
        return "BEH"
    return "SYS"


def _ui_event_level(event: SimEvent) -> str:
    summary = event.summary.upper()
    if any(token in summary for token in ("FAILED", "ERROR", "TIMEOUT", "OVERFLOW")):
        return "ERROR"
    if any(token in summary for token in ("TRIGGERED", "INTERRUPT", "CANCEL", "STALE")):
        return "WARN"
    if any(token in summary for token in ("SUCCESS", "COMPLETED", "LIVE", "STARTED")):
        return "OK"
    return "INFO"
