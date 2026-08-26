"""Responsive debug-console widgets for the Arcade viewer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import time
from typing import Any, Iterable

import arcade
import arcade.gui

from marsdog_sim2d import config
from marsdog_sim2d.action_visuals import visual_for_action
from marsdog_sim2d.components import AButton, AJsonPreviewer, AMessageBox, ATopicChip, BBox
from marsdog_sim2d.components.drawing import draw_text, measure_text
from marsdog_sim2d.sim_state import SimState
from marsdog_sim2d.voice_commands import voice_command_display

INPUT_TABS = ("Event", "State", "Command", "Scenario")
EVENT_SOURCES = ("Audio", "Vision", "Result")
STATE_TYPES = ("Need", "Emotion", "Personality")
LOG_SOURCES = ("VIS", "AUD", "NEED", "EMO", "BEH", "EXEC", "RESULT", "SYS")

TAB_LABELS = {
    "Event": "事件",
    "State": "状态",
    "Command": "指令",
    "Scenario": "场景",
}

OPTION_LABELS = {
    "Audio": "声音",
    "Vision": "视觉",
    "Result": "行为结果",
    "Need": "需求",
    "Emotion": "情绪",
    "Personality": "性格",
    "EVT_VOICE_COMMAND_KNOWN": "已知指令",
    "EVT_VOICE_COMMAND_UNKNOWN": "未知指令",
    "EVT_VOICE_CALL_NAME": "呼叫名字",
    "EVT_VOICE_MASTER_ID": "主人声纹",
    "EVT_VOICE_STRANGER_ID": "陌生声纹",
    "EVT_VOICE_PRAISE": "表扬",
    "EVT_VOICE_SCOLD": "批评",
    "EVT_VISION_MASTER": "主人",
    "EVT_VISION_STRANGER": "陌生人",
    "EVT_VISION_MASTER_HAPPY": "主人开心",
    "EVT_VISION_MASTER_SAD": "主人悲伤",
    "EVT_VISION_MASTER_NEUTRAL": "主人中性",
    "EVT_VISION_FALL": "人员跌倒",
    "EVT_VISION_STOP_GESTURE": "停止手势",
    "EVT_VISION_TOY": "玩具",
    "EVT_VISION_FOOD": "食物",
    "EVT_VISION_ANIMAL_CALM": "动物平静",
    "EVT_VISION_ANIMAL_GREET": "动物问候",
    "EVT_VISION_ANIMAL_PLAY": "动物邀玩",
    "EVT_VISION_ANIMAL_BOUNDARY": "动物边界",
    "CMD_SIT": "坐下",
    "CMD_COME_HERE": "过来",
    "CMD_HAND": "握手",
    "CMD_FOLLOW": "跟随",
    "CMD_STOP": "停止",
    "CMD_LIE_DOWN": "趴下",
    "CMD_SPIN": "转圈",
    "CMD_FETCH": "取物",
    "CMD_STAND_UP": "站起",
    "CMD_WAIT": "等待",
    "CMD_GIVE_PAW": "握手",
    "CMD_HIGH_FIVE": "击掌",
    "CMD_ROLL_OVER": "翻滚",
    "CMD_RETURN_TO_OWNER": "回到主人身边",
    "CMD_DROP_OBJECT": "吐掉",
    "CMD_PLAY_DEAD": "装死",
    "CMD_BRING_OBJECT": "拿来",
    "STARTED": "开始",
    "COMPLETED": "完成",
    "FAILED": "失败",
    "TIMEOUT": "超时",
    "INTERRUPTED": "中断",
    "CANCELLED": "取消",
    "CANCELED": "取消",
    "Hunger": "饥饿",
    "Bladder": "排泄",
    "Sleepiness": "困倦",
    "Cleanliness": "清洁",
    "Energy": "能量",
    "Social": "社交",
    "Exploration": "探索",
    "Joy": "快乐",
    "Excite": "兴奋",
    "Anxiety": "焦虑",
    "Fear": "恐惧",
    "Curious": "好奇",
    "Calm": "平静",
    "Custom": "自定义",
    "GentleCompanion": "温和陪伴",
    "SunnyExplorer": "阳光探索",
    "LoyalGuardian": "忠诚守护",
    "ProudIndependent": "独立自信",
    "A": "亲和 A",
    "O": "开放 O",
    "E": "外向 E",
    "C": "稳定 C",
    "waiting": "等待中",
    "running": "执行中",
    "accepted": "已接受",
    "completed": "已完成",
    "succeeded": "已成功",
    "failed": "失败",
    "timeout": "超时",
    "interrupted": "已中断",
    "cancelled": "已取消",
    "canceled": "已取消",
}

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

TOP_ENDPOINTS = (
    ("VIS", (config.TOPICS["visual_event"],)),
    ("AUDIO", (config.TOPICS["audio_event"],)),
    (
        "NEED",
        (config.TOPICS["internal_need_state"], config.TOPICS["internal_need_signal_event"]),
    ),
    (
        "EMO",
        (config.TOPICS["emotion_state"], config.TOPICS["emotion_signal_event"]),
    ),
    (
        "EXEC",
        (config.ACTION_FEEDBACK_TOPIC, config.ACTION_GOAL_TOPIC, config.ACTION_RESULT_TOPIC),
    ),
)


class StatusWidgets:
    """Draw and hit-test the non-scene portions of the debug console."""

    def __init__(
            self,
            manager: arcade.gui.UIManager,
            event_detail_action_handler: Callable[[str], object] | None = None,
            confirmation_action_handler: Callable[[str], object] | None = None,
    ) -> None:
        self._manager = manager
        self._event_detail_action_handler = event_detail_action_handler
        self._confirmation_action_handler = confirmation_action_handler
        self._event_payload_previewer: AJsonPreviewer | None = None
        self._event_detail_buttons: tuple[AButton, AButton] | None = None
        self._top_title_label: arcade.gui.UILabel | None = None
        self._top_time_label: arcade.gui.UILabel | None = None
        self._top_stats_label: arcade.gui.UILabel | None = None
        self._top_time_color: tuple[int, ...] | None = None
        self._topic_chips: dict[str, ATopicChip] = {}
        self._confirmation_box: AMessageBox | None = None
        self._confirmation_signature: tuple[object, ...] | None = None
        self._event_toolbar_layout: arcade.gui.UIBoxLayout | None = None
        self._event_toolbar_slots: dict[str, arcade.gui.UIWidget] = {}
        self._event_search_input: arcade.gui.UIInputText | None = None
        self._syncing_event_search = False
        self._hits: list[dict[str, Any]] = []
        self._hovered: dict[str, Any] | None = None
        self._right_scroll_max = 0.0

    @property
    def right_scroll_max(self) -> float:
        return self._right_scroll_max

    def draw(self, state: SimState) -> None:
        self._hits = []
        self._sync_top_status_bar(state)
        self._sync_event_payload_previewer(state)
        self._sync_event_detail_buttons(state)
        self._sync_confirmation(state)
        self._draw_panel_backgrounds()
        self._draw_status_panel(state)
        self._draw_scene_controls(state)
        self._draw_event_stream(state)
        self._draw_object_detail(state)
        self._draw_event_detail(state)
        self._draw_tooltip()

    def hit_test(self, x: float, y: float) -> dict[str, Any] | None:
        for item in reversed(self._hits):
            if item["x"] <= x <= item["x"] + item["w"] and item["y"] <= y <= item["y"] + item["h"]:
                return item
        return None

    def set_hover(self, x: float, y: float) -> None:
        self._hovered = self.hit_test(x, y)

    def _draw_panel_backgrounds(self) -> None:
        arcade.draw_lrbt_rectangle_filled(
            config.LEFT_PANEL_LEFT,
            config.LEFT_PANEL_RIGHT,
            config.BOTTOM_LOG_HEIGHT,
            config.TOP_BAR_BOTTOM,
            config.COLORS["panel_background"],
        )
        arcade.draw_lrbt_rectangle_filled(
            config.RIGHT_PANEL_LEFT,
            config.RIGHT_PANEL_RIGHT,
            config.BOTTOM_LOG_HEIGHT,
            config.TOP_BAR_BOTTOM,
            config.COLORS["panel_background"],
        )
        arcade.draw_lrbt_rectangle_filled(
            0,
            config.WINDOW_WIDTH,
            0,
            config.BOTTOM_LOG_HEIGHT,
            config.COLORS["log_background"],
        )
        arcade.draw_lrbt_rectangle_filled(
            0,
            config.WINDOW_WIDTH,
            config.TOP_BAR_BOTTOM,
            config.TOP_BAR_TOP,
            config.COLORS["top_bar"],
        )
        for x in (config.LEFT_PANEL_RIGHT, config.RIGHT_PANEL_LEFT):
            arcade.draw_line(
                x,
                config.BOTTOM_LOG_HEIGHT,
                x,
                config.TOP_BAR_BOTTOM,
                config.COLORS["separator"],
                config.PANEL_BORDER_WIDTH,
            )
        arcade.draw_line(
            0,
            config.BOTTOM_LOG_HEIGHT,
            config.WINDOW_WIDTH,
            config.BOTTOM_LOG_HEIGHT,
            config.COLORS["separator"],
            config.PANEL_BORDER_WIDTH,
        )
        arcade.draw_line(
            0,
            config.TOP_BAR_BOTTOM,
            config.WINDOW_WIDTH,
            config.TOP_BAR_BOTTOM,
            config.COLORS["separator"],
            config.PANEL_BORDER_WIDTH,
        )

    def _sync_top_status_bar(self, state: SimState) -> None:
        """Synchronize the native title, Topic chips, and runtime summary."""
        now = time.time()
        title = "MarsDog 调试控制台" if config.WINDOW_WIDTH >= 1280 else "MarsDog"
        title_bounds = BBox(
            16.0,
            config.TOP_BAR_BOTTOM + 6.0,
            330.0 if config.WINDOW_WIDTH >= 1280 else 120.0,
            32.0,
        )
        self._top_title_label = self._sync_top_label(
            self._top_title_label,
            title,
            title_bounds,
            font_size=config.FONT_SIZE_PAGE,
            color=config.COLORS["text"],
            bold=True,
        )

        chip_gap = 7.0
        chip_area_left = max(
            380.0 if config.WINDOW_WIDTH >= 1280 else 150.0,
            config.LEFT_PANEL_RIGHT + 8.0,
        )
        chip_area_width = max(
            360.0,
            config.RIGHT_PANEL_LEFT - chip_area_left - 12.0,
        )
        chip_width = min(
            118.0,
            (chip_area_width - chip_gap * (len(TOP_ENDPOINTS) - 1))
            / len(TOP_ENDPOINTS),
        )
        chip_row_width = (
                chip_width * len(TOP_ENDPOINTS)
                + chip_gap * (len(TOP_ENDPOINTS) - 1)
        )
        chip_x = chip_area_left + (chip_area_width - chip_row_width) / 2
        chip_y = config.TOP_BAR_BOTTOM + 6.0

        for label, topics in TOP_ENDPOINTS:
            status, status_text, detail = _endpoint_status(state, topics, label, now)
            color = _health_color(status)
            chip_text = f"{label}  {_compact_topic_status(status_text)}"
            bounds = BBox(chip_x, chip_y, chip_width, 31.0)
            chip = self._topic_chips.get(label)
            if chip is None or chip.appearance != (chip_text, tuple(color)):
                if chip is not None and self._widget_is_managed(
                        chip,
                        layer=arcade.gui.UIManager.DEFAULT_LAYER,
                ):
                    self._manager.remove(chip)
                chip = ATopicChip(bounds, chip_text, color)
                self._topic_chips[label] = chip
            elif chip.bbox != bounds:
                chip.bbox = bounds

            if not self._widget_is_managed(
                    chip,
                    layer=arcade.gui.UIManager.DEFAULT_LAYER,
            ):
                self._manager.add(chip)

            self._hit(
                "topic_detail",
                bounds.x,
                bounds.y,
                bounds.width,
                bounds.height,
                topic_label=label,
                topics=topics,
                tooltip=detail,
            )
            chip_x += chip_width + chip_gap

        time_text, time_color = _virtual_time_display(state)
        right_x = config.RIGHT_PANEL_LEFT + 8.0
        right_width = max(1.0, config.WINDOW_WIDTH - right_x - 16.0)
        if self._top_time_color != tuple(time_color):
            self._remove_top_label(self._top_time_label)
            self._top_time_label = None
            self._top_time_color = tuple(time_color)
        self._top_time_label = self._sync_top_label(
            self._top_time_label,
            time_text,
            BBox(right_x, config.TOP_BAR_BOTTOM + 21.0, right_width, 18.0),
            font_size=config.FONT_SIZE_BODY,
            color=time_color,
            bold=True,
            align="right",
        )
        self._top_stats_label = self._sync_top_label(
            self._top_stats_label,
            f"事件 {state.processed_events}  队列 {state.queue_depth}",
            BBox(right_x, config.TOP_BAR_BOTTOM + 5.0, right_width, 14.0),
            font_size=config.FONT_SIZE_AUX,
            color=config.COLORS["muted_text"],
            align="right",
        )

    def _sync_top_label(
            self,
            label: arcade.gui.UILabel | None,
            text: str,
            bounds: BBox,
            *,
            font_size: float,
            color: tuple[int, ...],
            bold: bool = False,
            align: str = "left",
    ) -> arcade.gui.UILabel:
        if label is None:
            label = arcade.gui.UILabel(
                x=bounds.x,
                y=bounds.y,
                width=bounds.width,
                height=bounds.height,
                text=text,
                font_name=config.FONT_NAMES,
                font_size=font_size,
                text_color=_rgba(color),
                bold=bold,
                align=align,
                size_hint=None,
            )
        elif label.text != text:
            label.text = text

        _set_widget_bounds(label, bounds)
        if not self._widget_is_managed(
                label,
                layer=arcade.gui.UIManager.DEFAULT_LAYER,
        ):
            self._manager.add(label)
        return label

    def _remove_top_label(self, label: arcade.gui.UILabel | None) -> None:
        if label is None:
            return
        if self._widget_is_managed(
                label,
                layer=arcade.gui.UIManager.DEFAULT_LAYER,
        ):
            self._manager.remove(label)

    def _draw_status_panel(self, state: SimState) -> None:
        x = config.RIGHT_PANEL_LEFT + 10
        width = config.RIGHT_PANEL_WIDTH - 20
        clip_bottom = config.BOTTOM_LOG_HEIGHT + 1
        clip_top = config.TOP_BAR_BOTTOM - 1
        scroll = max(0.0, min(state.ui_right_scroll, self._right_scroll_max))
        top = clip_top - 10 + scroll

        old_scissor = arcade.get_window().ctx.scissor
        arcade.get_window().ctx.scissor = (
            int(config.RIGHT_PANEL_LEFT),
            int(clip_bottom),
            int(config.RIGHT_PANEL_WIDTH),
            int(clip_top - clip_bottom),
        )
        try:
            top = self._draw_current_behavior(state, x, top, width)
            top = self._draw_decision_trace(state, x, top, width)
            top = self._draw_need_card(state, x, top, width)
            top = self._draw_emotion_card(state, x, top, width)
            top = self._draw_perception_card(state, x, top, width)
        finally:
            arcade.get_window().ctx.scissor = old_scissor

        content_height = (clip_top - 10 + scroll) - top
        viewport_height = clip_top - clip_bottom - 18
        self._right_scroll_max = max(0.0, content_height - viewport_height)
        state.ui_right_scroll = max(0.0, min(state.ui_right_scroll, self._right_scroll_max))
        if self._right_scroll_max > 0:
            track_x = config.RIGHT_PANEL_RIGHT - 4
            track_h = clip_top - clip_bottom - 12
            thumb_h = max(34.0, track_h * viewport_height / max(content_height, 1.0))
            thumb_y = clip_top - 6 - thumb_h - (track_h - thumb_h) * (state.ui_right_scroll / self._right_scroll_max)
            arcade.draw_lbwh_rectangle_filled(track_x, thumb_y, 2, thumb_h, config.COLORS["border_strong"])

    def _draw_scene_controls(self, state: SimState) -> None:
        audio_placement_active = bool(
            state.ui_pending_placement
            and state.ui_pending_placement.get("group") == "Audio"
        )
        controls = (
            (
                80.0,
                "放置声源",
                "placement_mode",
                "sound",
                {
                    "secondary": not audio_placement_active,
                    "active": audio_placement_active,
                    "group": "Audio",
                },
            ),
            (
                68.0,
                "移除" if state.ui_bowl_has_food else "放粮",
                "toggle_bowl_food",
                "bowl",
                {
                    "secondary": not state.ui_bowl_has_food,
                    "blue_active": state.ui_bowl_has_food,
                },
            ),
            (
                92.0,
                "解除异常" if state.ui_abnormal_simulation_active else "异常模拟",
                "toggle_abnormal_simulation",
                "warning",
                {
                    "secondary": not state.ui_abnormal_simulation_active,
                    "danger_active": state.ui_abnormal_simulation_active,
                },
            ),
            (
                88.0,
                "删除人物" if state.ui_user_visible else "添加人物",
                "toggle_virtual_user",
                "user",
                {
                    "secondary": not state.ui_user_visible,
                    "blue_active": state.ui_user_visible,
                },
            ),
            (
                62.0,
                "视野开" if state.ui_show_fov else "视野关",
                "toggle_fov",
                "eye",
                {"secondary": True, "active": state.ui_show_fov},
            ),
        )
        gap = config.SPACE_SM
        full_width = sum(item[0] for item in controls) + gap * (len(controls) - 1)

        toolbar_right = config.WORLD_RIGHT - config.SPACE_LG
        header_right = config.WORLD_LEFT + config.SPACE_LG + config.scene_header_width()
        icon_only = toolbar_right - full_width < header_right + config.SPACE_MD
        widths = [28.0] * len(controls) if icon_only else [item[0] for item in controls]

        x = toolbar_right - sum(widths) - gap * (len(widths) - 1)
        y = config.WORLD_TOP - 33

        for width, (_, label, action, icon, style) in zip(widths, controls):
            self._button(
                x,
                y,
                width,
                24,
                "" if icon_only else label,
                action,
                icon=icon,
                icon_only=icon_only,
                tooltip=label,
                **style,
            )
            x += width + gap

    def _draw_current_behavior(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "behavior" in state.ui_collapsed_cards
        expanded = state.ui_behavior_context_expanded
        height = 42 if collapsed else (292 if expanded else 230)
        if height != 42:
            height += 50

        status_color = _action_status_color(state)
        self._card(x, top, width, height, "当前行为", "behavior", state, accent=status_color)

        _draw_badge(x + width - 34, top - 10, option_label(state.action_status), status_color, right=True)

        if collapsed:
            return top - height - config.CARD_GAP

        y = top - 42 - 11
        draw_text(
            _truncate(state.active_behavior or "等待行为", 36),
            x + config.CARD_PADDING,
            y,
            config.COLORS["text"],
            config.FONT_SIZE_KEY,
            bold=True,
            anchor_y="top",
        )

        y -= 38
        draw_text(
            _truncate(state.action_current_action or "-", 46),
            x + config.CARD_PADDING,
            y,
            config.COLORS["accent"],
            config.FONT_SIZE_MODULE,
            bold=True,
            anchor_y="top",
        )

        y -= 28
        bar_x = x + config.CARD_PADDING
        bar_w = width - config.CARD_PADDING * 2
        progress_text_width = 44
        track_w = max(80.0, bar_w - progress_text_width - 8)
        arcade.draw_lbwh_rectangle_filled(bar_x, y - 7, track_w, 7, config.COLORS["progress_track"])
        arcade.draw_lbwh_rectangle_filled(bar_x, y - 7, track_w * _clamp01(state.action_progress), 7, status_color)
        draw_text(f"{state.action_progress * 100:.0f}%", bar_x + bar_w, y - 2, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_x="right", anchor_y="center")

        y -= 13
        total = max(0, state.action_stage_total)
        if total:
            active = max(1, min(total, state.action_stage_index or 1))
            self._draw_step_strip(bar_x, y, bar_w, total, active, status_color)
        else:
            draw_text("等待 Stage 反馈", bar_x, y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")

        y -= 30
        visual = visual_for_action(state.action_current_action)
        rows = (
            ("阶段", f"{state.action_stage_index or '-'}/{state.action_stage_total or '-'} {state.action_stage_label}"),
            ("目标", state.action_target_label),
            ("2D展示", f"图片: {visual.pose}" if visual is not None else ("等待动作" if state.action_current_action in {"", "-"} else "仅文字")),
            ("可中断", _interrupt_text(state.action_safe_to_interrupt, state.action_status)),
        )
        self._draw_key_value_grid(x + config.CARD_PADDING, y, bar_w, rows)

        if expanded:
            detail_y = top - 224
            details = (
                f"目标 ID {state.action_goal_id or '-'}",
                f"按 goal_id 追踪 {len(state.action_executions)} 个执行",
                f"来源 {state.action_source}  优先级 {state.action_priority_level if state.action_priority_level is not None else '-'}",
                f"反馈 {state.action_message}",
                f"结果 {state.action_result}  原因 {state.action_reason}",
            )
            for line in details:
                draw_text(
                    _truncate(line, 58), x + config.CARD_PADDING, detail_y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top"
                )
                detail_y -= 15

        self._hit(
            "behavior_context",
            x,
            top - height,
            width,
            height - 31,
            expanded=not expanded,
            tooltip="显示或隐藏完整执行上下文",
        )
        return top - height - config.CARD_GAP

    def _draw_decision_trace(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "decision" in state.ui_collapsed_cards
        height = 42 if collapsed else 283
        self._card(x, top, width, height, "决策链路", "decision", state)
        if collapsed:
            return top - height - config.CARD_GAP

        params = state.action_params or {}
        trigger = _decision_trigger(state)
        chain = (
            ("触发事件", trigger),
            ("意图", state.action_intent),
            ("行为", state.active_behavior or "-"),
            ("解析结果", f"{state.action_level} / {state.action_interaction_mode}"),
            ("选中 ACT", state.action_current_action),
        )
        y = top - 42 - 11

        line_x = x + 18
        line_height = 35
        for index, (label, value) in enumerate(chain):
            color = config.COLORS["accent"] if index == len(chain) - 1 else config.COLORS["need"]
            arcade.draw_circle_filled(line_x, y - 10, 3, color)
            if index < len(chain) - 1:
                arcade.draw_line(line_x, y - 9, line_x, y - line_height, config.COLORS["border_strong"], 1)

            draw_text(label, line_x + 10, y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(_truncate(value, 34), line_x + 100, y, config.COLORS["text"], config.FONT_SIZE_AUX, bold=index == 4, anchor_y="top")
            y -= line_height

        metadata = _dict(params.get("metadata"))
        fallback = params.get("fallback_reason") or metadata.get("fallback_reason") or "-"
        requested = params.get("requested_behavior") or params.get("requested_behavior_name") or state.active_behavior or "-"
        resolved = params.get("resolved_behavior") or params.get("resolved_behavior_name") or state.active_behavior or "-"
        sub_priority = params.get("sub_priority") or params.get("subPriority") or "-"
        footer = f"优先级 {state.action_priority_level if state.action_priority_level is not None else '-'} / 子级 {sub_priority}  请求 {requested} -> {resolved}"

        y -= 8
        y += 10
        draw_text(_truncate(footer, 58), x + 12, y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")

        requested_mode = params.get("requested_interaction_mode") or params.get("interaction_mode") or "-"
        resolved_mode = params.get("resolved_interaction_mode") or state.action_interaction_mode or "-"

        y -= 22
        draw_text(_truncate(f"模式 {requested_mode} -> {resolved_mode}", 58), x + 12, y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")

        if fallback != "-":
            y -= 22
            draw_text(_truncate(f"回退原因：{fallback}", 58), x + 12, y, config.COLORS["warning"], config.FONT_SIZE_AUX, anchor_y="top")

        return top - height - config.CARD_GAP

    def _draw_need_card(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "need" in state.ui_collapsed_cards
        height = 42 if collapsed else 225
        self._card(x, top, width, height, "需求状态", "need", state)
        if collapsed:
            return top - height - config.CARD_GAP

        rows = _need_meter_rows(state)
        dominant = _dominant_need(rows)
        y = top - 42 - 22

        for row in rows:
            active = row["name"] == dominant or _is_alert_level(row.get("level"), row.get("event"))
            self._draw_meter_row(x + 12, y, width - 24, row, config.COLORS["need"], active)
            y -= config.STATUS_METER_ROW_HEIGHT
        return top - height - config.CARD_GAP

    def _draw_emotion_card(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "emotion" in state.ui_collapsed_cards
        height = 42 if collapsed else 242
        self._card(x, top, width, height, "情绪状态", "emotion", state)
        if collapsed:
            return top - height - config.CARD_GAP

        y = top - 42 - 11
        rows = _emotion_meter_rows(state)
        dominant = _dominant_emotion(state, rows)
        dominant_row = next((row for row in rows if row["name"] == dominant), rows[0] if rows else {})
        value = _round_value(dominant_row.get("value"))
        level = _dash(dominant_row.get("level"))
        event = _dash(dominant_row.get("event"))

        draw_text(option_label(dominant) if dominant else "-", x + 12, y, config.COLORS["text"], config.FONT_SIZE_KEY, bold=True, anchor_y="top")
        draw_text(f"{_dash(value)}  {level}", x + width - 12, y, config.COLORS["emotion"], config.FONT_SIZE_BODY, bold=True, anchor_x="right", anchor_y="top")
        draw_text(_truncate(event, 46), x + 12, y - 50, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")

        y -= 81

        for row in rows:
            if row["name"] == dominant:
                continue

            self._draw_meter_row(x + 12, y, width - 24, row, config.COLORS["emotion"], False, compact=True)

            y -= 20
        return top - height - config.CARD_GAP

    def _draw_perception_card(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "perception" in state.ui_collapsed_cards
        height = 42 if collapsed else 184
        self._card(x, top, width, height, "感知摘要", "perception", state)
        if collapsed:
            return top - height - config.CARD_GAP

        y = top - 42 - 11

        visual = state.latest_visual_event or {}
        visual_raw = _dict(visual.get("raw"))
        audio = state.latest_audio_event or {}
        target = state.active_target or {}
        confidence = target.get("confidence") or target.get("face_confidence") or "-"
        lines = [
            {
                "人类": visual.get('humans_count', 0),
                "动物": _collection_count(visual_raw.get('animals')),
                "物体": visual.get('tracked_objects_count', 0)
            },
            {
                "当前目标": _dash(target.get('identity') or target.get('track_id'))
            },
            {
                "置信度": _dash(_round_value(confidence)),
                "姿态": _dash(target.get('pose_state'))
            },
            {
                "声音": _dash(audio.get('event_type')),
                "说话人": _dash(audio.get('speaker_id'))
            },
            {
                "最近事件": _event_list(visual.get('events')),
                "语音识别": voice_command_display(audio)
            },
        ]

        line_y = y
        for index, line in enumerate(lines):
            ew = width // len(line.keys())
            color = config.COLORS["text"] if index in {1, 3} else config.COLORS["muted_text"]
            fontsize = config.FONT_SIZE_BODY if index == 1 else config.FONT_SIZE_AUX
            bold = index == 1
            for column_index, (title, value) in enumerate(line.items()):
                line_x = x + 12 + ew * column_index
                data = f"{title}: {value}"
                draw_text(
                    _truncate(data, 55),
                    line_x,
                    line_y,
                    color,
                    fontsize,
                    bold=bold,
                    anchor_y="top",
                )
            line_y -= 25


        return top - height - config.CARD_GAP

    def _card(
            self,
            x: float,
            top: float,
            width: float,
            height: float,
            title: str,
            card_id: str,
            state: SimState,
            accent: tuple[int, int, int] | None = None,
    ) -> None:
        bottom = top - height
        border = accent or config.COLORS["border"]
        arcade.draw_lbwh_rectangle_filled(x, bottom, width, height, config.COLORS["surface"])
        arcade.draw_lbwh_rectangle_outline(x, bottom, width, height, border, 1)
        if accent:
            arcade.draw_lbwh_rectangle_filled(x, bottom, 3, height, accent)

        collapsed = card_id in state.ui_collapsed_cards

        draw_text(title, x + 12, top - 5, config.COLORS["text"], config.FONT_SIZE_MODULE, bold=True, anchor_y="top")

        draw_text("+" if collapsed else "-", x + width - 14, top - 18, config.COLORS["muted_text"], config.FONT_SIZE_MODULE, anchor_x="center", anchor_y="center")

        line_y = top - 42
        line_x = x + width - 10
        arcade.draw_line(start_x=x + 10, start_y=line_y, end_x=line_x, end_y=line_y, color=border, line_width=1)

        self._hit("toggle_card", x, top - 32, width, 32, card_id=card_id, tooltip=f"{'展开' if collapsed else '折叠'}{title}")

    def _draw_step_strip(self, x: float, top: float, width: float, total: int, active: int, color: tuple[int, int, int]) -> None:
        gap = 4
        total = min(total, 12)
        segment_w = max(12.0, (width - gap * (total - 1)) / total)
        for index in range(total):
            sx = x + index * (segment_w + gap)
            complete = index + 1 < active
            current = index + 1 == active
            fill = _mix(color, config.COLORS["surface"], 0.25 if current else 0.55) if index + 1 <= active else \
            config.COLORS["meter_track"]
            border = color if index + 1 <= active else config.COLORS["border"]
            arcade.draw_lbwh_rectangle_filled(sx, top - 14, segment_w, 14, fill)
            arcade.draw_lbwh_rectangle_outline(sx, top - 14, segment_w, 14, border, 1)
            draw_text(str(index + 1), sx + segment_w / 2, top + 4, config.COLORS["text"] if current or complete else config.COLORS["muted_text"], config.FONT_SIZE_AUX, bold=current, anchor_x="center", anchor_y="top")

    def _draw_key_value_grid(self, x: float, top: float, width: float, rows: Iterable[tuple[str, Any]]) -> None:
        rows = tuple(rows)
        column_gap = 16
        cell_width = (width - column_gap) / 2
        value_chars = max(12, int((cell_width - 4) / 9.0))

        divider_x = x + cell_width + column_gap / 2
        divider_height = config.STATUS_GRID_ROW_HEIGHT + config.STATUS_GRID_VALUE_OFFSET + 20
        arcade.draw_line(divider_x, top + 1, divider_x, top - divider_height, config.COLORS["border"], 1)

        for index, (label, value) in enumerate(rows):
            col = index % 2
            row = index // 2
            cell_x = x + col * (cell_width + column_gap)
            cell_y = top - row * config.STATUS_GRID_ROW_HEIGHT - 11 * row
            draw_text(label, cell_x, cell_y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(
                _truncate(_dash(value), value_chars),
                cell_x + 6,
                cell_y - config.STATUS_GRID_VALUE_OFFSET - 4,
                config.COLORS["text"],
                config.FONT_SIZE_BODY,
                bold=label in {"阶段", "目标"},
                anchor_y="top",
            )

    def _draw_meter_row(self,
            x: float,
            y: float,
            width: float,
            row: dict[str, Any],
            base_color: tuple[int, int, int],
            active: bool,
            compact: bool = False,
    ) -> None:
        name = str(row.get("name") or "-")
        value = row.get("value")
        level = _dash(row.get("level"))
        event = _dash(row.get("event"))
        fraction = _value_fraction(value)

        color = _meter_color(value, level, event, base_color, active)
        if active:
            arcade.draw_lbwh_rectangle_filled(x - 5, y - 14, width + 10, 20, _mix(color, config.COLORS["surface"], 0.84))
            arcade.draw_lbwh_rectangle_filled(x - 5, y - 14, 2, 20, color)

        draw_text(option_label(name), x, y + 6.5, config.COLORS["text"] if active else config.COLORS["muted_text"], config.FONT_SIZE_AUX, bold=active, anchor_y="top")

        bar_x = x + 68
        bar_y = y - 8
        bar_h = 5 if compact else 7
        bar_w = max(64, min(112 if not compact else 94, width * 0.31))
        arcade.draw_lbwh_rectangle_filled(bar_x, bar_y, bar_w, bar_h, config.COLORS["meter_track"])
        if fraction is not None:
            arcade.draw_lbwh_rectangle_filled(bar_x, bar_y, bar_w * fraction, bar_h, color)

        value_y = y + 6.5
        value_x = bar_x + bar_w + 7
        draw_text(_dash(_round_value(value)), value_x, value_y, config.COLORS["text"], config.FONT_SIZE_AUX, anchor_y="top")

        meta = level if compact else f"{level} {event}"
        meta_x = value_x + 34
        meta_y = value_y
        available_chars = max(5, int((x + width - meta_x - 8) / 6))
        draw_text(_truncate(meta, min(18 if compact else 24, available_chars)), meta_x, meta_y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")

    def _draw_event_stream(self, state: SimState) -> None:
        top = config.BOTTOM_LOG_HEIGHT
        self._hit("log_resize", 0, top - 5, config.WINDOW_WIDTH, 10, tooltip="拖动调整事件流高度")
        arcade.draw_line(config.WINDOW_WIDTH / 2 - 28, top - 4, config.WINDOW_WIDTH / 2 + 28, top - 4,
                         config.COLORS["border_strong"], 2)

        toolbar_slots = self._sync_event_toolbar_layout(top)
        title_slot = toolbar_slots["title"]
        draw_text(
            "事件流",
            title_slot.left,
            title_slot.center_y,
            config.COLORS["text"],
            config.FONT_SIZE_MODULE,
            bold=True,
            anchor_x="left",
            anchor_y="center",
        )
        for source in LOG_SOURCES:
            active = source in state.ui_log_filters
            source_slot = toolbar_slots[f"source:{source}"]
            self._chip(
                source_slot.left,
                source_slot.top,
                source_slot.width,
                source,
                active,
                "toggle_log_filter",
                source=source,
            )

        search_slot = toolbar_slots["search"]
        self._search_input(
            state,
            search_slot.left,
            search_slot.bottom,
            search_slot.width,
        )

        button_specs = (
            (
                "pause",
                "继续" if state.ui_log_paused else "暂停",
                "toggle_log_pause",
                state.ui_log_paused,
            ),
            ("clear", "清空", "clear_log", False),
            ("auto", "自动", "toggle_log_auto", state.ui_log_auto_scroll),
        )
        for slot_name, label, action, active in button_specs:
            button_slot = toolbar_slots[slot_name]
            self._small_button(
                button_slot.left,
                button_slot.bottom,
                button_slot.width,
                button_slot.height,
                label,
                action,
                active=active,
            )

        header_top = top - 48
        columns = _log_columns(config.WINDOW_WIDTH)
        arcade.draw_lbwh_rectangle_filled(12, header_top - 20, config.WINDOW_WIDTH - 24, 20,
                                          config.COLORS["table_header"])
        for label, key in (("时间", "time"), ("来源", "source"), ("事件", "event"), ("等级 / 状态", "level"),
                           ("摘要", "summary")):
            draw_text(label, columns[key], header_top - 4, config.COLORS["subtle_text"], config.FONT_SIZE_AUX,
                      bold=True, anchor_y="top")

        records = _filtered_event_records(state)
        available_h = max(22.0, header_top - 24)
        row_h = 22
        visible_count = max(1, int(available_h // row_h))
        start = min(max(0, state.ui_log_scroll), max(0, len(records) - visible_count))
        if state.ui_log_auto_scroll:
            start = 0
            state.ui_log_scroll = 0
        visible = records[start: start + visible_count]
        row_top = header_top - 24
        for index, record in enumerate(visible):
            row_y = row_top - index * row_h
            selected = record.get("id") == state.ui_selected_event_id
            if selected:
                arcade.draw_lbwh_rectangle_filled(12, row_y - row_h + 2, config.WINDOW_WIDTH - 24, row_h - 1,
                                                  config.COLORS["surface_hover"])
            elif index % 2:
                arcade.draw_lbwh_rectangle_filled(12, row_y - row_h + 2, config.WINDOW_WIDTH - 24, row_h - 1,
                                                  config.COLORS["table_alt"])
            timestamp = time.strftime("%H:%M:%S", time.localtime(float(record.get("at") or 0)))
            source = str(record.get("source") or "SYS")
            count = int(record.get("count") or 1)
            event_name = str(record.get("event") or "-")
            summary = str(record.get("summary") or "-")
            if count > 1:
                summary = f"{summary}  x {count}"
            draw_text(timestamp, columns["time"], row_y - 4, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
            _draw_source_tag(columns["source"], row_y - 4, source)
            draw_text(_truncate(event_name, 24), columns["event"], row_y - 4, config.COLORS["text"], config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(_truncate(str(record.get("level") or "INFO"), 14), columns["level"], row_y - 4, _event_level_color(str(record.get("level") or "")), config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(_truncate(summary, max(20, int((config.WINDOW_WIDTH - columns["summary"] - 18) / 6))), columns["summary"], row_y - 4, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
            self._hit("select_event", 12, row_y - row_h + 2, config.WINDOW_WIDTH - 24, row_h, event_id=record.get("id"))

        if not records:
            draw_text("等待符合筛选条件的 ROS2 事件", 18, row_top - 8, config.COLORS["muted_text"],
                      config.FONT_SIZE_BODY, anchor_y="top")

    def _sync_event_toolbar_layout(self, top: float | int) -> dict[str, arcade.gui.UIWidget]:
        """Lay out the event toolbar as one native horizontal row."""

        if self._event_toolbar_layout is None:
            layout = arcade.gui.UIBoxLayout(
                vertical=False,
                align="center",
                space_between=config.SPACE_XS,
                size_hint=None,
            )
            slots: dict[str, arcade.gui.UIWidget] = {
                "title": arcade.gui.UISpace(
                    width=118,
                    height=24,
                    size_hint=None,
                ),
            }
            layout.add(slots["title"])

            for source in LOG_SOURCES:
                source_slot = arcade.gui.UISpace(
                    width=47 if len(source) <= 4 else 57,
                    height=23,
                    size_hint=None,
                )
                slots[f"source:{source}"] = source_slot
                layout.add(source_slot)

            layout.add(arcade.gui.UISpace(
                width=config.SPACE_SM,
                height=24,
                size_hint=(1, None),
                size_hint_min=(config.SPACE_SM, None),
            ))

            for slot_name, width in (
                    ("search", 190),
                    ("pause", 58),
                    ("clear", 58),
                    ("auto", 58),
            ):
                slot = arcade.gui.UISpace(
                    width=width,
                    height=24,
                    size_hint=None,
                )
                slots[slot_name] = slot
                layout.add(slot)

            self._event_toolbar_layout = layout
            self._event_toolbar_slots = slots

        layout = self._event_toolbar_layout
        layout.left = 14
        layout.bottom = top - 48
        layout.width = config.WINDOW_WIDTH - 28
        layout.height = 48
        layout.do_layout()
        return self._event_toolbar_slots

    def _draw_object_detail(self, state: SimState) -> None:
        if not state.ui_selected_object or state.ui_selected_event_id is not None:
            return

        details = _selected_object_details(state, state.ui_selected_object)
        if not details:
            return

        height = 126
        width = min(310.0, config.WORLD_WIDTH - 30)

        x = config.WORLD_RIGHT - width - 14
        top = config.WORLD_TOP - 42
        arcade.draw_lbwh_rectangle_filled(x, top - height, width, height, config.COLORS["detail_background"])
        arcade.draw_lbwh_rectangle_outline(x, top - height, width, height, config.COLORS["accent"], 1)
        arcade.draw_line(x + 5, top - 38, x + width - 5, top - 38, config.COLORS["accent"], 1)

        draw_text("对象详情", x + 12, top - 4, config.COLORS["text"], config.FONT_SIZE_MODULE, bold=True, anchor_y="top")
        self._icon_button(x + width - 34, top - 30, 22, 22, "x", "close_object_detail", "关闭")
        y = top - 38
        for line in details[:5]:
            draw_text(_truncate(line, 45), x + 12, y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
            y -= 15

    def _draw_event_detail(self, state: SimState) -> None:
        if state.ui_payload_preview_expanded:
            return

        record = _selected_event_record(state)
        if record is None:
            return

        x, top, width, height = _event_detail_bounds()
        arcade.draw_lbwh_rectangle_filled(x, top - height, width, height, config.COLORS["table_header"])
        arcade.draw_lbwh_rectangle_outline(x, top - height, width, height, config.COLORS["accent"], 1)
        draw_text(
            f"{record.get('source')} / {record.get('event')}",
            x + 14,
            top - 12,
            config.COLORS["text"],
            config.FONT_SIZE_MODULE,
            bold=True,
            anchor_y="top",
        )
        topic = record.get("topic") or "-"
        draw_text(_truncate(f"topic: {topic}", 80), x + 14, top - 38, config.COLORS["accent"], config.FONT_SIZE_AUX,
                  anchor_y="top")

    def _sync_event_payload_previewer(self, state: SimState) -> None:
        """Keep the native JSON preview aligned with the custom detail shell."""
        record = _selected_event_record(state)
        if record is None or state.ui_payload_preview_expanded:
            self._remove_event_payload_previewer()
            return

        x, top, width, height = _event_detail_bounds()
        bounds = BBox(x + 14, top - height + 12, width - 28, height - 78)
        payload = record.get("payload") or {}
        if self._event_payload_previewer is None:
            self._event_payload_previewer = AJsonPreviewer(bounds, payload)
        else:
            if self._event_payload_previewer.bbox != bounds:
                self._event_payload_previewer.bbox = bounds
            self._event_payload_previewer.set_value(payload)

        if not self._widget_is_managed(self._event_payload_previewer):
            self._manager.add(
                self._event_payload_previewer,
                layer=arcade.gui.UIManager.OVERLAY_LAYER,
            )

    def _remove_event_payload_previewer(self) -> None:
        if self._event_payload_previewer is None:
            return

        if self._widget_is_managed(self._event_payload_previewer):
            self._manager.remove(self._event_payload_previewer)
        self._event_payload_previewer = None

    def _sync_event_detail_buttons(self, state: SimState) -> None:
        """Keep native detail actions aligned with the detail shell."""
        record = _selected_event_record(state)
        if record is None or state.ui_payload_preview_expanded:
            self._remove_event_detail_buttons()
            return

        x, top, width, _height = _event_detail_bounds()
        button_height = 26.0
        button_y = top - button_height - 13.0
        close_width = 58.0
        copy_width = 92.0
        close_x = x + width - 14.0 - close_width
        copy_bounds = BBox(
            close_x - config.SPACE_SM - copy_width,
            button_y,
            copy_width,
            button_height,
        )
        close_bounds = BBox(close_x, button_y, close_width, button_height)

        if self._event_detail_buttons is None:
            copy_button = AButton(copy_bounds, "复制到剪切板")
            close_button = AButton(close_bounds, "关闭")

            @copy_button.event("on_click")
            def handle_copy(_event: Any) -> None:
                if self._event_detail_action_handler is not None:
                    self._event_detail_action_handler("copy_event_payload")

            @close_button.event("on_click")
            def handle_close(_event: Any) -> None:
                if self._event_detail_action_handler is not None:
                    self._event_detail_action_handler("close_event_detail")

            self._event_detail_buttons = copy_button, close_button
        else:
            copy_button, close_button = self._event_detail_buttons
            if copy_button.bbox != copy_bounds:
                copy_button.bbox = copy_bounds
            if close_button.bbox != close_bounds:
                close_button.bbox = close_bounds

        for button in self._event_detail_buttons:
            if not self._widget_is_managed(button):
                self._manager.add(
                    button,
                    layer=arcade.gui.UIManager.OVERLAY_LAYER,
                )

    def _remove_event_detail_buttons(self) -> None:
        if self._event_detail_buttons is None:
            return

        for button in self._event_detail_buttons:
            if self._widget_is_managed(button):
                self._manager.remove(button)
        self._event_detail_buttons = None

    def _widget_is_managed(
            self,
            widget: arcade.gui.UIWidget,
            *,
            layer: int = arcade.gui.UIManager.OVERLAY_LAYER,
    ) -> bool:
        """Return whether a widget is currently attached to a manager layer."""

        return any(
            managed_widget is widget
            for managed_widget in self._manager.walk_widgets(
                layer=layer,
            )
        )

    def _sync_confirmation(self, state: SimState) -> None:
        """Synchronize the pending action with the localized message box."""
        pending = state.ui_pending_confirmation
        if not pending:
            self._remove_confirmation_box()
            return

        is_alert = pending.get("kind") == "alert"
        title = str(
            pending.get("title")
            or ("提示" if is_alert else "确认调试注入")
        )
        message = str(
            pending.get("message")
            or (
                "操作暂不可用"
                if is_alert
                else "此操作可能触发高优先级行为。"
            )
        )
        if not is_alert:
            message = f"{message}"
        buttons = ("知道了",) if is_alert else ("取消", "确认发送")
        width = min(560.0, config.WINDOW_WIDTH - 80.0)
        height = 150.0 if is_alert else 170.0
        signature = (title, message, buttons, width, height)

        if self._confirmation_signature != signature:
            self._remove_confirmation_box()
            message_box = AMessageBox(
                width=width,
                height=height,
                message_text=message,
                title=title,
                buttons=buttons,
            )

            @message_box.event("on_action")
            def handle_action(event: Any) -> None:
                action = (
                    "confirm_action"
                    if not is_alert and event.action == "确认发送"
                    else "cancel_confirmation"
                )
                if self._confirmation_action_handler is not None:
                    self._confirmation_action_handler(action)

            self._confirmation_box = message_box
            self._confirmation_signature = signature

        if self._confirmation_box is not None and not self._widget_is_managed(
                self._confirmation_box,
        ):
            self._manager.add(
                self._confirmation_box,
                layer=arcade.gui.UIManager.OVERLAY_LAYER,
            )

    def _remove_confirmation_box(self) -> None:
        if self._confirmation_box is not None and self._widget_is_managed(
                self._confirmation_box,
        ):
            self._manager.remove(self._confirmation_box)
        self._confirmation_box = None
        self._confirmation_signature = None

    def _draw_tooltip(self) -> None:
        if not self._hovered or not self._hovered.get("tooltip"):
            return

        text = str(self._hovered["tooltip"])
        text_width, _ = measure_text(
            text,
            font_size=config.FONT_SIZE_AUX,
        )
        maximum_width = max(
            140.0,
            min(520.0, config.WINDOW_WIDTH - 16.0),
        )
        minimum_width = min(220.0, maximum_width)
        width = min(maximum_width, max(minimum_width, text_width + 18.0))
        content_width = max(1, int(width - 18.0))
        _, text_height = measure_text(
            text,
            font_size=config.FONT_SIZE_AUX,
            width=content_width,
            multiline=True,
        )
        height = max(25.0, text_height + 10.0)
        x = max(
            8.0,
            min(config.WINDOW_WIDTH - width - 8.0, self._hovered["x"]),
        )
        y = max(
            config.BOTTOM_LOG_HEIGHT + 8.0,
            self._hovered["y"] - height - 7.0,
        )
        arcade.draw_lbwh_rectangle_filled(
            x,
            y,
            width,
            height,
            config.COLORS["tooltip_background"],
        )
        arcade.draw_lbwh_rectangle_outline(
            x,
            y,
            width,
            height,
            config.COLORS["border_strong"],
            1,
        )
        draw_text(
            text,
            x + 9.0,
            y + height - 5.0,
            config.COLORS["text"],
            config.FONT_SIZE_AUX,
            width=content_width,
            multiline=True,
            anchor_y="top",
        )

    def _search_input(self, state: SimState, x: float, y: float, width: float) -> None:
        placeholder = "搜索事件"
        bounds = BBox(x, y, width, 24.0)
        if self._event_search_input is None:
            widget = arcade.gui.UIInputText(
                x=bounds.x,
                y=bounds.y,
                width=bounds.width,
                height=bounds.height,
                text=state.ui_log_search or placeholder,
                font_name=config.FONT_NAMES,
                font_size=config.FONT_SIZE_AUX,
                text_color=_rgba(config.COLORS["text"]),
                caret_color=_rgba(config.COLORS["accent"]),
                border_color=_rgba(config.COLORS["border"]),
                border_width=1,
                size_hint=None,
            )
            widget.with_background(color=_rgba(config.COLORS["surface_raised"]))

            @widget.event("on_click")
            def handle_click(_event: Any) -> None:
                if state.ui_log_search or widget.text != placeholder:
                    return
                self._set_event_search_text(widget, "")

            @widget.event("on_change")
            def handle_change(event: Any) -> None:
                if self._syncing_event_search:
                    return
                value = str(event.new_value)[:80]
                if value != event.new_value:
                    self._set_event_search_text(widget, value)
                state.ui_log_search = value

            self._event_search_input = widget

        widget = self._event_search_input
        _set_widget_bounds(widget, bounds)
        display_text = (
            placeholder
            if not state.ui_log_search and not widget.active
            else state.ui_log_search
        )
        if widget.text != display_text:
            self._set_event_search_text(widget, display_text)

        if not self._widget_is_managed(
                widget,
                layer=arcade.gui.UIManager.DEFAULT_LAYER,
        ):
            self._manager.add(widget)

    def _set_event_search_text(
            self,
            widget: arcade.gui.UIInputText,
            value: str,
    ) -> None:
        """Synchronize native search text without feeding its change event back."""

        self._syncing_event_search = True
        try:
            widget.text = value
        finally:
            self._syncing_event_search = False

    def _button(
            self,
            x: float,
            y: float,
            width: float,
            height: float,
            label: str,
            action: str,
            primary: bool = False,
            secondary: bool = False,
            active: bool = False,
            blue_active: bool = False,
            danger_active: bool = False,
            icon: str | None = None,
            icon_only: bool = False,
            **data: Any,
    ) -> None:
        if danger_active:
            fill = config.COLORS["button_active_red"]
            border = config.COLORS["button_active_red_border"]
        elif blue_active:
            fill = config.COLORS["button_active_blue"]
            border = config.COLORS["button_active_blue_border"]
        elif primary:
            fill = config.COLORS["accent_dim"]
            border = config.COLORS["accent"]
        elif active:
            fill = config.COLORS["surface_hover"]
            border = config.COLORS["accent"]
        else:
            fill = config.COLORS["surface_raised"] if secondary else config.COLORS["surface"]
            border = config.COLORS["border_strong"] if secondary else config.COLORS["border"]
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, fill)
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, border, 1)
        if icon:
            _draw_toolbar_icon(
                icon,
                x + width / 2 if icon_only else x + 11,
                y + height / 2,
                config.COLORS["text"],
            )
        if not icon_only:
            draw_text(
                label,
                x + width / 2 + (11 if icon else 0),
                y + height / 2,
                config.COLORS["text"],
                config.FONT_SIZE_BODY,
                bold=primary or blue_active or danger_active,
                anchor_x="center",
                anchor_y="center",
            )
        self._hit(action, x, y, width, height, **data)

    def _small_button(
            self,
            x: float,
            y: float,
            width: float,
            height: float,
            label: str,
            action: str,
            active: bool = False,
            icon: str | None = None,
    ) -> None:
        self._button(
            x,
            y,
            width,
            height,
            label,
            action,
            secondary=True,
            active=active,
            icon=icon,
        )

    def _icon_button(self, x: float, y: float, width: float, height: float, label: str, action: str, tooltip: str,
                     **data: Any) -> None:
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["surface_raised"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, config.COLORS["border"], 1)
        draw_text(
            label,
            x + width / 2,
            y + height / 2,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            bold=bool(data.get("active")),
            anchor_x="center",
            anchor_y="center",
        )
        self._hit(action, x, y, width, height, tooltip=tooltip, **data)

    def _chip(self, x: float, top: float, width: float, label: str, active: bool, action: str, **data: Any) -> None:
        height = 23
        y = top - height
        fill = config.COLORS["surface_hover"] if active else config.COLORS["chip_idle"]
        border = config.COLORS["accent_dim"] if active else config.COLORS["border"]
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, fill)
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, border, 1)
        draw_text(
            label,
            x + width / 2,
            y + height / 2,
            config.COLORS["text"] if active else config.COLORS["subtle_text"],
            config.FONT_SIZE_AUX,
            anchor_x="center",
            anchor_y="center",
        )
        self._hit(action, x, y, width, height, **data)

    def _hit(self, action: str, x: float, y: float, w: float, h: float, **data: Any) -> None:
        self._hits.append({"action": action, "x": x, "y": y, "w": w, "h": h, **data})


def option_label(value: str) -> str:
    return OPTION_LABELS.get(value, value)


def _compact_topic_status(status: str) -> str:
    return {
        "Waiting": "等待",
        "Offline": "错误",
        "Stale": "延迟",
        "Active": "活动",
        "Live": "正常",
    }.get(status, status)


def _set_widget_bounds(widget: arcade.gui.UIWidget, bounds: BBox) -> None:
    widget.width = bounds.width
    widget.height = bounds.height
    widget.left = bounds.x
    widget.bottom = bounds.y


def _rgba(color: tuple[int, ...]) -> tuple[int, int, int, int]:
    alpha = color[3] if len(color) >= 4 else 255
    return int(color[0]), int(color[1]), int(color[2]), int(alpha)


def _draw_toolbar_icon(
        icon: str,
        center_x: float,
        center_y: float,
        color: tuple[int, int, int],
) -> None:
    if icon == "sound":
        arcade.draw_circle_filled(center_x - 4, center_y, 1.8, color)
        arcade.draw_arc_outline(center_x - 4, center_y, 8, 10, color, -52, 52, 1)
        arcade.draw_arc_outline(center_x - 4, center_y, 14, 16, color, -48, 48, 1)
        return
    if icon == "bowl":
        arcade.draw_line(center_x - 6, center_y + 3, center_x + 6, center_y + 3, color, 1)
        arcade.draw_line(center_x - 6, center_y + 3, center_x - 3, center_y - 4, color, 1)
        arcade.draw_line(center_x + 6, center_y + 3, center_x + 3, center_y - 4, color, 1)
        arcade.draw_line(center_x - 3, center_y - 4, center_x + 3, center_y - 4, color, 1)
        return
    if icon == "warning":
        arcade.draw_triangle_outline(
            center_x,
            center_y + 7,
            center_x - 7,
            center_y - 6,
            center_x + 7,
            center_y - 6,
            color,
            1,
        )
        arcade.draw_line(center_x, center_y + 3, center_x, center_y - 1, color, 1)
        arcade.draw_circle_filled(center_x, center_y - 3.5, 1, color)
        return
    if icon == "user":
        arcade.draw_circle_outline(center_x, center_y + 4, 3, color, 1)
        arcade.draw_line(center_x, center_y + 1, center_x, center_y - 6, color, 1)
        arcade.draw_line(center_x - 5, center_y - 1, center_x + 5, center_y - 1, color, 1)
        return
    if icon == "eye":
        arcade.draw_ellipse_outline(center_x, center_y, 14, 8, color, 1)
        arcade.draw_circle_filled(center_x, center_y, 2, color)


def event_type_field(group: str) -> str | None:
    return {
        "Audio": "audio_event_type",
        "Vision": "vision_events",
        "Result": "result_type",
    }.get(group)


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
        "Result": (
            ("result_action_type", "动作类型", "input"),
            ("result_demand_type", "需求类型", "input"),
            ("result_metadata", "Metadata", "input"),
        ),
    }
    return fields.get(group, ())


def _endpoint_status(state: SimState, topics: tuple[str, ...], label: str, now: float) -> tuple[str, str, str]:
    stats_items = [state.topic_stats.get(topic) for topic in topics]
    stats_items = [stats for stats in stats_items if stats is not None]
    latest = max((stats.last_received_at or 0.0 for stats in stats_items), default=0.0)
    count = sum(stats.count for stats in stats_items)
    external_count = sum(
        state.ros_external_publisher_counts.get(topic, 0)
        for topic in topics
    )
    publisher_nodes = sorted(
        {
            (
                f"{endpoint.get('node_namespace') or '/'}"
                f"{endpoint.get('node_name') or '?'}"
            ).replace("//", "/")
            for topic in topics
            for endpoint in state.ros_external_publishers.get(topic, [])
            if isinstance(endpoint, dict)
        }
    )
    if external_count <= 0:
        return "waiting", "Waiting", f"未发现外部 Publisher | {', '.join(topics)}"
    if not latest or not count:
        detail = (
            f"已发现 {external_count} 个外部 Publisher"
            f" ({', '.join(publisher_nodes) or '-'})，尚未收到消息"
        )
        return "connected", "Connected", detail
    age = now - latest
    rate = max((_topic_rate(stats, now) for stats in stats_items), default=0.0)
    rate_text = (
        ">999 Hz"
        if rate >= 1000
        else f"{rate:.0f} Hz"
        if rate >= 1
        else f"{rate:.1f} Hz"
        if rate > 0
        else "Live"
    )
    detail = f"{', '.join(topics)} | count={count} | age={age:.1f}s | {rate_text}"
    if age <= 2.5:
        return "live", rate_text, detail
    if age <= 10.0:
        return "stale", "Stale", detail
    return "error", "Offline", detail


def _virtual_time_display(state: SimState) -> tuple[str, tuple[int, int, int]]:
    payload = state.simulation_time_state or {}
    context = _dict(payload.get("timeContext"))
    raw_datetime = str(context.get("virtualDateTime") or "").strip()
    if not raw_datetime:
        if state.ros_time_online:
            return "虚拟时间  已连接，等待数据", config.COLORS["warning"]
        return "虚拟时间  离线", config.COLORS["muted_text"]

    try:
        display_datetime = datetime.fromisoformat(raw_datetime).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        display_datetime = raw_datetime.replace("T", " ")

    base_scale = context.get("scale")
    effective_scale = context.get("effectiveScale")
    shown_scale = effective_scale if effective_scale is not None else base_scale
    scale_text = f"  ×{_dash(shown_scale)}" if shown_scale is not None else ""
    base_value = _to_float(base_scale)
    effective_value = _to_float(effective_scale)
    accelerated = (
            effective_value is not None
            and base_value is not None
            and effective_value != base_value
    )
    color = config.COLORS["warning"] if accelerated else config.COLORS["success"]
    return f"虚拟时间  {display_datetime}{scale_text}", color


def _topic_rate(stats: Any, now: float, window_sec: float = 5.0) -> float:
    if stats is None:
        return 0.0
    timestamps = [value for value in stats.recent_received_at if now - value <= window_sec]
    if len(timestamps) < 2:
        return 0.0
    duration = max(0.001, timestamps[-1] - timestamps[0])
    return (len(timestamps) - 1) / duration


def _health_color(status: str) -> tuple[int, int, int] | None | Any:
    return {
        "live": config.COLORS["success"],
        "connected": config.COLORS["warning"],
        "stale": config.COLORS["warning"],
        "error": config.COLORS["error"],
    }.get(status, config.COLORS["waiting"])


def _action_status_color(state: SimState) -> tuple[int, int, int]:
    status = str(state.action_status or "").lower()
    if status in {"running", "accepted"}:
        return config.COLORS["accent"]
    if status in {"success", "succeeded"}:
        return config.COLORS["success"]
    if status in {"failed", "failure", "timeout", "canceled", "cancelled", "interrupted"}:
        return config.COLORS["error"]
    return config.COLORS["waiting"]


def _need_meter_rows(state: SimState) -> list[dict[str, Any]]:
    data = state.internal_need_state or {}
    demands = _dict(data.get("demands"))
    level_events = _dict(data.get("levelEvents"))
    signal = _fresh_signal(state.internal_need_signal_event)
    rows = []
    for name in config.DEMAND_NAMES:
        source = demands.get(name)
        event = level_events.get(name)
        if signal and signal.get("demand") == name:
            source = {"value": signal.get("value"), "level": signal.get("level"),
                      "levelEvent": signal.get("event_type")}
        rows.append(_meter_row(name, source, event))
    return rows


def _emotion_meter_rows(state: SimState) -> list[dict[str, Any]]:
    data = state.emotion_state or {}
    emotions = _dict(data.get("emotions"))
    level_events = _dict(data.get("levelEvents"))
    signal = _fresh_signal(state.emotion_signal_event)
    rows = []
    for name in config.EMOTION_NAMES:
        source = emotions.get(name)
        event = level_events.get(name)
        if signal and signal.get("emotion") == name:
            source = {"value": signal.get("value"),
                      "level": signal.get("level") or signal.get("zone") or signal.get("range"),
                      "levelEvent": signal.get("event_type")}
        rows.append(_meter_row(name, source, event))
    return rows


def _meter_row(name: str, source: Any, event: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return {"name": name, "value": source.get("value"), "level": source.get("level"),
                "event": source.get("levelEvent") or event}
    return {"name": name, "value": source, "level": None, "event": event}


def _dominant_need(rows: list[dict[str, Any]]) -> str:
    alerts = [row for row in rows if _is_alert_level(row.get("level"), row.get("event"))]
    candidates = alerts or rows
    if not candidates:
        return "-"

    def score(row: dict[str, Any]) -> float:
        value = _to_float(row.get("value"))
        if value is None:
            return -1.0
        return 100.0 - value if row.get("name") == "Energy" else value

    return str(max(candidates, key=score).get("name") or "-")


def _dominant_emotion(state: SimState, rows: list[dict[str, Any]]) -> str:
    data = state.emotion_state or {}
    explicit = data.get("dominantEmotion") or data.get("dominant_emotion")
    if explicit:
        return str(explicit)
    if not rows:
        return "-"
    return str(max(rows, key=lambda row: _to_float(row.get("value")) or -1).get("name") or "-")


def _is_alert_level(level: Any, event: Any) -> bool:
    text = f"{level or ''} {event or ''}".upper()
    return any(token in text for token in ("TRIGGER", "OVERFLOW", "CRITICAL"))


def _meter_color(value: Any, level: Any, event: Any, base: tuple[int, int, int], active: bool) -> tuple[int, int, int]:
    text = f"{level or ''} {event or ''}".upper()
    if "OVERFLOW" in text or "CRITICAL" in text:
        return config.COLORS["error"]
    if "TRIGGER" in text:
        return config.COLORS["warning"]
    return base if active else _mix(base, config.COLORS["surface"], 0.48)


def _decision_trigger(state: SimState) -> str:
    if state.action_trigger_reason and state.action_trigger_reason != "-":
        return state.action_trigger_reason
    for signal in (state.emotion_signal_event, state.internal_need_signal_event):
        if signal and signal.get("event_type"):
            return str(signal["event_type"])
    audio = state.latest_audio_event or {}
    visual = state.latest_visual_event or {}
    return str(audio.get("event_type") or _event_list(visual.get("events")) or "-")


def _filtered_event_records(state: SimState) -> list[dict[str, Any]]:
    source = state.ui_log_pause_snapshot if state.ui_log_paused else list(state.event_records)
    query = state.ui_log_search.strip().lower()
    result = []
    for record in reversed(source):
        if record.get("source") not in state.ui_log_filters:
            continue
        if query:
            haystack = f"{record.get('source')} {record.get('event')} {record.get('summary')} {record.get('topic')}".lower()
            if query not in haystack:
                continue
        result.append(record)
    return result


def _log_columns(width: float) -> dict[str, float]:
    return {
        "time": 20.0,
        "source": 96.0,
        "event": 166.0,
        "level": min(420.0, width * 0.31),
        "summary": min(555.0, width * 0.41),
    }


def _event_level_color(level: str) -> tuple[int, int, int]:
    level = level.upper()
    if level == "ERROR":
        return config.COLORS["error"]
    if level == "WARN":
        return config.COLORS["warning"]
    if level == "OK":
        return config.COLORS["success"]
    return config.COLORS["muted_text"]


def _draw_source_tag(x: float, top: float, source: str) -> None:
    color = {
        "VIS": config.COLORS["visual"],
        "AUD": config.COLORS["audio"],
        "NEED": config.COLORS["need"],
        "EMO": config.COLORS["emotion"],
        "EXEC": config.COLORS["accent"],
        "RESULT": config.COLORS["success"],
    }.get(source, config.COLORS["waiting"])
    width = 42 if len(source) <= 4 else 53
    arcade.draw_lbwh_rectangle_filled(x, top - 12, width, 14, _mix(color, config.COLORS["log_background"], 0.64))
    draw_text(source, x + width / 2, top, color, config.FONT_SIZE_AUX, bold=True, anchor_x="center", anchor_y="top")


def _draw_badge(x: float, top: float, text: str, color: tuple[int, int, int], right: bool = False) -> None:
    width = _badge_width(text)
    left = x - width if right else x
    arcade.draw_lbwh_rectangle_filled(left, top - 18, width, 20, _mix(color, config.COLORS["surface"], 0.66))
    arcade.draw_lbwh_rectangle_outline(left, top - 18, width, 20, color, 1)
    draw_text(_truncate(text, 20), left + width / 2, top + 3, color, config.FONT_SIZE_AUX, bold=True, anchor_x="center", anchor_y="top")


def _badge_width(text: str) -> float:
    return min(132.0, max(54.0, len(str(text)) * 6.0 + 16))


def _selected_event_record(state: SimState) -> dict[str, Any] | None:
    if state.ui_selected_event_id is None:
        return None

    return next(
        (
            item
            for item in state.event_records
            if item.get("id") == state.ui_selected_event_id
        ),
        None,
    )


def _event_detail_bounds() -> tuple[float, float, float, float]:
    width = min(650.0, config.WORLD_WIDTH + config.RIGHT_PANEL_WIDTH - 40)
    height = min(350.0, config.WORLD_HEIGHT - 36)

    x = max(config.LEFT_PANEL_RIGHT + 50, config.RIGHT_PANEL_LEFT - width - 50)
    top = config.TOP_BAR_BOTTOM - 18
    return x, top, width, height


def _selected_object_details(state: SimState, selected: str) -> list[str]:
    if selected == "dog":
        return [
            "ID：MarsDog",
            f"位置：{state.dog_x:.0f}, {state.dog_y:.0f}",
            f"朝向：{state.dog_heading:.0f} deg",
            f"行为：{state.active_behavior or '-'}",
            f"动作：{state.action_current_action}",
        ]
    if selected == "user":
        target = state.active_target or {}
        return [
            f"ID：{_dash(target.get('identity') or 'user')}",
            f"位置：{state.user_x:.0f}, {state.user_y:.0f}",
            f"置信度：{_dash(target.get('confidence'))}",
            f"姿态：{_dash(target.get('pose_state'))}",
            f"选择原因：{_dash(target.get('selection_reason'))}",
        ]
    item = state.room_objects.get(selected)
    if item:
        return [
            f"ID：{selected}",
            f"类型：{_dash(item.get('kind'))}",
            f"标签：{_dash(item.get('label'))}",
            f"位置：{_dash(item.get('x'))}, {_dash(item.get('y'))}",
            f"当前目标：{'是' if item.get('active') else '否'}",
        ]
    if selected.startswith("tracked:"):
        try:
            index = int(selected.split(":", 1)[1])
        except ValueError:
            return []
        tracked = (state.latest_visual_event or {}).get("tracked_objects")
        if isinstance(tracked, list) and 0 <= index < len(tracked) and isinstance(tracked[index], dict):
            item = tracked[index]
            return [
                f"ID：tracked:{index}",
                f"标签：{_dash(item.get('label'))}",
                f"置信度：{_dash(item.get('confidence'))}",
                f"中心：{_dash(item.get('center_x'))}, {_dash(item.get('center_y'))}",
                f"边界框：{_dash(item.get('x'))}, {_dash(item.get('y'))}, {_dash(item.get('w'))}, {_dash(item.get('h'))}",
            ]
    return []


def _fresh_signal(signal: dict[str, Any] | None, ttl_sec: float = 6.0) -> dict[str, Any]:
    if not signal:
        return {}
    received = _to_float(signal.get("received_at"))
    if received is not None and time.time() - received > ttl_sec:
        return {}
    return signal


def _value_fraction(value: Any) -> float | None:
    numeric = _to_float(value)
    return None if numeric is None else _clamp01(numeric / 100.0)


def _interrupt_text(value: bool | None, status: str) -> str:
    if status != "running":
        return "未执行"
    if value is True:
        return "安全"
    if value is False:
        return "锁定"
    return "未知"


def _event_list(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) or "-"
    return str(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _collection_count(value: Any) -> int:
    if isinstance(value, (list, tuple, dict, set)):
        return len(value)
    return 0 if value is None else 1


def _round_value(value: Any) -> Any:
    numeric = _to_float(value)
    if numeric is None:
        return value
    return int(numeric) if numeric.is_integer() else round(numeric, 2)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dash(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def _truncate(value: Any, limit: int) -> str:
    text = _dash(value)
    if len(text) <= limit:
        return text
    if limit <= 3:
        return "." * max(0, limit)
    return text[: limit - 3] + "..."


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mix(
        color: tuple[int, int, int],
        other: tuple[int, int, int],
        amount: float,
) -> tuple[int, int, int]:
    amount = _clamp01(amount)
    return tuple(int(color[index] * (1.0 - amount) + other[index] * amount) for index in range(3))
