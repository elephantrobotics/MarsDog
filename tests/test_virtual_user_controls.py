import unittest
from pathlib import Path
import queue
import time

from marsdog_sim2d import config
from marsdog_sim2d.arcade_viewer_node import (
    FOLLOW_STATIONARY_TIMEOUT_SEC,
    SimWindow,
    _move_virtual_user_from_screen,
    _reset_virtual_user,
    _toggle_virtual_user,
    _toggle_virtual_user_motion,
    _voice_command_requires_visible_user,
)
from marsdog_sim2d.event_injector import default_field_values
from marsdog_sim2d.sim_state import SimEvent, SimState


class VirtualUserControlTests(unittest.TestCase):
    def setUp(self) -> None:
        config.update_layout(
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT,
            False,
            config.DEFAULT_LOG_HEIGHT,
        )

    def test_virtual_user_is_hidden_until_added(self) -> None:
        state = SimState()
        self.assertFalse(state.ui_user_visible)
        self.assertFalse(state.ui_dragging_user)

    def test_add_resets_position_and_delete_clears_selection(self) -> None:
        state = SimState(
            user_x=123.0,
            user_y=234.0,
            ui_selected_object="user",
            ui_follow_user_active=True,
            ui_follow_goal_id="local-follow",
        )

        _toggle_virtual_user(state)

        self.assertTrue(state.ui_user_visible)
        self.assertEqual(config.DEFAULT_USER_X, state.user_x)
        self.assertEqual(config.DEFAULT_USER_Y, state.user_y)

        state.ui_dragging_user = True
        _toggle_virtual_user(state)

        self.assertFalse(state.ui_user_visible)
        self.assertFalse(state.ui_dragging_user)
        self.assertFalse(state.ui_follow_user_active)
        self.assertFalse(state.ui_follow_user_requested)
        self.assertIsNone(state.ui_follow_goal_id)
        self.assertIsNone(state.ui_selected_object)

    def test_follow_mouse_converts_world_center_to_scene_center(self) -> None:
        state = SimState(ui_user_visible=True)
        screen_x = (config.WORLD_LEFT + config.WORLD_RIGHT) / 2.0
        screen_y = (config.WORLD_BOTTOM + config.WORLD_TOP) / 2.0

        _move_virtual_user_from_screen(state, screen_x, screen_y)

        self.assertAlmostEqual(
            (config.SCENE_LOGICAL_LEFT + config.SCENE_LOGICAL_RIGHT) / 2.0,
            state.user_x,
        )
        self.assertAlmostEqual(
            (config.SCENE_LOGICAL_BOTTOM + config.SCENE_LOGICAL_TOP) / 2.0,
            state.user_y,
        )

    def test_follow_mouse_is_clamped_inside_visible_world(self) -> None:
        state = SimState(ui_user_visible=True)

        _move_virtual_user_from_screen(state, -1000.0, -1000.0)

        self.assertGreater(state.user_x, config.SCENE_LOGICAL_LEFT)
        self.assertGreater(state.user_y, config.SCENE_LOGICAL_BOTTOM)

    def test_right_click_reset_helper_restores_initial_position(self) -> None:
        state = SimState(
            user_x=320.0,
            user_y=510.0,
            ui_user_visible=True,
            ui_dragging_user=True,
        )

        _reset_virtual_user(state)

        self.assertEqual(config.DEFAULT_USER_X, state.user_x)
        self.assertEqual(config.DEFAULT_USER_Y, state.user_y)
        self.assertFalse(state.ui_dragging_user)

    def test_repeated_person_clicks_cycle_between_move_and_lock(self) -> None:
        state = SimState(
            user_x=620.0,
            user_y=460.0,
            ui_user_visible=True,
        )

        for click_index in range(1, 7):
            _toggle_virtual_user_motion(state)
            self.assertEqual(
                click_index % 2 == 1,
                state.ui_dragging_user,
            )

        self.assertEqual((620.0, 460.0), (state.user_x, state.user_y))

    def test_hidden_person_cannot_enter_mouse_follow_mode(self) -> None:
        state = SimState(
            ui_user_visible=False,
            ui_dragging_user=True,
        )

        _toggle_virtual_user_motion(state)

        self.assertFalse(state.ui_dragging_user)

    def test_known_voice_commands_require_visible_virtual_user(self) -> None:
        fields = default_field_values()
        fields["audio_event_type"] = "EVT_VOICE_COMMAND_KNOWN"
        fields["audio_command_id"] = "CMD_SIT"

        self.assertTrue(
            _voice_command_requires_visible_user("Audio", fields)
        )
        fields["audio_event_type"] = "EVT_VOICE_CALL_NAME"
        self.assertFalse(
            _voice_command_requires_visible_user("Audio", fields)
        )

    def test_sending_voice_command_without_person_shows_owner_alert(self) -> None:
        class Harness:
            pass

        harness = Harness()
        harness.sim_state = SimState(
            ui_user_visible=False,
            event_injector_group="Audio",
            event_injector_fields=default_field_values(),
        )
        harness.injection_queue = queue.Queue()
        harness._resolved_fields = lambda group: {
            **default_field_values(),
            "audio_event_type": "EVT_VOICE_COMMAND_KNOWN",
            "audio_command_id": "CMD_FOLLOW",
        }

        SimWindow._send_custom_injection(harness, "Audio")

        self.assertTrue(harness.injection_queue.empty())
        self.assertEqual(
            "没有识别到主人",
            harness.sim_state.ui_pending_confirmation["message"],
        )
        self.assertEqual(
            "alert",
            harness.sim_state.ui_pending_confirmation["kind"],
        )

    @staticmethod
    def _follow_harness(state: SimState):
        class Harness:
            pass

        from marsdog_sim2d.virtual_executor import LocalVirtualRunner

        harness = Harness()
        harness.sim_state = state
        harness.local_runner = LocalVirtualRunner()
        harness._voice_local_goal_id = None
        harness._pending_voice_command = None
        harness._pending_manual_need = None
        harness._manual_need_local_goal_id = None
        harness._emotion_idle_goal_id = None
        harness._calm_idle_index = 0
        harness._visual_idle_block_until = 0.0
        harness._next_emotion_idle_at = 0.0
        return harness

    def test_follow_request_persists_until_virtual_person_is_removed(self) -> None:
        state = SimState(
            ui_user_visible=True,
            ui_follow_user_requested=True,
        )
        harness = self._follow_harness(state)

        SimWindow._maybe_resume_requested_follow(harness)

        self.assertEqual(
            "follow_owner",
            harness.local_runner.plan.behavior_name,
        )
        self.assertTrue(state.ui_follow_user_active)

        _toggle_virtual_user(state)
        SimWindow._stop_virtual_user_follow(
            harness,
            "Virtual person removed from UI",
        )

        self.assertFalse(state.ui_user_visible)
        self.assertFalse(state.ui_follow_user_requested)
        self.assertFalse(state.ui_follow_user_active)
        self.assertIsNone(harness.local_runner.plan)

    def test_internal_need_pauses_follow_and_follow_resumes_after_recovery(self) -> None:
        state = SimState(
            ui_user_visible=True,
            ui_follow_user_requested=True,
        )
        harness = self._follow_harness(state)
        SimWindow._maybe_resume_requested_follow(harness)
        state.internal_need_state = {
            "triggered": [{"type": "Cleanliness"}],
        }

        SimWindow._yield_local_voice_to_external_action(harness)

        self.assertIsNone(harness.local_runner.plan)
        self.assertFalse(state.ui_follow_user_active)
        self.assertTrue(state.ui_follow_user_requested)

        state.internal_need_state = {
            "triggered": [],
            "demands": {},
        }
        SimWindow._maybe_resume_requested_follow(harness)

        self.assertEqual(
            "follow_owner",
            harness.local_runner.plan.behavior_name,
        )
        self.assertTrue(state.ui_follow_user_active)

    def test_stationary_owner_releases_follow_and_starts_idle_play(self) -> None:
        state = SimState(
            ui_user_visible=True,
            ui_follow_user_requested=True,
            ui_follow_stationary_since=(
                time.monotonic()
                - FOLLOW_STATIONARY_TIMEOUT_SEC
                - 1.0
            ),
        )
        harness = self._follow_harness(state)
        SimWindow._maybe_resume_requested_follow(harness)

        SimWindow._expire_stationary_follow_if_needed(harness)

        self.assertFalse(state.ui_follow_user_requested)
        self.assertFalse(state.ui_follow_user_active)
        self.assertIsNone(harness.local_runner.plan)

        state.action_result_at = time.time() - 1.0
        harness._next_emotion_idle_at = 0.0
        SimWindow._maybe_start_emotion_idle(harness)
        self.assertIsNotNone(harness.local_runner.plan)
        self.assertNotEqual(
            "follow_owner",
            harness.local_runner.plan.behavior_name,
        )

    def test_moving_owner_resets_stationary_follow_timeout(self) -> None:
        old_stationary_since = (
            time.monotonic() - FOLLOW_STATIONARY_TIMEOUT_SEC - 1.0
        )
        state = SimState(
            ui_user_visible=True,
            ui_follow_user_requested=True,
            ui_follow_stationary_since=old_stationary_since,
        )
        harness = self._follow_harness(state)

        _move_virtual_user_from_screen(
            state,
            config.WORLD_LEFT + 70.0,
            config.WORLD_BOTTOM + 90.0,
        )
        SimWindow._expire_stationary_follow_if_needed(harness)

        self.assertGreater(
            state.ui_follow_stationary_since,
            old_stationary_since,
        )
        self.assertTrue(state.ui_follow_user_requested)

    def test_stationary_timeout_never_starts_play_during_internal_need(self) -> None:
        state = SimState(
            ui_user_visible=True,
            ui_follow_user_requested=True,
            ui_follow_stationary_since=(
                time.monotonic() - FOLLOW_STATIONARY_TIMEOUT_SEC - 1.0
            ),
            internal_need_state={
                "triggered": [{"type": "Bladder"}],
            },
        )
        harness = self._follow_harness(state)

        SimWindow._expire_stationary_follow_if_needed(harness)
        state.action_result_at = time.time() - 1.0
        harness._next_emotion_idle_at = 0.0
        SimWindow._maybe_start_emotion_idle(harness)

        self.assertFalse(state.ui_follow_user_requested)
        self.assertIsNone(harness.local_runner.plan)

    def test_stationary_timeout_suppresses_late_external_follow_feedback(self) -> None:
        state = SimState(
            ui_user_visible=True,
            ui_follow_user_requested=True,
            ui_follow_user_active=True,
            ui_follow_goal_id="external-follow",
            ui_follow_stationary_since=(
                time.monotonic() - FOLLOW_STATIONARY_TIMEOUT_SEC - 1.0
            ),
            action_goal_id="external-follow",
            active_behavior="follow_owner",
            action_status="running",
            action_current_action="ACT_INTERACT_FOLLOW_OWNER",
            action_visual_action="ACT_INTERACT_FOLLOW_OWNER",
            action_executions={
                "external-follow": {
                    "sequence": 1,
                    "status": "running",
                },
            },
        )
        harness = self._follow_harness(state)

        SimWindow._expire_stationary_follow_if_needed(harness)

        self.assertEqual(
            "external-follow",
            state.ui_follow_suppressed_goal_id,
        )
        self.assertEqual("canceled", state.action_status)

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "external-follow",
                    "behavior_name": "follow_owner",
                    "status": "RUNNING",
                    "progress": 0.8,
                    "current_action": "ACT_INTERACT_FOLLOW_OWNER",
                },
                "late external follow feedback",
            )
        )
        self.assertEqual("canceled", state.action_status)

    def test_generated_virtual_user_asset_is_rgba_png(self) -> None:
        asset = (
            Path(__file__).parents[1]
            / "marsdog_sim2d"
            / "assets"
            / "human"
            / "virtual_owner.png"
        )
        data = asset.read_bytes()

        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertLessEqual(int.from_bytes(data[16:20], "big"), 256)
        self.assertLessEqual(int.from_bytes(data[20:24], "big"), 256)
        self.assertEqual(6, data[25])  # PNG color type 6 = RGBA.


if __name__ == "__main__":
    unittest.main()
