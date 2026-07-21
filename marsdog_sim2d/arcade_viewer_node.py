"""Program entry point for the MarsDog Arcade/ROS2 2D viewer."""

from __future__ import annotations

import json
import logging
import math
import queue
import threading
import time
from typing import Sequence

import arcade
import rclpy
from rclpy.executors import MultiThreadedExecutor

from . import config
from .event_injector import (
    InjectionCommand,
    build_custom_injection_command,
    build_scenario_command,
    default_field_values,
    field_max_chars,
    next_field_id,
    place_injection_command,
    resolve_emotion_output,
    resolve_need_output,
)
from .renderer import WorldRenderer
from .ros_bridge import RosBridge
from .sim_state import SimEvent, SimState
from .virtual_executor import LocalVirtualRunner
from .widgets import StatusWidgets

LOGGER = logging.getLogger("marsdog_sim2d")


class SimWindow(arcade.Window):
    """Arcade window that owns rendering and state updates."""

    def __init__(
        self,
        sim_state: SimState,
        event_queue: queue.Queue[SimEvent],
        injection_queue: queue.Queue[InjectionCommand],
    ) -> None:
        super().__init__(
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT,
            config.WINDOW_TITLE,
            resizable=True,
        )
        self.set_minimum_size(config.MIN_WINDOW_WIDTH, config.MIN_WINDOW_HEIGHT)
        self.sim_state = sim_state
        self.event_queue = event_queue
        self.injection_queue = injection_queue
        self.renderer = WorldRenderer()
        self.widgets = StatusWidgets()
        self.local_runner = LocalVirtualRunner()
        if not self.sim_state.event_injector_fields:
            self.sim_state.event_injector_fields.update(default_field_values())
        self.sim_state.event_injector_fields.setdefault("personality_trait", "A")
        config.update_layout(
            self.width,
            self.height,
            self.sim_state.ui_left_collapsed,
            self.sim_state.ui_log_height,
        )
        self._refresh_payload_preview()
        arcade.set_background_color(config.COLORS["background"])

    def on_update(self, delta_time: float) -> None:
        del delta_time
        self.sim_state.drain_queue(self.event_queue)
        for event in self.local_runner.update():
            self.sim_state.apply_event(event)

    def on_draw(self) -> None:
        config.update_layout(
            self.width,
            self.height,
            self.sim_state.ui_left_collapsed,
            self.sim_state.ui_log_height,
        )
        self.clear()
        self.renderer.draw(self.sim_state)
        self.widgets.draw(self.sim_state)

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        config.update_layout(
            width,
            height,
            self.sim_state.ui_left_collapsed,
            self.sim_state.ui_log_height,
        )

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        del modifiers
        if self.sim_state.ui_pending_confirmation:
            if symbol == arcade.key.ESCAPE:
                self.sim_state.ui_pending_confirmation = None
            elif symbol in {arcade.key.ENTER, getattr(arcade.key, "NUM_ENTER", arcade.key.ENTER)}:
                self._confirm_pending_action()
            return
        if symbol == arcade.key.ESCAPE and self.sim_state.ui_open_select:
            self.sim_state.ui_open_select = None
            return
        if self._handle_injector_key(symbol):
            return
        if symbol == arcade.key.T:
            self._start_local_behavior("exploreRoom")
        elif symbol == arcade.key.F:
            self._start_local_behavior("seekFood")
        elif symbol == arcade.key.S:
            self._start_local_behavior("sleepNow")
        elif symbol == arcade.key.C:
            self._start_local_behavior("seekInteraction")
        elif symbol == arcade.key.W:
            self._start_local_behavior("wagTailFast")
        elif symbol == arcade.key.P:
            self._start_local_behavior("spinInCircle")
        elif symbol == arcade.key.G:
            self._start_local_behavior("cleanSelf")
        elif symbol == arcade.key.E:
            self._start_local_behavior("defecate")
        elif symbol == arcade.key.R:
            self._start_local_behavior("recharge")
        elif symbol == arcade.key.H:
            self._start_local_behavior("hideAway")

    def on_text(self, text: str) -> None:
        field_id = self.sim_state.ui_text_focus
        if not field_id or not text:
            return
        if field_id == "log_search":
            self.sim_state.ui_log_search = (self.sim_state.ui_log_search + text)[:80]
            return
        value = self.sim_state.event_injector_fields.get(field_id, "")
        max_chars = field_max_chars(field_id)
        self.sim_state.event_injector_fields[field_id] = (value + text)[:max_chars]
        self._refresh_payload_preview()

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        del dx, dy
        self.widgets.set_hover(x, y)

    def on_mouse_press(
        self,
        x: float,
        y: float,
        button: int,
        modifiers: int,
    ) -> None:
        del modifiers
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        item = self.widgets.hit_test(x, y)
        if item is None:
            self.sim_state.ui_open_select = None
            self.sim_state.ui_text_focus = None
            if self._point_in_world(x, y):
                if self.sim_state.ui_pending_placement:
                    self._place_pending_in_scene(x, y)
                else:
                    selected = self.renderer.hit_test(self.sim_state, x, y)
                    self.sim_state.ui_selected_object = selected
            return
        action = str(item["action"])
        if self.sim_state.ui_pending_confirmation and action not in {
            "cancel_confirmation",
            "confirm_action",
        }:
            return
        if action == "collapse_left":
            self.sim_state.ui_left_collapsed = True
            self.sim_state.ui_open_select = None
            config.update_layout(self.width, self.height, True, self.sim_state.ui_log_height)
            return
        if action == "expand_left":
            self.sim_state.ui_left_collapsed = False
            config.update_layout(self.width, self.height, False, self.sim_state.ui_log_height)
            return
        if action in {"input_tab", "collapsed_tab"}:
            self.sim_state.ui_input_tab = str(item["tab"])
            self.sim_state.ui_left_scroll = 0.0
            if action == "collapsed_tab":
                self.sim_state.ui_left_collapsed = False
            self.sim_state.ui_open_select = None
            self.sim_state.ui_text_focus = None
            self._normalize_group_for_tab()
            self._refresh_payload_preview()
            return
        if action == "select_toggle":
            select_id = str(item["select_id"])
            self.sim_state.ui_open_select = (
                None if self.sim_state.ui_open_select == select_id else select_id
            )
            self.sim_state.ui_text_focus = None
            return
        if action == "select_option":
            self._apply_select_option(item)
            return
        if action == "focus_input":
            field_id = str(item["field_id"])
            self.sim_state.ui_text_focus = field_id
            self.sim_state.event_injector_focused_field = field_id
            self.sim_state.ui_open_select = None
            return
        if action == "focus_log_search":
            self.sim_state.ui_text_focus = "log_search"
            self.sim_state.ui_open_select = None
            return
        if action == "placement_mode":
            group = str(item["group"])
            if self.sim_state.ui_pending_placement and self.sim_state.ui_pending_placement.get("group") == group:
                self.sim_state.ui_pending_placement = None
            else:
                self.sim_state.ui_pending_placement = {
                    "group": group,
                    "kind": self._placement_kind(group),
                    "x": None,
                    "y": None,
                }
            self._refresh_payload_preview()
            return
        if action in {"send_event", "send_command"}:
            self._send_custom_injection("Audio" if action == "send_command" else None)
            return
        if action == "command_quick":
            self.sim_state.event_injector_fields["audio_command_id"] = str(item["command_id"])
            self.sim_state.event_injector_fields["audio_event_type"] = "EVT_VOICE_COMMAND_KNOWN"
            self._refresh_payload_preview()
            self._send_custom_injection("Audio")
            return
        if action == "publish_state_output":
            self._request_state_output()
            return
        if action == "scenario":
            self._request_scenario(str(item["scenario_id"]))
            return
        if action == "toggle_card":
            card_id = str(item["card_id"])
            if card_id in self.sim_state.ui_collapsed_cards:
                self.sim_state.ui_collapsed_cards.remove(card_id)
            else:
                self.sim_state.ui_collapsed_cards.add(card_id)
            return
        if action == "behavior_context":
            self.sim_state.ui_behavior_context_expanded = bool(item["expanded"])
            return
        if action == "toggle_fov":
            self.sim_state.ui_show_fov = not self.sim_state.ui_show_fov
            return
        if action == "toggle_log_filter":
            source = str(item["source"])
            if source in self.sim_state.ui_log_filters:
                self.sim_state.ui_log_filters.remove(source)
            else:
                self.sim_state.ui_log_filters.add(source)
            return
        if action == "toggle_log_pause":
            self.sim_state.ui_log_paused = not self.sim_state.ui_log_paused
            self.sim_state.ui_log_pause_snapshot = (
                [dict(record) for record in self.sim_state.event_records]
                if self.sim_state.ui_log_paused
                else []
            )
            return
        if action == "toggle_log_auto":
            self.sim_state.ui_log_auto_scroll = not self.sim_state.ui_log_auto_scroll
            return
        if action == "clear_log":
            self.sim_state.event_records.clear()
            self.sim_state.event_log.clear()
            self.sim_state.ui_selected_event_id = None
            self.sim_state.ui_log_pause_snapshot = []
            return
        if action == "select_event":
            self.sim_state.ui_selected_event_id = int(item["event_id"])
            self.sim_state.ui_selected_object = None
            return
        if action == "close_event_detail":
            self.sim_state.ui_selected_event_id = None
            return
        if action == "copy_event_payload":
            self._copy_selected_payload()
            return
        if action == "close_object_detail":
            self.sim_state.ui_selected_object = None
            return
        if action == "log_resize":
            self.sim_state.ui_dragging_log = True
            return
        if action == "cancel_confirmation":
            self.sim_state.ui_pending_confirmation = None
            return
        if action == "confirm_action":
            self._confirm_pending_action()

    def on_mouse_release(
        self,
        x: float,
        y: float,
        button: int,
        modifiers: int,
    ) -> None:
        del x, y, button, modifiers
        self.sim_state.ui_dragging_log = False

    def on_mouse_drag(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> None:
        del x, dx, dy, buttons, modifiers
        if not self.sim_state.ui_dragging_log:
            return
        self.sim_state.ui_log_height = max(
            config.MIN_LOG_HEIGHT,
            min(config.MAX_LOG_HEIGHT, y),
        )
        config.update_layout(
            self.width,
            self.height,
            self.sim_state.ui_left_collapsed,
            self.sim_state.ui_log_height,
        )

    def on_mouse_scroll(
        self,
        x: float,
        y: float,
        scroll_x: float,
        scroll_y: float,
    ) -> None:
        del scroll_x
        if (
            config.LEFT_PANEL_LEFT <= x <= config.LEFT_PANEL_RIGHT
            and config.BOTTOM_LOG_HEIGHT <= y <= config.TOP_BAR_BOTTOM
            and config.LEFT_PANEL_WIDTH > config.COLLAPSED_LEFT_PANEL_WIDTH + 1
        ):
            self.sim_state.ui_left_scroll = max(
                0.0,
                min(
                    self.widgets.left_scroll_max,
                    self.sim_state.ui_left_scroll - scroll_y * 34.0,
                ),
            )
            return
        if config.RIGHT_PANEL_LEFT <= x <= config.RIGHT_PANEL_RIGHT and y >= config.BOTTOM_LOG_HEIGHT:
            self.sim_state.ui_right_scroll = max(
                0.0,
                min(
                    self.widgets.right_scroll_max,
                    self.sim_state.ui_right_scroll - scroll_y * 34.0,
                ),
            )
            return
        if y <= config.BOTTOM_LOG_HEIGHT:
            self.sim_state.ui_log_auto_scroll = False
            self.sim_state.ui_log_scroll = max(0, self.sim_state.ui_log_scroll - int(scroll_y * 2))

    def _start_local_behavior(self, behavior_name: str) -> None:
        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(behavior_name)
        self.sim_state.apply_event(event)
        LOGGER.info("Started local virtual behavior self-test: %s", behavior_name)

    def _handle_injector_key(self, symbol: int) -> bool:
        field_id = self.sim_state.ui_text_focus
        if not field_id:
            return False

        enter_keys = {arcade.key.ENTER}
        num_enter = getattr(arcade.key, "NUM_ENTER", None)
        if num_enter is not None:
            enter_keys.add(num_enter)
        if symbol in enter_keys:
            if field_id == "log_search":
                self.sim_state.ui_text_focus = None
            elif self.sim_state.ui_input_tab == "State":
                self._request_state_output()
            elif self.sim_state.ui_input_tab == "Scenario":
                self._request_scenario(self.sim_state.ui_selected_scenario)
            else:
                self._send_custom_injection(
                    "Audio" if self.sim_state.ui_input_tab == "Command" else None
                )
            return True
        if symbol == arcade.key.ESCAPE:
            self.sim_state.event_injector_focused_field = None
            self.sim_state.ui_text_focus = None
            self.sim_state.ui_open_select = None
            return True
        if symbol == arcade.key.TAB:
            if field_id == "log_search":
                self.sim_state.ui_text_focus = None
            else:
                next_field = next_field_id(self.sim_state.event_injector_group, field_id)
                self.sim_state.event_injector_focused_field = next_field
                self.sim_state.ui_text_focus = next_field
            return True
        if symbol == arcade.key.BACKSPACE:
            self._delete_focused_character(field_id)
            return True
        if symbol == arcade.key.DELETE:
            self._clear_focused_value(field_id)
            return True
        return True

    def _send_custom_injection(self, forced_group: str | None = None) -> None:
        self.sim_state.event_injector_fields = {
            **default_field_values(),
            **self.sim_state.event_injector_fields,
        }
        group = forced_group or self.sim_state.event_injector_group
        fields = self._resolved_fields(group)
        command = build_custom_injection_command(
            group,
            fields,
        )
        placement = self.sim_state.ui_pending_placement
        if placement and placement.get("group") == group and placement.get("normalized_x") is not None:
            command = place_injection_command(
                command,
                float(placement["normalized_x"]),
                float(placement["normalized_y"]),
            )
            if group == "Vision" and placement.get("kind") == "human":
                normalized_x = float(placement["normalized_x"])
                normalized_y = float(placement["normalized_y"])
                self.sim_state.user_x = config.SCENE_LOGICAL_LEFT + normalized_x * (
                    config.SCENE_LOGICAL_RIGHT - config.SCENE_LOGICAL_LEFT
                )
                self.sim_state.user_y = config.SCENE_LOGICAL_TOP - normalized_y * (
                    config.SCENE_LOGICAL_TOP - config.SCENE_LOGICAL_BOTTOM
                )
        self.injection_queue.put(command)
        self.sim_state.ui_pending_placement = None
        self._refresh_payload_preview()
        LOGGER.info("Queued custom ROS2 event injection: %s", command.label)

    def _apply_select_option(self, item: dict[str, object]) -> None:
        target = str(item.get("target") or "")
        value = str(item.get("value") or "")
        if target == "event_group":
            self.sim_state.event_injector_group = value
            self.sim_state.ui_left_scroll = 0.0
        elif target == "field":
            field_id = str(item.get("field_id") or "")
            self.sim_state.event_injector_fields[field_id] = value
        self.sim_state.ui_open_select = None
        self._refresh_payload_preview()

    def _normalize_group_for_tab(self) -> None:
        if self.sim_state.ui_input_tab == "Event" and self.sim_state.event_injector_group not in {"Audio", "Vision", "Result"}:
            self.sim_state.event_injector_group = "Audio"
        elif self.sim_state.ui_input_tab == "State" and self.sim_state.event_injector_group not in {"Need", "Emotion", "Personality"}:
            self.sim_state.event_injector_group = "Need"
        elif self.sim_state.ui_input_tab == "Command":
            self.sim_state.event_injector_group = "Audio"
            self.sim_state.event_injector_fields["audio_event_type"] = "EVT_VOICE_COMMAND_KNOWN"

    def _refresh_payload_preview(self) -> None:
        try:
            if self.sim_state.ui_input_tab == "Scenario":
                command = build_scenario_command(self.sim_state.ui_selected_scenario)
            else:
                group = "Audio" if self.sim_state.ui_input_tab == "Command" else self.sim_state.event_injector_group
                command = build_custom_injection_command(group, self._resolved_fields(group))
                placement = self.sim_state.ui_pending_placement
                if placement and placement.get("group") == group and placement.get("normalized_x") is not None:
                    command = place_injection_command(
                        command,
                        float(placement["normalized_x"]),
                        float(placement["normalized_y"]),
                    )
            self.sim_state.ui_preview_topics = list(dict.fromkeys(message.topic for message in command.messages))
            preview = [
                {"topic": message.topic, "payload": message.payload}
                for message in command.messages
            ]
            self.sim_state.ui_payload_preview = json.dumps(preview, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            self.sim_state.ui_preview_topics = []
            self.sim_state.ui_payload_preview = f"Preview unavailable: {exc}"

    def _resolved_fields(self, group: str) -> dict[str, str]:
        fields = {**default_field_values(), **self.sim_state.event_injector_fields}
        if group == "Need":
            level, event_type = resolve_need_output(
                fields.get("need_demand", "Hunger"),
                _safe_float(fields.get("need_value"), 82.0),
            )
            fields["need_level"] = level
            fields["need_event_type"] = event_type
        if group == "Emotion":
            level, event_type, _level_range = resolve_emotion_output(
                fields.get("emotion_name", "Joy"),
                _safe_float(fields.get("emotion_value"), 90.0),
            )
            fields["emotion_level"] = level
            fields["emotion_event_type"] = event_type or ""
        return fields

    def _request_state_output(self) -> None:
        group = self.sim_state.event_injector_group
        fields = self._resolved_fields(group)
        dangerous = fields.get("need_level") == "OVERFLOW" or (
            group == "Emotion"
            and fields.get("emotion_name") == "Fear"
            and fields.get("emotion_level") == "HIGH"
        )
        if dangerous:
            self.sim_state.ui_pending_confirmation = {
                "kind": "state_output",
                "group": group,
                "message": f"确认发布处于高风险等级的模拟 {group} 输出？",
            }
            return
        self._send_custom_injection(group)

    def _request_scenario(self, scenario_id: str) -> None:
        self.sim_state.ui_selected_scenario = scenario_id
        self._refresh_payload_preview()
        if scenario_id in {"high_hunger", "low_energy", "fear_response"}:
            self.sim_state.ui_pending_confirmation = {
                "kind": "scenario",
                "scenario_id": scenario_id,
                "message": f"确认运行场景“{scenario_id}”？这可能触发紧急行为。",
            }
            return
        self._send_scenario(scenario_id)

    def _send_scenario(self, scenario_id: str) -> None:
        command = build_scenario_command(scenario_id)
        self.injection_queue.put(command)
        LOGGER.info("Queued manual ROS2 scenario: %s", command.label)

    def _confirm_pending_action(self) -> None:
        pending = self.sim_state.ui_pending_confirmation or {}
        self.sim_state.ui_pending_confirmation = None
        if pending.get("kind") == "scenario":
            self._send_scenario(str(pending.get("scenario_id") or ""))
        elif pending.get("kind") == "state_output":
            self._send_custom_injection(str(pending.get("group") or self.sim_state.event_injector_group))

    def _place_pending_in_scene(self, x: float, y: float) -> None:
        pending = self.sim_state.ui_pending_placement
        if not pending:
            return
        normalized_x = max(0.0, min(1.0, (x - config.WORLD_LEFT) / max(1.0, config.WORLD_WIDTH)))
        normalized_y = max(0.0, min(1.0, (config.WORLD_TOP - y) / max(1.0, config.WORLD_HEIGHT)))
        pending.update(
            x=x,
            y=y,
            normalized_x=normalized_x,
            normalized_y=normalized_y,
            confidence=_safe_float(self.sim_state.event_injector_fields.get("audio_confidence"), 0.9),
        )
        if pending.get("group") == "Audio":
            dog_x, dog_y = self.renderer.scene_to_screen(self.sim_state.dog_x, self.sim_state.dog_y)
            angle = math.degrees(math.atan2(y - dog_y, x - dog_x)) - self.sim_state.dog_heading
            while angle > 180:
                angle -= 360
            while angle < -180:
                angle += 360
            self.sim_state.event_injector_fields["audio_wake_angle"] = f"{angle:.1f}"
        self._refresh_payload_preview()

    def _placement_kind(self, group: str) -> str:
        if group == "Audio":
            return "audio"
        if self.sim_state.event_injector_fields.get("vision_object"):
            return "object"
        return "human"

    def _delete_focused_character(self, field_id: str) -> None:
        if field_id == "log_search":
            self.sim_state.ui_log_search = self.sim_state.ui_log_search[:-1]
            return
        value = self.sim_state.event_injector_fields.get(field_id, "")
        self.sim_state.event_injector_fields[field_id] = value[:-1]
        self._refresh_payload_preview()

    def _clear_focused_value(self, field_id: str) -> None:
        if field_id == "log_search":
            self.sim_state.ui_log_search = ""
            return
        self.sim_state.event_injector_fields[field_id] = ""
        self._refresh_payload_preview()

    def _copy_selected_payload(self) -> None:
        record = next(
            (
                item
                for item in self.sim_state.event_records
                if item.get("id") == self.sim_state.ui_selected_event_id
            ),
            None,
        )
        if record is None:
            return
        self.set_clipboard_text(
            json.dumps(record.get("payload") or {}, ensure_ascii=False, indent=2, default=str)
        )

    @staticmethod
    def _point_in_world(x: float, y: float) -> bool:
        return (
            config.WORLD_LEFT <= x <= config.WORLD_RIGHT
            and config.WORLD_BOTTOM <= y <= config.WORLD_TOP
        )


def main(args: Sequence[str] | None = None) -> None:
    """Start ROS2 in a background thread and Arcade in the main thread."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    LOGGER.info("Starting marsdog_sim2d")

    event_queue: queue.Queue[SimEvent] = queue.Queue()
    injection_queue: queue.Queue[InjectionCommand] = queue.Queue()
    sim_state = SimState()
    ros_node: RosBridge | None = None
    ros_thread: threading.Thread | None = None

    try:
        rclpy.init(args=list(args) if args is not None else None)
        ros_node = RosBridge(event_queue, injection_queue)
        ros_thread = threading.Thread(
            target=_spin_ros,
            args=(ros_node,),
            name="marsdog_sim2d_ros_spin",
            daemon=True,
        )
        ros_thread.start()

        SimWindow(sim_state, event_queue, injection_queue)
        LOGGER.info("Arcade window initialized")
        arcade.run()
    except Exception:
        LOGGER.exception("Arcade/ROS2 viewer failed")
        raise
    finally:
        LOGGER.info("Shutting down marsdog_sim2d")
        if rclpy.ok():
            rclpy.shutdown()
        if ros_thread is not None:
            ros_thread.join(timeout=2.0)
        if ros_node is not None:
            ros_node.destroy_node()
        LOGGER.info("ROS2 shutdown complete")


def _spin_ros(ros_node: RosBridge) -> None:
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(ros_node)
    try:
        executor.spin()
    except Exception as exc:  # pragma: no cover - depends on ROS2 runtime shutdown
        if rclpy.ok():
            LOGGER.exception("ROS2 spin failed: %s", exc)
    finally:
        executor.shutdown()


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    main()
