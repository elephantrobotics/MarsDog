"""Manual ROS2 event injection templates for the Arcade UI."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import time
from typing import Any

from . import config


MANUAL_INJECTION_TOPIC = "manual_event_injector"
MANUAL_SOURCE = "marsdog_sim2d"
INJECTOR_GROUPS = ("Audio", "Need", "Emotion", "Vision", "Result", "Personality")
DEFAULT_INJECTOR_GROUP = "Audio"
_VOICE_EVENT_BY_COMMAND_ID = {
    "CMD_SIT": "EVT_VOICE_COMMAND_SIT",
    "CMD_COME_HERE": "EVT_VOICE_COMMAND_COME",
    "CMD_HAND": "EVT_VOICE_COMMAND_GIVE_PAW",
    "CMD_GIVE_PAW": "EVT_VOICE_COMMAND_GIVE_PAW",
    "CMD_FOLLOW": "EVT_VOICE_COMMAND_FOLLOW",
    "CMD_STOP": "EVT_VOICE_COMMAND_STOP",
    "CMD_LIE_DOWN": "EVT_VOICE_COMMAND_LIE_DOWN",
    "CMD_STAND_UP": "EVT_VOICE_COMMAND_STAND",
    "CMD_WAIT": "EVT_VOICE_COMMAND_WAIT",
    "CMD_HIGH_FIVE": "EVT_VOICE_COMMAND_HIGH_FIVE",
    "CMD_ROLL_OVER": "EVT_VOICE_COMMAND_ROLL",
    "CMD_SPIN": "EVT_VOICE_COMMAND_SPIN",
    "CMD_RETURN_TO_OWNER": "EVT_VOICE_COMMAND_RETURN",
    "CMD_DROP_OBJECT": "EVT_VOICE_COMMAND_DROP",
    "CMD_PLAY_DEAD": "EVT_VOICE_COMMAND_PLAY_DEAD",
    "CMD_BRING_OBJECT": "EVT_VOICE_COMMAND_BRING",
    "CMD_FETCH": "EVT_VOICE_COMMAND_FETCH",
}
SCENARIOS = (
    ("high_hunger", "High Hunger", "Hunger overflow drives food seeking"),
    ("low_energy", "Low Energy", "Critical energy drives recharge"),
    ("owner_calls", "Owner Calls Dog", "Owner visible plus name call"),
    ("joy_interaction", "Joy Interaction", "Owner present with high joy"),
    ("fear_response", "Fear Response", "Unknown human with high fear"),
    ("explore_toy", "Explore Toy", "Toy detection plus exploration need"),
)

_RAIL_X = config.EVENT_PANEL_LEFT + 12
_RAIL_TOP = config.WORLD_TOP - 48
_RAIL_WIDTH = config.EVENT_PANEL_WIDTH - 24
_DRAWER_X = _RAIL_X
_DRAWER_WIDTH = _RAIL_WIDTH
_ITEM_HEIGHT = 18
_ITEM_GAP = 4
_INPUT_HEIGHT = 19
_INPUT_GAP = 4


@dataclass(frozen=True, slots=True)
class EventMessageSpec:
    topic: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EventTemplate:
    template_id: str
    group: str
    label: str
    messages: tuple[EventMessageSpec, ...]


@dataclass(frozen=True, slots=True)
class InputFieldSpec:
    field_id: str
    group: str
    label: str
    max_chars: int = 80


@dataclass(frozen=True, slots=True)
class InjectionMessage:
    topic: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InjectionCommand:
    template_id: str
    label: str
    messages: tuple[InjectionMessage, ...]


def build_injection_command(template_id: str) -> InjectionCommand:
    template = EVENT_TEMPLATE_BY_ID[template_id]
    timestamp = time.time()
    messages = tuple(
        InjectionMessage(spec.topic, _with_timestamp(spec.payload, timestamp, template))
        for spec in template.messages
    )
    return InjectionCommand(template.template_id, template.label, messages)


def default_field_values() -> dict[str, str]:
    return dict(_DEFAULT_FIELD_VALUES)


def ensure_field_defaults(values: dict[str, str] | None) -> dict[str, str]:
    merged = default_field_values()
    if values:
        merged.update({str(key): str(value) for key, value in values.items()})
    return merged


def field_max_chars(field_id: str) -> int:
    spec = _FIELD_SPEC_BY_ID.get(field_id)
    return spec.max_chars if spec is not None else 80


def next_field_id(group: str, current_field_id: str | None) -> str | None:
    specs = CUSTOM_FIELD_SPECS.get(normalize_group(group), ())
    if not specs:
        return None
    if current_field_id is None:
        return specs[0].field_id
    field_ids = [spec.field_id for spec in specs]
    try:
        index = field_ids.index(current_field_id)
    except ValueError:
        return field_ids[0]
    return field_ids[(index + 1) % len(field_ids)]


def build_custom_injection_command(
    group: str,
    field_values: dict[str, str] | None,
) -> InjectionCommand:
    group = normalize_group(group)
    fields = ensure_field_defaults(field_values)
    timestamp = time.time()

    if group == "Audio":
        label, messages = _build_custom_audio(fields)
    elif group == "Need":
        label, messages = _build_custom_need(fields)
    elif group == "Emotion":
        label, messages = _build_custom_emotion(fields)
    elif group == "Vision":
        label, messages = _build_custom_vision(fields)
    elif group == "Result":
        label, messages = _build_custom_result(fields)
    elif group == "Personality":
        label, messages = _build_custom_personality(fields)
    else:
        label, messages = "Custom Audio", _build_custom_audio(fields)[1]

    template = _custom_template(group, label)
    stamped = tuple(
        InjectionMessage(
            message.topic,
            _with_timestamp(message.payload, timestamp, template),
        )
        for message in messages
    )
    return InjectionCommand(f"custom_{group.lower()}", label, stamped)


def build_scenario_command(scenario_id: str) -> InjectionCommand:
    """Compose existing manual injections into a repeatable UI scenario."""

    fields = default_field_values()
    commands: list[InjectionCommand] = []
    labels = {item[0]: item[1] for item in SCENARIOS}

    if scenario_id == "high_hunger":
        fields.update(need_demand="Hunger", need_value="94")
        commands.append(build_custom_injection_command("Need", fields))
    elif scenario_id == "low_energy":
        fields.update(need_demand="Energy", need_value="7")
        commands.append(build_custom_injection_command("Need", fields))
    elif scenario_id == "owner_calls":
        fields.update(
            vision_events="EVT_VISION_MASTER",
            vision_identity="owner",
            audio_event_type="EVT_VOICE_CALL_NAME",
            audio_asr_text="MarsDog",
            audio_speaker_id="owner",
            audio_confidence="0.96",
        )
        commands.extend(
            (
                build_custom_injection_command("Vision", fields),
                build_custom_injection_command("Audio", fields),
            )
        )
    elif scenario_id == "joy_interaction":
        fields.update(
            vision_events="EVT_VISION_MASTER",
            vision_identity="owner",
            emotion_name="Joy",
            emotion_value="88",
        )
        commands.extend(
            (
                build_custom_injection_command("Vision", fields),
                build_custom_injection_command("Emotion", fields),
            )
        )
    elif scenario_id == "fear_response":
        fields.update(
            vision_events="EVT_VISION_STRANGER",
            vision_identity="stranger",
            emotion_name="Fear",
            emotion_value="86",
        )
        commands.extend(
            (
                build_custom_injection_command("Vision", fields),
                build_custom_injection_command("Emotion", fields),
            )
        )
    elif scenario_id == "explore_toy":
        fields.update(
            vision_events="EVT_VISION_TOY",
            vision_identity="none",
            vision_object="dog toy ball",
            need_demand="Exploration",
            need_value="78",
        )
        commands.extend(
            (
                build_custom_injection_command("Vision", fields),
                build_custom_injection_command("Need", fields),
            )
        )
    else:
        raise KeyError(f"Unknown scenario: {scenario_id}")

    messages = tuple(message for command in commands for message in command.messages)
    return InjectionCommand(
        f"scenario_{scenario_id}",
        labels.get(scenario_id, scenario_id),
        messages,
    )


def place_injection_command(
    command: InjectionCommand,
    normalized_x: float,
    normalized_y: float,
) -> InjectionCommand:
    """Apply a map-picked point to coordinate fields already present in a payload."""

    point_x = _clamp(normalized_x, 0.0, 1.0)
    point_y = _clamp(normalized_y, 0.0, 1.0)
    messages: list[InjectionMessage] = []
    for message in command.messages:
        payload = deepcopy(message.payload)
        if message.topic == config.TOPICS["visual_event"]:
            active_target = payload.get("active_target")
            if isinstance(active_target, dict) and active_target:
                active_target["body_center"] = [point_x, point_y]
                active_target["face_center"] = [point_x, max(0.0, point_y - 0.12)]
                bbox = active_target.get("bbox")
                width = float(bbox[2]) if isinstance(bbox, list) and len(bbox) >= 4 else 0.24
                height = float(bbox[3]) if isinstance(bbox, list) and len(bbox) >= 4 else 0.55
                active_target["bbox"] = [
                    _clamp(point_x - width / 2, 0.0, 1.0),
                    _clamp(point_y - height / 2, 0.0, 1.0),
                    width,
                    height,
                ]
            for collection_name, default_width, default_height in (
                ("faces", 0.10, 0.12),
                ("humans", 0.24, 0.55),
            ):
                collection = payload.get(collection_name)
                if not isinstance(collection, list):
                    continue
                for item in collection:
                    if not isinstance(item, dict):
                        continue
                    width = float(item.get("w") or default_width)
                    height = float(item.get("h") or default_height)
                    item["x"] = _clamp(point_x - width / 2, 0.0, 1.0)
                    item["y"] = _clamp(point_y - height / 2, 0.0, 1.0)
            tracked_objects = payload.get("tracked_objects")
            if isinstance(tracked_objects, list):
                for item in tracked_objects:
                    if not isinstance(item, dict):
                        continue
                    item["center_x"] = point_x
                    item["center_y"] = point_y
                    width = float(item.get("w") or 0.12)
                    height = float(item.get("h") or 0.12)
                    item["x"] = _clamp(point_x - width / 2, 0.0, 1.0)
                    item["y"] = _clamp(point_y - height / 2, 0.0, 1.0)
        messages.append(InjectionMessage(message.topic, payload))
    return InjectionCommand(command.template_id, command.label, tuple(messages))


def template_at(x: float, y: float) -> EventTemplate | None:
    item = hit_layout_item(x, y, is_open=True, active_group=DEFAULT_INJECTOR_GROUP)
    if item is not None and item["kind"] == "button":
        return item["template"]
    return None


def hit_layout_item(
    x: float,
    y: float,
    is_open: bool,
    active_group: str,
    field_values: dict[str, str] | None = None,
    focused_field: str | None = None,
) -> dict[str, Any] | None:
    for item in iter_layout_items(is_open, active_group, field_values, focused_field):
        if not item.get("clickable", False):
            continue
        if item["x"] <= x <= item["x"] + item["w"] and item["y"] <= y <= item["y"] + item["h"]:
            return item
    return None


def iter_layout_items(
    is_open: bool = False,
    active_group: str = DEFAULT_INJECTOR_GROUP,
    field_values: dict[str, str] | None = None,
    focused_field: str | None = None,
) -> list[dict[str, Any]]:
    active_group = normalize_group(active_group)
    fields = ensure_field_defaults(field_values)
    items: list[dict[str, Any]] = []
    y = _RAIL_TOP - 22
    items.append(
        {
            "kind": "toggle",
            "label": "Event Injector",
            "x": _RAIL_X,
            "y": y,
            "w": _RAIL_WIDTH,
            "h": 20,
            "clickable": True,
        }
    )
    y -= 25
    for group in INJECTOR_GROUPS:
        items.append(
            {
                "kind": "group_tab",
                "label": group,
                "group": group,
                "active": group == active_group,
                "x": _RAIL_X,
                "y": y,
                "w": _RAIL_WIDTH,
                "h": _ITEM_HEIGHT,
                "clickable": True,
            }
        )
        y -= _ITEM_HEIGHT + _ITEM_GAP

    if not is_open:
        return items

    drawer_y = y - 6
    group_templates = [template for template in EVENT_TEMPLATES if template.group == active_group]
    field_specs = CUSTOM_FIELD_SPECS.get(active_group, ())
    custom_rows = len(field_specs) + 1 if field_specs else 0
    row_count = custom_rows + len(group_templates)
    items.append(
        {
            "kind": "drawer",
            "label": active_group,
            "x": _DRAWER_X,
            "y": drawer_y - 31 - row_count * (_INPUT_HEIGHT + _INPUT_GAP),
            "w": _DRAWER_WIDTH,
            "h": 35 + row_count * (_INPUT_HEIGHT + _INPUT_GAP),
            "clickable": False,
        }
    )
    items.append(
        {
            "kind": "drawer_title",
            "label": active_group,
            "x": _DRAWER_X + 8,
            "y": drawer_y - 1,
            "w": _DRAWER_WIDTH - 18,
            "h": 18,
            "clickable": False,
        }
    )
    y = drawer_y - 25
    for spec in field_specs:
        items.append(
            {
                "kind": "input",
                "field": spec,
                "value": fields.get(spec.field_id, ""),
                "active": focused_field == spec.field_id,
                "x": _DRAWER_X + 8,
                "y": y - _INPUT_HEIGHT,
                "w": _DRAWER_WIDTH - 16,
                "h": _INPUT_HEIGHT,
                "clickable": True,
            }
        )
        y -= _INPUT_HEIGHT + _INPUT_GAP

    if field_specs:
        items.append(
            {
                "kind": "custom_send",
                "label": f"Send {active_group}",
                "x": _DRAWER_X + 8,
                "y": y - _INPUT_HEIGHT,
                "w": _DRAWER_WIDTH - 16,
                "h": _INPUT_HEIGHT,
                "clickable": True,
            }
        )
        y -= _INPUT_HEIGHT + _INPUT_GAP

    for template in group_templates:
        items.append(
            {
                "kind": "button",
                "template": template,
                "x": _DRAWER_X + 8,
                "y": y - _ITEM_HEIGHT,
                "w": _DRAWER_WIDTH - 16,
                "h": _ITEM_HEIGHT,
                "clickable": True,
            }
        )
        y -= _ITEM_HEIGHT + _ITEM_GAP
    return items


def normalize_group(group: str) -> str:
    return group if group in INJECTOR_GROUPS else DEFAULT_INJECTOR_GROUP


CUSTOM_FIELD_SPECS: dict[str, tuple[InputFieldSpec, ...]] = {
    "Audio": (
        InputFieldSpec("audio_event_type", "Audio", "event", 32),
        InputFieldSpec("audio_asr_text", "Audio", "asr", 48),
        InputFieldSpec("audio_command_id", "Audio", "cmd", 28),
        InputFieldSpec("audio_wake_angle", "Audio", "angle", 8),
        InputFieldSpec("audio_speaker_id", "Audio", "speaker", 24),
        InputFieldSpec("audio_confidence", "Audio", "conf", 8),
    ),
    "Need": (
        InputFieldSpec("need_demand", "Need", "demand", 24),
        InputFieldSpec("need_value", "Need", "value", 8),
    ),
    "Emotion": (
        InputFieldSpec("emotion_name", "Emotion", "emotion", 20),
        InputFieldSpec("emotion_value", "Emotion", "value", 8),
    ),
    "Vision": (
        InputFieldSpec("vision_events", "Vision", "events", 64),
        InputFieldSpec("vision_identity", "Vision", "identity", 24),
        InputFieldSpec("vision_pose", "Vision", "pose", 24),
        InputFieldSpec("vision_object", "Vision", "object", 32),
    ),
    "Result": (
        InputFieldSpec("result_action_type", "Result", "action", 34),
        InputFieldSpec("result_demand_type", "Result", "demand", 24),
        InputFieldSpec("result_type", "Result", "result", 18),
        InputFieldSpec("result_metadata", "Result", "metadata", 90),
    ),
    "Personality": (
        InputFieldSpec("personality_profile", "Personality", "profile", 28),
        InputFieldSpec("personality_a", "Personality", "A", 6),
        InputFieldSpec("personality_o", "Personality", "O", 6),
        InputFieldSpec("personality_e", "Personality", "E", 6),
        InputFieldSpec("personality_c", "Personality", "C", 6),
    ),
}
_FIELD_SPEC_BY_ID = {
    spec.field_id: spec
    for specs in CUSTOM_FIELD_SPECS.values()
    for spec in specs
}

_DEFAULT_FIELD_VALUES = {
    "audio_event_type": "EVT_VOICE_COMMAND_KNOWN",
    "audio_asr_text": "坐下",
    "audio_command_id": "CMD_SIT",
    "audio_wake_angle": "0",
    "audio_speaker_id": "owner",
    "audio_confidence": "0.95",
    "need_demand": "Hunger",
    "need_value": "82",
    "emotion_name": "Joy",
    "emotion_value": "90",
    "vision_events": "EVT_VISION_MASTER",
    "vision_identity": "owner",
    "vision_pose": "standing",
    "vision_object": "",
    "result_action_type": "ACTION_EAT",
    "result_demand_type": "auto",
    "result_type": "COMPLETED",
    "result_metadata": '{"foodType":"NormalFood","portions":1,"eatEfficiency":"Full"}',
    "personality_profile": "Custom",
    "personality_a": "80",
    "personality_o": "80",
    "personality_e": "80",
    "personality_c": "70",
}


_DEMAND_SPECS: dict[str, dict[str, Any]] = {
    "Hunger": {"normal": 42.0, "triggerThreshold": 70, "triggerOperator": "gt", "overflowThreshold": 90, "overflowOperator": "gt"},
    "Bladder": {"normal": 35.0, "triggerThreshold": 75, "triggerOperator": "gt", "overflowThreshold": 90, "overflowOperator": "gt"},
    "Sleepiness": {"normal": 30.0, "triggerThreshold": 65, "triggerOperator": "gt", "overflowThreshold": 90, "overflowOperator": "gt"},
    "Cleanliness": {"normal": 38.0, "triggerThreshold": 70, "triggerOperator": "gt", "overflowThreshold": 90, "overflowOperator": "gt"},
    "Energy": {"normal": 82.0, "triggerThreshold": 20, "triggerOperator": "lt", "overflowThreshold": 10, "overflowOperator": "lt"},
    "Social": {"normal": 34.0, "triggerThreshold": 60, "triggerOperator": "gt", "overflowThreshold": 90, "overflowOperator": "gt"},
    "Exploration": {"normal": 32.0, "triggerThreshold": 60, "triggerOperator": "gt", "overflowThreshold": 90, "overflowOperator": "gt"},
}

_EMOTION_SPECS: dict[str, dict[str, Any]] = {
    "Joy": {"triggerThreshold": 30, "triggerOperator": "gte"},
    "Excite": {"triggerThreshold": 40, "triggerOperator": "gte"},
    "Anxiety": {"triggerThreshold": 25, "triggerOperator": "gte"},
    "Fear": {"triggerThreshold": 30, "triggerOperator": "gte"},
    "Curious": {"triggerThreshold": 20, "triggerOperator": "gte"},
    "Calm": {"triggerThreshold": 0, "triggerOperator": "gte"},
}

_EMOTION_LEVEL_RANGES: dict[str, tuple[tuple[str, int, int], ...]] = {
    "Calm": (("NORMAL", 0, 60), ("HIGH", 61, 100)),
    "Joy": (("LOW", 30, 60), ("MID", 61, 85), ("HIGH", 86, 100)),
    "Excite": (("LOW", 40, 70), ("HIGH", 71, 100)),
    "Anxiety": (("LOW", 25, 50), ("HIGH", 51, 100)),
    "Fear": (("LOW", 30, 60), ("HIGH", 61, 100)),
    "Curious": (("LOW", 20, 50), ("HIGH", 51, 100)),
}


def resolve_need_output(demand: str, value: float) -> tuple[str, str]:
    """Derive a documented need level and signal event from a 0-100 value."""

    resolved_demand = demand if demand in _DEMAND_SPECS else "Hunger"
    spec = _DEMAND_SPECS[resolved_demand]
    resolved_value = max(0.0, min(100.0, float(value)))
    if spec["triggerOperator"] == "lt":
        if resolved_value < spec["overflowThreshold"]:
            level = "OVERFLOW"
        elif resolved_value < spec["triggerThreshold"]:
            level = "TRIGGERED"
        else:
            level = "NORMAL"
    else:
        if resolved_value > spec["overflowThreshold"]:
            level = "OVERFLOW"
        elif resolved_value > spec["triggerThreshold"]:
            level = "TRIGGERED"
        else:
            level = "NORMAL"
    suffix = "RECOVERED" if level == "NORMAL" else level
    return level, f"NEED_{resolved_demand.upper()}_{suffix}"


def resolve_emotion_output(
    emotion: str,
    value: float,
) -> tuple[str, str | None, tuple[int, int] | None]:
    """Derive the documented emotion interval and optional signal event."""

    resolved_emotion = emotion if emotion in _EMOTION_LEVEL_RANGES else "Joy"
    resolved_value = max(0.0, min(100.0, float(value)))
    for level, minimum, maximum in _EMOTION_LEVEL_RANGES[resolved_emotion]:
        if minimum <= resolved_value <= maximum:
            return (
                level,
                f"EMO_{resolved_emotion.upper()}_{level}",
                (minimum, maximum),
            )
    return "NONE", None, None

_ACTION_DEMAND: dict[str, str] = {
    "ACTION_EAT": "Hunger",
    "ACTION_DEFECATE": "Bladder",
    "ACTION_SLEEP": "Sleepiness",
    "ACTION_GROOM": "Cleanliness",
    "ACTION_RECHARGE": "Energy",
    "ACTION_PLAY_INVITE": "Social",
    "ACTION_SOCIAL_GREET": "Social",
    "ACTION_BOUNDARY_TEST": "Social",
    "ACTION_ATTENTION_SEEK": "Social",
    "ACTION_RESOURCE_SHARE": "Social",
    "ACTION_EXPLORE": "Exploration",
    "ACTION_SPACE_EXPLORE": "Exploration",
    "ACTION_OBJECT_EXPLORE": "Exploration",
}


def _with_timestamp(
    payload: dict[str, Any],
    timestamp: float,
    template: EventTemplate,
) -> dict[str, Any]:
    data = deepcopy(payload)
    data["timestamp"] = timestamp
    data["manual_source"] = MANUAL_SOURCE
    data["manual_event_id"] = template.template_id
    header = data.get("header")
    if isinstance(header, dict):
        header["stamp"] = timestamp
        data["header"] = header
    return data


def _custom_template(group: str, label: str) -> EventTemplate:
    return EventTemplate(f"custom_{group.lower()}", group, label, ())


def _build_custom_audio(fields: dict[str, str]) -> tuple[str, tuple[InjectionMessage, ...]]:
    event_type = _field(fields, "audio_event_type", "EVT_VOICE_COMMAND_KNOWN").upper()
    confidence = _clamp(_float_field(fields, "audio_confidence", 0.95), 0.0, 1.0)
    command_id = _field(fields, "audio_command_id", "CMD_SIT")
    if event_type == "EVT_VOICE_COMMAND_KNOWN":
        event_type = _VOICE_EVENT_BY_COMMAND_ID.get(
            command_id,
            "EVT_VOICE_COMMAND_UNKNOWN",
        )
    payload: dict[str, Any] = {
        "header": {"frame_id": "base_link"},
        "event_type": event_type,
    }

    if event_type == "EVT_VOICE_CALL_NAME":
        payload.update(
            {
                "wake_word": _field(fields, "audio_asr_text", "你好小狗"),
                "wake_angle": _float_field(fields, "audio_wake_angle", 0.0),
                "wake_confidence": max(1.0, confidence * 1400.0),
                "state": "attention",
            }
        )
    elif event_type in {"EVT_VOICE_MASTER_ID", "EVT_VOICE_STRANGER_ID"}:
        payload.update(
            {
                "speaker_id": _field(
                    fields,
                    "audio_speaker_id",
                    "owner" if event_type == "EVT_VOICE_MASTER_ID" else "unknown",
                ),
                "speaker_confidence": confidence,
            }
        )
    else:
        if event_type == "EVT_VOICE_COMMAND_UNKNOWN" and command_id == "CMD_SIT":
            command_id = "CMD_UNKNOWN"
        payload.update(
            {
                "command_id": command_id,
                "intent_category": _intent_category_for_voice(event_type, command_id),
                "intent_source": "manual_ui",
                "intent_confidence": confidence,
                "slots": [{"key": "raw_tag", "value": _raw_tag_for_command(command_id, event_type)}],
                "asr_text": _field(fields, "audio_asr_text", ""),
                "response_text": "",
                "is_executable": (
                    event_type in _VOICE_EVENT_BY_COMMAND_ID.values()
                    and command_id != "CMD_UNKNOWN"
                ),
                "state": "execution",
                "latency_ms": 0.0,
            }
        )

    label = f"Audio {event_type}"
    return label, (InjectionMessage(config.TOPICS["audio_event"], payload),)


def _build_custom_need(fields: dict[str, str]) -> tuple[str, tuple[InjectionMessage, ...]]:
    demand = _choice(_field(fields, "need_demand", "Hunger"), config.DEMAND_NAMES)
    value = _clamp(_float_field(fields, "need_value", 82.0), 0.0, 100.0)
    level, event_type = resolve_need_output(demand, value)
    state_payload, signal_payload = _need_payloads(demand, event_type, value, level)
    label = f"Need {demand} {value:g} {level}"
    return label, (
        InjectionMessage(config.TOPICS["internal_need_state"], state_payload),
        InjectionMessage(config.TOPICS["internal_need_signal_event"], signal_payload),
    )


def _build_custom_emotion(fields: dict[str, str]) -> tuple[str, tuple[InjectionMessage, ...]]:
    emotion = _choice(_field(fields, "emotion_name", "Joy"), config.EMOTION_NAMES)
    value = _clamp(_float_field(fields, "emotion_value", 90.0), 0.0, 100.0)
    level, event_type, level_range = resolve_emotion_output(emotion, value)
    state_payload, signal_payload = _emotion_payloads(
        emotion,
        event_type,
        value,
        level,
        level_range,
    )
    messages = [InjectionMessage(config.TOPICS["emotion_state"], state_payload)]
    if signal_payload is not None:
        messages.append(InjectionMessage(config.TOPICS["emotion_signal_event"], signal_payload))
    label = f"Emotion {emotion} {value:g} {level}"
    return label, tuple(messages)


def _build_custom_vision(fields: dict[str, str]) -> tuple[str, tuple[InjectionMessage, ...]]:
    events = _csv(_field(fields, "vision_events", "EVT_VISION_MASTER"))
    identity = _field(fields, "vision_identity", "owner")
    pose = _field(fields, "vision_pose", "standing")
    object_label = _field(fields, "vision_object", "")
    active_target: dict[str, Any] = {}
    faces: list[dict[str, Any]] = []
    humans: list[dict[str, Any]] = []
    tracked_objects: list[dict[str, Any]] = []

    if identity and identity.lower() not in {"none", "-", "unknown_empty"}:
        active_target = {
            "track_id": 1,
            "identity": identity,
            "speaker_id": _field(fields, "audio_speaker_id", identity),
            "is_registered": identity not in {"unknown", "stranger"},
            "confidence": 0.9,
            "face_confidence": 0.88,
            "speaker_confidence": 0.0,
            "bbox": [0.56, 0.35, 0.24, 0.55],
            "face_bbox": [0.64, 0.25, 0.10, 0.12],
            "body_center": [0.72, 0.42],
            "face_center": [0.72, 0.30],
            "is_speaking": True,
            "pose_state": pose,
            "pose_action": _pose_action_for_events(events),
            "pose_action_label": pose,
            "selection_reason": "manual event",
        }
        faces = [
            {
                "track_id": 1,
                "x": 0.64,
                "y": 0.25,
                "w": 0.10,
                "h": 0.12,
                "confidence": 0.88,
                "recognized_user": identity if identity != "unknown" else "",
                "identity_confidence": 0.9,
                "identity_state": "confirmed_known" if identity != "unknown" else "confirmed_unknown",
            }
        ]
        humans = [
            {
                "track_id": 1,
                "x": 0.56,
                "y": 0.35,
                "w": 0.24,
                "h": 0.55,
                "confidence": 0.9,
                "pose_state": pose,
                "pose_action": active_target["pose_action"],
                "pose_action_label": pose,
            }
        ]

    if object_label or any(item in events for item in ("EVT_VISION_TOY", "EVT_VISION_FOOD")):
        label = object_label or ("dog bowl" if "EVT_VISION_FOOD" in events else "dog toy ball")
        tracked_objects.append(
            {
                "label": label,
                "x": 0.68,
                "y": 0.43,
                "w": 0.12,
                "h": 0.12,
                "confidence": 0.88,
                "center_x": 0.74,
                "center_y": 0.49,
            }
        )

    payload = {
        "header": {"frame_id": "camera_link"},
        "active_target": active_target,
        "faces": faces,
        "humans": humans,
        "hands": _hands_for_events(events),
        "tracked_objects": tracked_objects,
        "events": events,
    }
    label = f"Vision {','.join(events) if events else 'empty'}"
    return label, (InjectionMessage(config.TOPICS["visual_event"], payload),)


def _build_custom_result(fields: dict[str, str]) -> tuple[str, tuple[InjectionMessage, ...]]:
    action_type = _field(fields, "result_action_type", "ACTION_EAT").upper()
    raw_demand_type = _field(fields, "result_demand_type", "")
    mapped_demand_type = _ACTION_DEMAND.get(action_type, "")
    if raw_demand_type.lower() in {"", "-", "auto"}:
        demand_type = mapped_demand_type
    else:
        demand_type = raw_demand_type
    result_type = _field(fields, "result_type", "COMPLETED").upper()
    raw_metadata = _field(fields, "result_metadata", "")
    if (
        raw_metadata == _DEFAULT_FIELD_VALUES["result_metadata"]
        and action_type != _DEFAULT_FIELD_VALUES["result_action_type"]
    ):
        metadata = _default_result_metadata(action_type)
    else:
        metadata = _json_object(raw_metadata) or _default_result_metadata(action_type)
    payload = {
        "event_id": f"manual-result-{time.time_ns()}",
        "action_type": action_type,
        "demand_type": demand_type,
        "result_type": result_type,
        "metadata": metadata,
    }
    label = f"Result {action_type} {result_type}"
    return label, (InjectionMessage(config.TOPICS["behavior_result_event"], payload),)


def _build_custom_personality(fields: dict[str, str]) -> tuple[str, tuple[InjectionMessage, ...]]:
    params = {
        "A": _int_clamped(fields, "personality_a", 80),
        "O": _int_clamped(fields, "personality_o", 80),
        "E": _int_clamped(fields, "personality_e", 80),
        "C": _int_clamped(fields, "personality_c", 70),
    }
    payload = {
        "schema_version": "1.0",
        "profile": _field(fields, "personality_profile", "Custom"),
        "params": params,
        "coefficients": {
            "Joy": round(1.0 + params["A"] / 100.0, 2),
            "Excite": round(1.0 + params["E"] / 100.0, 2),
            "Anxiety": round(2.0 - params["C"] / 100.0, 2),
            "Fear": round(2.0 - params["A"] / 100.0, 2),
            "Curious": round(1.0 + params["O"] / 100.0, 2),
            "Calm": round(1.0 + params["C"] / 100.0, 2),
            "Social": round(1.0 + params["A"] / 100.0, 2),
        },
    }
    label = f"Personality {payload['profile']}"
    return label, (InjectionMessage(config.TOPICS["personality_state"], payload),)


def _field(fields: dict[str, str], key: str, default: str) -> str:
    value = fields.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def _float_field(fields: dict[str, str], key: str, default: float) -> float:
    try:
        return float(_field(fields, key, str(default)))
    except ValueError:
        return default


def _int_clamped(fields: dict[str, str], key: str, default: int) -> int:
    return int(_clamp(_float_field(fields, key, float(default)), 0.0, 100.0))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _choice(value: str, options: tuple[str, ...]) -> str:
    normalized = value.strip().lower()
    for option in options:
        if option.lower() == normalized:
            return option
    upper = value.strip().upper()
    for option in options:
        if option.upper().startswith(upper):
            return option
    return options[0]


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _json_object(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _need_payloads(
    demand: str,
    event_type: str,
    value: float,
    level: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    demands: dict[str, dict[str, Any]] = {}
    level_events: dict[str, str | None] = {}
    triggered: list[dict[str, Any]] = []

    for name, spec in _DEMAND_SPECS.items():
        active = name == demand
        current_value = value if active else spec["normal"]
        derived_level, derived_event = resolve_need_output(name, current_value)
        current_level = level if active else derived_level
        current_event = event_type if active else derived_event
        is_triggered = current_level in {"TRIGGERED", "OVERFLOW"}
        is_overflow = current_level == "OVERFLOW"
        demands[name] = {
            "value": current_value,
            "triggerThreshold": spec["triggerThreshold"],
            "triggerOperator": spec["triggerOperator"],
            "overflowThreshold": spec["overflowThreshold"],
            "overflowOperator": spec["overflowOperator"],
            "triggered": is_triggered,
            "overflow": is_overflow,
            "level": current_level,
            "levelEvent": current_event,
            "levelActive": current_level != "NORMAL",
        }
        level_events[name] = current_event
        if active and is_triggered:
            triggered.append(
                {
                    "type": name,
                    "value": current_value,
                    "triggerThreshold": spec["triggerThreshold"],
                    "triggerOperator": spec["triggerOperator"],
                    "overflow": is_overflow,
                }
            )

    state_payload = {
        "schema_version": "1.0",
        "demands": demands,
        "levelEvents": level_events,
        "triggered": triggered,
        "sleep": {
            "isSleeping": demand == "Sleepiness" and level in {"TRIGGERED", "OVERFLOW"},
            "sleepDepth": "Shallow",
            "sleepDurationMinutes": 0,
            "shallowSleepTicksRemaining": 0,
        },
    }
    spec = _DEMAND_SPECS[demand]
    signal_payload = {
        "schema_version": "1.0",
        "event_type": event_type,
        "demand": demand,
        "value": value,
        "level": level,
        "previousLevel": "TRIGGERED" if level == "NORMAL" else "NORMAL",
        "triggerThreshold": spec["triggerThreshold"],
        "triggerOperator": spec["triggerOperator"],
        "overflowThreshold": spec["overflowThreshold"],
        "overflowOperator": spec["overflowOperator"],
        "trigger": "LEVEL_CHANGED",
    }
    return state_payload, signal_payload


def _emotion_payloads(
    emotion: str,
    event_type: str | None,
    value: float,
    level: str,
    level_range: tuple[int, int] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    emotions: dict[str, dict[str, Any]] = {}
    level_events: dict[str, str | None] = {}
    triggered: list[dict[str, Any]] = []

    for name, spec in _EMOTION_SPECS.items():
        active = name == emotion
        current_value = value if active else 0.0
        derived_level, derived_event, derived_range = resolve_emotion_output(name, current_value)
        current_level = level if active else derived_level
        current_event = event_type if active else derived_event
        current_range = level_range if active else derived_range
        level_active = current_event is not None and current_range is not None
        emotions[name] = {
            "value": current_value,
            "triggerThreshold": spec["triggerThreshold"],
            "triggerOperator": spec["triggerOperator"],
            "triggered": level_active,
            "level": current_level,
            "levelEvent": current_event,
            "levelRange": list(current_range) if current_range is not None else None,
            "levelActive": level_active,
        }
        level_events[name] = current_event
        if level_active:
            triggered.append(
                {
                    "type": name,
                    "value": current_value,
                    "level": current_level,
                    "eventType": current_event,
                    "range": list(current_range),
                    "triggerThreshold": spec["triggerThreshold"],
                    "triggerOperator": spec["triggerOperator"],
                }
            )

    state_payload = {
        "schema_version": "1.0",
        "emotions": emotions,
        "levelEvents": level_events,
        "triggered": triggered,
        "dominantEmotion": emotion,
        "dominantEmotionSignal": {
            "emotion": emotion,
            "value": value,
            "level": level,
            "eventType": event_type,
            "range": list(level_range) if level_range is not None else None,
            "active": event_type is not None,
        },
        "personality": {"A": 50, "O": 50, "E": 50, "C": 50},
        "lastEmotionEventResult": {},
    }
    signal_payload = None
    if event_type is not None and level_range is not None:
        signal_payload = {
            "schema_version": "1.0",
            "event_type": event_type,
            "emotion": emotion,
            "value": value,
            "level": level,
            "range": list(level_range),
            "trigger": "LEVEL_CHANGED_AND_DOMINANT_CHANGED",
            "isDominant": True,
            "dominantChanged": True,
        }
    return state_payload, signal_payload


def _intent_category_for_voice(event_type: str, command_id: str) -> str:
    if event_type == "EVT_VOICE_PRAISE" or command_id in {"CMD_PRAISE", "CMD_ENCOUR"}:
        return "praise"
    if event_type == "EVT_VOICE_SCOLD":
        return "scold"
    if event_type in {"EVT_VOICE_HAPPY", "EVT_VOICE_SAD", "EVT_VOICE_NEUTRAL"}:
        return "emotion"
    if command_id == "CMD_CHAT":
        return "chat"
    if command_id == "CMD_UNKNOWN" or event_type == "EVT_VOICE_COMMAND_UNKNOWN":
        return "unknown"
    return "command"


def _raw_tag_for_command(command_id: str, event_type: str) -> str:
    action = command_id.removeprefix("CMD_") or "UNKNOWN"
    intent = "U" if command_id == "CMD_UNKNOWN" else "C"
    if event_type == "EVT_VOICE_PRAISE":
        intent = "P"
    elif event_type == "EVT_VOICE_SCOLD":
        intent = "B"
    elif event_type in {"EVT_VOICE_HAPPY", "EVT_VOICE_SAD", "EVT_VOICE_NEUTRAL"}:
        intent = "E"
    return f"{intent}|{action}|N|E"


def _pose_action_for_events(events: list[str]) -> str:
    if "EVT_VISION_FALL" in events:
        return "fallen_down"
    if "EVT_VISION_STOP_GESTURE" in events:
        return "stop_gesture"
    if "EVT_VISION_MASTER_HAPPY" in events:
        return "thumbs_up"
    if "EVT_VISION_MASTER_SAD" in events:
        return "head_down_slumped"
    return "neutral_stand_sit"


def _hands_for_events(events: list[str]) -> list[dict[str, Any]]:
    if "EVT_VISION_STOP_GESTURE" not in events and "EVT_VISION_HAND_TO_NOSE" not in events:
        return []
    action = "stop_gesture" if "EVT_VISION_STOP_GESTURE" in events else "hand_to_nose"
    label = "停止/别动手势" if action == "stop_gesture" else "手靠近鼻子"
    return [
        {
            "handedness": "Right",
            "hand_action": action,
            "hand_action_label": label,
            "landmarks": [{"id": 0, "x": 0.68, "y": 0.42}],
        }
    ]


def _default_result_metadata(action_type: str) -> dict[str, Any]:
    if action_type == "ACTION_EAT":
        return {"foodType": "NormalFood", "portions": 1, "eatEfficiency": "Full"}
    if action_type == "ACTION_RECHARGE":
        return {"energyValue": 88}
    if action_type.startswith("ACTION_SOCIAL") or action_type in {
        "ACTION_PLAY_INVITE",
        "ACTION_BOUNDARY_TEST",
        "ACTION_ATTENTION_SEEK",
        "ACTION_RESOURCE_SHARE",
    }:
        return {"socialOutcome": "OwnerInteraction"}
    return {}


def _audio_wake_template(
    template_id: str,
    label: str,
    wake_word: str,
    wake_angle: float,
) -> EventTemplate:
    payload: dict[str, Any] = {
        "header": {"frame_id": "base_link"},
        "event_type": "EVT_VOICE_CALL_NAME",
        "wake_word": wake_word,
        "wake_angle": wake_angle,
        "wake_confidence": 1205.0,
        "state": "attention",
    }
    return EventTemplate(
        template_id,
        "Audio",
        label,
        (EventMessageSpec(config.TOPICS["audio_event"], payload),),
    )


def _audio_command_template(
    template_id: str,
    label: str,
    asr_text: str,
    command_id: str,
    raw_tag: str,
) -> EventTemplate:
    payload: dict[str, Any] = {
        "header": {"frame_id": "base_link"},
        "event_type": _VOICE_EVENT_BY_COMMAND_ID.get(
            command_id,
            "EVT_VOICE_COMMAND_UNKNOWN",
        ),
        "command_id": command_id,
        "intent_category": "command",
        "intent_source": "manual_ui",
        "intent_confidence": 0.98,
        "slots": [{"key": "raw_tag", "value": raw_tag}],
        "asr_text": asr_text,
        "response_text": "",
        "is_executable": True,
        "state": "execution",
        "latency_ms": 0.0,
    }
    return EventTemplate(
        template_id,
        "Audio",
        label,
        (EventMessageSpec(config.TOPICS["audio_event"], payload),),
    )


def _need_template(
    template_id: str,
    label: str,
    demand: str,
    event_type: str,
    value: float,
) -> EventTemplate:
    spec = _DEMAND_SPECS[demand]
    level = _need_level_for_event(event_type)
    demands: dict[str, dict[str, Any]] = {}
    level_events: dict[str, str | None] = {}
    triggered: list[dict[str, Any]] = []

    for name, demand_spec in _DEMAND_SPECS.items():
        active = name == demand
        current_level = level if active else "NORMAL"
        current_value = value if active else demand_spec["normal"]
        current_event = event_type if active else None
        is_triggered = current_level in {"TRIGGERED", "OVERFLOW"}
        is_overflow = current_level == "OVERFLOW"
        demands[name] = {
            "value": current_value,
            "triggerThreshold": demand_spec["triggerThreshold"],
            "triggerOperator": demand_spec["triggerOperator"],
            "overflowThreshold": demand_spec["overflowThreshold"],
            "overflowOperator": demand_spec["overflowOperator"],
            "triggered": is_triggered,
            "overflow": is_overflow,
            "level": current_level,
            "levelEvent": current_event,
            "levelActive": current_level != "NORMAL",
        }
        level_events[name] = current_event
        if active and is_triggered:
            triggered.append(
                {
                    "type": name,
                    "value": current_value,
                    "triggerThreshold": demand_spec["triggerThreshold"],
                    "triggerOperator": demand_spec["triggerOperator"],
                    "overflow": is_overflow,
                }
            )

    state_payload = {
        "schema_version": "1.0",
        "demands": demands,
        "levelEvents": level_events,
        "triggered": triggered,
        "sleep": {
            "isSleeping": False,
            "sleepDepth": "Shallow",
            "sleepDurationMinutes": 0,
            "shallowSleepTicksRemaining": 0,
        },
    }
    signal_payload = {
        "schema_version": "1.0",
        "event_type": event_type,
        "demand": demand,
        "value": value,
        "level": level,
        "previousLevel": "NORMAL",
        "triggerThreshold": spec["triggerThreshold"],
        "triggerOperator": spec["triggerOperator"],
        "overflowThreshold": spec["overflowThreshold"],
        "overflowOperator": spec["overflowOperator"],
        "trigger": "LEVEL_CHANGED",
    }
    return EventTemplate(
        template_id,
        "Need",
        label,
        (
            EventMessageSpec(config.TOPICS["internal_need_state"], state_payload),
            EventMessageSpec(config.TOPICS["internal_need_signal_event"], signal_payload),
        ),
    )


def _emotion_template(
    template_id: str,
    label: str,
    emotion: str,
    event_type: str,
    value: float,
    level: str,
    level_range: tuple[int, int],
) -> EventTemplate:
    emotions: dict[str, dict[str, Any]] = {}
    level_events: dict[str, str | None] = {}
    triggered: list[dict[str, Any]] = []

    for name, emotion_spec in _EMOTION_SPECS.items():
        active = name == emotion
        current_value = value if active else 0.0
        current_level = level if active else "NONE"
        current_event = event_type if active else None
        current_range = list(level_range) if active else None
        emotions[name] = {
            "value": current_value,
            "triggerThreshold": emotion_spec["triggerThreshold"],
            "triggerOperator": emotion_spec["triggerOperator"],
            "triggered": active,
            "level": current_level,
            "levelEvent": current_event,
            "levelRange": current_range,
            "levelActive": active,
        }
        level_events[name] = current_event
        if active:
            triggered.append(
                {
                    "type": name,
                    "value": value,
                    "level": level,
                    "eventType": event_type,
                    "range": list(level_range),
                    "triggerThreshold": emotion_spec["triggerThreshold"],
                    "triggerOperator": emotion_spec["triggerOperator"],
                }
            )

    signal = {
        "schema_version": "1.0",
        "event_type": event_type,
        "emotion": emotion,
        "value": value,
        "level": level,
        "range": list(level_range),
        "trigger": "LEVEL_CHANGED_AND_DOMINANT_CHANGED",
        "isDominant": True,
        "dominantChanged": True,
    }
    state_payload = {
        "schema_version": "1.0",
        "emotions": emotions,
        "levelEvents": level_events,
        "triggered": triggered,
        "dominantEmotion": emotion,
        "dominantEmotionSignal": {
            "emotion": emotion,
            "value": value,
            "level": level,
            "eventType": event_type,
            "range": list(level_range),
            "active": True,
        },
        "personality": {"A": 50, "O": 50, "E": 50, "C": 50},
        "lastEmotionEventResult": {},
    }
    return EventTemplate(
        template_id,
        "Emotion",
        label,
        (
            EventMessageSpec(config.TOPICS["emotion_state"], state_payload),
            EventMessageSpec(config.TOPICS["emotion_signal_event"], signal),
        ),
    )


def _visual_template(template_id: str, label: str, payload: dict[str, Any]) -> EventTemplate:
    return EventTemplate(
        template_id,
        "Vision",
        label,
        (EventMessageSpec(config.TOPICS["visual_event"], payload),),
    )


def _need_level_for_event(event_type: str) -> str:
    if event_type.endswith("_OVERFLOW"):
        return "OVERFLOW"
    if event_type.endswith("_TRIGGERED"):
        return "TRIGGERED"
    return "NORMAL"


EVENT_TEMPLATES: tuple[EventTemplate, ...] = (
    _audio_wake_template("audio_call", "Call Name", "你好小狗", 25.0),
    _audio_command_template("cmd_sit", "CMD Sit", "坐下", "CMD_SIT", "C|SIT|N|E"),
    _audio_command_template("cmd_come", "CMD Come", "过来", "CMD_COME_HERE", "C|COME|N|E"),
    _audio_command_template("cmd_hand", "CMD Hand", "握手", "CMD_HAND", "C|HAND|N|E"),
    _audio_command_template("cmd_follow", "CMD Follow", "跟着我", "CMD_FOLLOW", "C|FOLLOW|N|E"),
    _audio_command_template("cmd_stop", "CMD Stop", "停止", "CMD_STOP", "C|STOP|N|T"),
    _need_template("need_hunger", "Hunger Trig", "Hunger", "NEED_HUNGER_TRIGGERED", 88.0),
    _need_template("need_bladder", "Bladder Trig", "Bladder", "NEED_BLADDER_TRIGGERED", 82.0),
    _need_template("need_sleep", "Sleepy Trig", "Sleepiness", "NEED_SLEEPINESS_TRIGGERED", 76.0),
    _need_template("need_clean", "Dirty Trig", "Cleanliness", "NEED_CLEANLINESS_TRIGGERED", 84.0),
    _need_template("need_social", "Social Trig", "Social", "NEED_SOCIAL_TRIGGERED", 82.0),
    _need_template("need_explore", "Explore Trig", "Exploration", "NEED_EXPLORATION_TRIGGERED", 80.0),
    _need_template("need_energy", "Energy Low", "Energy", "NEED_ENERGY_TRIGGERED", 18.0),
    _emotion_template("emo_joy", "Joy High", "Joy", "EMO_JOY_HIGH", 92.0, "HIGH", (86, 100)),
    _emotion_template("emo_excite", "Excite High", "Excite", "EMO_EXCITE_HIGH", 90.0, "HIGH", (71, 100)),
    _emotion_template("emo_curious", "Curious High", "Curious", "EMO_CURIOUS_HIGH", 86.0, "HIGH", (51, 100)),
    _emotion_template("emo_fear", "Fear High", "Fear", "EMO_FEAR_HIGH", 88.0, "HIGH", (61, 100)),
    _emotion_template("emo_anxiety", "Anxiety High", "Anxiety", "EMO_ANXIETY_HIGH", 84.0, "HIGH", (51, 100)),
    _emotion_template("emo_calm", "Calm High", "Calm", "EMO_CALM_HIGH", 78.0, "HIGH", (61, 100)),
    _visual_template(
        "vision_owner",
        "Owner Present",
        {
            "header": {"frame_id": "camera_link"},
            "events": ["EVT_VISION_MASTER"],
            "active_target": {
                "track_id": 1,
                "identity": "owner",
                "speaker_id": "owner",
                "is_registered": True,
                "confidence": 0.92,
                "face_confidence": 0.90,
                "speaker_confidence": 0.0,
                "bbox": [0.56, 0.35, 0.24, 0.55],
                "face_bbox": [0.64, 0.25, 0.10, 0.12],
                "body_center": [0.72, 0.42],
                "face_center": [0.72, 0.30],
                "is_speaking": True,
                "pose_state": "standing",
                "selection_reason": "currently speaking",
            },
            "faces": [
                {
                    "track_id": 1,
                    "x": 0.64,
                    "y": 0.25,
                    "w": 0.10,
                    "h": 0.12,
                    "confidence": 0.90,
                    "recognized_user": "owner",
                    "identity_confidence": 0.92,
                    "identity_state": "confirmed_known",
                }
            ],
            "humans": [
                {
                    "track_id": 1,
                    "x": 0.56,
                    "y": 0.35,
                    "w": 0.24,
                    "h": 0.55,
                    "confidence": 0.92,
                    "pose_state": "standing",
                    "pose_action": "neutral_stand_sit",
                    "pose_action_label": "自然站立/端坐",
                }
            ],
            "hands": [],
            "tracked_objects": [],
        },
    ),
    _visual_template(
        "vision_toy",
        "Toy Visible",
        {
            "header": {"frame_id": "camera_link"},
            "events": ["EVT_VISION_TOY"],
            "active_target": {},
            "faces": [],
            "humans": [],
            "hands": [],
            "tracked_objects": [
                {
                    "label": "dog toy ball",
                    "x": 0.68,
                    "y": 0.43,
                    "w": 0.12,
                    "h": 0.12,
                    "confidence": 0.88,
                    "center_x": 0.74,
                    "center_y": 0.49,
                }
            ],
        },
    ),
)

EVENT_TEMPLATE_BY_ID = {template.template_id: template for template in EVENT_TEMPLATES}
