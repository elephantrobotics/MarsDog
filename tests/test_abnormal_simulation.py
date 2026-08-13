import unittest
from pathlib import Path
import time

from marsdog_sim2d import config
from marsdog_sim2d.arcade_viewer_node import (
    SimWindow,
    _activate_abnormal_simulation,
    _deactivate_abnormal_simulation,
)
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import LocalVirtualRunner


class AbnormalSimulationTests(unittest.TestCase):
    def test_window_toggle_pauses_and_resumes_local_plan(self) -> None:
        class FakeRunner:
            def __init__(self) -> None:
                self.plan = object()
                self.pause_called = False
                self.resume_called = False

            def pause(self) -> None:
                self.pause_called = True

            def resume(self) -> None:
                self.resume_called = True

        class Harness:
            pass

        harness = Harness()
        harness.sim_state = SimState(
            active_behavior="expressCalmAlone",
            action_status="running",
            action_goal_id="local-calm",
        )
        harness.local_runner = FakeRunner()
        harness._emotion_idle_goal_id = "local-calm"
        harness._voice_local_goal_id = None
        harness._pending_voice_command = None
        harness._calm_idle_index = 2
        harness._last_voice_audio_at = None
        harness._last_visual_event_at = None
        harness._next_emotion_idle_at = 0.0

        SimWindow._toggle_abnormal_simulation(harness)

        self.assertTrue(harness.sim_state.ui_abnormal_simulation_active)
        self.assertTrue(harness.local_runner.pause_called)
        self.assertIsNotNone(harness.local_runner.plan)

        SimWindow._toggle_abnormal_simulation(harness)

        self.assertFalse(harness.sim_state.ui_abnormal_simulation_active)
        self.assertTrue(harness.local_runner.resume_called)
        self.assertEqual("running", harness.sim_state.action_status)
        self.assertEqual(
            "expressCalmAlone",
            harness.sim_state.active_behavior,
        )

    def test_activation_stops_motion_and_locks_whine_action(self) -> None:
        state = SimState(
            dog_x=310.0,
            dog_y=420.0,
            dog_motion_target_x=700.0,
            dog_motion_target_y=200.0,
            dog_motion_duration=1.5,
            active_behavior="seekFood",
            action_status="running",
            action_goal_id="goal-food",
            action_current_action="ACT_LOWER_HEAD_AND_APPROACH_BOWL",
            action_visual_action="ACT_LOWER_HEAD_AND_APPROACH_BOWL",
            ui_user_visible=True,
            ui_follow_user_active=True,
            ui_follow_goal_id="goal-food",
        )

        _activate_abnormal_simulation(state)

        self.assertTrue(state.ui_abnormal_simulation_active)
        self.assertEqual("goal-food", state.ui_abnormal_interrupted_goal_id)
        self.assertEqual("abnormalSimulation", state.active_behavior)
        self.assertEqual("ACT_VOCAL_WHINE", state.action_current_action)
        self.assertEqual("ACT_VOCAL_WHINE", state.action_visual_action)
        self.assertEqual(0.0, state.dog_motion_duration)
        self.assertEqual((310.0, 420.0), (state.dog_motion_target_x, state.dog_motion_target_y))
        self.assertFalse(state.ui_follow_user_active)
        self.assertIsNone(state.ui_follow_goal_id)

        _deactivate_abnormal_simulation(state)

        self.assertEqual("seekFood", state.active_behavior)
        self.assertEqual(
            "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
            state.action_visual_action,
        )
        self.assertEqual(1.5, state.dog_motion_duration)
        self.assertEqual(
            (700.0, 200.0),
            (state.dog_motion_target_x, state.dog_motion_target_y),
        )
        self.assertTrue(state.ui_follow_user_active)
        self.assertEqual("goal-food", state.ui_follow_goal_id)

    def test_action_feedback_cannot_override_active_abnormal_mode(self) -> None:
        state = SimState(
            active_behavior="seekFood",
            action_status="running",
            action_goal_id="goal-food",
        )
        _activate_abnormal_simulation(state)

        state.apply_event(
            SimEvent(
                kind="action_feedback",
                topic="/execute_behavior/_action/feedback",
                summary="external feedback",
                payload={
                    "goal_id": "goal-food",
                    "behavior_name": "seekFood",
                    "current_action": "ACT_LICK_FOOD",
                    "status": "running",
                    "progress": 0.8,
                    "dog_pose": {"x": 900.0, "y": 700.0},
                },
            )
        )

        self.assertEqual("abnormalSimulation", state.active_behavior)
        self.assertEqual("ACT_VOCAL_WHINE", state.action_visual_action)
        self.assertNotEqual((900.0, 700.0), (state.dog_x, state.dog_y))
        self.assertEqual(1, len(state.ui_abnormal_deferred_events))

    def test_clearing_restores_interrupted_goal(self) -> None:
        state = SimState(
            active_behavior="sleepNow",
            action_status="running",
            action_goal_id="goal-sleep",
            action_current_action="ACT_SLEEP_ON_SIDE",
            action_visual_action="ACT_SLEEP_ON_SIDE",
        )
        _activate_abnormal_simulation(state)
        _deactivate_abnormal_simulation(state)

        self.assertEqual("running", state.action_status)
        self.assertEqual("sleepNow", state.active_behavior)
        self.assertEqual("ACT_SLEEP_ON_SIDE", state.action_visual_action)

        state.apply_event(
            SimEvent(
                kind="action_feedback",
                topic=config.ACTION_FEEDBACK_TOPIC,
                summary="stale feedback",
                payload={
                    "goal_id": "goal-sleep",
                    "behavior_name": "sleepNow",
                    "current_action": "ACT_SLEEP_ON_SIDE",
                    "status": "running",
                },
            )
        )
        self.assertEqual("running", state.action_status)
        self.assertEqual("sleepNow", state.active_behavior)

        state.apply_event(
            SimEvent(
                kind="action_goal",
                topic=config.ACTION_GOAL_TOPIC,
                summary="new goal",
                payload={
                    "goal_id": "goal-new",
                    "behavior_name": "exploreRoom",
                },
            )
        )
        self.assertEqual("running", state.action_status)
        state.apply_event(
            SimEvent(
                kind="action_feedback",
                topic=config.ACTION_FEEDBACK_TOPIC,
                summary="new goal feedback",
                payload={
                    "goal_id": "goal-new",
                    "behavior_name": "exploreRoom",
                    "current_action": "ACT_PATROL",
                    "status": "running",
                },
            )
        )
        self.assertEqual("exploreRoom", state.active_behavior)
        self.assertIsNone(state.ui_abnormal_interrupted_goal_id)

    def test_deferred_external_stages_resume_in_order(self) -> None:
        state = SimState(
            active_behavior="sit_down",
            action_status="running",
            action_goal_id="goal-sit",
            action_current_action="ACT_LOCO_WALK_TO_OWNER",
            action_visual_action="ACT_LOCO_WALK_TO_OWNER",
        )
        _activate_abnormal_simulation(state)
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "goal-sit",
                    "behavior_name": "sit_down",
                    "status": "RUNNING",
                    "progress": 0.8,
                    "current_action": "ACT_BASIC_SIT",
                },
                "deferred sit feedback",
            )
        )
        state.apply_event(
            SimEvent(
                "action_result",
                config.ACTION_RESULT_TOPIC,
                {
                    "goal_id": "goal-sit",
                    "behavior_name": "sit_down",
                    "status": "SUCCESS",
                    "result": "completed",
                },
                "deferred sit result",
            )
        )
        _deactivate_abnormal_simulation(state)

        class Harness:
            pass

        harness = Harness()
        harness.sim_state = state
        state.ui_abnormal_replay_next_at = 0.0
        SimWindow._replay_deferred_abnormal_event(harness)
        self.assertEqual(
            "ACT_BASIC_SIT",
            state.action_current_action,
        )
        self.assertEqual("running", state.action_status)

        state.ui_abnormal_replay_next_at = 0.0
        SimWindow._replay_deferred_abnormal_event(harness)
        self.assertEqual("success", state.action_status)
        self.assertEqual("completed", state.action_result)

    def test_internal_need_plan_keeps_remaining_duration(self) -> None:
        state = SimState(
            internal_need_state={
                "demands": {
                    "Sleepiness": {
                        "level": "TRIGGERED",
                        "triggered": True,
                    }
                }
            }
        )
        runner = LocalVirtualRunner()
        runner.sync_from_state(state)
        start_event = runner.start("sleepNow", timeout_sec=6.0)
        state.apply_event(start_event)

        class Harness:
            pass

        harness = Harness()
        harness.sim_state = state
        harness.local_runner = runner
        harness._emotion_idle_goal_id = None
        harness._voice_local_goal_id = None
        harness._pending_voice_command = None
        harness._manual_need_local_goal_id = runner.plan.goal_id
        harness._manual_need_local_demand = "SLEEPINESS"
        harness._calm_idle_index = 0
        harness._last_voice_audio_at = None
        harness._last_visual_event_at = None
        harness._next_emotion_idle_at = time.monotonic() + 6.0

        SimWindow._toggle_abnormal_simulation(harness)
        self.assertIsNotNone(runner.paused_at)
        runner.paused_at -= 30.0
        state.ui_abnormal_started_monotonic -= 30.0

        SimWindow._toggle_abnormal_simulation(harness)
        self.assertIsNone(runner.paused_at)
        self.assertIsNotNone(runner.plan)
        self.assertEqual(
            harness._manual_need_local_goal_id,
            runner.plan.goal_id,
        )
        events = runner.update(state)
        self.assertTrue(events)
        self.assertLess(events[0].payload["progress"], 1.0)

    def test_whine_asset_is_rgba_png(self) -> None:
        asset = (
            Path(__file__).parents[1]
            / "marsdog_sim2d"
            / "assets"
            / "dog"
            / "marsdog_whine.png"
        )
        data = asset.read_bytes()

        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(256, int.from_bytes(data[16:20], "big"))
        self.assertEqual(256, int.from_bytes(data[20:24], "big"))
        self.assertEqual(6, data[25])


if __name__ == "__main__":
    unittest.main()
