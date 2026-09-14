"""Native Arcade GUI controls for the left debug-input panel."""

from __future__ import annotations

import typing as T
from collections import Counter
from collections.abc import Callable, Iterable

import arcade
import arcade.gui

from marsdog_sim2d import config
from marsdog_sim2d.components import AJsonPreviewer, BBox, arcade_button_style
from marsdog_sim2d.controllers.left_panel_controller import (
    show_toilet_training_control,
)
from marsdog_sim2d.simevent.event_injector import (
    SCENARIOS,
    TACTILE_EVENT_SPECS,
    field_max_chars,
    resolve_emotion_output,
    resolve_need_output,
)
from marsdog_sim2d.simevent.external_damage_simulation import (
    EXTERNAL_DAMAGE_SPECS,
    build_external_damage_payload,
)
from marsdog_sim2d.simevent.injection import InjectionFormState
from marsdog_sim2d.simevent.sim_state import SimState
from marsdog_sim2d.pages.widgets import option_label

INPUT_TAB_LABELS = {
    "Event": "事件",
    "State": "状态",
    "Command": "指令",
    "Scenario": "场景",
}

EVENT_SOURCES = ("Audio", "Tactile", "Damage", "Vision", "Result")
STATE_TYPES = ("Need", "Emotion", "Personality")
SCENARIO_LABELS = {
    "high_hunger": ("高饥饿", "模拟饥饿满溢并触发觅食"),
    "low_energy": ("低能量", "模拟能量不足并触发充电"),
    "owner_calls": ("主人呼叫", "主人出现并呼叫 MarsDog"),
    "joy_interaction": ("快乐互动", "主人出现并注入高快乐情绪"),
    "fear_response": ("恐惧反应", "陌生人出现并注入高恐惧情绪"),
    "explore_toy": ("探索玩具", "发现玩具并触发探索需求"),
}

SELECT_OPTIONS: dict[str, tuple[str, ...]] = {
    "audio_event_type": (
        "EVT_VOICE_COMMAND_KNOWN",
        "EVT_VOICE_COMMAND_UNKNOWN",
        "EVT_VOICE_CALL_NAME",
        "EVT_VOICE_MASTER_ID",
        "EVT_VOICE_STRANGER_ID",
        "EVT_VOICE_PRAISE",
        "EVT_VOICE_SCOLD",
    ),
    "audio_command_id": (
        "CMD_SIT",
        "CMD_COME_HERE",
        "CMD_HAND",
        "CMD_FOLLOW",
        "CMD_STOP",
        "CMD_LIE_DOWN",
        "CMD_STAND_UP",
        "CMD_WAIT",
        "CMD_GIVE_PAW",
        "CMD_HIGH_FIVE",
        "CMD_ROLL_OVER",
        "CMD_SPIN",
        "CMD_RETURN_TO_OWNER",
        "CMD_DROP_OBJECT",
        "CMD_PLAY_DEAD",
        "CMD_BRING_OBJECT",
        "CMD_FETCH",
    ),
    "tactile_event_type": tuple(TACTILE_EVENT_SPECS),
    "damage_event_type": tuple(EXTERNAL_DAMAGE_SPECS),
    "damage_confirmed": ("unconfirmed", "confirmed"),
    "vision_events": (
        "EVT_VISION_MASTER",
        "EVT_VISION_STRANGER",
        "EVT_VISION_MASTER_HAPPY",
        "EVT_VISION_MASTER_SAD",
        "EVT_VISION_MASTER_NEUTRAL",
        "EVT_VISION_FALL",
        "EVT_VISION_STOP_GESTURE",
        "EVT_VISION_TOY",
        "EVT_VISION_FOOD",
        "EVT_VISION_ANIMAL_CALM",
        "EVT_VISION_ANIMAL_GREET",
        "EVT_VISION_ANIMAL_PLAY",
        "EVT_VISION_ANIMAL_BOUNDARY",
    ),
    "need_demand": config.DEMAND_NAMES,
    "toilet_spot_taught": ("false", "true"),
    "emotion_name": config.EMOTION_NAMES,
    "result_type": ("STARTED", "COMPLETED", "FAILED", "TIMEOUT", "INTERRUPTED", "CANCELLED"),
    "personality_profile": (
        "Custom",
        "GentleCompanion",
        "SunnyExplorer",
        "LoyalGuardian",
        "ProudIndependent",
    ),
    "personality_trait": ("A", "O", "E", "C"),
}
PanelActionHandler = Callable[[dict[str, object]], object]

QUICK_COMMANDS = (
    ("坐下", "CMD_SIT"),
    ("过来", "CMD_COME_HERE"),
    ("跟随", "CMD_FOLLOW"),
    ("握手", "CMD_GIVE_PAW"),
    ("翻滚", "CMD_ROLL_OVER"),
    ("趴下", "CMD_LIE_DOWN"),
    ("站起", "CMD_STAND_UP"),
    ("击掌", "CMD_HIGH_FIVE"),
    ("转圈", "CMD_SPIN"),
    ("装死", "CMD_PLAY_DEAD"),
    ("回来", "CMD_RETURN_TO_OWNER"),
    ("停止", "CMD_STOP"),
)


def event_parameter_fields(group: str) -> tuple[tuple[str, str, str], ...]:
    fields = {
        "Audio": (
            ("audio_asr_text", "ASR 文本", "input"),
            ("audio_command_id", "语音指令", "select"),
            ("audio_speaker_id", "说话人", "input"),
            ("audio_confidence", "置信度", "input"),
            ("audio_wake_angle", "声源角度", "input"),
        ),
        "Vision": (
            ("vision_identity", "目标 ID", "input"),
            ("vision_pose", "姿态", "input"),
            ("vision_object", "物体标签", "input"),
        ),
        "Damage": (
            ("damage_risk_score", "风险值 (0-100)", "input"),
            ("damage_confirmed", "故障确认", "select"),
        ),
        "Result": (
            ("result_action_type", "动作类型", "input"),
            ("result_demand_type", "需求类型", "input"),
            ("result_metadata", "Metadata", "input"),
        ),
    }
    return fields.get(group, ())


def event_type_field(group: str) -> str | None:
    return {
        "Audio": "audio_event_type",
        "Tactile": "tactile_event_type",
        "Damage": "damage_event_type",
        "Vision": "vision_events",
        "Result": "result_type",
    }.get(group)


class LeftControlPanel:
    """Render and dispatch the left panel through Arcade's native GUI system."""

    def __init__(
        self,
        window: arcade.Window,
        state: SimState,
        form: InjectionFormState,
        action_handler: PanelActionHandler,
        manager: T.Optional[arcade.gui.UIManager] = None,
    ) -> None:
        self._state = state
        self._form = form
        self._action_handler = action_handler
        self._window = window
        self._manager = manager or arcade.gui.UIManager(window)
        self._manager.enable()
        self._manager_enabled = True
        self._mouse_cursor_name = "default"
        self._signature: tuple[object, ...] | None = None
        self._rebuild_requested = True
        self._syncing = False
        self._payload_widget: AJsonPreviewer | None = None
        self._payload_title: arcade.gui.UILabel | None = None
        self._topic_label: arcade.gui.UILabel | None = None
        self._input_widgets: dict[str, arcade.gui.UIInputText] = {}
        self._dropdown_widgets: dict[str, tuple[arcade.gui.UIDropdown, dict[str, str], dict[str, str]]] = {}

    def draw(self) -> None:
        """Synchronize the native controls and draw them above the custom HUD."""
        if self.sync():
            self._manager.draw()

    def sync(self) -> bool:
        """Synchronize controls and report whether the GUI layer should draw."""
        if self._state.ui_pending_confirmation:
            self._set_enabled(True)
            return True

        self._set_enabled(True)
        signature = self._layout_signature()
        if self._rebuild_requested or signature != self._signature:
            self._rebuild(signature)

        self._sync_dynamic_values()
        return True

    def close(self) -> None:
        """Detach the manager from the window event stack."""
        self._set_enabled(False)
        self._set_mouse_cursor("default")

    def update_mouse_cursor(self, x: float, y: float, fallback_cursor_name: str = "default") -> None:
        """Show the native cursor matching the topmost interactive control."""
        widgets = self._manager.get_widgets_at((x, y), layer=None) if self._manager_enabled else ()
        cursor_name = _cursor_name_for_widgets(widgets)
        self._set_mouse_cursor(fallback_cursor_name if cursor_name == "default" else cursor_name)

    def request_rebuild(self) -> None:
        """Recreate controls after an action changes panel structure."""
        self._rebuild_requested = True

    def _set_enabled(self, enabled: bool) -> None:
        if enabled == self._manager_enabled:
            return

        if enabled:
            self._manager.enable()
        else:
            self._manager.disable()
        self._manager_enabled = enabled

    def _layout_signature(self) -> tuple[object, ...]:
        placement = self._state.ui_pending_placement or {}
        return (
            round(config.LEFT_PANEL_WIDTH, 2),
            round(config.BOTTOM_LOG_HEIGHT, 2),
            round(config.TOP_BAR_BOTTOM, 2),
            self._state.ui_left_collapsed,
            self._form.tab,
            self._form.group,
            self._form.selected_scenario,
            len(self._form.preview_topics),
            placement.get("group"),
            self._state.ui_payload_preview_expanded,
        )

    def _rebuild(self, signature: tuple[object, ...]) -> None:
        self._manager.clear()
        self._input_widgets.clear()
        self._dropdown_widgets.clear()
        self._payload_widget = None
        self._payload_title = None
        self._topic_label = None
        self._signature = signature
        self._rebuild_requested = False

        if config.LEFT_PANEL_WIDTH <= config.COLLAPSED_LEFT_PANEL_WIDTH + 1:
            self._build_collapsed_panel()
        else:
            self._build_panel()

        if self._state.ui_payload_preview_expanded:
            self._build_payload_dialog()

    def _build_collapsed_panel(self) -> None:
        x = config.LEFT_PANEL_LEFT + 8
        top = config.TOP_BAR_BOTTOM - 10
        self._add_button(x, top - 28, 32, 28, ">>", "expand_left")
        top -= 56

        for tab, label in INPUT_TAB_LABELS.items():
            self._add_button(
                x,
                top - 30,
                32,
                30,
                label,
                "collapsed_tab",
                active=self._form.tab == tab,
                tab=tab,
            )
            top -= 40

    def _build_panel(self) -> None:
        x = config.LEFT_PANEL_LEFT + 12
        width = config.LEFT_PANEL_WIDTH - 24
        top = config.TOP_BAR_BOTTOM - 10
        self._add_label("输入控制", x, top, width - 36, 24, font_size=config.FONT_SIZE_MODULE, bold=True)
        self._add_button(
            config.LEFT_PANEL_RIGHT - 38,
            top - 26,
            26,
            23,
            "<<",
            "collapse_left",
        )
        top -= 38

        tab_gap = 2
        input_tab_size = len(INPUT_TAB_LABELS)
        tab_width = (width - tab_gap * (input_tab_size - 1)) / input_tab_size
        tab_y = top - config.TAB_HEIGHT

        for index, (tab, label) in enumerate(INPUT_TAB_LABELS.items()):
            self._add_button(
                x + index * (tab_width + tab_gap),
                tab_y,
                tab_width,
                config.TAB_HEIGHT,
                label,
                "input_tab",
                active=self._form.tab == tab,
                tab=tab,
            )
        top = tab_y - 8
        bottom = config.BOTTOM_LOG_HEIGHT + 10

        if self._form.tab == "State":
            self._build_state_tab(x, top, width, bottom)
        elif self._form.tab == "Command":
            self._build_command_tab(x, top, width, bottom)
        elif self._form.tab == "Scenario":
            self._build_scenario_tab(x, top, width, bottom)
        else:
            self._build_event_tab(x, top, width, bottom)

    def _build_event_tab(self, x: float, top: float, width: float, bottom: float) -> None:
        group = self._form.group if self._form.group in EVENT_SOURCES else "Audio"
        top = self._add_dropdown_row(
            "event_source",
            "事件来源",
            group,
            EVENT_SOURCES,
            x,
            top,
            width,
            target="event_group",
        )
        field_id = event_type_field(group)
        if field_id:
            top = self._add_dropdown_row(
                "event_type",
                "事件类型",
                self._form.fields.get(field_id, "-"),
                SELECT_OPTIONS.get(field_id, (self._form.fields.get(field_id, "-"),), ),
                x,
                top,
                width,
                target="field",
                field_id=field_id,
            )

        for parameter_id, label, kind in event_parameter_fields(group):
            if kind == "select":
                top = self._add_dropdown_row(
                    f"event_{parameter_id}",
                    label,
                    self._form.fields.get(parameter_id, ""),
                    SELECT_OPTIONS.get(parameter_id, (self._form.fields.get(parameter_id, ""),), ),
                    x,
                    top,
                    width,
                    target="field",
                    field_id=parameter_id,
                )
            else:
                top = self._add_input_row(
                    parameter_id,
                    label,
                    self._form.fields.get(parameter_id, ""),
                    x,
                    top,
                    width,
                )

        if group == "Damage":
            event_type = self._form.fields.get(
                "damage_event_type",
                "EVT_DAMAGE_LIGHT_IMPACT",
            )
            score = _to_float(
                self._form.fields.get("damage_risk_score")
            )
            payload = build_external_damage_payload(
                event_type,
                60.0 if score is None else score,
                confirmed=(
                    self._form.fields.get("damage_confirmed")
                    == "confirmed"
                ),
            )
            top = self._add_notice(
                f"判定：{payload['risk_level']}",
                (
                    f"表格建议 {payload['suggested_risk_level']} · "
                    f"{payload['duration_label']} · 仅本地模拟"
                ),
                x,
                top,
                width,
            )

        if group == "Vision":
            active = bool(
                self._state.ui_pending_placement
                and self._state.ui_pending_placement.get("group") == group
            )
            top = self._add_action_row(
                x,
                top,
                width,
                "在场景中放置目标",
                "placement_mode",
                active=active,
                group=group,
            )

        self._add_payload_section(x, top, width, bottom, "发送事件", "send_event")

    def _build_state_tab(self, x: float, top: float, width: float, bottom: float) -> None:
        group = (
            self._form.group
            if self._form.group in STATE_TYPES
            else "Need"
        )
        top = self._add_dropdown_row(
            "state_type",
            "状态类型",
            group,
            STATE_TYPES,
            x,
            top,
            width,
            target="event_group",
        )

        if group == "Need":
            top = self._add_dropdown_row(
                "state_item",
                "需求项",
                self._form.fields.get("need_demand", "Hunger"),
                config.DEMAND_NAMES,
                x,
                top,
                width,
                target="field",
                field_id="need_demand",
            )
            top = self._add_input_row(
                "need_value",
                "数值 (0-100)",
                self._form.fields.get("need_value", ""),
                x,
                top,
                width,
            )
            if show_toilet_training_control(
                group,
                self._form.fields.get("need_demand", "Hunger"),
            ):
                top = self._add_dropdown_row(
                    "toilet_training",
                    "定点示教",
                    self._form.fields.get("toilet_spot_taught", "false"),
                    SELECT_OPTIONS["toilet_spot_taught"],
                    x,
                    top,
                    width,
                    target="field",
                    field_id="toilet_spot_taught",
                )
            value = _to_float(self._form.fields.get("need_value"))
            level, event_name = resolve_need_output(
                self._form.fields.get("need_demand", "Hunger"),
                82.0 if value is None else value,
            )

            top = self._add_notice(f"推导等级：{level}", event_name, x, top, width)
            button_label = "发布状态与事件"
        elif group == "Emotion":
            top = self._add_dropdown_row(
                "state_item",
                "情绪项",
                self._form.fields.get("emotion_name", "Joy"),
                config.EMOTION_NAMES,
                x,
                top,
                width,
                target="field",
                field_id="emotion_name",
            )
            top = self._add_input_row(
                "emotion_value",
                "数值 (0-100)",
                self._form.fields.get("emotion_value", ""),
                x,
                top,
                width,
            )
            value = _to_float(self._form.fields.get("emotion_value"))
            level, event_name, level_range = resolve_emotion_output(
                self._form.fields.get("emotion_name", "Joy"),
                90.0 if value is None else value,
            )
            detail = (
                f"{event_name}  区间 {level_range[0]}-{level_range[1]}"
                if event_name and level_range
                else "当前数值没有对应的情绪事件"
            )
            top = self._add_notice(f"推导等级：{level}", detail, x, top, width)
            button_label = "发布状态与事件" if event_name else "仅发布状态快照"
        else:
            trait = self._form.fields.get("personality_trait", "A")
            top = self._add_dropdown_row(
                "state_item",
                "性格维度",
                trait,
                SELECT_OPTIONS["personality_trait"],
                x,
                top,
                width,
                target="field",
                field_id="personality_trait",
            )
            value_field = f"personality_{trait.lower()}"
            top = self._add_input_row(
                value_field,
                "数值 (0-100)",
                self._form.fields.get(value_field, ""),
                x,
                top,
                width,
            )
            top = self._add_dropdown_row(
                "state_profile",
                "性格配置",
                self._form.fields.get("personality_profile", "Custom"),
                SELECT_OPTIONS["personality_profile"],
                x,
                top,
                width,
                target="field",
                field_id="personality_profile",
            )
            top = self._add_notice(
                "仅模拟状态快照",
                "不会持久修改 personality_node",
                x,
                top,
                width,
            )
            button_label = "发布性格快照"

        self._add_payload_section(
            x,
            top,
            width,
            bottom,
            button_label,
            "publish_state_output",
        )

    def _build_command_tab(self, x: float, top: float, width: float, bottom: float) -> None:
        top = self._add_dropdown_row(
            "command_id",
            "指令类型",
            self._form.fields.get("audio_command_id", "CMD_SIT"),
            SELECT_OPTIONS["audio_command_id"],
            x,
            top,
            width,
            target="field",
            field_id="audio_command_id",
        )
        for field_id, label in (
                ("audio_asr_text", "ASR 文本"),
                ("audio_speaker_id", "说话人"),
                ("audio_confidence", "置信度"),
        ):
            top = self._add_input_row(
                field_id,
                label,
                self._form.fields.get(field_id, ""),
                x,
                top,
                width,
            )

        top = self._add_label("快捷指令", x, top, width, 16, font_size=config.FONT_SIZE_AUX)
        gap = 5
        button_height = 26
        cell_width = (width - gap * 2) / 3
        for index, (label, command_id) in enumerate(QUICK_COMMANDS):
            row = index // 3
            column = index % 3
            self._add_button(
                x + column * (cell_width + gap),
                top - (row + 1) * button_height - row * gap,
                cell_width,
                button_height,
                label,
                "command_quick",
                command_id=command_id,
                asr_text=label,
            )
        top -= 4 * button_height + 3 * gap + 6
        self._add_payload_section(x, top, width, bottom, "发送指令", "send_command")

    def _build_scenario_tab(
            self,
            x: float,
            top: float,
            width: float,
            _bottom: float,
    ) -> None:
        top = self._add_label(
            "预设测试场景",
            x,
            top,
            width,
            18,
            font_size=config.FONT_SIZE_AUX,
        )
        for scenario_id, label, summary in SCENARIOS:
            label, summary = SCENARIO_LABELS.get(scenario_id, (label, summary))
            height = 46
            button = self._add_button(
                x,
                top - height,
                width,
                height,
                f"{label}\n{summary}",
                "scenario",
                active=self._form.selected_scenario == scenario_id,
                multiline=True,
                scenario_id=scenario_id,
            )
            button.place_text(anchor_x="left", align_x=12)
            top -= height + 6

    def _add_payload_section(
            self,
            x: float,
            top: float,
            width: float,
            bottom: float,
            action_label: str,
            action: str,
            **data: object,
    ) -> None:
        top = self._add_label(
            "发布话题:",
            x,
            top - 11,
            width,
            12,
            font_size=config.FONT_SIZE_AUX,
        )

        topic_height = max(
            1,
            len(self._form.preview_topics),
        ) * config.LINE_HEIGHT
        self._topic_label = self._manager.add(self._add_label_widget(
            ", ".join(self._form.preview_topics) or "-",
            x,
            top - config.SPACE_XS - topic_height,
            width,
            topic_height,
            font_size=config.FONT_SIZE_AUX,
            color=config.COLORS["accent"],
            multiline=True,
        ))

        top -= topic_height + config.SPACE_XS + config.SPACE_SM

        label_width = min(82.0, width * 0.34)
        preview_width = width - label_width
        self._add_button(
            x + label_width,
            top - 26,
            preview_width,
            26,
            "预览",
            "show_payload_preview",
        )
        self._payload_title = self._manager.add(self._add_label_widget(
            "Payload",
            x,
            top - 26,
            label_width - config.SPACE_XS,
            26,
            font_size=config.FONT_SIZE_AUX,
            color=config.COLORS["muted_text"]
        ))

        top -= 31
        self._add_button(
            x,
            max(bottom, top - config.BUTTON_HEIGHT) - 11,
            width,
            config.BUTTON_HEIGHT,
            action_label,
            action,
            primary=True,
            **data,
        )

    def _build_payload_dialog(self) -> None:
        """Build the read-only Payload preview dialog."""
        overlay = arcade.gui.UIWidget(
            x=0,
            y=0,
            width=config.WINDOW_WIDTH,
            height=config.WINDOW_HEIGHT,
            size_hint=None,
        ).with_background(color=(0, 0, 0, 180))
        self._manager.add(overlay, layer=arcade.gui.UIManager.OVERLAY_LAYER)

        width = min(780.0, config.WINDOW_WIDTH - 80)
        height = min(560.0, config.TOP_BAR_BOTTOM - config.BOTTOM_LOG_HEIGHT - 40)
        x = (config.WINDOW_WIDTH - width) / 2
        y = config.BOTTOM_LOG_HEIGHT + (
                config.TOP_BAR_BOTTOM - config.BOTTOM_LOG_HEIGHT - height
        ) / 2
        panel = arcade.gui.UIWidget(
            x=x,
            y=y,
            width=width,
            height=height,
            size_hint=None,
        ).with_background(color=_rgba(config.COLORS["modal_background"]))
        self._manager.add(panel, layer=arcade.gui.UIManager.OVERLAY_LAYER)

        self._payload_title = self._add_label_widget(
            "Payload",
            x + 14,
            y + height - 36,
            width - 70,
            24,
            font_size=config.FONT_SIZE_MODULE,
            bold=True,
        )
        self._manager.add(self._payload_title, layer=arcade.gui.UIManager.OVERLAY_LAYER)
        self._topic_label = self._add_label_widget(
            ", ".join(self._form.preview_topics) or "-",
            x + 14,
            y + height - 57,
            width - 70,
            18,
            font_size=config.FONT_SIZE_AUX,
            color=config.COLORS["accent"],
        )
        self._manager.add(self._topic_label, layer=arcade.gui.UIManager.OVERLAY_LAYER)
        self._add_button(
            x + width - 44,
            y + height - 36,
            30,
            26,
            "×",
            "close_payload_preview",
            layer=arcade.gui.UIManager.OVERLAY_LAYER,
        )

        payload_widget = AJsonPreviewer(
            BBox(x + 14, y + 14, width - 28, height - 82),
            self._form.payload_preview,
            font_size=10,
            size_hint=None,
        )

        self._payload_widget = payload_widget

        self._manager.add(
            payload_widget,
            layer=arcade.gui.UIManager.OVERLAY_LAYER,
        )

    def _add_input_row(
            self,
            field_id: str,
            label: str,
            value: str,
            x: float,
            top: float,
            width: float,
    ) -> float:
        label_width = min(82.0, width * 0.34)
        height = config.CONTROL_HEIGHT
        self._manager.add(self._add_label_widget(
            label,
            x,
            top - height,
            label_width - 4,
            height,
            font_size=config.FONT_SIZE_AUX,
        ))
        widget = arcade.gui.UIInputText(
            x=x + label_width,
            y=top - height,
            width=width - label_width,
            height=height,
            text=value,
            font_name=config.FONT_NAMES,
            font_size=config.FONT_SIZE_BODY,
            text_color=_rgba(config.COLORS["text"]),
            caret_color=_rgba(config.COLORS["accent"]),
            border_color=_rgba(config.COLORS["border"]),
            border_width=1,
            size_hint=None,
        ).with_background(color=_rgba(config.COLORS["surface_raised"]))
        widget.doc.set_paragraph_style(0, len(value), {"align": "center"})
        widget.layout.content_valign = "center"

        @widget.event("on_change")
        def handle_change(event: T.Any, current_field_id: str = field_id) -> None:
            self._update_field(current_field_id, str(event.new_value), widget)

        self._input_widgets[field_id] = widget
        self._manager.add(widget)
        return top - height - config.FORM_ROW_GAP

    def _add_dropdown_row(
            self,
            select_id: str,
            label: str,
            value: str,
            options: Iterable[str],
            x: float,
            top: float,
            width: float,
            target: str,
            field_id: str | None = None,
    ) -> float:
        label_width = min(82.0, width * 0.34)
        height = config.CONTROL_HEIGHT
        self._manager.add(self._add_label_widget(
            label,
            x,
            top - height,
            label_width - 4,
            height,
            font_size=config.FONT_SIZE_AUX,
        ))
        raw_to_display, display_to_raw = _display_options(options)
        display_value = raw_to_display.get(value, option_label(value))
        widget = arcade.gui.UIDropdown(
            x=x + label_width,
            y=top - height,
            width=width - label_width,
            height=height,
            default=display_value,
            options=list(display_to_raw),
            primary_style=_dropdown_style(active=False),
            dropdown_style=_dropdown_style(active=False),
            active_style=_dropdown_style(active=True),
            size_hint=None,
        )

        @widget.event("on_change")
        def handle_change(event: T.T.Any) -> None:
            if self._syncing:
                return
            raw_value = display_to_raw.get(str(event.new_value), str(event.new_value))
            self._dispatch(
                "select_option",
                select_id=select_id,
                target=target,
                field_id=field_id,
                value=raw_value,
            )
            self.request_rebuild()

        self._dropdown_widgets[select_id] = (
            widget,
            raw_to_display,
            display_to_raw,
        )
        self._manager.add(widget)
        return top - height - config.FORM_ROW_GAP

    def _add_action_row(
            self,
            x: float,
            top: float,
            width: float,
            label: str,
            action: str,
            **data: object,
    ) -> float:
        height = config.BUTTON_HEIGHT
        self._add_button(x, top - height, width, height, label, action, **data)
        return top - height - config.FORM_ROW_GAP

    def _add_notice(self, title: str, detail: str, x: float, top: float, width: float) -> float:
        notice_height = 2 * config.LINE_HEIGHT + 2 * config.SPACE_XS if detail else config.CONTROL_HEIGHT

        notice_bottom = top - notice_height
        # notice_background = arcade.gui.UIWidget(
        #     x=x,
        #     y=notice_bottom,
        #     width=width,
        #     height=notice_height,
        #     size_hint=None,
        # ).with_background(color=_rgba(config.COLORS["surface"]))
        # self._manager.add(notice_background)

        label_x = x + config.SPACE_SM
        label_width = max(1.0, width - 2 * config.SPACE_SM)
        title_y = top - config.SPACE_XS - config.LINE_HEIGHT if detail else notice_bottom + (
                notice_height - config.LINE_HEIGHT) / 2

        self._manager.add(self._add_label_widget(
            title,
            label_x,
            title_y,
            label_width,
            config.LINE_HEIGHT,
            font_size=config.FONT_SIZE_AUX,
            color=config.COLORS["text"],
        ))

        if detail:
            self._manager.add(self._add_label_widget(
                detail,
                label_x,
                notice_bottom + config.SPACE_XS,
                label_width,
                config.LINE_HEIGHT,
                font_size=config.FONT_SIZE_AUX,
                color=config.COLORS["muted_text"],
            ))

        return top - notice_height - config.FORM_ROW_GAP

    def _add_button(
            self,
            x: float,
            y: float,
            width: float,
            height: float,
            label: str,
            action: str,
            *,
            primary: bool = False,
            active: bool = False,
            multiline: bool = False,
            layer: int = arcade.gui.UIManager.DEFAULT_LAYER,
            **data: object,
    ) -> arcade.gui.UIFlatButton:
        button = arcade.gui.UIFlatButton(
            x=x,
            y=y,
            width=width,
            height=height,
            text=label,
            multiline=multiline,
            style=arcade_button_style(primary=primary, active=active),
            size_hint=None,
        )

        @button.event("on_click")
        def handle_click(_event: T.Any) -> None:
            self._dispatch(action, **data)
            self.request_rebuild()

        self._manager.add(button, layer=layer)
        return button

    def _add_label(
            self,
            text: str,
            x: float,
            top: float,
            width: float,
            height: float,
            **kwargs: T.Any,
    ) -> float:
        self._manager.add(
            self._add_label_widget(
                text,
                x,
                top - height,
                width,
                height,
                **kwargs,
            )
        )
        return top - height

    def _add_label_widget(
            self,
            text: str,
            x: float,
            y: float,
            width: float,
            height: float,
            *,
            font_size: float = config.FONT_SIZE_AUX,
            color: tuple[int, ...] = config.COLORS["muted_text"],
            bold: bool = False,
            multiline: bool = False,
    ) -> arcade.gui.UILabel:
        return arcade.gui.UILabel(
            x=x,
            y=y,
            width=width,
            height=height,
            text=text,
            font_name=config.FONT_NAMES,
            font_size=font_size,
            text_color=_rgba(color),
            bold=bold,
            multiline=multiline,
            size_hint=None,
        )

    def _update_field(
            self,
            field_id: str,
            value: str,
            widget: arcade.gui.UIInputText,
    ) -> None:
        if self._syncing:
            return

        limited_value = value[: field_max_chars(field_id)]
        if limited_value != value:
            self._syncing = True
            try:
                widget.text = limited_value
            finally:
                self._syncing = False
        self._dispatch(
            "field_changed",
            field_id=field_id,
            value=limited_value,
        )

    def _update_payload(self, value: str) -> None:
        if self._syncing:
            return

        limited_value = value[: config.MAX_PAYLOAD_PREVIEW_CHARS]
        self._dispatch("payload_changed", value=limited_value)

    def _dispatch(self, action: str, **data: object) -> None:
        self._action_handler({"action": action, **data})

    def _set_mouse_cursor(self, cursor_name: str) -> None:
        if cursor_name == self._mouse_cursor_name:
            return

        cursor = (
            None
            if cursor_name == "default"
            else self._window.get_system_mouse_cursor(cursor_name)
        )
        self._window.set_mouse_cursor(cursor)
        self._mouse_cursor_name = cursor_name

    def _sync_dynamic_values(self) -> None:
        self._syncing = True
        try:
            if self._payload_widget is not None:
                payload_text = self._form.payload_preview
                self._payload_widget.set_value(payload_text)
            if self._payload_title is not None:
                expanded = self._state.ui_payload_preview_expanded
                title = "Payload"
                if self._payload_title.text != title:
                    self._payload_title.text = title
            if self._topic_label is not None:
                topic_text = ", ".join(self._form.preview_topics) or "-"
                if self._topic_label.text != topic_text:
                    self._topic_label.text = topic_text

            for field_id, widget in self._input_widgets.items():
                value = self._form.fields.get(field_id, "")
                if widget.text != value:
                    widget.text = value

            for select_id, (widget, raw_to_display, _display_to_raw) in self._dropdown_widgets.items():
                raw_value = self._selected_raw_value(select_id)
                display_value = raw_to_display.get(raw_value, option_label(raw_value))
                if widget.value != display_value:
                    widget.value = display_value
        finally:
            self._syncing = False

    def _selected_raw_value(self, select_id: str) -> str:
        if select_id == "event_source" or select_id == "state_type":
            return self._form.group
        field_ids = {
            "event_type": event_type_field(self._form.group) or "",
            "state_item": {
                "Need": "need_demand",
                "Emotion": "emotion_name",
                "Personality": "personality_trait",
            }.get(self._form.group, ""),
            "state_profile": "personality_profile",
            "command_id": "audio_command_id",
            "toilet_training": "toilet_spot_taught",
        }
        field_id = field_ids.get(select_id)
        if not field_id and select_id.startswith("event_"):
            field_id = select_id.removeprefix("event_")
        return self._form.fields.get(field_id or "", "")


def _display_options(options: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    raw_values = tuple(str(option) for option in options)
    labels = [option_label(value) for value in raw_values]
    counts = Counter(labels)
    raw_to_display = {
        raw_value: (
            f"{label} ({raw_value})"
            if counts[label] > 1
            else label
        )
        for raw_value, label in zip(raw_values, labels)
    }
    display_to_raw = {
        display: raw_value
        for raw_value, display in raw_to_display.items()
    }
    return raw_to_display, display_to_raw


def _cursor_name_for_widgets(widgets: Iterable[arcade.gui.UIWidget]) -> str:
    for widget in widgets:
        if isinstance(widget, arcade.gui.UIInputText):
            return "text"
        if isinstance(widget, arcade.gui.UIInteractiveWidget):
            return "hand"
    return "default"


def _dropdown_style(*, active: bool) -> dict[str, T.T.Any]:
    return arcade_button_style(active=active)


def _rgba(color: tuple[int, ...]) -> tuple[int, int, int, int]:
    if len(color) >= 4:
        return int(color[0]), int(color[1]), int(color[2]), int(color[3])
    return int(color[0]), int(color[1]), int(color[2]), 255


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
