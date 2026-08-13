"""Resolve perception audio events to documented voice-command behaviors."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class VoiceCommandSpec:
    behavior_name: str
    label: str
    timeout_sec: float
    command_ids: tuple[str, ...]
    phrases: tuple[str, ...]


VOICE_COMMAND_SPECS = (
    VoiceCommandSpec(
        "respond_owner_call",
        "回应呼叫",
        4.0,
        ("VOICE_CALL_NAME",),
        (),
    ),
    VoiceCommandSpec(
        "sit_down",
        "坐下",
        4.0,
        ("CMD_SIT", "CMD_SIT_DOWN", "SIT_DOWN"),
        ("坐下", "坐好", "坐一会"),
    ),
    VoiceCommandSpec(
        "lie_down",
        "趴下",
        5.0,
        ("CMD_LIE_DOWN", "CMD_DOWN", "LIE_DOWN"),
        ("趴下", "躺下", "卧倒"),
    ),
    VoiceCommandSpec(
        "stand_up",
        "站起",
        4.0,
        ("CMD_STAND", "CMD_STAND_UP", "STAND_UP"),
        ("站起来", "站起", "起立"),
    ),
    VoiceCommandSpec(
        "wait_in_place",
        "原地等待",
        4.0,
        ("CMD_WAIT", "CMD_STAY", "CMD_WAIT_IN_PLACE", "WAIT_IN_PLACE"),
        ("原地等待", "等一下", "别动", "待在这里"),
    ),
    VoiceCommandSpec(
        "come_to_owner",
        "过来",
        5.0,
        ("CMD_COME", "CMD_COME_HERE", "CMD_COME_TO_OWNER", "COME_TO_OWNER"),
        ("过来", "到我身边", "来我这里", "到这边来"),
    ),
    VoiceCommandSpec(
        "follow_owner",
        "跟随",
        30.0,
        ("CMD_FOLLOW", "CMD_FOLLOW_USER", "FOLLOW_USER"),
        ("跟随", "跟着我", "跟我走", "跟上我", "随我来"),
    ),
    VoiceCommandSpec(
        "give_paw",
        "握手",
        4.0,
        ("CMD_HAND", "CMD_GIVE_PAW", "CMD_HAND_SHAKE", "GIVE_PAW"),
        ("握手", "握个手", "伸手", "给我爪子", "给个爪"),
    ),
    VoiceCommandSpec(
        "high_five",
        "击掌",
        4.0,
        ("CMD_FIVE", "CMD_HIGH_FIVE", "HIGH_FIVE"),
        ("击掌", "击个掌", "来个击掌"),
    ),
    VoiceCommandSpec(
        "roll_over",
        "翻滚",
        4.5,
        ("CMD_ROLL", "CMD_ROLL_OVER", "ROLL_OVER"),
        ("翻滚", "打滚", "翻个身", "滚一圈"),
    ),
    VoiceCommandSpec(
        "spin_around",
        "转圈",
        3.5,
        ("CMD_SPIN", "CMD_SPIN_AROUND", "SPIN_AROUND"),
        ("转圈", "转一圈", "原地转圈"),
    ),
    VoiceCommandSpec(
        "return_to_owner",
        "回到主人身边",
        5.0,
        ("CMD_RETURN", "CMD_RETURN_TO_OWNER", "RETURN_TO_OWNER"),
        ("回来", "回到我身边", "回主人身边"),
    ),
    VoiceCommandSpec(
        "drop_object",
        "吐掉",
        2.0,
        ("CMD_DROP", "CMD_SPIT", "CMD_DROP_OBJECT", "DROP_OBJECT"),
        ("吐掉", "放下", "松口", "把它放下"),
    ),
    VoiceCommandSpec(
        "play_dead",
        "装死",
        4.5,
        ("CMD_PLAY_DEAD", "PLAY_DEAD"),
        ("装死", "假装死掉"),
    ),
    VoiceCommandSpec(
        "bring_object",
        "拿来",
        6.0,
        ("CMD_BRING", "CMD_BRING_OBJECT", "BRING_OBJECT"),
        ("拿来", "带过来", "把东西拿来"),
    ),
    VoiceCommandSpec(
        "fetch_object",
        "寻找捡回",
        6.0,
        ("CMD_FETCH", "CMD_FETCH_OBJECT", "FETCH_OBJECT"),
        ("捡回来", "找回来", "去捡", "寻找捡回"),
    ),
    VoiceCommandSpec(
        "emergency_stop",
        "紧急停止",
        2.0,
        ("CMD_STOP", "CMD_EMERGENCY_STOP", "EMERGENCY_STOP"),
        ("停止", "马上停下", "紧急停止"),
    ),
)

_SPEC_BY_COMMAND_ID = {
    command_id: spec
    for spec in VOICE_COMMAND_SPECS
    for command_id in spec.command_ids
}

_BEHAVIOR_BY_EVENT_TYPE = {
    "EVT_VOICE_CALL_NAME": "respond_owner_call",
    "EVT_VOICE_COMMAND_SIT": "sit_down",
    "EVT_VOICE_COMMAND_LIE_DOWN": "lie_down",
    "EVT_VOICE_COMMAND_STAND": "stand_up",
    "EVT_VOICE_COMMAND_WAIT": "wait_in_place",
    "EVT_VOICE_COMMAND_COME": "come_to_owner",
    "EVT_VOICE_COMMAND_FOLLOW": "follow_owner",
    "EVT_VOICE_COMMAND_GIVE_PAW": "give_paw",
    "EVT_VOICE_COMMAND_HIGH_FIVE": "high_five",
    "EVT_VOICE_COMMAND_ROLL": "roll_over",
    "EVT_VOICE_COMMAND_SPIN": "spin_around",
    "EVT_VOICE_COMMAND_RETURN": "return_to_owner",
    "EVT_VOICE_COMMAND_DROP": "drop_object",
    "EVT_VOICE_COMMAND_PLAY_DEAD": "play_dead",
    "EVT_VOICE_COMMAND_BRING": "bring_object",
    "EVT_VOICE_COMMAND_FETCH": "fetch_object",
    "EVT_VOICE_COMMAND_STOP": "emergency_stop",
}
_SPEC_BY_BEHAVIOR = {
    spec.behavior_name: spec
    for spec in VOICE_COMMAND_SPECS
}
EXTERNAL_COMMAND_BEHAVIORS = frozenset(
    spec.behavior_name
    for spec in VOICE_COMMAND_SPECS
    if spec.behavior_name != "emergency_stop"
)

# Direct commands whose final pose is performed beside the visible owner.
# Follow remains a separate continuous controller, object fetch/bring keep
# their toy route, and emergency_stop must take effect immediately.
OWNER_SIDE_COMMAND_BEHAVIORS = frozenset(
    {
        "respond_owner_call",
        "sit_down",
        "lie_down",
        "stand_up",
        "wait_in_place",
        "come_to_owner",
        "give_paw",
        "high_five",
        "roll_over",
        "spin_around",
        "return_to_owner",
        "drop_object",
        "play_dead",
    }
)


def behavior_runs_beside_owner(behavior_name: Any) -> bool:
    return str(behavior_name or "") in OWNER_SIDE_COMMAND_BEHAVIORS


def is_external_command_behavior(behavior_name: Any) -> bool:
    """Return whether a behavior is started by an ordinary owner command."""

    return str(behavior_name or "") in EXTERNAL_COMMAND_BEHAVIORS


def resolve_voice_command(audio_event: dict[str, Any] | None) -> VoiceCommandSpec | None:
    if not audio_event or audio_event.get("is_executable") is False:
        return None

    event_type = _normalize_command_id(audio_event.get("event_type"))
    behavior_name = _BEHAVIOR_BY_EVENT_TYPE.get(event_type)
    if behavior_name is not None:
        return _SPEC_BY_BEHAVIOR[behavior_name]

    command_id = _normalize_command_id(audio_event.get("command_id"))
    if command_id:
        matched = _SPEC_BY_COMMAND_ID.get(command_id)
        if matched is not None:
            return matched

    text = _normalize_text(audio_event.get("asr_text"))
    if not text:
        return None
    for spec in VOICE_COMMAND_SPECS:
        if any(_normalize_text(phrase) in text for phrase in spec.phrases):
            return spec
    return None


def voice_command_display(audio_event: dict[str, Any] | None) -> str:
    if not audio_event:
        return "-"
    text = str(audio_event.get("asr_text") or "").strip()
    command = resolve_voice_command(audio_event)
    if command is None:
        return text or "-"
    if not text or _normalize_text(text) == _normalize_text(command.label):
        return f"{command.label} → {command.behavior_name}"
    return f"{text} → {command.label}"


def _normalize_command_id(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def _normalize_text(value: Any) -> str:
    return re.sub(r"[\\s,，。.!！?？、;；:：]+", "", str(value or "").strip().lower())
