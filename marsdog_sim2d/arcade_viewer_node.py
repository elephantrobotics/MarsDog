"""Program entry point for the MarsDog Arcade/ROS2 2D viewer."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import math
import queue
import random
import threading
import time
from typing import Sequence

import arcade
import rclpy
from rclpy.executors import MultiThreadedExecutor

from . import config
from .event_injector import (
    InjectionCommand,
    MANUAL_SOURCE,
    build_custom_injection_command,
    build_scenario_command,
    default_field_values,
    field_max_chars,
    next_field_id,
    place_injection_command,
    resolve_emotion_output,
    resolve_need_output,
)
from .feeding_interface import FeedingCoordinator
from .renderer import WorldRenderer
from .ros_bridge import RosBridge
from .sim_state import SimEvent, SimState
from .virtual_executor import LocalVirtualRunner
from .voice_commands import (
    VoiceCommandSpec,
    is_external_command_behavior,
    resolve_voice_command,
)
from .widgets import StatusWidgets

LOGGER = logging.getLogger("marsdog_sim2d")

EMOTION_IDLE_BEHAVIORS = {
    "CALM": ("expressCalmAlone", 4.5),
    "JOY": ("expressJoyAlone", 3.2),
    "EXCITE": ("expressExcitementAlone", 3.8),
    "ANXIETY": ("expressAnxietyAlone", 3.2),
    "FEAR": ("expressFearAlone", 3.2),
    "CURIOUS": ("expressCuriosityAlone", 3.6),
}
CALM_IDLE_SEQUENCE = (
    ("expressCalmAlone", 4.5, None),
    ("roll_over", 3.2, "ACT_TRICK_ROLL_OVER"),
    ("expressExcitementAlone", 3.8, "ACT_SHAKE_TOY"),
)
CALM_IDLE_PLAY_DELAY_OPTIONS_SEC = (1.0, 2.0, 3.0)
EMOTION_IDLE_INITIAL_DELAY_SEC = 2.0
EMOTION_IDLE_COOLDOWN_SEC = 4.0
CALM_IDLE_TRANSITION_SEC = 0.12
VOICE_COMMAND_ACTION_GRACE_SEC = 0.35
MANUAL_NEED_ACTION_GRACE_SEC = 0.35
VISUAL_ACTION_GRACE_SEC = 2.0
FOLLOW_USER_OFFSET_X = 112.0
FOLLOW_USER_OFFSET_Y = 50.0
FOLLOW_USER_SPEED = 185.0
FOLLOW_USER_ARRIVAL_DISTANCE = 8.0
FOLLOW_STATIONARY_TIMEOUT_SEC = 30.0

MANUAL_NEED_BEHAVIORS = {
    "HUNGER": ("seekFood", 5.5),
    "BLADDER": ("barkShortAlert", 5.0),
    "SLEEPINESS": ("sleepNow", 6.0),
    "CLEANLINESS": ("lickPaws", 4.5),
    "ENERGY": ("recharge", 5.5),
    "SOCIAL": ("seekInteraction", 4.5),
    "EXPLORATION": ("exploreRoom", 5.5),
}
MANUAL_NEED_RECOVERY = {
    "HUNGER": ("Hunger", 42.0),
    "BLADDER": ("Bladder", 35.0),
    "SLEEPINESS": ("Sleepiness", 30.0),
    "CLEANLINESS": ("Cleanliness", 38.0),
    "ENERGY": ("Energy", 82.0),
    "SOCIAL": ("Social", 34.0),
    "EXPLORATION": ("Exploration", 32.0),
}
INTERNAL_NEED_BEHAVIORS = frozenset(
    {
        "eatNormally",
        "seekFood",
        "eatExcitedly",
        "seekFoodUrgently",
        "barkShortAlert",
        "lickPaws",
        "sleepOnSide",
        "sleepNow",
        "restInPlace",
        "recharge",
        "seekHumanInteraction",
        "seekInteraction",
        "inviteHumanToPlay",
        "exploreRoom",
        "inspectObject",
        "inspectFamiliarPlayItem",
        "inspectTrashCan",
        "inspectDeliveryBox",
        "inspectTissuePaper",
        "inspectDoor",
        "inspectDogFood",
    }
)


class SimWindow(arcade.Window):
    """Arcade window that owns rendering and state updates."""

    def __init__(
        self,
        sim_state: SimState,
        event_queue: queue.Queue[SimEvent],
        injection_queue: queue.Queue[InjectionCommand],
        feeding_coordinator: FeedingCoordinator | None = None,
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
        self.feeding_coordinator = (
            feeding_coordinator or FeedingCoordinator()
        )
        self._emotion_idle_goal_id: str | None = None
        self._voice_local_goal_id: str | None = None
        self._last_voice_audio_at: float | None = None
        self._pending_voice_command: tuple[VoiceCommandSpec, float] | None = None
        self._last_manual_need_signal_at: float | None = None
        self._pending_manual_need: tuple[str, float, float, str] | None = None
        self._manual_need_local_goal_id: str | None = None
        self._manual_need_local_demand: str | None = None
        self._manual_need_triggered_at: float | None = None
        self._manual_hunger_phase: str | None = None
        self._last_visual_event_at: float | None = None
        self._last_visual_activity_signature: tuple[str, ...] | None = None
        self._visual_idle_block_until = 0.0
        self._calm_idle_index = 0
        self._next_emotion_idle_at = time.monotonic() + EMOTION_IDLE_INITIAL_DELAY_SEC
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
        self.sim_state.drain_queue(self.event_queue)
        self._sync_feeding_interface()
        if self.sim_state.ui_abnormal_simulation_active:
            return
        self._replay_deferred_abnormal_event()
        if (
            self.sim_state.ui_food_eating_until > 0.0
            and time.monotonic() >= self.sim_state.ui_food_eating_until
        ):
            self.sim_state.finish_food_eating_display()
        if (
            self.sim_state.action_status == "running"
            and _state_is_follow_action(self.sim_state)
            and self.sim_state.ui_follow_user_requested
            and not _follow_is_blocked_by_internal_need(self.sim_state)
        ):
            self.sim_state.ui_follow_user_active = True
            self.sim_state.ui_user_visible = True
            self.sim_state.ui_follow_goal_id = self.sim_state.action_goal_id
        self._capture_latest_visual_activity()
        self._capture_latest_voice_command()
        self._expire_stationary_follow_if_needed()
        self._capture_latest_manual_need()
        self._yield_emotion_idle_to_external_action()
        self._yield_local_voice_to_external_action()
        self._yield_local_need_to_external_action()
        self._maybe_start_manual_need()
        self._maybe_start_voice_command()
        for event in self.local_runner.update(self.sim_state):
            self.sim_state.apply_event(event)
        self._advance_manual_need_completion()
        self.sim_state.advance_virtual_motion(delta_time)
        self._advance_external_virtual_user_follow(delta_time)
        if self._emotion_idle_goal_id is not None and self.local_runner.plan is None:
            self._emotion_idle_goal_id = None
        if self._voice_local_goal_id is not None and self.local_runner.plan is None:
            self._voice_local_goal_id = None
        if (
            self._manual_need_local_goal_id is not None
            and self.local_runner.plan is None
        ):
            self._manual_need_local_goal_id = None
            self._manual_need_local_demand = None
            self._manual_need_triggered_at = None
            self._manual_hunger_phase = None
        self._maybe_resume_requested_follow()
        # This is a global quiet-state fallback, not a wake-up callback.
        # Every frame can enter it once needs, external commands and
        # perception grace periods have all released control.
        self._maybe_start_emotion_idle()
        self._sync_feeding_interface()

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
            self._start_local_behavior("expressJoyAlone")
        elif symbol == arcade.key.P:
            self._start_local_behavior("spin_around")
        elif symbol == arcade.key.G:
            self._start_local_behavior("lickPaws")
        elif symbol == arcade.key.E:
            self._start_local_behavior("barkShortAlert")
        elif symbol == arcade.key.R:
            self._start_local_behavior("recharge")
        elif symbol == arcade.key.H:
            self._start_local_behavior("expressFearAlone")

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
        if self.sim_state.ui_dragging_user and self.sim_state.ui_user_visible:
            _move_virtual_user_from_screen(self.sim_state, x, y)
        self.widgets.set_hover(x, y)

    def on_mouse_press(
        self,
        x: float,
        y: float,
        button: int,
        modifiers: int,
    ) -> None:
        del modifiers
        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self.sim_state.ui_user_visible:
                _reset_virtual_user(self.sim_state)
            return
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
                    if selected == "user" and self.sim_state.ui_user_visible:
                        if self.sim_state.ui_dragging_user:
                            _move_virtual_user_from_screen(
                                self.sim_state,
                                x,
                                y,
                            )
                        _toggle_virtual_user_motion(self.sim_state)
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
            self.sim_state.event_injector_fields["audio_asr_text"] = str(
                item.get("asr_text") or ""
            )
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
        if action == "toggle_virtual_user":
            was_visible = self.sim_state.ui_user_visible
            _toggle_virtual_user(self.sim_state)
            if was_visible and not self.sim_state.ui_user_visible:
                self._stop_virtual_user_follow("Virtual person removed from UI")
            return
        if action == "toggle_abnormal_simulation":
            self._toggle_abnormal_simulation()
            return
        if action == "toggle_bowl_food":
            self._toggle_bowl_food()
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
        del dx, dy, buttons, modifiers
        if self.sim_state.ui_dragging_user and self.sim_state.ui_user_visible:
            _move_virtual_user_from_screen(self.sim_state, x, y)
            return
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
        if self.sim_state.ui_abnormal_simulation_active:
            return
        self._emotion_idle_goal_id = None
        self._voice_local_goal_id = None
        self._pending_voice_command = None
        self._calm_idle_index = 0
        self._next_emotion_idle_at = time.monotonic() + CALM_IDLE_TRANSITION_SEC
        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(behavior_name)
        self.sim_state.apply_event(event)
        LOGGER.info("Started local virtual behavior self-test: %s", behavior_name)

    def _toggle_abnormal_simulation(self) -> None:
        if self.sim_state.ui_abnormal_simulation_active:
            paused_duration = _deactivate_abnormal_simulation(
                self.sim_state
            )
            resume_runner = getattr(self.local_runner, "resume", None)
            if callable(resume_runner):
                resume_runner()
            self._last_voice_audio_at = _received_at(
                self.sim_state.latest_audio_event
            )
            self._last_visual_event_at = _received_at(
                self.sim_state.latest_visual_event
            )
            self._next_emotion_idle_at += paused_duration
            if (
                self.local_runner.plan is None
                and self.sim_state.action_status
                not in {"pending", "running"}
                and not self.sim_state.ui_abnormal_replay_active
            ):
                self._next_emotion_idle_at = (
                    time.monotonic() + CALM_IDLE_TRANSITION_SEC
                )
            LOGGER.info(
                "UI abnormal simulation cleared; paused behavior restored"
            )
            return

        pause_runner = getattr(self.local_runner, "pause", None)
        if callable(pause_runner):
            pause_runner()
        _activate_abnormal_simulation(self.sim_state)
        LOGGER.info("UI abnormal simulation activated")

    def _replay_deferred_abnormal_event(self) -> None:
        """Resume buffered external stages at a visible, ordered pace."""

        state = self.sim_state
        if not state.ui_abnormal_replay_active:
            return
        if state.virtual_motion_active():
            return
        now = time.monotonic()
        if now < state.ui_abnormal_replay_next_at:
            return
        if not state.ui_abnormal_deferred_events:
            state.ui_abnormal_replay_active = False
            state.ui_abnormal_replay_goal_id = None
            state.ui_abnormal_replay_next_at = 0.0
            return

        deferred = state.ui_abnormal_deferred_events.popleft()
        replayed = SimEvent(
            deferred.kind,
            deferred.topic,
            {
                **deferred.payload,
                "_ui_abnormal_replay": True,
            },
            deferred.summary,
            received_at=time.time(),
            format_hint=deferred.format_hint,
        )
        state.apply_event(replayed)
        state.ui_abnormal_replay_next_at = (
            now + (0.45 if deferred.kind == "action_feedback" else 0.25)
        )

    def _toggle_bowl_food(self) -> None:
        """Add/remove food; external eating waits for the ROS handshake."""

        self.sim_state.ui_bowl_has_food = not self.sim_state.ui_bowl_has_food
        if self.sim_state.ui_bowl_has_food:
            if self.sim_state.ui_food_waiting:
                local_food_goal = (
                    self.local_runner.plan is not None
                    and self.local_runner.plan.goal_id
                    == self.sim_state.ui_food_wait_goal_id
                )
                if local_food_goal:
                    if (
                        getattr(self, "_manual_hunger_phase", None)
                        == "seeking"
                    ):
                        SimWindow._start_manual_hunger_eating(self)
                    else:
                        # UI-only keyboard behavior has no external action
                        # system to call the service, so it authorizes itself.
                        self.sim_state.ui_food_eating_authorized = True
                        self.sim_state.release_food_wait()
            SimWindow._sync_feeding_interface(self)
            LOGGER.info(
                "UI food added to bowl%s",
                (
                    ""
                    if not self.sim_state.ui_food_waiting
                    else "; waiting for action-system eating authorization"
                ),
            )
            return

        self.sim_state.ui_food_eating_authorized = False
        current_action = (
            self.sim_state.action_current_action
            or self.sim_state.action_visual_action
            or ""
        )
        self.sim_state.gate_food_action(
            current_action,
            motion_queued=self.sim_state.virtual_motion_active(),
        )
        SimWindow._sync_feeding_interface(self)
        LOGGER.info("UI food removed from bowl")

    def _sync_feeding_interface(self) -> None:
        coordinator = getattr(self, "feeding_coordinator", None)
        if coordinator is None:
            return
        coordinator.update_from_ui(
            food_available=self.sim_state.ui_bowl_has_food,
            dog_at_bowl=_food_interaction_ready(self.sim_state),
            waiting_for_food=self.sim_state.ui_food_waiting,
            eating_authorized=self.sim_state.ui_food_eating_authorized,
            active_goal_id=self.sim_state.action_goal_id,
        )

    def _capture_latest_visual_activity(self) -> None:
        visual = self.sim_state.latest_visual_event or {}
        try:
            received_at = float(visual.get("received_at"))
        except (TypeError, ValueError):
            return
        if self._last_visual_event_at == received_at:
            return
        self._last_visual_event_at = received_at

        signature = _visual_activity_signature(visual)
        if signature is None:
            self._last_visual_activity_signature = None
            return
        if signature == self._last_visual_activity_signature:
            return
        self._last_visual_activity_signature = signature

        now = time.monotonic()
        self._visual_idle_block_until = now + VISUAL_ACTION_GRACE_SEC
        self._next_emotion_idle_at = max(
            self._next_emotion_idle_at,
            self._visual_idle_block_until,
        )
        if self._emotion_idle_goal_id is not None and self.local_runner.plan is not None:
            cancel_event = self.local_runner.cancel(
                "Interrupted by visual perception event"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
            self._emotion_idle_goal_id = None
            LOGGER.info(
                "Stopped calm idle animation for visual activity: %s",
                ",".join(signature),
            )

    def _capture_latest_voice_command(self) -> None:
        audio = self.sim_state.latest_audio_event or {}
        try:
            received_at = float(audio.get("received_at"))
        except (TypeError, ValueError):
            return
        if self._last_voice_audio_at == received_at:
            return
        self._last_voice_audio_at = received_at

        command = resolve_voice_command(audio)
        if command is not None and _is_stop_behavior(command.behavior_name):
            SimWindow._handle_stop_voice_command(self)
            return
        follow_requested = (
            command is not None
            and _is_follow_behavior(command.behavior_name)
        )
        if follow_requested and not self.sim_state.ui_user_visible:
            self.sim_state.ui_follow_user_requested = False
            self.sim_state.ui_follow_user_active = False
            self.sim_state.ui_follow_goal_id = None
            self._pending_voice_command = None
            self.sim_state.ui_pending_confirmation = {
                "kind": "alert",
                "title": "提示",
                "message": "没有识别到主人",
            }
            LOGGER.info(
                "Ignored follow command because no virtual owner is visible"
            )
            return
        if follow_requested:
            self.sim_state.ui_follow_user_requested = True
            self.sim_state.ui_follow_stationary_since = time.monotonic()
            self.sim_state.ui_follow_suppressed_goal_id = None
        if command is not None and _voice_is_blocked_by_internal_need(self.sim_state):
            self._pending_voice_command = None
            if follow_requested:
                self.sim_state.ui_follow_user_active = False
                self.sim_state.ui_follow_goal_id = None
            LOGGER.info(
                "Recognized voice command %s, but internal need keeps priority",
                command.behavior_name,
            )
            return
        if command is not None:
            self.sim_state.ui_follow_user_active = follow_requested
            self.sim_state.ui_follow_goal_id = None
        if (
            command is not None
            and self._emotion_idle_goal_id is not None
            and self.local_runner.plan is not None
        ):
            cancel_event = self.local_runner.cancel(
                "Interrupted by recognized voice command"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
            self._emotion_idle_goal_id = None
        self._pending_voice_command = (
            (command, received_at)
            if command is not None
            else None
        )

    def _handle_stop_voice_command(self) -> bool:
        """Immediately end owner-command presentation without touching needs."""

        internal_need_active = _internal_need_owns_control(self)
        pending_voice = self._pending_voice_command
        pending_was_external = (
            pending_voice is not None
            and is_external_command_behavior(
                pending_voice[0].behavior_name
            )
        )
        self._pending_voice_command = None

        # Stop also clears an external Follow request that was paused behind a
        # need, but it must never cancel the need plan that currently owns the
        # local runner.
        follow_was_requested = (
            self.sim_state.ui_follow_user_requested
            or self.sim_state.ui_follow_user_active
        )
        self.sim_state.ui_follow_user_requested = False
        self.sim_state.ui_follow_user_active = False
        self.sim_state.ui_follow_goal_id = None
        self.sim_state.ui_follow_stationary_since = None
        self.sim_state.ui_owner_approach_goal_id = None
        self.sim_state.ui_owner_action_hold_until = 0.0

        stopped = pending_was_external or follow_was_requested
        plan = self.local_runner.plan
        local_voice_goal_id = self._voice_local_goal_id
        if (
            not internal_need_active
            and plan is not None
            and local_voice_goal_id is not None
            and plan.goal_id == local_voice_goal_id
            and is_external_command_behavior(plan.behavior_name)
        ):
            cancel_event = self.local_runner.cancel(
                "Stopped by owner command"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
            stopped = True
        self._voice_local_goal_id = None

        current_goal_id = self.sim_state.action_goal_id
        current_external = (
            not internal_need_active
            and self.sim_state.action_status in {"pending", "running"}
            and (
                not str(current_goal_id or "").startswith("local-")
                or current_goal_id == local_voice_goal_id
            )
            and is_external_command_behavior(
                self.sim_state.active_behavior
            )
        )
        if (
            current_external
            and current_goal_id
            and current_goal_id != local_voice_goal_id
        ):
            self.sim_state.apply_event(
                SimEvent(
                    "action_result",
                    config.ACTION_RESULT_TOPIC,
                    {
                        "goal_id": current_goal_id,
                        "behavior_name": self.sim_state.active_behavior,
                        "status": "CANCELED",
                        "result": "interrupted",
                        "reason": "Stopped by owner command",
                    },
                    "UI stopped external owner command",
                )
            )
            self.sim_state.ui_stopped_external_goal_ids.add(
                current_goal_id
            )
            stopped = True

        # Discard command Goals that were queued but had not yet taken over the
        # current card. Late Goal/Feedback/Result packets for these ids are
        # ignored by SimState.
        for goal_id, execution in tuple(
            self.sim_state.action_executions.items()
        ):
            if str(goal_id).startswith("local-"):
                continue
            if not is_external_command_behavior(
                execution.get("behavior_name")
            ):
                continue
            self.sim_state.ui_stopped_external_goal_ids.add(goal_id)
            self.sim_state.action_executions.pop(goal_id, None)
            stopped = True

        if stopped and not internal_need_active:
            _freeze_rendered_dog(self.sim_state)
            self.sim_state.action_current_action = "-"
            self.sim_state.action_visual_action = "-"
            self.sim_state.action_pending_visual_action = None
            self.sim_state.action_unit_type = "-"
            self._next_emotion_idle_at = (
                time.monotonic() + CALM_IDLE_TRANSITION_SEC
            )

        if internal_need_active:
            LOGGER.info(
                "Ignored Stop for active internal need; cleared only paused "
                "external command requests"
            )
            return False
        LOGGER.info(
            "Stop command %s an active external command",
            "interrupted" if stopped else "found no",
        )
        return stopped

    def _capture_latest_manual_need(self) -> None:
        """Queue a UI fallback for one newly injected need transition."""

        signal = self.sim_state.internal_need_signal_event or {}
        try:
            received_at = float(signal.get("received_at"))
        except (TypeError, ValueError):
            return
        if self._last_manual_need_signal_at == received_at:
            return
        self._last_manual_need_signal_at = received_at

        raw = signal.get("raw")
        if not isinstance(raw, dict) or raw.get("manual_source") != MANUAL_SOURCE:
            return
        level = str(signal.get("level") or "").strip().upper()
        if level not in {"TRIGGERED", "OVERFLOW", "CRITICAL"}:
            self._pending_manual_need = None
            return

        demand = str(signal.get("demand") or "").strip().upper()
        behavior_spec = MANUAL_NEED_BEHAVIORS.get(demand)
        if behavior_spec is None:
            return
        behavior_name, duration = behavior_spec
        self._pending_manual_need = (
            behavior_name,
            duration,
            received_at,
            demand,
        )
        self._pending_voice_command = None
        LOGGER.info(
            "Queued manual need animation: %s -> %s",
            demand,
            behavior_name,
        )

    def _maybe_start_manual_need(self) -> None:
        pending = self._pending_manual_need
        if pending is None or self.sim_state.ui_abnormal_simulation_active:
            return
        behavior_name, duration, received_at, demand = pending

        local_goal_ids = {
            goal_id
            for goal_id in (
                self._emotion_idle_goal_id,
                self._voice_local_goal_id,
                self._manual_need_local_goal_id,
                (
                    self.local_runner.plan.goal_id
                    if self.local_runner.plan is not None
                    else None
                ),
            )
            if goal_id
        }
        if _external_action_started_after(
            self.sim_state,
            local_goal_ids,
            received_at,
        ):
            self._pending_manual_need = None
            LOGGER.info(
                "External action system accepted manual need: %s",
                demand,
            )
            return
        if self.sim_state.ros_executor_online:
            # Integrated mode waits for the behavior tree/action system and
            # must not race it with a duplicate local fallback animation.
            return
        if time.time() - received_at < MANUAL_NEED_ACTION_GRACE_SEC:
            return

        if self.local_runner.plan is not None:
            cancel_event = self.local_runner.cancel(
                "Interrupted by manually triggered internal need"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)

        self._emotion_idle_goal_id = None
        self._voice_local_goal_id = None
        self._pending_voice_command = None
        self._calm_idle_index = 0
        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(
            behavior_name,
            timeout_sec=duration,
            preferred_action=(
                "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD"
                if demand == "HUNGER"
                else None
            ),
        )
        self._manual_need_local_goal_id = (
            self.local_runner.plan.goal_id
            if self.local_runner.plan is not None
            else None
        )
        self._manual_need_local_demand = demand
        self._manual_need_triggered_at = received_at
        self._manual_hunger_phase = (
            "seeking"
            if demand == "HUNGER"
            else None
        )
        self._next_emotion_idle_at = (
            time.monotonic()
            + (
                self.local_runner.plan.duration
                if self.local_runner.plan is not None
                else duration
            )
            + CALM_IDLE_TRANSITION_SEC
        )
        self._pending_manual_need = None
        self.sim_state.apply_event(event)
        LOGGER.info(
            "Started manual need fallback animation: %s -> %s",
            demand,
            behavior_name,
        )

    def _yield_local_need_to_external_action(self) -> None:
        if (
            self._manual_need_local_goal_id is None
            or self.local_runner.plan is None
        ):
            return
        external_goal_id = _newest_external_goal_id_started_after(
            self.sim_state,
            {self._manual_need_local_goal_id},
            self._manual_need_triggered_at or 0.0,
        )
        if external_goal_id is None:
            return
        cancel_event = self.local_runner.cancel(
            "External action Goal took ownership of manual need"
        )
        if cancel_event is not None:
            self.sim_state.apply_event(cancel_event)
        self._manual_need_local_goal_id = None
        self._manual_need_local_demand = None
        self._manual_need_triggered_at = None
        self._manual_hunger_phase = None
        LOGGER.info(
            "Stopped manual need fallback; external action took ownership: %s",
            external_goal_id,
        )

    def _advance_manual_need_completion(self) -> None:
        """Continue Hunger if needed, then recover a completed manual need."""

        if (
            self._manual_need_local_goal_id is None
            or self.local_runner.plan is not None
        ):
            return
        demand = self._manual_need_local_demand
        if (
            demand == "HUNGER"
            and self._manual_hunger_phase == "seeking"
            and self.sim_state.ui_bowl_has_food
        ):
            SimWindow._start_manual_hunger_eating(self)
            return
        expected_behavior = (
            "eatNormally"
            if demand == "HUNGER" and self._manual_hunger_phase == "eating"
            else (
                MANUAL_NEED_BEHAVIORS.get(demand or "", ("", 0.0))[0]
            )
        )
        action_completed = (
            bool(expected_behavior)
            and self.sim_state.action_status == "success"
            and str(self.sim_state.active_behavior or "")
            == expected_behavior
        )
        if action_completed and demand:
            if demand == "HUNGER":
                self.sim_state.clear_food_gate()
            if _recover_manual_need_state(self.sim_state, demand):
                LOGGER.info(
                    "Manual need recovered after behavior completion: %s",
                    demand,
                )
            self._next_emotion_idle_at = min(
                self._next_emotion_idle_at,
                time.monotonic() + CALM_IDLE_TRANSITION_SEC,
            )
        self._manual_need_local_goal_id = None
        self._manual_need_local_demand = None
        self._manual_need_triggered_at = None
        self._manual_hunger_phase = None

    def _start_manual_hunger_eating(self) -> None:
        """Replace a completed/waiting seek Goal with exact eatNormally."""

        plan = self.local_runner.plan
        if plan is not None:
            cancel_event = self.local_runner.cancel(
                "Food supplied; continue with four-stage eating"
            )
            # A waiting food gate intentionally ignores same-Goal results.
            # Clear it before applying the transition result and next Goal.
            self.sim_state.clear_food_gate()
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
        else:
            self.sim_state.clear_food_gate()

        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(
            "eatNormally",
            timeout_sec=8.0,
        )
        self._manual_need_local_goal_id = (
            self.local_runner.plan.goal_id
            if self.local_runner.plan is not None
            else None
        )
        self._manual_need_local_demand = "HUNGER"
        self._manual_hunger_phase = "eating"
        self.sim_state.ui_food_eating_authorized = True
        self.sim_state.apply_event(event)
        LOGGER.info(
            "Food supplied; manual hunger advanced to eatNormally"
        )

    def _maybe_start_voice_command(self) -> None:
        pending = self._pending_voice_command
        if pending is None:
            return
        if _voice_is_blocked_by_internal_need(self.sim_state):
            self._pending_voice_command = None
            return
        command, received_at = pending

        local_goal_ids = {
            goal_id
            for goal_id in (
                self._emotion_idle_goal_id,
                self._voice_local_goal_id,
            )
            if goal_id
        }
        external_action_started = _external_action_started_after(
            self.sim_state,
            local_goal_ids,
            received_at,
        )
        if external_action_started:
            # The behavior tree/action system has taken ownership.  Its debug
            # feedback will drive the same visual mappings without a duplicate
            # local animation.
            if _is_follow_behavior(command.behavior_name):
                self.sim_state.ui_follow_goal_id = (
                    self.sim_state.action_goal_id
                )
            self._pending_voice_command = None
            return
        if self.sim_state.ros_executor_online:
            return
        if time.time() - received_at < VOICE_COMMAND_ACTION_GRACE_SEC:
            return

        if self.local_runner.plan is not None:
            cancel_event = self.local_runner.cancel(
                "Interrupted by recognized voice command"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)

        self._emotion_idle_goal_id = None
        self._calm_idle_index = 0
        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(
            command.behavior_name,
            timeout_sec=command.timeout_sec,
        )
        self._voice_local_goal_id = (
            self.local_runner.plan.goal_id
            if self.local_runner.plan is not None
            else None
        )
        if _is_follow_behavior(command.behavior_name):
            self.sim_state.ui_follow_goal_id = self._voice_local_goal_id
        self._next_emotion_idle_at = (
            time.monotonic()
            + (
                self.local_runner.plan.duration
                if self.local_runner.plan is not None
                else command.timeout_sec
            )
            + CALM_IDLE_TRANSITION_SEC
        )
        self._pending_voice_command = None
        self.sim_state.apply_event(event)
        LOGGER.info(
            "Started recognized voice command animation: %s -> %s",
            command.label,
            command.behavior_name,
        )

    def _yield_local_voice_to_external_action(self) -> None:
        if self._voice_local_goal_id is None or self.local_runner.plan is None:
            return
        if _voice_is_blocked_by_internal_need(self.sim_state):
            cancel_event = self.local_runner.cancel(
                "Interrupted by higher-priority internal need"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
            self._voice_local_goal_id = None
            self._pending_voice_command = None
            self.sim_state.ui_follow_user_active = False
            self.sim_state.ui_follow_goal_id = None
            self._next_emotion_idle_at = (
                time.monotonic() + CALM_IDLE_TRANSITION_SEC
            )
            LOGGER.info(
                "Stopped local voice animation for higher-priority internal need"
            )
            return
        external_goal_id = _newest_external_goal_id(
            self.sim_state,
            {self._voice_local_goal_id},
        )
        if external_goal_id:
            external_is_follow = (
                self.sim_state.ui_follow_user_active
                or _state_is_follow_action(self.sim_state)
            )
            cancel_event = self.local_runner.cancel(
                "External action Goal took ownership"
            )
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
            self._voice_local_goal_id = None
            self.sim_state.ui_follow_user_active = external_is_follow
            self.sim_state.ui_follow_goal_id = (
                external_goal_id if external_is_follow else None
            )
            self._next_emotion_idle_at = (
                time.monotonic() + CALM_IDLE_TRANSITION_SEC
            )
            LOGGER.info(
                "Stopped local voice animation; external action took ownership: %s",
                external_goal_id,
            )

    def _yield_emotion_idle_to_external_action(self) -> None:
        if self._emotion_idle_goal_id is None or self.local_runner.plan is None:
            return
        external_goal_id = _newest_external_goal_id(
            self.sim_state,
            {self._emotion_idle_goal_id},
        )
        external_goal_active = bool(external_goal_id)
        need_active = _has_active_internal_need(self.sim_state)
        external_executor_online = self.sim_state.ros_executor_online
        if external_goal_active or need_active or external_executor_online:
            if external_goal_active:
                cancel_event = self.local_runner.cancel(
                    "External action Goal took ownership"
                )
                if cancel_event is not None:
                    self.sim_state.apply_event(cancel_event)
            elif external_executor_online:
                cancel_event = self.local_runner.cancel(
                    "External action system came online"
                )
                if cancel_event is not None:
                    self.sim_state.apply_event(cancel_event)
            else:
                cancel_event = self.local_runner.cancel("Interrupted by active internal need")
                if cancel_event is not None:
                    self.sim_state.apply_event(cancel_event)
            self._emotion_idle_goal_id = None
            self._calm_idle_index = 0
            self._next_emotion_idle_at = (
                time.monotonic() + CALM_IDLE_TRANSITION_SEC
            )
            LOGGER.info(
                "Stopped emotion idle animation for higher-priority activity: %s",
                external_goal_id
                or (
                    "external_executor"
                    if external_executor_online
                    else "internal_need"
                ),
            )

    def _maybe_start_emotion_idle(self) -> None:
        now = time.monotonic()
        if (
            self.sim_state.ui_abnormal_simulation_active
            or self.sim_state.ui_food_waiting
            or self._pending_voice_command is not None
            or self.sim_state.ui_follow_user_requested
            or self.sim_state.ui_follow_user_active
            or self.sim_state.ui_owner_approach_goal_id is not None
            or now < self.sim_state.ui_owner_action_hold_until
            or now < self._visual_idle_block_until
            or self.local_runner.plan is not None
            or _has_pending_action_execution(self.sim_state)
            or self.sim_state.ros_executor_online
        ):
            return

        if _completed_sleep_is_waiting_for_result(self.sim_state):
            _finish_completed_sleep_visual_state(self.sim_state)
            self._calm_idle_index = 0
            self._next_emotion_idle_at = min(
                self._next_emotion_idle_at,
                now + CALM_IDLE_TRANSITION_SEC,
            )

        if now < self._next_emotion_idle_at:
            return
        if self.sim_state.action_status in {"pending", "running"} or _has_active_internal_need(self.sim_state):
            self._calm_idle_index = 0
            self._next_emotion_idle_at = now + 1.0
            return

        dominant_emotion = _dominant_emotion_name(self.sim_state)
        result_settle_sec = (
            CALM_IDLE_TRANSITION_SEC
            if dominant_emotion == "CALM"
            else 2.0
        )
        if (
            self.sim_state.action_result_at is not None
            and time.time() - self.sim_state.action_result_at < result_settle_sec
        ):
            return

        if dominant_emotion == "CALM":
            behavior_spec = CALM_IDLE_SEQUENCE[
                self._calm_idle_index % len(CALM_IDLE_SEQUENCE)
            ]
            next_delay = _random_calm_idle_delay()
        else:
            self._calm_idle_index = 0
            behavior_spec = EMOTION_IDLE_BEHAVIORS.get(dominant_emotion)
            next_delay = EMOTION_IDLE_COOLDOWN_SEC
        if behavior_spec is None:
            self._next_emotion_idle_at = now + EMOTION_IDLE_COOLDOWN_SEC
            return

        behavior_name, duration, preferred_action = behavior_spec
        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(
            behavior_name,
            timeout_sec=duration,
            preferred_action=preferred_action,
            random_preview_target=preferred_action is not None,
        )
        self._emotion_idle_goal_id = self.local_runner.plan.goal_id if self.local_runner.plan else None
        if dominant_emotion == "CALM":
            self._calm_idle_index = (self._calm_idle_index + 1) % len(
                CALM_IDLE_SEQUENCE
            )
        planned_duration = (
            self.local_runner.plan.duration
            if self.local_runner.plan is not None
            else duration
        )
        self._next_emotion_idle_at = now + planned_duration + next_delay
        self.sim_state.apply_event(event)
        LOGGER.info(
            "Started emotion idle animation: %s -> %s; next delay %.0fs",
            dominant_emotion,
            behavior_name,
            next_delay,
        )

    def _advance_external_virtual_user_follow(self, delta_time: float) -> None:
        """Keep external follow feedback attached to the draggable UI person."""

        if not self.sim_state.ui_follow_user_active:
            return
        if _follow_is_blocked_by_internal_need(self.sim_state):
            self.sim_state.ui_follow_user_active = False
            self.sim_state.ui_follow_goal_id = None
            return

        local_plan = self.local_runner.plan
        if local_plan is not None and _is_follow_behavior(local_plan.behavior_name):
            # LocalVirtualRunner already emits continuous dynamic follow frames.
            return

        pending_follow = (
            self._pending_voice_command is not None
            and _is_follow_behavior(self._pending_voice_command[0].behavior_name)
        )
        bound_follow_goal = (
            bool(self.sim_state.ui_follow_goal_id)
            and self.sim_state.action_goal_id
            == self.sim_state.ui_follow_goal_id
        )
        if not (
            self.sim_state.action_status == "running"
            and (bound_follow_goal or _state_is_follow_action(self.sim_state))
        ):
            if not pending_follow:
                self.sim_state.ui_follow_user_active = False
                self.sim_state.ui_follow_goal_id = None
            return

        _advance_follow_pose(self.sim_state, delta_time)
        # Keep the executor's exact ACT key in both the status card and the
        # sprite channel.  Motion state controls whether the walk texture is
        # animated; the UI must not invent legacy sub-action labels.
        self.sim_state.action_visual_action = "ACT_INTERACT_FOLLOW_OWNER"

    def _stop_virtual_user_follow(self, reason: str) -> None:
        self.sim_state.ui_follow_user_requested = False
        self.sim_state.ui_follow_user_active = False
        self.sim_state.ui_follow_goal_id = None
        self.sim_state.ui_follow_stationary_since = None
        plan = self.local_runner.plan
        if plan is not None and _is_follow_behavior(plan.behavior_name):
            cancel_event = self.local_runner.cancel(reason)
            if cancel_event is not None:
                self.sim_state.apply_event(cancel_event)
        elif _state_is_follow_action(self.sim_state):
            external_goal_id = self.sim_state.action_goal_id
            if external_goal_id:
                self.sim_state.ui_follow_suppressed_goal_id = external_goal_id
                self.sim_state.apply_event(
                    SimEvent(
                        "action_result",
                        config.ACTION_RESULT_TOPIC,
                        {
                            "goal_id": external_goal_id,
                            "behavior_name": "follow_owner",
                            "status": "CANCELED",
                            "result": "interrupted",
                            "reason": reason,
                        },
                        f"UI follow stopped: {reason}",
                    )
                )
        self._voice_local_goal_id = None
        self._pending_voice_command = None
        self._next_emotion_idle_at = (
            time.monotonic() + CALM_IDLE_TRANSITION_SEC
        )

    def _expire_stationary_follow_if_needed(self) -> None:
        """End Follow after the visible owner remains still for 30 seconds."""

        if (
            not self.sim_state.ui_follow_user_requested
            or not self.sim_state.ui_user_visible
        ):
            return
        now = time.monotonic()
        stationary_since = self.sim_state.ui_follow_stationary_since
        if stationary_since is None:
            self.sim_state.ui_follow_stationary_since = now
            return
        if now - stationary_since < FOLLOW_STATIONARY_TIMEOUT_SEC:
            return
        SimWindow._stop_virtual_user_follow(
            self,
            "Virtual owner remained stationary for 30 seconds",
        )
        LOGGER.info(
            "Follow released after virtual owner stayed still for %.0fs",
            FOLLOW_STATIONARY_TIMEOUT_SEC,
        )

    def _maybe_resume_requested_follow(self) -> None:
        """Keep Follow active until owner removal or stationary timeout."""

        if not self.sim_state.ui_follow_user_requested:
            return
        if not self.sim_state.ui_user_visible:
            self.sim_state.ui_follow_user_requested = False
            self.sim_state.ui_follow_user_active = False
            self.sim_state.ui_follow_goal_id = None
            self.sim_state.ui_follow_stationary_since = None
            return
        if self.sim_state.ui_follow_stationary_since is None:
            self.sim_state.ui_follow_stationary_since = time.monotonic()
        if (
            self.sim_state.ui_abnormal_simulation_active
            or _has_active_internal_need(self.sim_state)
            or self._pending_manual_need is not None
            or self._manual_need_local_goal_id is not None
        ):
            self.sim_state.ui_follow_user_active = False
            return

        plan = self.local_runner.plan
        if plan is not None:
            if _is_follow_behavior(plan.behavior_name):
                self.sim_state.ui_follow_user_active = True
                self.sim_state.ui_follow_goal_id = plan.goal_id
            return
        if (
            self.sim_state.action_status in {"pending", "running"}
            or _has_pending_action_execution(self.sim_state)
        ):
            if _state_is_follow_action(self.sim_state):
                self.sim_state.ui_follow_user_active = True
                self.sim_state.ui_follow_goal_id = self.sim_state.action_goal_id
            return
        if self.sim_state.ros_executor_online:
            return

        self.local_runner.sync_from_state(self.sim_state)
        event = self.local_runner.start(
            "follow_owner",
            timeout_sec=86400.0,
        )
        self._voice_local_goal_id = (
            self.local_runner.plan.goal_id
            if self.local_runner.plan is not None
            else None
        )
        self.sim_state.ui_follow_user_active = True
        self.sim_state.ui_follow_goal_id = self._voice_local_goal_id
        self.sim_state.apply_event(event)
        LOGGER.info("Resumed persistent follow for visible virtual owner")

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
        if (
            _voice_command_requires_visible_user(group, fields)
            and not self.sim_state.ui_user_visible
        ):
            self.sim_state.ui_pending_confirmation = {
                "kind": "alert",
                "title": "提示",
                "message": "没有识别到主人",
            }
            return
        if _fields_request_stop(group, fields):
            if _internal_need_owns_control(self):
                SimWindow._handle_stop_voice_command(self)
                self.sim_state.ui_pending_confirmation = {
                    "kind": "alert",
                    "title": "提示",
                    "message": "内部需求正在执行，停止指令已忽略",
                }
                return
            # Apply the presentation-side stop immediately instead of waiting
            # for the ROS echo or Action cancellation round trip.
            SimWindow._handle_stop_voice_command(self)
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


_ABNORMAL_PAUSED_STATE_FIELDS = (
    "active_behavior",
    "action_status",
    "action_goal_id",
    "action_behavior_id",
    "action_progress",
    "action_visual_progress",
    "action_visual_progress_start",
    "action_current_action",
    "action_visual_action",
    "action_pending_visual_action",
    "action_unit_type",
    "action_message",
    "action_safe_to_interrupt",
    "action_result",
    "action_reason",
    "action_reward",
    "action_priority_level",
    "action_params",
    "action_stage_index",
    "action_stage_total",
    "action_stage_label",
    "action_phase",
    "action_target_label",
    "action_trigger_reason",
    "action_transition",
    "action_source",
    "action_intent",
    "action_level",
    "action_interaction_mode",
    "action_completed_stages",
    "action_executed_units",
    "action_started_at",
    "action_updated_at",
    "action_result_at",
    "recent_action_steps",
    "dog_motion_start_x",
    "dog_motion_start_y",
    "dog_motion_start_heading",
    "dog_motion_target_x",
    "dog_motion_target_y",
    "dog_motion_target_heading",
    "dog_motion_elapsed",
    "dog_motion_duration",
    "dog_pose_last_received_at",
    "ui_follow_user_active",
    "ui_follow_goal_id",
    "ui_owner_approach_goal_id",
)


def _abnormal_action_snapshot(state: SimState) -> dict[str, object]:
    snapshot = {
        field_name: deepcopy(getattr(state, field_name))
        for field_name in _ABNORMAL_PAUSED_STATE_FIELDS
    }
    snapshot["_room_object_active"] = {
        name: bool(room_object.get("active"))
        for name, room_object in state.room_objects.items()
    }
    return snapshot


def _activate_abnormal_simulation(state: SimState) -> None:
    """Pause the rendered action and give abnormal mode temporary control."""

    if state.ui_abnormal_simulation_active:
        return

    previous_goal = state.action_goal_id
    state.ui_abnormal_paused_action = _abnormal_action_snapshot(state)
    state.ui_abnormal_started_monotonic = time.monotonic()
    if not state.ui_abnormal_replay_active:
        state.ui_abnormal_deferred_events.clear()
    state.ui_abnormal_replay_active = False
    state.ui_abnormal_replay_goal_id = None
    state.ui_abnormal_replay_next_at = 0.0
    if previous_goal and previous_goal != "ui-abnormal-simulation":
        state.ui_abnormal_interrupted_goal_id = previous_goal

    now = time.time()
    state.ui_abnormal_simulation_active = True
    state.ui_dragging_user = False
    state.ui_follow_user_active = False
    state.ui_follow_goal_id = None

    state.dog_motion_start_x = state.dog_x
    state.dog_motion_start_y = state.dog_y
    state.dog_motion_start_heading = state.dog_heading
    state.dog_motion_target_x = state.dog_x
    state.dog_motion_target_y = state.dog_y
    state.dog_motion_target_heading = state.dog_heading
    state.dog_motion_elapsed = 0.0
    state.dog_motion_duration = 0.0

    state.active_behavior = "abnormalSimulation"
    state.action_status = "running"
    state.action_goal_id = "ui-abnormal-simulation"
    state.action_behavior_id = "ui-abnormal-simulation"
    state.action_progress = 1.0
    state.action_visual_progress = 1.0
    state.action_visual_progress_start = 1.0
    state.action_current_action = "ACT_VOCAL_WHINE"
    state.action_visual_action = "ACT_VOCAL_WHINE"
    state.action_pending_visual_action = None
    state.action_unit_type = "action"
    state.action_message = "UI abnormal simulation active"
    state.action_safe_to_interrupt = False
    state.action_result = "-"
    state.action_reason = "Paused by UI abnormal simulation"
    state.action_reward = None
    state.action_priority_level = None
    state.action_params = {"source": "UI", "intent": "abnormal_simulation"}
    state.action_stage_index = 1
    state.action_stage_total = 1
    state.action_stage_label = "狗狗呜咽"
    state.action_phase = "abnormal"
    state.action_target_label = "-"
    state.action_trigger_reason = "手动异常模拟"
    state.action_transition = "paused"
    state.action_source = "UI"
    state.action_intent = "abnormal_simulation"
    state.action_level = "-"
    state.action_interaction_mode = "solo"
    state.action_completed_stages.clear()
    state.action_executed_units.clear()
    state.action_started_at = now
    state.action_updated_at = now
    state.action_result_at = None
    state.recent_action_steps.clear()
    state.recent_action_steps.append((now, "ACT_VOCAL_WHINE"))
    for room_object in state.room_objects.values():
        room_object["active"] = False


def _deactivate_abnormal_simulation(state: SimState) -> float:
    """Release the UI lock and restore the action paused beneath it."""

    if not state.ui_abnormal_simulation_active:
        return 0.0
    now_monotonic = time.monotonic()
    paused_duration = max(
        0.0,
        now_monotonic
        - (
            state.ui_abnormal_started_monotonic
            if state.ui_abnormal_started_monotonic is not None
            else now_monotonic
        ),
    )
    snapshot = state.ui_abnormal_paused_action
    paused_goal_id = state.ui_abnormal_interrupted_goal_id
    state.ui_abnormal_simulation_active = False
    if snapshot is not None:
        for field_name in _ABNORMAL_PAUSED_STATE_FIELDS:
            if field_name in snapshot:
                setattr(
                    state,
                    field_name,
                    deepcopy(snapshot[field_name]),
                )
        room_active = snapshot.get("_room_object_active")
        if isinstance(room_active, dict):
            for name, active in room_active.items():
                room_object = state.room_objects.get(str(name))
                if room_object is not None:
                    room_object["active"] = bool(active)
    else:
        state.active_behavior = None
        state.action_status = "waiting"
        state.action_goal_id = None
        state.action_behavior_id = None
        state.action_progress = 0.0
        state.action_visual_progress = 0.0
        state.action_visual_progress_start = 0.0
        state.action_current_action = "-"
        state.action_visual_action = "-"
        state.action_pending_visual_action = None
        state.action_unit_type = "-"
        state.action_message = "Abnormal simulation cleared"
        state.action_safe_to_interrupt = None
        state.action_result = "-"
        state.action_reason = "-"
        state.action_reward = None
        state.action_priority_level = None
        state.action_params = {}
        state.action_stage_index = 0
        state.action_stage_total = 0
        state.action_stage_label = "-"
        state.action_phase = "idle"
        state.action_target_label = "-"
        state.action_trigger_reason = "-"
        state.action_transition = "waiting"
        state.action_source = "-"
        state.action_intent = "-"
        state.action_level = "-"
        state.action_interaction_mode = "-"
        state.action_completed_stages.clear()
        state.action_executed_units.clear()
        state.action_started_at = None
        state.action_updated_at = time.time()
        state.action_result_at = time.time()
        state.recent_action_steps.clear()

    if state.ui_follow_stationary_since is not None:
        state.ui_follow_stationary_since += paused_duration
    if not state.ui_user_visible:
        state.ui_follow_user_active = False
        state.ui_follow_goal_id = None
    if state.ui_food_eating_until > 0.0:
        state.ui_food_eating_until += paused_duration
    if state.ui_owner_action_hold_until > 0.0:
        state.ui_owner_action_hold_until += paused_duration

    state.ui_abnormal_paused_action = None
    state.ui_abnormal_started_monotonic = None
    state.ui_abnormal_interrupted_goal_id = None
    state.ui_abnormal_replay_active = bool(
        state.ui_abnormal_deferred_events
    )
    state.ui_abnormal_replay_goal_id = paused_goal_id
    state.ui_abnormal_replay_next_at = (
        now_monotonic + 0.35
        if state.ui_abnormal_replay_active
        else 0.0
    )
    return paused_duration


def _received_at(payload: dict[str, object] | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    try:
        return float(payload.get("received_at"))
    except (TypeError, ValueError):
        return None


def _toggle_virtual_user(state: SimState) -> None:
    if state.ui_user_visible:
        state.ui_user_visible = False
        state.ui_dragging_user = False
        state.ui_follow_user_requested = False
        state.ui_follow_user_active = False
        state.ui_follow_goal_id = None
        state.ui_follow_stationary_since = None
        if state.ui_selected_object == "user":
            state.ui_selected_object = None
        return
    state.ui_user_visible = True
    _reset_virtual_user(state)


def _reset_virtual_user(state: SimState) -> None:
    previous = (state.user_x, state.user_y)
    state.user_x = config.DEFAULT_USER_X
    state.user_y = config.DEFAULT_USER_Y
    state.ui_dragging_user = False
    if (
        state.ui_follow_user_requested
        and previous != (state.user_x, state.user_y)
    ):
        state.ui_follow_stationary_since = time.monotonic()


def _toggle_virtual_user_motion(state: SimState) -> None:
    """Alternate every person click between following and locked states."""

    if not state.ui_user_visible:
        state.ui_dragging_user = False
        return
    state.ui_dragging_user = not state.ui_dragging_user


def _move_virtual_user_from_screen(
    state: SimState,
    screen_x: float,
    screen_y: float,
) -> None:
    if not state.ui_user_visible:
        return
    padding_x = 48.0
    padding_y = 64.0
    clamped_x = max(
        config.WORLD_LEFT + padding_x,
        min(config.WORLD_RIGHT - padding_x, screen_x),
    )
    clamped_y = max(
        config.WORLD_BOTTOM + padding_y,
        min(config.WORLD_TOP - padding_y, screen_y),
    )
    normalized_x = (clamped_x - config.WORLD_LEFT) / max(1.0, config.WORLD_WIDTH)
    normalized_y = (clamped_y - config.WORLD_BOTTOM) / max(1.0, config.WORLD_HEIGHT)
    user_x = config.SCENE_LOGICAL_LEFT + normalized_x * (
        config.SCENE_LOGICAL_RIGHT - config.SCENE_LOGICAL_LEFT
    )
    user_y = config.SCENE_LOGICAL_BOTTOM + normalized_y * (
        config.SCENE_LOGICAL_TOP - config.SCENE_LOGICAL_BOTTOM
    )
    moved = math.hypot(
        user_x - state.user_x,
        user_y - state.user_y,
    ) > 0.01
    state.user_x = user_x
    state.user_y = user_y
    if moved and state.ui_follow_user_requested:
        state.ui_follow_stationary_since = time.monotonic()


def _advance_follow_pose(state: SimState, delta_time: float) -> bool:
    """Move the rendered dog toward its offset behind the virtual person."""

    target_x = max(
        config.SCENE_LOGICAL_LEFT + 36.0,
        min(
            config.SCENE_LOGICAL_RIGHT - 36.0,
            state.user_x - FOLLOW_USER_OFFSET_X,
        ),
    )
    target_y = max(
        config.SCENE_LOGICAL_BOTTOM + 36.0,
        min(
            config.SCENE_LOGICAL_TOP - 36.0,
            state.user_y - FOLLOW_USER_OFFSET_Y,
        ),
    )
    owner_distance = math.hypot(
        state.user_x - state.dog_x,
        state.user_y - state.dog_y,
    )
    moving = owner_distance > config.OWNER_NEAR_DISTANCE
    distance = math.hypot(target_x - state.dog_x, target_y - state.dog_y)
    step = (
        min(
            distance,
            FOLLOW_USER_SPEED * max(0.0, min(float(delta_time), 0.12)),
        )
        if moving
        else 0.0
    )
    if distance > 0.0 and step > 0.0:
        ratio = step / distance
        state.dog_x += (target_x - state.dog_x) * ratio
        state.dog_y += (target_y - state.dog_y) * ratio

    state.dog_heading = math.degrees(
        math.atan2(
            state.user_y - state.dog_y,
            state.user_x - state.dog_x,
        )
    )
    state.dog_motion_start_x = state.dog_x
    state.dog_motion_start_y = state.dog_y
    state.dog_motion_start_heading = state.dog_heading
    state.dog_motion_target_x = state.dog_x
    state.dog_motion_target_y = state.dog_y
    state.dog_motion_target_heading = state.dog_heading
    state.dog_motion_elapsed = 0.0
    state.dog_motion_duration = 0.0
    remaining = math.hypot(target_x - state.dog_x, target_y - state.dog_y)
    return moving and remaining > FOLLOW_USER_ARRIVAL_DISTANCE


def _is_follow_behavior(behavior_name: str | None) -> bool:
    key = str(behavior_name or "").upper().replace("-", "_").replace(" ", "_")
    return key == "FOLLOW_OWNER"


def _is_stop_behavior(behavior_name: str | None) -> bool:
    key = str(behavior_name or "").upper().replace("-", "_").replace(" ", "_")
    return key == "EMERGENCY_STOP"


def _fields_request_stop(group: str, fields: dict[str, str]) -> bool:
    if str(group or "").strip().upper() != "AUDIO":
        return False
    command_id = str(
        fields.get("audio_command_id") or ""
    ).strip().upper()
    event_type = str(
        fields.get("audio_event_type") or ""
    ).strip().upper()
    return (
        command_id in {"CMD_STOP", "CMD_EMERGENCY_STOP", "EMERGENCY_STOP"}
        or event_type == "EVT_VOICE_COMMAND_STOP"
    )


def _internal_need_owns_control(window: object) -> bool:
    """Return whether Stop must leave the current behavior untouched."""

    state = getattr(window, "sim_state")
    if (
        _has_active_internal_need(state)
        or getattr(window, "_pending_manual_need", None) is not None
        or getattr(window, "_manual_need_local_goal_id", None) is not None
    ):
        return True
    if state.action_status not in {"pending", "running"}:
        return False
    source = str(state.action_source or "").strip().lower()
    if source in {"need", "internal_need", "internal-need"}:
        return True
    return str(state.active_behavior or "") in INTERNAL_NEED_BEHAVIORS


def _freeze_rendered_dog(state: SimState) -> None:
    """Cancel interpolation at the dog's current rendered position."""

    state.dog_motion_start_x = state.dog_x
    state.dog_motion_start_y = state.dog_y
    state.dog_motion_start_heading = state.dog_heading
    state.dog_motion_target_x = state.dog_x
    state.dog_motion_target_y = state.dog_y
    state.dog_motion_target_heading = state.dog_heading
    state.dog_motion_elapsed = 0.0
    state.dog_motion_duration = 0.0


def _newest_external_goal_id(
    state: SimState,
    local_goal_ids: set[str | None],
) -> str | None:
    excluded = {
        str(goal_id)
        for goal_id in local_goal_ids
        if goal_id
    }
    candidates = [
        (
            int(execution.get("sequence") or 0),
            goal_id,
        )
        for goal_id, execution in state.action_executions.items()
        if goal_id not in excluded
        and str(execution.get("status") or "").lower()
        in {"pending", "running"}
    ]
    if not candidates:
        return None
    return max(candidates)[1]


def _newest_external_goal_id_started_after(
    state: SimState,
    local_goal_ids: set[str | None],
    received_at: float,
) -> str | None:
    """Return only an active external Goal newer than a priority trigger."""

    excluded = {
        str(goal_id)
        for goal_id in local_goal_ids
        if goal_id
    }
    candidates: list[tuple[int, str]] = []
    for goal_id, execution in state.action_executions.items():
        if goal_id in excluded or str(goal_id).startswith("local-"):
            continue
        if str(execution.get("status") or "").lower() not in {
            "pending",
            "running",
        }:
            continue
        try:
            goal_received_at = float(execution.get("received_at"))
        except (TypeError, ValueError):
            continue
        if goal_received_at < received_at:
            continue
        candidates.append(
            (
                int(execution.get("sequence") or 0),
                goal_id,
            )
        )
    return max(candidates)[1] if candidates else None


def _has_pending_action_execution(state: SimState) -> bool:
    return any(
        str(execution.get("status") or "").lower()
        in {"pending", "running"}
        for execution in state.action_executions.values()
    )


def _external_action_started_after(
    state: SimState,
    local_goal_ids: set[str],
    received_at: float,
) -> bool:
    for goal_id, execution in state.action_executions.items():
        if goal_id in local_goal_ids or str(goal_id).startswith("local-"):
            continue
        try:
            goal_received_at = float(execution.get("received_at"))
        except (TypeError, ValueError):
            continue
        if goal_received_at >= received_at:
            return True
    return (
        state.action_goal_id not in local_goal_ids
        and not str(state.action_goal_id or "").startswith("local-")
        and state.action_started_at is not None
        and state.action_started_at >= received_at
    )


def _state_is_follow_action(state: SimState) -> bool:
    text = " ".join(
        (
            str(state.active_behavior or ""),
            str(state.action_current_action or ""),
            str(state.action_visual_action or ""),
        )
    ).upper()
    return "FOLLOW" in text or "MATCH_OWNER" in text


def _follow_is_blocked_by_internal_need(state: SimState) -> bool:
    if _has_active_internal_need(state):
        return True
    if state.action_status != "running":
        return False
    return str(state.action_source or "").strip().lower() in {
        "need",
        "internal_need",
        "internal-need",
    }


def _dog_is_near_virtual_user(state: SimState) -> bool:
    return (
        math.hypot(
            state.user_x - state.dog_x,
            state.user_y - state.dog_y,
        )
        <= config.OWNER_NEAR_DISTANCE
    )


def _voice_command_requires_visible_user(
    group: str,
    fields: dict[str, str],
) -> bool:
    if str(group).upper() != "AUDIO":
        return False
    event_type = str(fields.get("audio_event_type") or "").upper()
    command_id = str(fields.get("audio_command_id") or "").upper()
    return (
        event_type == "EVT_VOICE_COMMAND_KNOWN"
        and command_id not in {"", "CMD_UNKNOWN"}
    )


def _visual_activity_signature(
    visual_event: dict[str, object] | None,
) -> tuple[str, ...] | None:
    if not visual_event:
        return None
    raw_events = visual_event.get("events")
    if not isinstance(raw_events, (list, tuple, set)):
        return None
    neutral_events = {
        "",
        "NONE",
        "NO_EVENT",
        "EVT_VISION_NONE",
        "EVT_VISION_NO_EVENT",
    }
    events = tuple(
        sorted(
            {
                str(item).strip().upper()
                for item in raw_events
                if str(item).strip().upper() not in neutral_events
            }
        )
    )
    return events or None


def _dominant_emotion_name(state: SimState) -> str:
    data = state.emotion_state or {}
    explicit = data.get("dominantEmotion") or data.get("dominant_emotion")
    if not explicit:
        signal = data.get("dominantEmotionSignal") or data.get("dominant_emotion_signal")
        if isinstance(signal, dict):
            explicit = signal.get("emotion") or signal.get("type")
    if not explicit:
        emotions = data.get("emotions")
        if isinstance(emotions, dict):
            ranked: list[tuple[float, str]] = []
            for name, value in emotions.items():
                item = value if isinstance(value, dict) else {}
                ranked.append((_safe_float(item.get("value"), 0.0), str(name)))
            if ranked:
                highest_value, highest_name = max(ranked)
                explicit = highest_name if highest_value > 0.0 else None
    key = str(explicit or "").strip().upper()
    if not key:
        # Before the first emotion packet (or between emotion snapshots), the
        # absence of an active emotion is the neutral/calm UI state.
        return "CALM"
    return {
        "CALM": "CALM",
        "JOY": "JOY",
        "HAPPY": "JOY",
        "EXCITE": "EXCITE",
        "EXCITED": "EXCITE",
        "ANXIETY": "ANXIETY",
        "ANXIOUS": "ANXIETY",
        "FEAR": "FEAR",
        "FEARFUL": "FEAR",
        "CURIOUS": "CURIOUS",
        "CURIOSITY": "CURIOUS",
    }.get(key, "")


def _random_calm_idle_delay(rng: random.Random | None = None) -> float:
    """Choose a whole-second pause between calm autonomous play actions."""

    chooser = rng if rng is not None else random
    return float(chooser.choice(CALM_IDLE_PLAY_DELAY_OPTIONS_SEC))


def _food_interaction_ready(state: SimState) -> bool:
    """Return whether the rendered dog has reached the bowl interaction point."""

    if state.virtual_motion_active():
        return False
    if state.ui_food_waiting:
        return True
    if state.action_progress < 0.68:
        return False
    action_text = " ".join(
        (
            str(state.active_behavior or ""),
            str(state.action_current_action or ""),
            str(state.action_visual_action or ""),
            str(state.action_target_label or ""),
        )
    ).upper()
    return any(
        token in action_text
        for token in ("FOOD", "BOWL", "EAT")
    )


def _has_active_internal_need(state: SimState) -> bool:
    if state.ui_food_waiting:
        # An empty-bowl wait remains an active need from the UI's point of
        # view even if the external need packet has already dropped below its
        # trigger threshold after dispatching the food behavior.
        return True

    data = state.internal_need_state or {}
    triggered = data.get("triggered")
    if _triggered_need_collection_active(triggered):
        return True

    sleep = data.get("sleep")
    if isinstance(sleep, dict) and _flag_is_true(sleep.get("isSleeping")):
        return True

    demands = data.get("demands")
    if not isinstance(demands, dict):
        return False
    for value in demands.values():
        if not isinstance(value, dict):
            continue
        if _flag_is_true(value.get("triggered")):
            return True
        if str(value.get("level") or "").upper() in {"TRIGGERED", "OVERFLOW", "CRITICAL"}:
            return True
    return False


def _triggered_need_collection_active(value: object) -> bool:
    """Interpret both active-record lists and name-to-state mappings."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _flag_is_true(value) if value.strip().lower() in {
            "true",
            "false",
            "1",
            "0",
            "yes",
            "no",
        } else bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(_triggered_need_collection_active(item) for item in value)
    if not isinstance(value, dict):
        return bool(value)

    is_record = any(key in value for key in ("type", "demand", "name"))
    if is_record:
        for key in ("triggered", "active", "isTriggered", "levelActive"):
            if key in value:
                return _flag_is_true(value.get(key))
        level = str(value.get("level") or "").upper()
        if level:
            return level in {"TRIGGERED", "OVERFLOW", "CRITICAL"}
        return True

    return any(_triggered_need_collection_active(item) for item in value.values())


def _flag_is_true(value: object) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "off", "", "none", "null"}:
            return False
        if normalized in {"true", "1", "yes", "on"}:
            return True
    return bool(value)


def _recover_manual_need_state(state: SimState, demand: str) -> bool:
    """Release one completed UI-injected need without touching real state."""

    demand_key = str(demand or "").strip().upper()
    recovery = MANUAL_NEED_RECOVERY.get(demand_key)
    if recovery is None:
        return False
    demand_name, recovery_value = recovery
    data = state.internal_need_state
    if not isinstance(data, dict):
        return False
    raw = data.get("raw")
    if not isinstance(raw, dict) or raw.get("manual_source") != MANUAL_SOURCE:
        # A real need node owns authoritative recovery for non-UI state.
        return False

    demands = data.get("demands")
    if not isinstance(demands, dict):
        return False
    demand_state = demands.get(demand_name)
    if not isinstance(demand_state, dict):
        return False

    event_type = f"NEED_{demand_key}_RECOVERED"
    recovered_demand = {
        **demand_state,
        "value": recovery_value,
        "triggered": False,
        "overflow": False,
        "level": "NORMAL",
        "levelEvent": event_type,
        "levelActive": False,
    }
    recovered_demands = {
        **demands,
        demand_name: recovered_demand,
    }
    triggered = data.get("triggered")
    if isinstance(triggered, list):
        recovered_triggered = [
            item
            for item in triggered
            if not (
                isinstance(item, dict)
                and str(
                    item.get("type")
                    or item.get("demand")
                    or item.get("name")
                    or ""
                ).upper()
                == demand_key
            )
        ]
    elif isinstance(triggered, dict):
        recovered_triggered = {
            key: value
            for key, value in triggered.items()
            if str(key).upper() != demand_key
        }
    else:
        recovered_triggered = []

    level_events = data.get("levelEvents")
    recovered_level_events = (
        {
            **level_events,
            demand_name: event_type,
        }
        if isinstance(level_events, dict)
        else {demand_name: event_type}
    )
    recovered_sleep = data.get("sleep")
    if demand_key == "SLEEPINESS" and isinstance(recovered_sleep, dict):
        recovered_sleep = {
            **recovered_sleep,
            "isSleeping": False,
            "sleepDurationMinutes": 0,
            "shallowSleepTicksRemaining": 0,
        }
    state.internal_need_state = {
        **data,
        "demands": recovered_demands,
        "triggered": recovered_triggered,
        "levelEvents": recovered_level_events,
        **(
            {"sleep": recovered_sleep}
            if isinstance(recovered_sleep, dict)
            else {}
        ),
    }
    state.internal_need_signal_event = {
        "schema_version": str(data.get("schema_version") or "1.0"),
        "event_type": event_type,
        "demand": demand_name,
        "value": recovery_value,
        "level": "NORMAL",
        "previousLevel": "TRIGGERED",
        "trigger": "LOCAL_BEHAVIOR_COMPLETED",
        "received_at": time.time(),
        "raw": {
            "manual_source": MANUAL_SOURCE,
            "event_type": event_type,
        },
    }
    return True


def _completed_sleep_is_waiting_for_result(state: SimState) -> bool:
    if state.action_status != "running" or state.action_progress < 0.999:
        return False
    sleep = (state.internal_need_state or {}).get("sleep")
    if not isinstance(sleep, dict) or "isSleeping" not in sleep:
        return False
    if _flag_is_true(sleep.get("isSleeping")):
        return False
    action_text = " ".join(
        (
            str(state.active_behavior or ""),
            str(state.action_current_action or ""),
            str(state.action_visual_action or ""),
        )
    ).upper()
    return "SLEEP" in action_text or "NAP" in action_text


def _finish_completed_sleep_visual_state(state: SimState) -> None:
    """Release a fully completed sleep action when its result packet is late."""

    now = time.time()
    state.active_behavior = None
    state.action_status = "success"
    state.action_progress = 1.0
    state.action_visual_progress = 1.0
    state.action_visual_progress_start = 1.0
    state.action_current_action = "-"
    state.action_visual_action = "-"
    state.action_pending_visual_action = None
    state.action_unit_type = "-"
    state.action_message = "Sleep completed; authoritative state reports awake"
    state.action_safe_to_interrupt = None
    state.action_result = "completed"
    state.action_reason = "Authoritative sleep state reports awake"
    state.action_phase = "completed"
    state.action_transition = "completed"
    state.action_stage_label = "completed"
    state.action_result_at = now
    state.action_updated_at = now


def _voice_is_blocked_by_internal_need(state: SimState) -> bool:
    if _has_active_internal_need(state):
        return True
    if state.action_status != "running":
        return False
    source = str(state.action_source or "").strip().lower()
    if source in {"need", "internal_need", "internal-need"}:
        return True
    priority = state.action_priority_level
    return priority is not None and priority < 5


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
    feeding_coordinator = FeedingCoordinator()
    ros_node: RosBridge | None = None
    ros_thread: threading.Thread | None = None

    try:
        rclpy.init(args=list(args) if args is not None else None)
        ros_node = RosBridge(
            event_queue,
            injection_queue,
            feeding_coordinator,
        )
        ros_thread = threading.Thread(
            target=_spin_ros,
            args=(ros_node,),
            name="marsdog_sim2d_ros_spin",
            daemon=True,
        )
        ros_thread.start()

        SimWindow(
            sim_state,
            event_queue,
            injection_queue,
            feeding_coordinator,
        )
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
