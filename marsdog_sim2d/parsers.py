"""JSON-to-SimEvent parsers for documented MarsDog ROS2 String topics."""

from __future__ import annotations

from typing import Any, Callable

from . import config
from .sim_state import SimEvent

Parser = Callable[[dict[str, Any]], SimEvent]


def parse_simulation_time_state(data: dict[str, Any]) -> SimEvent:
    source = _payload_object(
        data,
        "time_state",
        "timeState",
        "payload",
        required_keys=(
            "timeContext",
            "time_context",
            "virtualDateTime",
            "virtual_datetime",
        ),
    )
    raw_context = _first_present(
        source.get("timeContext"),
        source.get("time_context"),
    )
    time_context = _normalize_time_context(raw_context)
    if not time_context:
        time_context = _normalize_time_context(source)
    payload = {
        "event_type": _first_present(
            source.get("event_type"),
            source.get("eventType"),
        ),
        "tickSequence": _first_present(
            source.get("tickSequence"),
            source.get("tick_sequence"),
        ),
        "timeContext": time_context,
        "raw": data,
    }
    summary = (
        f"simulation_time: {payload.get('event_type') or 'unknown'} "
        f"virtual={time_context.get('virtualDateTime') or '-'} "
        f"scale={_dash(time_context.get('effectiveScale'))}"
    )
    return SimEvent(
        "simulation_time_state",
        config.TOPICS["simulation_time_state"],
        payload,
        summary,
    )


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
    source = _payload_object(
        data,
        "state",
        "need_state",
        "needState",
        "payload",
        required_keys=(
            "demands",
            "needs",
            "needStates",
            "internalNeeds",
            "triggered",
        ),
    )
    raw_demands = _first_present(
        source.get("demands"),
        source.get("needs"),
        source.get("needStates"),
        source.get("internalNeeds"),
    )
    demands = _normalize_named_state_map(raw_demands, config.DEMAND_NAMES)
    if not demands:
        demands = _normalize_top_level_states(source, config.DEMAND_NAMES)
    payload = {
        "schema_version": _first_present(
            source.get("schema_version"),
            source.get("schemaVersion"),
        ),
        "timestamp": source.get("timestamp"),
        "event_type": _first_present(
            source.get("event_type"),
            source.get("eventType"),
        ),
        "demands": demands,
        "levelEvents": _normalize_named_value_map(
            _first_present(
                source.get("levelEvents"),
                source.get("level_events"),
            ),
            config.DEMAND_NAMES,
        ),
        "triggered": _first_present(
            source.get("triggered"),
            source.get("activeDemands"),
            source.get("active_demands"),
        ),
        "sleep": _first_present(
            source.get("sleep"),
            source.get("sleepState"),
            source.get("sleep_state"),
        ),
        "timeContext": _normalize_time_context(
            _first_present(
                source.get("timeContext"),
                source.get("time_context"),
            )
        ),
    }
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
    source = _payload_object(
        data,
        "signal",
        "event",
        "payload",
        required_keys=("demand", "need", "event_type", "eventType"),
    )
    demand = _canonical_name(
        _first_present(
            source.get("demand"),
            source.get("need"),
            source.get("name"),
            source.get("type"),
        ),
        config.DEMAND_NAMES,
    )
    payload = {
        "schema_version": _first_present(
            source.get("schema_version"),
            source.get("schemaVersion"),
        ),
        "timestamp": source.get("timestamp"),
        "event_type": _first_present(
            source.get("event_type"),
            source.get("eventType"),
        ),
        "demand": demand,
        "value": _first_present(
            source.get("value"),
            source.get("currentValue"),
            source.get("current_value"),
        ),
        "level": _first_present(
            source.get("level"),
            source.get("state"),
        ),
        "previousLevel": _first_present(
            source.get("previousLevel"),
            source.get("previous_level"),
        ),
        "triggerThreshold": _first_present(
            source.get("triggerThreshold"),
            source.get("trigger_threshold"),
        ),
        "triggerOperator": _first_present(
            source.get("triggerOperator"),
            source.get("trigger_operator"),
        ),
        "urgentThreshold": _first_present(
            source.get("urgentThreshold"),
            source.get("urgent_threshold"),
        ),
        "urgentOperator": _first_present(
            source.get("urgentOperator"),
            source.get("urgent_operator"),
        ),
        "overflowThreshold": _first_present(
            source.get("overflowThreshold"),
            source.get("overflow_threshold"),
        ),
        "overflowOperator": _first_present(
            source.get("overflowOperator"),
            source.get("overflow_operator"),
        ),
        "trigger": source.get("trigger"),
        "timeContext": _normalize_time_context(
            _first_present(
                source.get("timeContext"),
                source.get("time_context"),
            )
        ),
    }
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
        "schema_version",
        "timestamp",
        "emotions",
        "levelEvents",
        "triggered",
        "dominantEmotion",
        "dominant_emotion",
        "dominantEmotionSignal",
        "dominant_emotion_signal",
        "personality",
        "lastEmotionEventResult",
        "timeContext",
    )
    payload["dominantEmotion"] = _first_present(
        payload.get("dominantEmotion"),
        payload.get("dominant_emotion"),
    )
    payload["dominantEmotionSignal"] = _first_present(
        payload.get("dominantEmotionSignal"),
        payload.get("dominant_emotion_signal"),
    )
    payload["timeContext"] = _normalize_time_context(
        _first_present(
            data.get("timeContext"),
            data.get("time_context"),
        )
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
        "schema_version",
        "timestamp",
        "event_type",
        "emotion",
        "value",
        "triggerThreshold",
        "triggerOperator",
        "level",
        "zone",
        "range",
        "trigger",
        "isDominant",
        "dominantChanged",
        "timeContext",
    )
    payload["timeContext"] = _normalize_time_context(
        _first_present(
            data.get("timeContext"),
            data.get("time_context"),
        )
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
    config.TOPICS["simulation_time_state"]: parse_simulation_time_state,
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


def _payload_object(
    data: dict[str, Any],
    *container_keys: str,
    required_keys: tuple[str, ...],
) -> dict[str, Any]:
    """Return a documented object or a common JSON envelope containing it."""

    if any(key in data for key in required_keys):
        return data
    for key in container_keys:
        candidate = data.get(key)
        if (
            isinstance(candidate, dict)
            and any(name in candidate for name in required_keys)
        ):
            return {**data, **candidate}
    return data


def _normalize_time_context(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    aliases = {
        "scale": ("scale",),
        "effectiveScale": ("effectiveScale", "effective_scale"),
        "virtualDateTime": ("virtualDateTime", "virtual_datetime"),
        "virtualTimestamp": ("virtualTimestamp", "virtual_timestamp"),
        "virtualElapsedSeconds": (
            "virtualElapsedSeconds",
            "virtual_elapsed_seconds",
        ),
        "wallTimestamp": ("wallTimestamp", "wall_timestamp"),
    }
    normalized: dict[str, Any] = {}
    for canonical, keys in aliases.items():
        value = _first_present(*(source.get(key) for key in keys))
        if value is not None:
            normalized[canonical] = value
    return normalized


def _normalize_named_state_map(
    value: Any,
    canonical_names: tuple[str, ...],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, (list, tuple)):
        items = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = _first_present(
                item.get("demand"),
                item.get("need"),
                item.get("name"),
                item.get("type"),
            )
            if name is not None:
                items.append((name, item))
    else:
        return normalized

    for raw_name, raw_state in items:
        name = _canonical_name(raw_name, canonical_names)
        if name is None:
            continue
        normalized[name] = _normalize_state_value(raw_state)
    return normalized


def _normalize_top_level_states(
    source: dict[str, Any],
    canonical_names: tuple[str, ...],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name in canonical_names:
        value = None
        for key in (
            name,
            name.lower(),
            _camel_to_snake(name),
            f"{name.lower()}Value",
            f"{_camel_to_snake(name)}_value",
        ):
            if key in source:
                value = source.get(key)
                break
        if value is not None:
            normalized[name] = _normalize_state_value(value)
    return normalized


def _normalize_named_value_map(
    value: Any,
    canonical_names: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        canonical: raw_value
        for raw_name, raw_value in value.items()
        if (canonical := _canonical_name(raw_name, canonical_names)) is not None
    }


def _normalize_state_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    normalized["value"] = _first_present(
        value.get("value"),
        value.get("current"),
        value.get("currentValue"),
        value.get("current_value"),
        value.get("score"),
    )
    normalized["level"] = _first_present(
        value.get("level"),
        value.get("state"),
        value.get("status"),
    )
    level_event = _first_present(
        value.get("levelEvent"),
        value.get("level_event"),
        value.get("eventType"),
        value.get("event_type"),
    )
    if level_event is not None:
        normalized["levelEvent"] = level_event
    triggered = _first_present(
        value.get("triggered"),
        value.get("isTriggered"),
        value.get("is_triggered"),
        value.get("active"),
    )
    if triggered is not None:
        normalized["triggered"] = triggered
    return normalized


def _canonical_name(
    value: Any,
    canonical_names: tuple[str, ...],
) -> str | None:
    if value is None:
        return None
    key = "".join(character for character in str(value).casefold() if character.isalnum())
    for name in canonical_names:
        canonical_key = "".join(
            character for character in name.casefold() if character.isalnum()
        )
        if key == canonical_key:
            return name
    return str(value)


def _camel_to_snake(value: str) -> str:
    characters: list[str] = []
    for character in value:
        if character.isupper() and characters:
            characters.append("_")
        characters.append(character.lower())
    return "".join(characters)


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
