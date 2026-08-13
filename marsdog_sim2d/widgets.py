"""Responsive debug-console widgets for the Arcade viewer."""

from __future__ import annotations

from datetime import datetime
import json
import math
import time
from typing import Any, Iterable

import arcade

from . import config
from .action_visuals import visual_for_action
from .drawing import draw_text
from .event_injector import SCENARIOS, resolve_emotion_output, resolve_need_output
from .sim_state import SimState
from .voice_commands import voice_command_display


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

    def __init__(self) -> None:
        self._hits: list[dict[str, Any]] = []
        self._hovered: dict[str, Any] | None = None
        self._select_popup: dict[str, Any] | None = None
        self._left_scroll_max = 0.0
        self._right_scroll_max = 0.0

    @property
    def left_scroll_max(self) -> float:
        return self._left_scroll_max

    @property
    def right_scroll_max(self) -> float:
        return self._right_scroll_max

    def draw(self, state: SimState) -> None:
        self._hits = []
        self._select_popup = None
        self._draw_panel_backgrounds()
        self._draw_top_bar(state)
        self._draw_input_panel(state)
        self._draw_status_panel(state)
        self._draw_scene_controls(state)
        self._draw_event_stream(state)
        self._draw_object_detail(state)
        self._draw_event_detail(state)
        self._draw_confirmation(state)
        self._draw_select_popup(state)
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

    def _draw_top_bar(self, state: SimState) -> None:
        now = time.time()
        x = 16.0
        y = config.TOP_BAR_TOP - 11
        title = "MarsDog 调试控制台" if config.WINDOW_WIDTH >= 1280 else "MarsDog"
        draw_text(
            title,
            x,
            y,
            config.COLORS["text"],
            config.FONT_SIZE_PAGE,
            bold=True,
            anchor_y="top",
        )

        chip_x = max(380.0 if config.WINDOW_WIDTH >= 1280 else 150.0, config.LEFT_PANEL_RIGHT + 8.0)
        available = max(360.0, config.RIGHT_PANEL_LEFT - chip_x - 12.0)
        chip_gap = 7.0
        chip_w = min(118.0, (available - chip_gap * (len(TOP_ENDPOINTS) - 1)) / len(TOP_ENDPOINTS))
        for label, topics in TOP_ENDPOINTS:
            status, status_text, detail = _endpoint_status(state, topics, label, now)
            color = _health_color(status)
            self._draw_health_chip(chip_x, config.TOP_BAR_BOTTOM + 8, chip_w, label, status_text, color)
            self._hit(
                "topic_detail",
                chip_x,
                config.TOP_BAR_BOTTOM + 6,
                chip_w,
                31,
                topic_label=label,
                topics=topics,
                tooltip=detail,
            )
            chip_x += chip_w + chip_gap

        time_text, time_color = _virtual_time_display(state)
        draw_text(
            time_text,
            config.WINDOW_WIDTH - 16,
            config.TOP_BAR_TOP - 7,
            time_color,
            config.FONT_SIZE_BODY,
            bold=True,
            anchor_x="right",
            anchor_y="top",
        )
        draw_text(
            f"事件 {state.processed_events}  队列 {state.queue_depth}",
            config.WINDOW_WIDTH - 16,
            config.TOP_BAR_TOP - 25,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            anchor_x="right",
            anchor_y="top",
        )

    def _draw_health_chip(
        self,
        x: float,
        y: float,
        width: float,
        label: str,
        status: str,
        color: tuple[int, int, int],
    ) -> None:
        arcade.draw_circle_filled(x + 6, y + 9, 4, color)
        draw_text(
            label,
            x + 15,
            y + 15,
            config.COLORS["text"],
            config.FONT_SIZE_AUX,
            bold=True,
            anchor_y="top",
        )
        compact_status = {
            "Waiting": "等待",
            "Offline": "错误",
            "Stale": "延迟",
            "Active": "活动",
            "Live": "正常",
        }.get(status, status)
        draw_text(
            _truncate(compact_status, 9 if width >= 112 else 6),
            x + width,
            y + 15,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            anchor_x="right",
            anchor_y="top",
        )

    def _draw_input_panel(self, state: SimState) -> None:
        if config.LEFT_PANEL_WIDTH <= config.COLLAPSED_LEFT_PANEL_WIDTH + 1:
            self._draw_collapsed_input_panel(state)
            return

        x = config.LEFT_PANEL_LEFT + 12
        width = config.LEFT_PANEL_WIDTH - 24
        header_top = config.TOP_BAR_BOTTOM - 12
        draw_text(
            "输入控制",
            x,
            header_top,
            config.COLORS["text"],
            config.FONT_SIZE_MODULE,
            bold=True,
            anchor_y="top",
        )
        collapse_x = config.LEFT_PANEL_RIGHT - 38
        self._icon_button(
            collapse_x,
            header_top - 25,
            26,
            23,
            "<<",
            "collapse_left",
            "折叠输入面板",
        )
        divider_y = header_top - 29
        arcade.draw_line(x, divider_y, x + width, divider_y, config.COLORS["border"], 1)
        top = divider_y - 7

        tab_w = width / len(INPUT_TABS)
        for index, tab in enumerate(INPUT_TABS):
            tx = x + index * tab_w
            active = state.ui_input_tab == tab
            fill = config.COLORS["surface_raised"] if active else config.COLORS["surface"]
            border = config.COLORS["accent"] if active else config.COLORS["border"]
            arcade.draw_lbwh_rectangle_filled(tx, top - config.TAB_HEIGHT, tab_w - 2, config.TAB_HEIGHT, fill)
            arcade.draw_lbwh_rectangle_outline(tx, top - config.TAB_HEIGHT, tab_w - 2, config.TAB_HEIGHT, border, 1)
            draw_text(
                TAB_LABELS.get(tab, tab),
                tx + (tab_w - 2) / 2,
                top - 9,
                config.COLORS["text"] if active else config.COLORS["muted_text"],
                9,
                bold=active,
                anchor_x="center",
                anchor_y="top",
            )
            self._hit("input_tab", tx, top - config.TAB_HEIGHT, tab_w - 2, config.TAB_HEIGHT, tab=tab)
        top -= config.TAB_HEIGHT + 12

        clip_top = top
        clip_bottom = config.BOTTOM_LOG_HEIGHT + 1
        scroll = max(0.0, min(state.ui_left_scroll, self._left_scroll_max))
        content_top = clip_top + scroll
        hit_start = len(self._hits)
        old_scissor = arcade.get_window().ctx.scissor
        arcade.get_window().ctx.scissor = (
            int(config.LEFT_PANEL_LEFT),
            int(clip_bottom),
            int(config.LEFT_PANEL_WIDTH),
            int(max(1.0, clip_top - clip_bottom)),
        )
        try:
            if state.ui_input_tab == "State":
                content_bottom = self._draw_state_tab(state, x, content_top, width)
            elif state.ui_input_tab == "Command":
                content_bottom = self._draw_command_tab(state, x, content_top, width)
            elif state.ui_input_tab == "Scenario":
                content_bottom = self._draw_scenario_tab(state, x, content_top, width)
            else:
                content_bottom = self._draw_event_tab(state, x, content_top, width)
        finally:
            arcade.get_window().ctx.scissor = old_scissor

        visible_hits: list[dict[str, Any]] = []
        for item in self._hits[hit_start:]:
            item_bottom = max(float(item["y"]), clip_bottom)
            item_top = min(float(item["y"]) + float(item["h"]), clip_top)
            if item_top <= item_bottom:
                continue
            clipped = dict(item)
            clipped["y"] = item_bottom
            clipped["h"] = item_top - item_bottom
            visible_hits.append(clipped)
        self._hits[hit_start:] = visible_hits

        content_height = content_top - content_bottom
        viewport_height = max(1.0, clip_top - clip_bottom - 4)
        self._left_scroll_max = max(0.0, content_height - viewport_height)
        state.ui_left_scroll = max(0.0, min(state.ui_left_scroll, self._left_scroll_max))
        if self._left_scroll_max > 0:
            track_x = config.LEFT_PANEL_RIGHT - 4
            track_h = clip_top - clip_bottom - 8
            thumb_h = max(32.0, track_h * viewport_height / max(content_height, 1.0))
            thumb_y = clip_top - 4 - thumb_h - (track_h - thumb_h) * (
                state.ui_left_scroll / self._left_scroll_max
            )
            arcade.draw_lbwh_rectangle_filled(
                track_x,
                thumb_y,
                2,
                thumb_h,
                config.COLORS["border_strong"],
            )

    def _draw_collapsed_input_panel(self, state: SimState) -> None:
        x = config.LEFT_PANEL_LEFT + 8
        top = config.TOP_BAR_BOTTOM - 10
        self._icon_button(x, top - 22, 32, 28, ">>", "expand_left", "展开输入面板")
        top -= 56
        for tab in INPUT_TABS:
            active = state.ui_input_tab == tab
            self._icon_button(
                x,
                top - 28,
                32,
                30,
                {"Event": "事", "State": "态", "Command": "令", "Scenario": "景"}.get(tab, tab[0]),
                "collapsed_tab",
                TAB_LABELS.get(tab, tab),
                tab=tab,
                active=active,
            )
            top -= 40
        if state.ui_pending_placement:
            arcade.draw_circle_filled(x + 16, config.BOTTOM_LOG_HEIGHT + 26, 5, config.COLORS["warning"])

    def _draw_event_tab(self, state: SimState, x: float, top: float, width: float) -> float:
        group = state.event_injector_group if state.event_injector_group in EVENT_SOURCES else "Audio"
        top = self._select(
            state,
            "event_source",
            "事件来源",
            group,
            EVENT_SOURCES,
            x,
            top,
            width,
            target="event_group",
        )
        event_field = _event_type_field(group)
        if event_field:
            top = self._select(
                state,
                "event_type",
                "事件类型",
                state.event_injector_fields.get(event_field, "-"),
                SELECT_OPTIONS.get(event_field, (state.event_injector_fields.get(event_field, "-"),)),
                x,
                top,
                width,
                target="field",
                field_id=event_field,
            )

        for field_id, label, kind in _event_parameter_fields(group):
            if kind == "select":
                top = self._select(
                    state,
                    f"event_{field_id}",
                    label,
                    state.event_injector_fields.get(field_id, ""),
                    SELECT_OPTIONS.get(field_id, (state.event_injector_fields.get(field_id, ""),)),
                    x,
                    top,
                    width,
                    target="field",
                    field_id=field_id,
                )
            else:
                top = self._input(
                    state,
                    field_id,
                    label,
                    state.event_injector_fields.get(field_id, ""),
                    x,
                    top,
                    width,
                )

        if group in {"Vision", "Audio"}:
            placement_label = "在场景中放置声源" if group == "Audio" else "在场景中放置目标"
            active = bool(state.ui_pending_placement and state.ui_pending_placement.get("group") == group)
            top = self._button_row(
                x,
                top,
                width,
                placement_label,
                "placement_mode",
                secondary=True,
                active=active,
                group=group,
            )

        top = self._draw_payload_preview(state, x, top, width, max_lines=2)
        return self._button_row(x, top, width, "发送事件", "send_event", primary=True)

    def _draw_state_tab(self, state: SimState, x: float, top: float, width: float) -> float:
        group = state.event_injector_group if state.event_injector_group in STATE_TYPES else "Need"
        if group == "Personality":
            notice_text = "持久修改请使用 ROS2 参数服务"
        elif group == "Emotion":
            value = _to_float(state.event_injector_fields.get("emotion_value"))
            _level, event_type, _level_range = resolve_emotion_output(
                state.event_injector_fields.get("emotion_name", "Joy"),
                90.0 if value is None else value,
            )
            notice_text = "发布快照与推导事件" if event_type else "当前数值仅发布状态快照"
        else:
            notice_text = "发布快照与推导事件"
        _draw_notice(x, top - 34, width, "模拟计算节点输出", notice_text, config.COLORS["accent"])
        top -= 48
        top = self._select(
            state,
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
            top = self._select(
                state,
                "state_item",
                "需求项",
                state.event_injector_fields.get("need_demand", "Hunger"),
                config.DEMAND_NAMES,
                x,
                top,
                width,
                target="field",
                field_id="need_demand",
            )
            top = self._input(state, "need_value", "数值 (0-100)", state.event_injector_fields.get("need_value", ""), x, top, width)
            value = _to_float(state.event_injector_fields.get("need_value"))
            level, event_type = resolve_need_output(
                state.event_injector_fields.get("need_demand", "Hunger"),
                82.0 if value is None else value,
            )
            derived_title = f"推导等级：{level}"
            derived_text = event_type
            derived_color = config.COLORS["warning"] if level == "OVERFLOW" else config.COLORS["accent"]
            button_label = "发布状态与事件"
        elif group == "Emotion":
            top = self._select(
                state,
                "state_item",
                "情绪项",
                state.event_injector_fields.get("emotion_name", "Joy"),
                config.EMOTION_NAMES,
                x,
                top,
                width,
                target="field",
                field_id="emotion_name",
            )
            top = self._input(state, "emotion_value", "数值 (0-100)", state.event_injector_fields.get("emotion_value", ""), x, top, width)
            value = _to_float(state.event_injector_fields.get("emotion_value"))
            level, event_type, level_range = resolve_emotion_output(
                state.event_injector_fields.get("emotion_name", "Joy"),
                90.0 if value is None else value,
            )
            derived_title = f"推导等级：{level}"
            derived_text = (
                f"{event_type}  区间 {level_range[0]}-{level_range[1]}"
                if event_type and level_range
                else "当前数值没有对应的情绪事件"
            )
            derived_color = config.COLORS["accent"] if event_type else config.COLORS["waiting"]
            button_label = "发布状态与事件" if event_type else "仅发布状态快照"
        else:
            trait = state.event_injector_fields.get("personality_trait", "A")
            top = self._select(
                state,
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
            top = self._input(state, value_field, "数值 (0-100)", state.event_injector_fields.get(value_field, ""), x, top, width)
            top = self._select(
                state,
                "state_profile",
                "性格配置",
                state.event_injector_fields.get("personality_profile", "Custom"),
                SELECT_OPTIONS["personality_profile"],
                x,
                top,
                width,
                target="field",
                field_id="personality_profile",
            )
            derived_title = "仅模拟状态快照"
            derived_text = "不会持久修改 personality_node"
            derived_color = config.COLORS["warning"]
            button_label = "发布性格快照"

        _draw_notice(x, top - 35, width, derived_title, derived_text, derived_color)
        top -= 49
        top = self._draw_payload_preview(state, x, top, width, max_lines=3)
        return self._button_row(x, top, width, button_label, "publish_state_output", primary=True)

    def _draw_command_tab(self, state: SimState, x: float, top: float, width: float) -> float:
        draw_text(
            "语音指令",
            x,
            top,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            anchor_y="top",
        )
        top -= 18
        top = self._select(
            state,
            "command_id",
            "指令类型",
            state.event_injector_fields.get("audio_command_id", "CMD_SIT"),
            SELECT_OPTIONS["audio_command_id"],
            x,
            top,
            width,
            target="field",
            field_id="audio_command_id",
        )
        top = self._input(state, "audio_asr_text", "ASR 文本", state.event_injector_fields.get("audio_asr_text", ""), x, top, width)
        top = self._input(state, "audio_speaker_id", "说话人", state.event_injector_fields.get("audio_speaker_id", ""), x, top, width)
        top = self._input(state, "audio_confidence", "置信度", state.event_injector_fields.get("audio_confidence", ""), x, top, width)

        draw_text("快捷指令", x, top, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        top -= 20
        quick = (
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
        gap = 6
        cell_w = (width - gap * 2) / 3
        for index, (label, command_id) in enumerate(quick):
            row = index // 3
            col = index % 3
            bx = x + col * (cell_w + gap)
            by = top - row * (config.BUTTON_HEIGHT + 6) - config.BUTTON_HEIGHT
            self._button(
                bx,
                by,
                cell_w,
                config.BUTTON_HEIGHT,
                label,
                "command_quick",
                secondary=True,
                command_id=command_id,
                asr_text=label,
            )
        quick_rows = math.ceil(len(quick) / 3)
        top -= quick_rows * (config.BUTTON_HEIGHT + 6) + 4
        top = self._draw_payload_preview(state, x, top, width, max_lines=3)
        return self._button_row(x, top, width, "发送指令", "send_command", primary=True)

    def _draw_scenario_tab(self, state: SimState, x: float, top: float, width: float) -> float:
        draw_text(
            "预设测试场景",
            x,
            top,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            anchor_y="top",
        )
        top -= 24
        for scenario_id, label, summary in SCENARIOS:
            label, summary = SCENARIO_LABELS.get(scenario_id, (label, summary))
            height = 52
            selected = state.ui_selected_scenario == scenario_id
            fill = config.COLORS["surface_hover"] if selected else config.COLORS["surface"]
            border = config.COLORS["accent"] if selected else config.COLORS["border"]
            arcade.draw_lbwh_rectangle_filled(x, top - height, width, height, fill)
            arcade.draw_lbwh_rectangle_outline(x, top - height, width, height, border, 1)
            draw_text(label, x + 10, top - 8, config.COLORS["text"], config.FONT_SIZE_BODY, bold=True, anchor_y="top")
            draw_text(_truncate(summary, 38), x + 10, top - 28, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
            self._hit("scenario", x, top - height, width, height, scenario_id=scenario_id)
            top -= height + 7
        return top

    def _draw_payload_preview(
        self,
        state: SimState,
        x: float,
        top: float,
        width: float,
        max_lines: int = 4,
    ) -> float:
        topic = ", ".join(state.ui_preview_topics) or "-"
        draw_text("发布 Topic", x, top, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
        draw_text(_truncate(topic, 40), x, top - 15, config.COLORS["accent"], config.FONT_SIZE_AUX, anchor_y="top")
        top -= 38
        preview_height = 21 + max_lines * 13
        arcade.draw_lbwh_rectangle_filled(x, top - preview_height, width, preview_height, config.COLORS["preview_background"])
        arcade.draw_lbwh_rectangle_outline(x, top - preview_height, width, preview_height, config.COLORS["border"], 1)
        draw_text("Payload 预览", x + 8, top - 7, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        lines = _preview_lines(state.ui_payload_preview, max_lines, 42)
        line_y = top - 23
        for line in lines:
            draw_text(line, x + 8, line_y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
            line_y -= 13
        return top - preview_height - 8

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
        fov_width = 62
        x = config.WORLD_RIGHT - fov_width - 16
        y = config.WORLD_TOP - 33
        self._small_button(
            x,
            y,
            fov_width,
            24,
            "视野开" if state.ui_show_fov else "视野关",
            "toggle_fov",
            active=state.ui_show_fov,
        )
        user_width = 88
        user_x = x - user_width - 8
        self._button(
            user_x,
            y,
            user_width,
            24,
            "删除人物" if state.ui_user_visible else "添加人物",
            "toggle_virtual_user",
            secondary=not state.ui_user_visible,
            blue_active=state.ui_user_visible,
        )
        abnormal_width = 92
        abnormal_x = user_x - abnormal_width - 8
        self._button(
            abnormal_x,
            y,
            abnormal_width,
            24,
            "解除异常" if state.ui_abnormal_simulation_active else "异常模拟",
            "toggle_abnormal_simulation",
            secondary=not state.ui_abnormal_simulation_active,
            danger_active=state.ui_abnormal_simulation_active,
        )
        food_width = 68
        self._button(
            abnormal_x - food_width - 8,
            y,
            food_width,
            24,
            "移除" if state.ui_bowl_has_food else "放粮",
            "toggle_bowl_food",
            secondary=not state.ui_bowl_has_food,
            blue_active=state.ui_bowl_has_food,
        )

    def _draw_current_behavior(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "behavior" in state.ui_collapsed_cards
        expanded = state.ui_behavior_context_expanded
        height = 42 if collapsed else (292 if expanded else 230)
        status_color = _action_status_color(state)
        self._card(x, top, width, height, "当前行为", "behavior", state, accent=status_color)
        if collapsed:
            return top - height - config.CARD_GAP

        y = top - 39
        _draw_badge(x + width - 34, top - 10, _option_label(state.action_status), status_color, right=True)
        draw_text(
            _truncate(state.active_behavior or "等待行为", 36),
            x + config.CARD_PADDING,
            y,
            config.COLORS["text"],
            config.FONT_SIZE_KEY,
            bold=True,
            anchor_y="top",
        )
        y -= 27
        draw_text(
            _truncate(state.action_current_action or "-", 46),
            x + config.CARD_PADDING,
            y,
            config.COLORS["accent"],
            config.FONT_SIZE_MODULE,
            bold=True,
            anchor_y="top",
        )
        y -= 25

        bar_x = x + config.CARD_PADDING
        bar_w = width - config.CARD_PADDING * 2
        progress_text_width = 44
        track_w = max(80.0, bar_w - progress_text_width - 8)
        arcade.draw_lbwh_rectangle_filled(bar_x, y - 7, track_w, 7, config.COLORS["progress_track"])
        arcade.draw_lbwh_rectangle_filled(bar_x, y - 7, track_w * _clamp01(state.action_progress), 7, status_color)
        draw_text(
            f"{state.action_progress * 100:.0f}%",
            bar_x + bar_w,
            y - 3,
            config.COLORS["muted_text"],
            config.FONT_SIZE_AUX,
            anchor_x="right",
            anchor_y="center",
        )
        y -= 23
        total = max(0, state.action_stage_total)
        if total:
            active = max(1, min(total, state.action_stage_index or 1))
            self._draw_step_strip(bar_x, y, bar_w, total, active, status_color)
        else:
            draw_text(
                "等待 Stage 反馈",
                bar_x,
                y,
                config.COLORS["subtle_text"],
                config.FONT_SIZE_AUX,
                anchor_y="top",
            )
        y -= 24

        visual = visual_for_action(state.action_current_action)
        rows = (
            ("阶段", f"{state.action_stage_index or '-'}/{state.action_stage_total or '-'} {state.action_stage_label}"),
            ("目标", state.action_target_label),
            (
                "2D展示",
                (
                    f"图片：{visual.pose}"
                    if visual is not None
                    else ("等待动作" if state.action_current_action in {"", "-"} else "仅文字")
                ),
            ),
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
                draw_text(_truncate(line, 58), x + config.CARD_PADDING, detail_y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
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
        height = 42 if collapsed else 222
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
        y = top - 40
        line_x = x + 18
        for index, (label, value) in enumerate(chain):
            color = config.COLORS["accent"] if index == len(chain) - 1 else config.COLORS["need"]
            arcade.draw_circle_filled(line_x, y - 5, 3, color)
            if index < len(chain) - 1:
                arcade.draw_line(line_x, y - 9, line_x, y - 22, config.COLORS["border_strong"], 1)
            draw_text(label, line_x + 10, y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(_truncate(value, 34), line_x + 100, y, config.COLORS["text"], config.FONT_SIZE_AUX, bold=index == 4, anchor_y="top")
            y -= 25

        metadata = _dict(params.get("metadata"))
        fallback = params.get("fallback_reason") or metadata.get("fallback_reason") or "-"
        requested = params.get("requested_behavior") or params.get("requested_behavior_name") or state.active_behavior or "-"
        resolved = params.get("resolved_behavior") or params.get("resolved_behavior_name") or state.active_behavior or "-"
        sub_priority = params.get("sub_priority") or params.get("subPriority") or "-"
        footer = f"优先级 {state.action_priority_level if state.action_priority_level is not None else '-'} / 子级 {sub_priority}  请求 {requested} -> {resolved}"
        draw_text(_truncate(footer, 58), x + 12, top - 167, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        requested_mode = params.get("requested_interaction_mode") or params.get("interaction_mode") or "-"
        resolved_mode = params.get("resolved_interaction_mode") or state.action_interaction_mode or "-"
        draw_text(_truncate(f"模式 {requested_mode} -> {resolved_mode}", 58), x + 12, top - 181, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        if fallback != "-":
            draw_text(_truncate(f"回退原因：{fallback}", 58), x + 12, top - 195, config.COLORS["warning"], config.FONT_SIZE_AUX, anchor_y="top")
        return top - height - config.CARD_GAP

    def _draw_need_card(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "need" in state.ui_collapsed_cards
        height = 42 if collapsed else 205
        self._card(x, top, width, height, "需求状态", "need", state)
        if collapsed:
            return top - height - config.CARD_GAP

        rows = _need_meter_rows(state)
        dominant = _dominant_need(rows)
        y = top - 39
        for row in rows:
            active = row["name"] == dominant or _is_alert_level(row.get("level"), row.get("event"))
            self._draw_meter_row(x + 12, y, width - 24, row, config.COLORS["need"], active)
            y -= config.STATUS_METER_ROW_HEIGHT
        return top - height - config.CARD_GAP

    def _draw_emotion_card(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "emotion" in state.ui_collapsed_cards
        height = 42 if collapsed else 202
        self._card(x, top, width, height, "情绪状态", "emotion", state)
        if collapsed:
            return top - height - config.CARD_GAP

        rows = _emotion_meter_rows(state)
        dominant = _dominant_emotion(state, rows)
        dominant_row = next((row for row in rows if row["name"] == dominant), rows[0] if rows else {})
        value = _round_value(dominant_row.get("value"))
        level = _dash(dominant_row.get("level"))
        event = _dash(dominant_row.get("event"))
        draw_text(_option_label(dominant) if dominant else "-", x + 12, top - 40, config.COLORS["text"], config.FONT_SIZE_KEY, bold=True, anchor_y="top")
        draw_text(f"{_dash(value)}  {level}", x + width - 12, top - 40, config.COLORS["emotion"], config.FONT_SIZE_BODY, bold=True, anchor_x="right", anchor_y="top")
        draw_text(_truncate(event, 46), x + 12, top - 62, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        y = top - 86
        for row in rows:
            if row["name"] == dominant:
                continue
            self._draw_meter_row(x + 12, y, width - 24, row, config.COLORS["emotion"], False, compact=True)
            y -= config.STATUS_COMPACT_ROW_HEIGHT
        return top - height - config.CARD_GAP

    def _draw_perception_card(self, state: SimState, x: float, top: float, width: float) -> float:
        collapsed = "perception" in state.ui_collapsed_cards
        height = 42 if collapsed else 184
        self._card(x, top, width, height, "感知摘要", "perception", state)
        if collapsed:
            return top - height - config.CARD_GAP

        visual = state.latest_visual_event or {}
        visual_raw = _dict(visual.get("raw"))
        audio = state.latest_audio_event or {}
        target = state.active_target or {}
        confidence = target.get("confidence") or target.get("face_confidence") or "-"
        lines = (
            f"人类 {visual.get('humans_count', 0)}   动物 {_collection_count(visual_raw.get('animals'))}   物体 {visual.get('tracked_objects_count', 0)}",
            f"当前目标  {_dash(target.get('identity') or target.get('track_id'))}",
            f"置信度  {_dash(_round_value(confidence))}   姿态  {_dash(target.get('pose_state'))}",
            f"声音  {_dash(audio.get('event_type'))}   说话人  {_dash(audio.get('speaker_id'))}",
            f"最近事件  {_event_list(visual.get('events'))}",
            f"语音识别  {voice_command_display(audio)}",
        )
        y = top - 41
        for index, line in enumerate(lines):
            draw_text(_truncate(line, 55), x + 12, y, config.COLORS["text"] if index in {1, 3} else config.COLORS["muted_text"], config.FONT_SIZE_BODY if index == 1 else config.FONT_SIZE_AUX, bold=index == 1, anchor_y="top")
            y -= config.STATUS_METER_ROW_HEIGHT
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
        draw_text(title, x + 12, top - 10, config.COLORS["text"], config.FONT_SIZE_MODULE, bold=True, anchor_y="top")
        collapsed = card_id in state.ui_collapsed_cards
        draw_text("+" if collapsed else "-", x + width - 14, top - 10, config.COLORS["muted_text"], config.FONT_SIZE_MODULE, anchor_x="center", anchor_y="top")
        self._hit("toggle_card", x, top - 32, width, 32, card_id=card_id, tooltip=f"{'展开' if collapsed else '折叠'}{title}")

    def _draw_step_strip(
        self,
        x: float,
        top: float,
        width: float,
        total: int,
        active: int,
        color: tuple[int, int, int],
    ) -> None:
        total = min(total, 12)
        gap = 4
        segment_w = max(12.0, (width - gap * (total - 1)) / total)
        for index in range(total):
            sx = x + index * (segment_w + gap)
            complete = index + 1 < active
            current = index + 1 == active
            fill = _mix(color, config.COLORS["surface"], 0.25 if current else 0.55) if index + 1 <= active else config.COLORS["meter_track"]
            border = color if index + 1 <= active else config.COLORS["border"]
            arcade.draw_lbwh_rectangle_filled(sx, top - 14, segment_w, 14, fill)
            arcade.draw_lbwh_rectangle_outline(sx, top - 14, segment_w, 14, border, 1)
            draw_text(str(index + 1), sx + segment_w / 2, top - 2, config.COLORS["text"] if current or complete else config.COLORS["muted_text"], config.FONT_SIZE_AUX, bold=current, anchor_x="center", anchor_y="top")

    def _draw_key_value_grid(
        self,
        x: float,
        top: float,
        width: float,
        rows: Iterable[tuple[str, Any]],
    ) -> None:
        rows = tuple(rows)
        column_gap = 16
        cell_width = (width - column_gap) / 2
        value_chars = max(12, int((cell_width - 4) / 9.0))
        divider_x = x + cell_width + column_gap / 2
        divider_height = config.STATUS_GRID_ROW_HEIGHT + config.STATUS_GRID_VALUE_OFFSET + 14
        arcade.draw_line(divider_x, top + 1, divider_x, top - divider_height, config.COLORS["border"], 1)
        for index, (label, value) in enumerate(rows):
            col = index % 2
            row = index // 2
            cell_x = x + col * (cell_width + column_gap)
            cell_y = top - row * config.STATUS_GRID_ROW_HEIGHT
            draw_text(label, cell_x, cell_y, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
            draw_text(
                _truncate(_dash(value), value_chars),
                cell_x,
                cell_y - config.STATUS_GRID_VALUE_OFFSET,
                config.COLORS["text"],
                config.FONT_SIZE_BODY,
                bold=label in {"阶段", "目标"},
                anchor_y="top",
            )

    def _draw_meter_row(
        self,
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
        name_w = 68
        bar_x = x + name_w
        bar_w = max(64, min(112 if not compact else 94, width * 0.31))
        bar_h = 5 if compact else 7
        color = _meter_color(value, level, event, base_color, active)
        if active:
            arcade.draw_lbwh_rectangle_filled(x - 5, y - 14, width + 10, 17, _mix(color, config.COLORS["surface"], 0.84))
            arcade.draw_lbwh_rectangle_filled(x - 5, y - 14, 2, 17, color)
        draw_text(_option_label(name), x, y, config.COLORS["text"] if active else config.COLORS["muted_text"], config.FONT_SIZE_AUX, bold=active, anchor_y="top")
        arcade.draw_lbwh_rectangle_filled(bar_x, y - 10, bar_w, bar_h, config.COLORS["meter_track"])
        if fraction is not None:
            arcade.draw_lbwh_rectangle_filled(bar_x, y - 10, bar_w * fraction, bar_h, color)
        value_x = bar_x + bar_w + 7
        draw_text(_dash(_round_value(value)), value_x, y, config.COLORS["text"], config.FONT_SIZE_AUX, anchor_y="top")
        meta = level if compact else f"{level} {event}"
        meta_x = value_x + 34
        available_chars = max(5, int((x + width - meta_x - 8) / 6))
        draw_text(_truncate(meta, min(18 if compact else 24, available_chars)), meta_x, y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")

    def _draw_event_stream(self, state: SimState) -> None:
        top = config.BOTTOM_LOG_HEIGHT
        self._hit("log_resize", 0, top - 5, config.WINDOW_WIDTH, 10, tooltip="拖动调整事件流高度")
        arcade.draw_line(config.WINDOW_WIDTH / 2 - 28, top - 4, config.WINDOW_WIDTH / 2 + 28, top - 4, config.COLORS["border_strong"], 2)

        x = 14
        toolbar_y = top - 15
        draw_text("事件流", x, toolbar_y, config.COLORS["text"], config.FONT_SIZE_MODULE, bold=True, anchor_y="top")
        x += 118
        for source in LOG_SOURCES:
            active = source in state.ui_log_filters
            width = 47 if len(source) <= 4 else 57
            self._chip(x, toolbar_y - 4, width, source, active, "toggle_log_filter", source=source)
            x += width + 4

        controls_right = config.WINDOW_WIDTH - 14
        button_specs = (
            ("自动", "toggle_log_auto", state.ui_log_auto_scroll),
            ("清空", "clear_log", False),
            ("继续" if state.ui_log_paused else "暂停", "toggle_log_pause", state.ui_log_paused),
        )
        for label, action, active in button_specs:
            width = 58
            controls_right -= width
            self._small_button(controls_right, toolbar_y - 9, width, 24, label, action, active=active)
            controls_right -= 5

        search_w = min(190.0, max(115.0, controls_right - x - 12))
        search_x = controls_right - search_w
        if search_x > x + 10:
            self._search_input(state, search_x, toolbar_y - 9, search_w)

        header_top = top - 48
        columns = _log_columns(config.WINDOW_WIDTH)
        arcade.draw_lbwh_rectangle_filled(12, header_top - 20, config.WINDOW_WIDTH - 24, 20, config.COLORS["table_header"])
        for label, key in (("时间", "time"), ("来源", "source"), ("事件", "event"), ("等级 / 状态", "level"), ("摘要", "summary")):
            draw_text(label, columns[key], header_top - 4, config.COLORS["subtle_text"], config.FONT_SIZE_AUX, bold=True, anchor_y="top")

        records = _filtered_event_records(state)
        available_h = max(22.0, header_top - 24)
        row_h = 22
        visible_count = max(1, int(available_h // row_h))
        start = min(max(0, state.ui_log_scroll), max(0, len(records) - visible_count))
        if state.ui_log_auto_scroll:
            start = 0
            state.ui_log_scroll = 0
        visible = records[start : start + visible_count]
        row_top = header_top - 24
        for index, record in enumerate(visible):
            row_y = row_top - index * row_h
            selected = record.get("id") == state.ui_selected_event_id
            if selected:
                arcade.draw_lbwh_rectangle_filled(12, row_y - row_h + 2, config.WINDOW_WIDTH - 24, row_h - 1, config.COLORS["surface_hover"])
            elif index % 2:
                arcade.draw_lbwh_rectangle_filled(12, row_y - row_h + 2, config.WINDOW_WIDTH - 24, row_h - 1, config.COLORS["table_alt"])
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
            self._hit("select_event", 12, row_y - row_h + 2, config.WINDOW_WIDTH - 24, row_h, event_id=record.get("id"), tooltip="查看原始 Payload")

        if not records:
            draw_text("等待符合筛选条件的 ROS2 事件", 18, row_top - 8, config.COLORS["muted_text"], config.FONT_SIZE_BODY, anchor_y="top")

    def _draw_object_detail(self, state: SimState) -> None:
        if not state.ui_selected_object or state.ui_selected_event_id is not None:
            return
        details = _selected_object_details(state, state.ui_selected_object)
        if not details:
            return
        width = min(310.0, config.WORLD_WIDTH - 30)
        height = 118
        x = config.WORLD_RIGHT - width - 14
        top = config.WORLD_TOP - 14
        arcade.draw_lbwh_rectangle_filled(x, top - height, width, height, config.COLORS["detail_background"])
        arcade.draw_lbwh_rectangle_outline(x, top - height, width, height, config.COLORS["accent"], 1)
        draw_text("对象详情", x + 12, top - 10, config.COLORS["text"], config.FONT_SIZE_MODULE, bold=True, anchor_y="top")
        self._icon_button(x + width - 34, top - 28, 22, 22, "x", "close_object_detail", "关闭")
        y = top - 38
        for line in details[:5]:
            draw_text(_truncate(line, 45), x + 12, y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
            y -= 15

    def _draw_event_detail(self, state: SimState) -> None:
        if state.ui_selected_event_id is None:
            return
        record = next((item for item in state.event_records if item.get("id") == state.ui_selected_event_id), None)
        if record is None:
            return
        width = min(650.0, config.WORLD_WIDTH + config.RIGHT_PANEL_WIDTH - 40)
        height = min(250.0, config.WORLD_HEIGHT - 36)
        x = max(config.LEFT_PANEL_RIGHT + 18, config.RIGHT_PANEL_LEFT - width - 18)
        top = config.TOP_BAR_BOTTOM - 18
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
        self._small_button(x + width - 126, top - 31, 72, 24, "复制 JSON", "copy_event_payload")
        self._icon_button(x + width - 42, top - 31, 28, 24, "x", "close_event_detail", "关闭")
        draw_text(_truncate(str(record.get("topic") or "-"), 80), x + 14, top - 38, config.COLORS["accent"], config.FONT_SIZE_AUX, anchor_y="top")
        payload = json.dumps(record.get("payload") or {}, ensure_ascii=False, indent=2, default=str)
        lines = _wrapped_json_lines(payload, max(40, int((width - 28) / 6)), max(4, int((height - 72) / 14)))
        y = top - 58
        for line in lines:
            draw_text(line, x + 14, y, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
            y -= 14

    def _draw_confirmation(self, state: SimState) -> None:
        pending = state.ui_pending_confirmation
        if not pending:
            return
        if pending.get("kind") == "alert":
            width = 350
            height = 132
            x = (config.WINDOW_WIDTH - width) / 2
            top = (
                (config.TOP_BAR_BOTTOM + config.BOTTOM_LOG_HEIGHT) / 2
                + height / 2
            )
            arcade.draw_lbwh_rectangle_filled(
                x,
                top - height,
                width,
                height,
                config.COLORS["modal_background"],
            )
            arcade.draw_lbwh_rectangle_outline(
                x,
                top - height,
                width,
                height,
                config.COLORS["warning"],
                2,
            )
            draw_text(
                str(pending.get("title") or "提示"),
                x + 18,
                top - 18,
                config.COLORS["warning"],
                config.FONT_SIZE_MODULE,
                bold=True,
                anchor_y="top",
            )
            draw_text(
                _truncate(
                    str(pending.get("message") or "操作暂不可用"),
                    48,
                ),
                x + 18,
                top - 51,
                config.COLORS["text"],
                config.FONT_SIZE_BODY,
                anchor_y="top",
            )
            self._button(
                x + (width - 140) / 2,
                top - 108,
                140,
                32,
                "知道了",
                "cancel_confirmation",
                primary=True,
            )
            return
        width = 390
        height = 156
        x = (config.WINDOW_WIDTH - width) / 2
        top = (config.TOP_BAR_BOTTOM + config.BOTTOM_LOG_HEIGHT) / 2 + height / 2
        arcade.draw_lbwh_rectangle_filled(x, top - height, width, height, config.COLORS["modal_background"])
        arcade.draw_lbwh_rectangle_outline(x, top - height, width, height, config.COLORS["warning"], 2)
        draw_text("确认调试注入", x + 18, top - 18, config.COLORS["warning"], config.FONT_SIZE_MODULE, bold=True, anchor_y="top")
        draw_text(_truncate(str(pending.get("message") or "此操作可能触发高优先级行为。"), 56), x + 18, top - 51, config.COLORS["text"], config.FONT_SIZE_BODY, anchor_y="top")
        draw_text("确认前不会发布 ROS2 数据。", x + 18, top - 76, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        self._button(x + 18, top - 132, 164, 32, "取消", "cancel_confirmation", secondary=True)
        self._button(x + width - 182, top - 132, 164, 32, "确认发送", "confirm_action", primary=True)

    def _draw_tooltip(self) -> None:
        if not self._hovered or not self._hovered.get("tooltip"):
            return
        text = str(self._hovered["tooltip"])
        width = min(390.0, max(140.0, len(text) * 6.0 + 20))
        x = min(config.WINDOW_WIDTH - width - 8, self._hovered["x"])
        y = max(config.BOTTOM_LOG_HEIGHT + 8, self._hovered["y"] - 32)
        arcade.draw_lbwh_rectangle_filled(x, y, width, 25, config.COLORS["tooltip_background"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, 25, config.COLORS["border_strong"], 1)
        draw_text(_truncate(text, 62), x + 9, y + 17, config.COLORS["text"], config.FONT_SIZE_AUX, anchor_y="top")

    def _draw_select_popup(self, state: SimState) -> None:
        popup = self._select_popup
        if not popup or state.ui_open_select != popup["select_id"]:
            return
        options = popup["options"]
        row_h = 27
        height = len(options) * row_h
        x = popup["x"]
        width = popup["w"]
        bottom = popup["y"] - height
        if bottom < config.BOTTOM_LOG_HEIGHT + 8:
            bottom = popup["y"] + popup["h"]
        arcade.draw_lbwh_rectangle_filled(x, bottom, width, height, config.COLORS["popover_background"])
        arcade.draw_lbwh_rectangle_outline(x, bottom, width, height, config.COLORS["accent"], 1)
        for index, option in enumerate(options):
            option_y = bottom + height - (index + 1) * row_h
            if option == popup["value"]:
                arcade.draw_lbwh_rectangle_filled(x + 1, option_y, width - 2, row_h, config.COLORS["surface_hover"])
            draw_text(_truncate(option, 34), x + 9, option_y + row_h - 7, config.COLORS["text"], config.FONT_SIZE_AUX, anchor_y="top")
            self._hit(
                "select_option",
                x,
                option_y,
                width,
                row_h,
                select_id=popup["select_id"],
                target=popup["target"],
                field_id=popup.get("field_id"),
                value=option,
            )

    def _select(
        self,
        state: SimState,
        select_id: str,
        label: str,
        value: str,
        options: tuple[str, ...],
        x: float,
        top: float,
        width: float,
        target: str,
        field_id: str | None = None,
    ) -> float:
        draw_text(label, x, top, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        options = tuple(options)
        if not options:
            return top - config.FORM_LABEL_HEIGHT - config.FORM_ROW_GAP
        columns = len(options) if len(options) <= 4 else 4
        rows = math.ceil(len(options) / columns)
        item_height = config.RADIO_OPTION_HEIGHT
        row_height = item_height + config.RADIO_ROW_GAP
        gap = 3
        cell_width = (width - gap * (columns - 1)) / columns
        first_top = top - config.FORM_LABEL_HEIGHT
        for index, option in enumerate(options):
            row = index // columns
            col = index % columns
            item_x = x + col * (cell_width + gap)
            item_y = first_top - row * row_height - item_height
            selected = str(option) == str(value)
            fill = config.COLORS["surface_hover"] if selected else config.COLORS["surface_raised"]
            border = config.COLORS["accent"] if selected else config.COLORS["border"]
            arcade.draw_lbwh_rectangle_filled(item_x, item_y, cell_width, item_height, fill)
            arcade.draw_lbwh_rectangle_outline(item_x, item_y, cell_width, item_height, border, 1)
            radio_x = item_x + 8
            radio_y = item_y + item_height / 2
            arcade.draw_circle_outline(radio_x, radio_y, 4, border, 1)
            if selected:
                arcade.draw_circle_filled(radio_x, radio_y, 2.3, config.COLORS["accent"])
            display = _option_label(str(option))
            max_chars = max(2, int((cell_width - 18) / 9))
            draw_text(
                _truncate(display, max_chars),
                item_x + 16,
                item_y + 15,
                config.COLORS["text"] if selected else config.COLORS["muted_text"],
                config.FONT_SIZE_AUX,
                bold=selected,
                anchor_y="top",
            )
            self._hit(
                "select_option",
                item_x,
                item_y,
                cell_width,
                item_height,
                select_id=select_id,
                target=target,
                field_id=field_id,
                value=option,
                tooltip=str(option),
            )
        last_bottom = first_top - (rows - 1) * row_height - item_height
        return last_bottom - config.FORM_ROW_GAP

    def _input(
        self,
        state: SimState,
        field_id: str,
        label: str,
        value: str,
        x: float,
        top: float,
        width: float,
        ui_value: bool = False,
    ) -> float:
        draw_text(label, x, top, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")
        control_y = top - config.FORM_LABEL_HEIGHT - config.CONTROL_HEIGHT
        active = state.ui_text_focus == field_id
        fill = config.COLORS["surface_hover"] if active else config.COLORS["surface_raised"]
        border = config.COLORS["accent"] if active else config.COLORS["border"]
        arcade.draw_lbwh_rectangle_filled(x, control_y, width, config.CONTROL_HEIGHT, fill)
        arcade.draw_lbwh_rectangle_outline(x, control_y, width, config.CONTROL_HEIGHT, border, 1)
        caret = "|" if active and int(time.time() * 2) % 2 else ""
        draw_text(_truncate(value + caret, 38), x + 9, control_y + 21, config.COLORS["text"], config.FONT_SIZE_BODY, anchor_y="top")
        self._hit("focus_input", x, control_y, width, config.CONTROL_HEIGHT, field_id=field_id, ui_value=ui_value)
        return control_y - config.FORM_ROW_GAP

    def _search_input(self, state: SimState, x: float, y: float, width: float) -> None:
        active = state.ui_text_focus == "log_search"
        arcade.draw_lbwh_rectangle_filled(x, y, width, 24, config.COLORS["surface_raised"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, 24, config.COLORS["accent"] if active else config.COLORS["border"], 1)
        text = state.ui_log_search or "搜索事件"
        draw_text(_truncate(text, 26), x + 8, y + 17, config.COLORS["text"] if state.ui_log_search else config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_y="top")
        self._hit("focus_log_search", x, y, width, 24)

    def _button_row(
        self,
        x: float,
        top: float,
        width: float,
        label: str,
        action: str,
        primary: bool = False,
        secondary: bool = False,
        active: bool = False,
        **data: Any,
    ) -> float:
        self._button(x, top - config.BUTTON_HEIGHT, width, config.BUTTON_HEIGHT, label, action, primary=primary, secondary=secondary, active=active, **data)
        return top - config.BUTTON_HEIGHT - 9

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
        draw_text(
            label,
            x + width / 2,
            y + height / 2 + 6,
            config.COLORS["text"],
            config.FONT_SIZE_BODY,
            bold=primary or blue_active or danger_active,
            anchor_x="center",
            anchor_y="top",
        )
        self._hit(action, x, y, width, height, **data)

    def _small_button(self, x: float, y: float, width: float, height: float, label: str, action: str, active: bool = False) -> None:
        self._button(x, y, width, height, label, action, secondary=True, active=active)

    def _icon_button(self, x: float, y: float, width: float, height: float, label: str, action: str, tooltip: str, **data: Any) -> None:
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, config.COLORS["surface_raised"])
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, config.COLORS["border"], 1)
        draw_text(label, x + width / 2, y + height / 2 + 6, config.COLORS["muted_text"], config.FONT_SIZE_AUX, bold=bool(data.get("active")), anchor_x="center", anchor_y="top")
        self._hit(action, x, y, width, height, tooltip=tooltip, **data)

    def _chip(self, x: float, top: float, width: float, label: str, active: bool, action: str, **data: Any) -> None:
        y = top - 23
        fill = config.COLORS["surface_hover"] if active else config.COLORS["chip_idle"]
        border = config.COLORS["accent_dim"] if active else config.COLORS["border"]
        arcade.draw_lbwh_rectangle_filled(x, y, width, 23, fill)
        arcade.draw_lbwh_rectangle_outline(x, y, width, 23, border, 1)
        draw_text(label, x + width / 2, top - 6, config.COLORS["text"] if active else config.COLORS["subtle_text"], config.FONT_SIZE_AUX, anchor_x="center", anchor_y="top")
        self._hit(action, x, y, width, 23, **data)

    def _hit(self, action: str, x: float, y: float, w: float, h: float, **data: Any) -> None:
        self._hits.append({"action": action, "x": x, "y": y, "w": w, "h": h, **data})


def _option_label(value: str) -> str:
    return OPTION_LABELS.get(value, value)


def _event_type_field(group: str) -> str | None:
    return {
        "Audio": "audio_event_type",
        "Vision": "vision_events",
        "Result": "result_type",
    }.get(group)


def _event_parameter_fields(group: str) -> tuple[tuple[str, str, str], ...]:
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


def _endpoint_status(
    state: SimState,
    topics: tuple[str, ...],
    label: str,
    now: float,
) -> tuple[str, str, str]:
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


def _health_color(status: str) -> tuple[int, int, int]:
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
            source = {"value": signal.get("value"), "level": signal.get("level"), "levelEvent": signal.get("event_type")}
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
            source = {"value": signal.get("value"), "level": signal.get("level") or signal.get("zone") or signal.get("range"), "levelEvent": signal.get("event_type")}
        rows.append(_meter_row(name, source, event))
    return rows


def _meter_row(name: str, source: Any, event: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return {"name": name, "value": source.get("value"), "level": source.get("level"), "event": source.get("levelEvent") or event}
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
    arcade.draw_lbwh_rectangle_filled(left, top - 18, width, 18, _mix(color, config.COLORS["surface"], 0.66))
    arcade.draw_lbwh_rectangle_outline(left, top - 18, width, 18, color, 1)
    draw_text(_truncate(text, 20), left + width / 2, top - 4, color, config.FONT_SIZE_AUX, bold=True, anchor_x="center", anchor_y="top")


def _badge_width(text: str) -> float:
    return min(132.0, max(54.0, len(str(text)) * 6.0 + 16))


def _draw_notice(x: float, y: float, width: float, title: str, text: str, color: tuple[int, int, int]) -> None:
    arcade.draw_lbwh_rectangle_filled(x, y, width, 35, _mix(color, config.COLORS["panel_background"], 0.82))
    arcade.draw_lbwh_rectangle_filled(x, y, 3, 35, color)
    draw_text(title, x + 10, y + 28, color, config.FONT_SIZE_AUX, bold=True, anchor_y="top")
    draw_text(_truncate(text, 39), x + 10, y + 14, config.COLORS["muted_text"], config.FONT_SIZE_AUX, anchor_y="top")


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


def _preview_lines(text: str, limit: int, width: int) -> list[str]:
    if not text:
        return ["无 Payload"]
    return _wrapped_json_lines(text, width, limit)


def _wrapped_json_lines(text: str, width: int, limit: int) -> list[str]:
    result: list[str] = []
    for raw in text.splitlines() or [text]:
        line = raw
        while len(line) > width and len(result) < limit:
            result.append(line[:width])
            line = line[width:]
        if len(result) < limit:
            result.append(line)
        if len(result) >= limit:
            break
    if len(text.splitlines()) > len(result) and result:
        result[-1] = _truncate(result[-1], max(4, width - 3)) + "..."
    return result


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
