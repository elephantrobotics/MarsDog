"""JSON-to-SimEvent parsers for documented MarsDog ROS2 String topics."""

from __future__ import annotations

from typing import Any, Callable

from . import config
from .sim_state import SimEvent

Parser = Callable[[dict[str, Any]], SimEvent]


def parse_visual_event(data: dict[str, Any]) -> SimEvent:
    events = _string_list(data.get("events"))
    active_target = _dict_or_none(data.get("active_target"))
    payload = {
        "header": data.get("header"),
        "active_target": active_target,
        "faces": data.get("faces"),
        "humans": data.get("humans"),
        "hands": data.get("hands"),
        "tracked_objects": data.get("tracked_objects"),
        "events": events,
        "faces_count": _count(data.get("faces")),
        "humans_count": _count(data.get("humans")),
        "hands_count": _count(data.get("hands")),
        "tracked_objects_count": _count(data.get("tracked_objects")),
        "raw": data,
    }
    event_text = ",".join(events) if events else "no_event"
    summary = (
        f"visual_event: {event_text} "
        f"faces={payload['faces_count']} humans={payload['humans_count']} "
        f"hands={payload['hands_count']} objects={payload['tracked_objects_count']}"
    )
    return SimEvent("visual_event", config.TOPICS["visual_event"], payload, summary)


def parse_audio_event(data: dict[str, Any]) -> SimEvent:
    payload = _pick(
        data,
        "header",
        "event_type",
        "state",
        "wake_word",
        "wake_angle",
        "wake_confidence",
        "speaker_id",
        "speaker_confidence",
        "asr_text",
        "command_id",
        "intent_category",
        "intent_source",
        "intent_confidence",
        "slots",
        "response_text",
        "is_executable",
        "latency_ms",
    )
    payload["raw"] = data

    parts = [f"audio_event: {payload.get('event_type') or 'unknown'}"]
    _append_if_present(parts, "wake_angle", payload.get("wake_angle"))
    _append_if_present(parts, "speaker", payload.get("speaker_id"))
    _append_if_present(parts, "command", payload.get("command_id"))
    _append_if_present(parts, "text", payload.get("asr_text"))
    return SimEvent(
        "audio_event",
        config.TOPICS["audio_event"],
        payload,
        " ".join(parts),
    )


def parse_internal_need_state(data: dict[str, Any]) -> SimEvent:
    payload = _pick(
        data,
        "schema_version",
        "timestamp",
        "event_type",
        "demands",
        "levelEvents",
        "triggered",
        "sleep",
    )
    payload["raw"] = data
    active = _active_names(payload.get("triggered"))
    summary = "need_state: " + (f"triggered={','.join(active)}" if active else "updated")
    return SimEvent(
        "internal_need_state",
        config.TOPICS["internal_need_state"],
        payload,
        summary,
    )


def parse_internal_need_signal_event(data: dict[str, Any]) -> SimEvent:
    payload = _pick(
        data,
        "schema_version",
        "timestamp",
        "event_type",
        "demand",
        "value",
        "level",
        "previousLevel",
        "triggerThreshold",
        "triggerOperator",
        "overflowThreshold",
        "overflowOperator",
        "trigger",
    )
    payload["raw"] = data
    summary = (
        f"need_signal: {payload.get('event_type') or 'unknown'} "
        f"demand={payload.get('demand') or '-'} "
        f"value={_dash(payload.get('value'))} level={payload.get('level') or '-'}"
    )
    return SimEvent(
        "internal_need_signal_event",
        config.TOPICS["internal_need_signal_event"],
        payload,
        summary,
    )


def parse_emotion_state(data: dict[str, Any]) -> SimEvent:
    payload = _pick(
        data,
        "emotions",
        "levelEvents",
        "triggered",
        "dominantEmotion",
        "dominant_emotion",
        "dominantEmotionSignal",
        "dominant_emotion_signal",
        "personality",
        "lastEmotionEventResult",
    )
    payload["dominantEmotion"] = _first_present(
        payload.get("dominantEmotion"),
        payload.get("dominant_emotion"),
    )
    payload["dominantEmotionSignal"] = _first_present(
        payload.get("dominantEmotionSignal"),
        payload.get("dominant_emotion_signal"),
    )
    payload["raw"] = data
    dominant = payload.get("dominantEmotion") or "-"
    signal = _dict_or_none(payload.get("dominantEmotionSignal")) or {}
    signal_type = signal.get("eventType") or signal.get("event_type") or "-"
    summary = f"emotion_state: dominant={dominant} signal={signal_type}"
    return SimEvent(
        "emotion_state",
        config.TOPICS["emotion_state"],
        payload,
        summary,
    )


def parse_emotion_signal_event(data: dict[str, Any]) -> SimEvent:
    payload = _pick(
        data,
        "event_type",
        "emotion",
        "value",
        "level",
        "zone",
        "range",
        "trigger",
        "isDominant",
        "dominantChanged",
    )
    payload["raw"] = data
    level = _first_present(payload.get("level"), payload.get("zone"), payload.get("range"))
    summary = (
        f"emotion_signal: {payload.get('event_type') or 'unknown'} "
        f"emotion={payload.get('emotion') or '-'} "
        f"value={_dash(payload.get('value'))} level={level or '-'}"
    )
    return SimEvent(
        "emotion_signal_event",
        config.TOPICS["emotion_signal_event"],
        payload,
        summary,
    )


def parse_behavior_result_event(data: dict[str, Any]) -> SimEvent:
    behavior_payload = _pick(
        data,
        "behavior_id",
        "behavior_name",
        "status",
        "result",
        "source_event",
        "reason",
        "reward",
        "emotion_delta_json",
        "need_delta_json",
        "timestamp",
    )
    mapping_payload = _pick(
        data,
        "event_id",
        "action_type",
        "demand_type",
        "result_type",
        "metadata",
    )
    payload = {**behavior_payload, **mapping_payload}
    payload["raw"] = data

    has_behavior_format = any(
        data.get(key) is not None
        for key in ("behavior_name", "behavior_id", "status", "result")
    )
    has_mapping_format = any(
        data.get(key) is not None
        for key in ("action_type", "demand_type", "result_type")
    )

    if has_behavior_format and has_mapping_format:
        format_hint = "combined"
    elif has_behavior_format:
        format_hint = "behavior_tree"
    elif has_mapping_format:
        format_hint = "need_emotion_mapping"
    else:
        format_hint = "unknown"

    result_type = _upper_or_none(payload.get("result_type"))
    payload["result_type_mapping"] = config.RESULT_TYPE_MAPPING.get(result_type)
    payload["format_hint"] = format_hint

    summary = _behavior_summary(payload, format_hint)
    return SimEvent(
        "behavior_result_event",
        config.TOPICS["behavior_result_event"],
        payload,
        summary,
        format_hint=format_hint,
    )


def parse_personality_state(data: dict[str, Any]) -> SimEvent:
    payload = _pick(data, "profile", "params", "coefficients")
    payload["raw"] = data
    params = _dict_or_none(payload.get("params")) or {}
    summary = (
        f"personality_state: profile={payload.get('profile') or '-'} "
        f"A={_dash(params.get('A'))} O={_dash(params.get('O'))} "
        f"E={_dash(params.get('E'))} C={_dash(params.get('C'))}"
    )
    return SimEvent(
        "personality_state",
        config.TOPICS["personality_state"],
        payload,
        summary,
    )


PARSER_BY_TOPIC: dict[str, Parser] = {
    config.TOPICS["visual_event"]: parse_visual_event,
    config.TOPICS["audio_event"]: parse_audio_event,
    config.TOPICS["internal_need_state"]: parse_internal_need_state,
    config.TOPICS["internal_need_signal_event"]: parse_internal_need_signal_event,
    config.TOPICS["emotion_state"]: parse_emotion_state,
    config.TOPICS["emotion_signal_event"]: parse_emotion_signal_event,
    config.TOPICS["behavior_result_event"]: parse_behavior_result_event,
    config.TOPICS["personality_state"]: parse_personality_state,
}


def _behavior_summary(payload: dict[str, Any], format_hint: str) -> str:
    behavior_name = payload.get("behavior_name")
    status = payload.get("status")
    result = payload.get("result")
    reward = payload.get("reward")
    source_event = payload.get("source_event")
    action_type = payload.get("action_type")
    demand_type = payload.get("demand_type")
    result_type = payload.get("result_type")

    if format_hint in {"behavior_tree", "combined"} and behavior_name:
        summary = f"behavior_result: {behavior_name} {_dash(status)} -> {_dash(result)}"
        if reward is not None:
            summary += f" reward={reward}"
        if source_event:
            summary += f" source={source_event}"
        return summary

    if format_hint == "need_emotion_mapping":
        mapping = payload.get("result_type_mapping") or "unmapped"
        return (
            f"behavior_result: action={_dash(action_type)} demand={_dash(demand_type)} "
            f"result_type={_dash(result_type)} map={mapping}"
        )

    return "behavior_result: unknown format"


def _pick(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: data.get(key) for key in keys}


def _append_if_present(parts: list[str], label: str, value: Any) -> None:
    if value is not None and str(value) != "":
        parts.append(f"{label}={value}")


def _dash(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _upper_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).upper()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return [str(value)]


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _count(value: Any) -> int:
    if isinstance(value, (list, tuple, dict, set)):
        return len(value)
    if value is None:
        return 0
    return 1


def _active_names(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(name) for name, active in value.items() if active]
    if isinstance(value, (list, tuple)):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("type") or item.get("demand") or item.get("name")
                if name:
                    names.append(str(name))
            elif item:
                names.append(str(item))
        return names
    if value:
        return [str(value)]
    return []
