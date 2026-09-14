"""Manual event-injection workflow for the left control panel."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging

from marsdog_sim2d import config
from marsdog_sim2d.simevent.event_injector import (
    InjectionCommand,
    build_local_external_damage_event,
    build_local_tactile_event,
    build_custom_injection_command,
    build_scenario_command,
    command_from_payload_preview,
    default_field_values,
    place_injection_command,
    resolve_emotion_output,
    resolve_need_output,
)
from marsdog_sim2d.simevent.events import SimEvent
from marsdog_sim2d.simevent.injection import InjectionFormState
from marsdog_sim2d.utils import safe_float


LOGGER = logging.getLogger("marsdog_sim2d")


@dataclass(slots=True)
class PanelEffect:
    """Side effects that the Arcade window must apply on the main thread."""

    command: InjectionCommand | None = None
    local_event: SimEvent | None = None
    local_behavior: str | None = None
    preferred_action: str | None = None
    external_damage: dict[str, object] | None = None
    confirmation: dict[str, object] | None = None
    stop_requested: bool = False
    placement_changed: bool = False
    pending_placement: dict[str, object] | None = None
    user_position: tuple[float, float] | None = None


class LeftPanelController:
    """Validate the form and produce commands without reaching into SimState."""

    def __init__(self, form: InjectionFormState) -> None:
        self.form = form
        if not self.form.fields:
            self.form.fields.update(default_field_values())
        self.form.fields.setdefault("personality_trait", "A")
        self.form.fields.setdefault("toilet_spot_taught", "false")

    def handle_action(
        self,
        item: dict[str, object],
        *,
        pending_placement: dict[str, object] | None = None,
        user_visible: bool = False,
        internal_need_active: bool = False,
    ) -> PanelEffect | None:
        """Apply one form action and return any work owned by the window."""
        action = item.get("action", "")

        if action in {"input_tab", "collapsed_tab"}:
            self.form.tab = str(item["tab"])
            self._normalize_group_for_tab()
            self.refresh_payload_preview(pending_placement)
            return PanelEffect()

        if action == "select_option":
            self._apply_select_option(item)
            self.refresh_payload_preview(pending_placement)
            return PanelEffect()

        if action == "field_changed":
            field_id = str(item.get("field_id") or "")
            self.form.fields[field_id] = str(item.get("value") or "")
            self.refresh_payload_preview(pending_placement)
            return PanelEffect()

        if action == "payload_changed":
            self.form.payload_preview = str(item.get("value") or "")[
                : config.MAX_PAYLOAD_PREVIEW_CHARS
            ]
            self.form.payload_preview_dirty = True
            return PanelEffect()

        if action == "placement_mode":
            return self._toggle_placement(str(item["group"]), pending_placement)

        if action in {"send_event", "send_command"}:
            forced_group = "Audio" if action == "send_command" else None
            return self.prepare_injection(
                forced_group,
                pending_placement=pending_placement,
                user_visible=user_visible,
                internal_need_active=internal_need_active,
            )

        if action == "command_quick":
            self.form.fields.update(
                audio_command_id=str(item["command_id"]),
                audio_asr_text=str(item.get("asr_text") or ""),
                audio_event_type="EVT_VOICE_COMMAND_KNOWN",
            )
            self.refresh_payload_preview(pending_placement)
            return self.prepare_injection(
                "Audio",
                pending_placement=pending_placement,
                user_visible=user_visible,
                internal_need_active=internal_need_active,
            )

        if action == "publish_state_output":
            return self._request_state_output(
                pending_placement=pending_placement,
                user_visible=user_visible,
                internal_need_active=internal_need_active,
            )

        if action == "scenario":
            return self._request_scenario(
                str(item.get("scenario_id") or ""),
                pending_placement,
            )

        return None

    def refresh_payload_preview(
        self,
        pending_placement: dict[str, object] | None = None,
    ) -> None:
        """Rebuild the topic list and generated JSON preview."""
        try:
            command = self._preview_command(pending_placement)
            self.form.preview_topics = list(
                dict.fromkeys(message.topic for message in command.messages)
            )
            preview = [
                {"topic": message.topic, "payload": message.payload}
                for message in command.messages
            ]
            self.form.payload_preview = json.dumps(
                preview,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except Exception as exc:
            LOGGER.warning("Left-panel payload preview failed: %s", exc)
            self.form.preview_topics = []
            self.form.payload_preview = f"Preview unavailable: {exc}"

        self.form.payload_preview_dirty = False
        self.form.payload_preview_scroll = 0

    def prepare_injection(
        self,
        forced_group: str | None = None,
        *,
        pending_placement: dict[str, object] | None = None,
        user_visible: bool = False,
        internal_need_active: bool = False,
    ) -> PanelEffect:
        """Validate the current form and return the command to enqueue."""
        self.form.fields = {
            **default_field_values(),
            **self.form.fields,
        }
        group = forced_group or self.form.group
        fields = self._resolved_fields(group)

        if voice_command_requires_visible_user(group, fields) and not user_visible:
            return PanelEffect(confirmation=_alert("没有识别到主人"))

        stop_requested = fields_request_stop(group, fields)
        if stop_requested and internal_need_active:
            return PanelEffect(
                confirmation=_alert("内部需求正在执行，停止指令已忽略"),
                stop_requested=True,
            )

        command = build_custom_injection_command(group, fields)
        command = _place_command(command, group, pending_placement)

        if self.form.payload_preview_dirty:
            try:
                command = command_from_payload_preview(
                    command,
                    self.form.payload_preview,
                )
            except ValueError as exc:
                return PanelEffect(
                    confirmation={
                        "kind": "alert",
                        "title": "Payload 无效",
                        "message": str(exc),
                    }
                )

        if group == "Tactile":
            event_type = str(
                command.messages[0].payload.get("event_type")
                or "EVT_TACTILE_HEAD_PET"
            )
            try:
                local_event = build_local_tactile_event(event_type)
            except KeyError:
                return PanelEffect(
                    confirmation={
                        "kind": "alert",
                        "title": "Payload 无效",
                        "message": f"未知触觉事件：{event_type}",
                    }
                )
            local_event.payload = dict(command.messages[0].payload)
            self.refresh_payload_preview()
            return PanelEffect(
                local_event=local_event,
                local_behavior=str(local_event.payload["local_behavior"]),
                preferred_action=str(local_event.payload["preferred_action"]),
                placement_changed=True,
            )

        if group == "Damage":
            payload = command.messages[0].payload
            event_type = str(
                payload.get("event_type")
                or "EVT_DAMAGE_LIGHT_IMPACT"
            )
            try:
                local_event = build_local_external_damage_event(
                    event_type,
                    safe_float(payload.get("risk_score"), 60.0),
                    confirmed=_confirmed_value(payload.get("confirmed")),
                )
            except KeyError:
                return PanelEffect(
                    confirmation={
                        "kind": "alert",
                        "title": "Payload 无效",
                        "message": f"未知外部损伤事件：{event_type}",
                    }
                )
            for key in ("timestamp", "manual_source", "manual_event_id"):
                if key in payload:
                    local_event.payload[key] = payload[key]
            takeover = (
                dict(local_event.payload)
                if local_event.payload["risk_code"] != "NONE"
                else None
            )
            self.refresh_payload_preview()
            return PanelEffect(
                local_event=local_event,
                external_damage=takeover,
                placement_changed=True,
            )

        user_position = _placed_user_position(group, pending_placement)
        self.refresh_payload_preview()
        return PanelEffect(
            command=command,
            stop_requested=stop_requested,
            placement_changed=True,
            user_position=user_position,
        )

    def confirm(
        self,
        pending: dict[str, object],
        *,
        pending_placement: dict[str, object] | None = None,
        user_visible: bool = False,
        internal_need_active: bool = False,
    ) -> PanelEffect:
        """Resolve a confirmation previously requested by this workflow."""
        kind = pending.get("kind")
        if kind == "scenario":
            scenario_id = str(pending.get("scenario_id") or "")
            return PanelEffect(command=build_scenario_command(scenario_id))

        if kind == "state_output":
            group = str(pending.get("group") or self.form.group)
            return self.prepare_injection(
                group,
                pending_placement=pending_placement,
                user_visible=user_visible,
                internal_need_active=internal_need_active,
            )

        return PanelEffect()

    def _preview_command(
        self,
        pending_placement: dict[str, object] | None,
    ) -> InjectionCommand:
        if self.form.tab == "Scenario":
            return build_scenario_command(self.form.selected_scenario)

        group = "Audio" if self.form.tab == "Command" else self.form.group
        command = build_custom_injection_command(
            group,
            self._resolved_fields(group),
        )
        return _place_command(command, group, pending_placement)

    def _apply_select_option(self, item: dict[str, object]) -> None:
        target = str(item.get("target") or "")
        value = str(item.get("value") or "")
        if target == "event_group":
            self.form.group = value
        elif target == "field":
            field_id = str(item.get("field_id") or "")
            self.form.fields[field_id] = value

    def _normalize_group_for_tab(self) -> None:
        if self.form.tab == "Event" and self.form.group not in {
            "Audio",
            "Tactile",
            "Damage",
            "Vision",
            "Result",
        }:
            self.form.group = "Audio"
        elif self.form.tab == "State" and self.form.group not in {
            "Need",
            "Emotion",
            "Personality",
        }:
            self.form.group = "Need"
        elif self.form.tab == "Command":
            self.form.group = "Audio"
            self.form.fields["audio_event_type"] = "EVT_VOICE_COMMAND_KNOWN"

    def _resolved_fields(self, group: str) -> dict[str, str]:
        fields = {**default_field_values(), **self.form.fields}
        if group == "Need":
            level, event_type = resolve_need_output(
                fields.get("need_demand", "Hunger"),
                safe_float(fields.get("need_value"), 82.0),
            )
            fields["need_level"] = level
            fields["need_event_type"] = event_type
        elif group == "Emotion":
            level, event_type, _level_range = resolve_emotion_output(
                fields.get("emotion_name", "Joy"),
                safe_float(fields.get("emotion_value"), 90.0),
            )
            fields["emotion_level"] = level
            fields["emotion_event_type"] = event_type or ""
        return fields

    def _request_state_output(
        self,
        *,
        pending_placement: dict[str, object] | None,
        user_visible: bool,
        internal_need_active: bool,
    ) -> PanelEffect:
        group = self.form.group
        fields = self._resolved_fields(group)
        dangerous = fields.get("need_level") == "OVERFLOW" or (
            group == "Emotion"
            and fields.get("emotion_name") == "Fear"
            and fields.get("emotion_level") == "HIGH"
        )
        if dangerous:
            return PanelEffect(
                confirmation={
                    "kind": "state_output",
                    "group": group,
                    "message": f"确认发布处于高风险等级的模拟 {group} 输出？",
                }
            )

        return self.prepare_injection(
            group,
            pending_placement=pending_placement,
            user_visible=user_visible,
            internal_need_active=internal_need_active,
        )

    def _request_scenario(
        self,
        scenario_id: str,
        pending_placement: dict[str, object] | None,
    ) -> PanelEffect:
        self.form.selected_scenario = scenario_id
        self.refresh_payload_preview(pending_placement)
        if scenario_id in {"high_hunger", "low_energy", "fear_response"}:
            return PanelEffect(
                confirmation={
                    "kind": "scenario",
                    "scenario_id": scenario_id,
                    "message": f"确认运行场景“{scenario_id}”？这可能触发紧急行为。",
                }
            )
        return PanelEffect(command=build_scenario_command(scenario_id))

    def _toggle_placement(
        self,
        group: str,
        pending_placement: dict[str, object] | None,
    ) -> PanelEffect:
        if group == "Audio":
            self.form.tab = "Event"
            self.form.group = "Audio"

        if pending_placement and pending_placement.get("group") == group:
            next_placement = None
        else:
            next_placement = {
                "group": group,
                "kind": self._placement_kind(group),
                "x": None,
                "y": None,
            }

        self.refresh_payload_preview(next_placement)
        return PanelEffect(
            placement_changed=True,
            pending_placement=next_placement,
        )

    def _placement_kind(self, group: str) -> str:
        if group == "Audio":
            return "audio"
        if self.form.fields.get("vision_object"):
            return "object"
        return "human"


def fields_request_stop(group: str, fields: dict[str, str]) -> bool:
    """Return whether the current audio form requests an emergency stop."""
    if str(group or "").strip().upper() != "AUDIO":
        return False

    command_id = str(fields.get("audio_command_id") or "").strip().upper()
    event_type = str(fields.get("audio_event_type") or "").strip().upper()
    return (
        command_id in {"CMD_STOP", "CMD_EMERGENCY_STOP", "EMERGENCY_STOP"}
        or event_type == "EVT_VOICE_COMMAND_STOP"
    )


def voice_command_requires_visible_user(
    group: str,
    fields: dict[str, str],
) -> bool:
    """Return whether the selected voice command requires a visible owner."""
    if str(group).upper() != "AUDIO":
        return False

    event_type = str(fields.get("audio_event_type") or "").upper()
    command_id = str(fields.get("audio_command_id") or "").upper()
    return (
        event_type == "EVT_VOICE_COMMAND_KNOWN"
        and command_id not in {"", "CMD_UNKNOWN"}
    )


def show_toilet_training_control(group: str, demand: str) -> bool:
    """Show the local-only teaching choice only for bladder simulation."""

    return group == "Need" and demand == "Bladder"


def _confirmed_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {
        "1",
        "confirmed",
        "true",
        "yes",
    }


def _alert(message: str) -> dict[str, object]:
    return {"kind": "alert", "title": "提示", "message": message}


def _place_command(
    command: InjectionCommand,
    group: str,
    placement: dict[str, object] | None,
) -> InjectionCommand:
    if (
        not placement
        or placement.get("group") != group
        or placement.get("normalized_x") is None
    ):
        return command

    return place_injection_command(
        command,
        float(placement["normalized_x"]),
        float(placement["normalized_y"]),
    )


def _placed_user_position(
    group: str,
    placement: dict[str, object] | None,
) -> tuple[float, float] | None:
    if (
        group != "Vision"
        or not placement
        or placement.get("kind") != "human"
        or placement.get("normalized_x") is None
    ):
        return None

    return (
        float(placement["normalized_x"]),
        float(placement["normalized_y"]),
    )
