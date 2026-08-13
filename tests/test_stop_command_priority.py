from __future__ import annotations

import queue
import time
import unittest

from marsdog_sim2d import config
from marsdog_sim2d.arcade_viewer_node import SimWindow
from marsdog_sim2d.event_injector import default_field_values
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import LocalVirtualRunner


class StopCommandPriorityTests(unittest.TestCase):
    @staticmethod
    def _window_harness(state: SimState | None = None):
        class Harness:
            pass

        harness = Harness()
        harness.sim_state = state or SimState()
        harness.local_runner = LocalVirtualRunner()
        harness.injection_queue = queue.Queue()
        harness._emotion_idle_goal_id = None
        harness._voice_local_goal_id = None
        harness._last_voice_audio_at = None
        harness._pending_voice_command = None
        harness._pending_manual_need = None
        harness._manual_need_local_goal_id = None
        harness._manual_need_local_demand = None
        harness._manual_need_triggered_at = None
        harness._manual_hunger_phase = None
        harness._next_emotion_idle_at = 0.0
        harness._resolved_fields = lambda group: {
            **default_field_values(),
            **harness.sim_state.event_injector_fields,
        }
        return harness

    @staticmethod
    def _apply_stop_audio(state: SimState) -> None:
        state.apply_event(
            SimEvent(
                "audio_event",
                config.TOPICS["audio_event"],
                {
                    "event_type": "EVT_VOICE_COMMAND_STOP",
                    "command_id": "CMD_STOP",
                    "asr_text": "停止",
                    "is_executable": True,
                },
                "stop voice command",
                received_at=time.time(),
            )
        )

    def test_stop_immediately_cancels_local_external_command(self) -> None:
        harness = self._window_harness()
        harness.local_runner.sync_from_state(harness.sim_state)
        start_event = harness.local_runner.start(
            "sit_down",
            timeout_sec=4.0,
        )
        harness._voice_local_goal_id = harness.local_runner.plan.goal_id
        harness.sim_state.apply_event(start_event)
        harness.sim_state.dog_motion_duration = 2.0
        harness.sim_state.dog_motion_target_x = 800.0

        self._apply_stop_audio(harness.sim_state)
        SimWindow._capture_latest_voice_command(harness)

        self.assertIsNone(harness.local_runner.plan)
        self.assertIsNone(harness._voice_local_goal_id)
        self.assertEqual("canceled", harness.sim_state.action_status)
        self.assertEqual("-", harness.sim_state.action_visual_action)
        self.assertEqual(0.0, harness.sim_state.dog_motion_duration)
        self.assertEqual(
            harness.sim_state.dog_x,
            harness.sim_state.dog_motion_target_x,
        )

    def test_stop_cancels_external_display_and_ignores_late_feedback(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "external-sit",
                    "behavior_name": "sit_down",
                    "status": "PENDING",
                    "params": {"source": "voice"},
                },
                "external sit goal",
            )
        )
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "external-sit",
                    "behavior_name": "sit_down",
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_action": "ACT_BASIC_SIT",
                },
                "external sit feedback",
            )
        )
        harness = self._window_harness(state)

        self._apply_stop_audio(state)
        SimWindow._capture_latest_voice_command(harness)

        self.assertEqual("canceled", state.action_status)
        self.assertEqual("-", state.action_visual_action)
        self.assertIn(
            "external-sit",
            state.ui_stopped_external_goal_ids,
        )

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "external-sit",
                    "behavior_name": "sit_down",
                    "status": "RUNNING",
                    "progress": 0.9,
                    "current_action": "ACT_BASIC_SIT",
                },
                "late external sit feedback",
            )
        )
        self.assertEqual("canceled", state.action_status)
        self.assertEqual("-", state.action_visual_action)

    def test_stop_does_not_cancel_active_internal_need(self) -> None:
        state = SimState(
            internal_need_state={
                "demands": {
                    "Sleepiness": {
                        "level": "TRIGGERED",
                        "triggered": True,
                    }
                }
            },
            ui_follow_user_requested=True,
            ui_follow_user_active=False,
        )
        harness = self._window_harness(state)
        harness.local_runner.sync_from_state(state)
        start_event = harness.local_runner.start(
            "sleepNow",
            timeout_sec=6.0,
        )
        need_goal_id = harness.local_runner.plan.goal_id
        harness._manual_need_local_goal_id = need_goal_id
        harness._manual_need_local_demand = "SLEEPINESS"
        state.apply_event(start_event)

        self._apply_stop_audio(state)
        SimWindow._capture_latest_voice_command(harness)

        self.assertIsNotNone(harness.local_runner.plan)
        self.assertEqual(
            need_goal_id,
            harness.local_runner.plan.goal_id,
        )
        self.assertEqual("sleepNow", state.active_behavior)
        self.assertNotEqual("canceled", state.action_status)
        self.assertFalse(state.ui_follow_user_requested)

    def test_stop_preserves_external_executor_need_after_value_recovers(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "external-eating",
                    "behavior_name": "eatNormally",
                    "status": "PENDING",
                    "params": {"source": "internal_need"},
                },
                "external eating need goal",
            )
        )
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "external-eating",
                    "behavior_name": "eatNormally",
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_action": "ACT_LICK_FOOD",
                },
                "external eating feedback",
            )
        )
        harness = self._window_harness(state)

        self._apply_stop_audio(state)
        SimWindow._capture_latest_voice_command(harness)

        self.assertEqual("running", state.action_status)
        self.assertEqual("eatNormally", state.active_behavior)
        self.assertEqual("ACT_LICK_FOOD", state.action_current_action)
        self.assertNotIn(
            "external-eating",
            state.ui_stopped_external_goal_ids,
        )

    def test_stop_does_not_target_keyboard_rendering_self_test(self) -> None:
        harness = self._window_harness()
        harness.local_runner.sync_from_state(harness.sim_state)
        start_event = harness.local_runner.start(
            "spin_around",
            timeout_sec=3.5,
        )
        keyboard_goal_id = harness.local_runner.plan.goal_id
        harness.sim_state.apply_event(start_event)

        self._apply_stop_audio(harness.sim_state)
        SimWindow._capture_latest_voice_command(harness)

        self.assertIsNotNone(harness.local_runner.plan)
        self.assertEqual(
            keyboard_goal_id,
            harness.local_runner.plan.goal_id,
        )
        self.assertNotIn(
            keyboard_goal_id,
            harness.sim_state.ui_stopped_external_goal_ids,
        )

    def test_ui_stop_is_not_published_during_internal_need(self) -> None:
        state = SimState(
            ui_user_visible=True,
            internal_need_state={
                "demands": {
                    "Hunger": {
                        "level": "TRIGGERED",
                        "triggered": True,
                    }
                }
            },
        )
        state.event_injector_fields = {
            **default_field_values(),
            "audio_event_type": "EVT_VOICE_COMMAND_KNOWN",
            "audio_command_id": "CMD_STOP",
            "audio_asr_text": "停止",
        }
        harness = self._window_harness(state)

        SimWindow._send_custom_injection(harness, "Audio")

        self.assertTrue(harness.injection_queue.empty())
        self.assertEqual(
            "内部需求正在执行，停止指令已忽略",
            state.ui_pending_confirmation["message"],
        )


if __name__ == "__main__":
    unittest.main()
