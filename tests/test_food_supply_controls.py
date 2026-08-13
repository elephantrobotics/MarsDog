import time
import unittest

from marsdog_sim2d import config
from marsdog_sim2d.arcade_viewer_node import (
    SimWindow,
    _has_active_internal_need,
)
from marsdog_sim2d.behavior_contract import SelectedStage
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import LocalVirtualRunner


class FoodSupplyControlTests(unittest.TestCase):
    @staticmethod
    def _harness(state: SimState, runner: LocalVirtualRunner):
        class Harness:
            pass

        harness = Harness()
        harness.sim_state = state
        harness.local_runner = runner
        harness._manual_need_local_goal_id = None
        harness._manual_need_local_demand = None
        harness._manual_need_triggered_at = None
        harness._manual_hunger_phase = None
        return harness

    def test_bowl_starts_empty_and_button_cycles_food_state(self) -> None:
        state = SimState()
        harness = self._harness(state, LocalVirtualRunner())
        self.assertFalse(state.ui_bowl_has_food)
        SimWindow._toggle_bowl_food(harness)
        self.assertTrue(state.ui_bowl_has_food)
        SimWindow._toggle_bowl_food(harness)
        self.assertFalse(state.ui_bowl_has_food)

    def test_local_eating_stage_pauses_at_empty_bowl(self) -> None:
        state = SimState()
        runner = LocalVirtualRunner()
        state.apply_event(runner.start("eatNormally", timeout_sec=4.0))
        runner.plan.selected_stages = (
            SelectedStage("prepare", 1, "ACT_LOWER_HEAD_AND_APPROACH_BOWL"),
            SelectedStage("eating", 2, "ACT_LICK_FOOD"),
            SelectedStage("interaction", 3, "ACT_BURP"),
            SelectedStage("exit", 4, "ACT_LICK_LIPS_OR_NOSE"),
        )
        runner.started_at = time.monotonic() - runner.plan.duration * 0.45

        event = runner.update(state)[0]
        self.assertEqual("ACT_LICK_FOOD", event.payload["current_action"])
        self.assertIsNotNone(runner.food_wait_started_at)
        state.apply_event(event)
        self.assertTrue(state.ui_food_waiting)
        self.assertEqual(
            "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            state.action_pending_visual_action,
        )
        self.assertEqual(
            "ACT_LICK_FOOD",
            state.action_current_action,
        )
        state.advance_virtual_motion(state.dog_motion_duration)
        self.assertEqual(
            "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            state.action_visual_action,
        )

    def test_local_food_wait_resumes_after_food_is_added(self) -> None:
        state = SimState(
            active_behavior="eatNormally",
            action_status="running",
            action_goal_id="local-food",
            action_current_action="ACT_LICK_FOOD",
            action_visual_action="ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            ui_food_waiting=True,
            ui_food_wait_goal_id="local-food",
            ui_food_wait_resume_action="ACT_LICK_FOOD",
        )
        runner = LocalVirtualRunner()
        runner.plan = runner.room.build_plan(
            {
                "goal_id": "local-food",
                "behavior_name": "eatNormally",
                "timeout_sec": 4.0,
            }
        )
        harness = self._harness(state, runner)

        SimWindow._toggle_bowl_food(harness)

        self.assertTrue(state.ui_bowl_has_food)
        self.assertTrue(state.ui_food_eating_authorized)
        self.assertFalse(state.ui_food_waiting)
        self.assertEqual("ACT_LICK_FOOD", state.action_visual_action)

    def test_manual_hunger_waits_then_starts_four_stage_eating(self) -> None:
        state = SimState()
        runner = LocalVirtualRunner()
        goal = runner.start(
            "seekFood",
            timeout_sec=5.5,
            preferred_action="ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
        )
        state.apply_event(goal)
        harness = self._harness(state, runner)
        harness._manual_need_local_goal_id = runner.plan.goal_id
        harness._manual_need_local_demand = "HUNGER"
        harness._manual_need_triggered_at = time.time() - 1.0
        harness._manual_hunger_phase = "seeking"

        for event in runner.update(state):
            state.apply_event(event)

        self.assertTrue(state.ui_food_waiting)
        self.assertIsNotNone(runner.plan)
        self.assertEqual("seekFood", runner.plan.behavior_name)
        self.assertEqual(
            "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            runner.plan.current_action,
        )

        SimWindow._toggle_bowl_food(harness)

        self.assertTrue(state.ui_bowl_has_food)
        self.assertFalse(state.ui_food_waiting)
        self.assertEqual("eating", harness._manual_hunger_phase)
        self.assertEqual("eatNormally", runner.plan.behavior_name)
        self.assertEqual(4, len(runner.plan.selected_stages))
        self.assertEqual(
            ["prepare", "eating", "interaction", "exit"],
            [stage.stage_id for stage in runner.plan.selected_stages],
        )

    def test_completed_manual_eating_keeps_food_and_returns_to_idle_play(self) -> None:
        state = SimState(
            internal_need_state={
                "schema_version": "1.0",
                "raw": {"manual_source": "marsdog_sim2d"},
                "triggered": [{"type": "Hunger", "value": 82.0}],
                "levelEvents": {
                    "Hunger": "NEED_HUNGER_TRIGGERED",
                },
                "demands": {
                    "Hunger": {
                        "value": 82.0,
                        "triggered": True,
                        "overflow": False,
                        "level": "TRIGGERED",
                        "levelActive": True,
                    },
                },
            },
        )
        runner = LocalVirtualRunner()
        state.ui_bowl_has_food = True
        goal = runner.start("eatNormally", timeout_sec=8.0)
        state.apply_event(goal)
        harness = self._harness(state, runner)
        harness._manual_need_local_goal_id = runner.plan.goal_id
        harness._manual_need_local_demand = "HUNGER"
        harness._manual_need_triggered_at = time.time() - 9.0
        harness._manual_hunger_phase = "eating"
        harness._next_emotion_idle_at = 0.0

        runner.started_at = time.monotonic() - 9.0
        for event in runner.update(state):
            state.apply_event(event)
        SimWindow._advance_manual_need_completion(harness)

        self.assertTrue(state.ui_bowl_has_food)
        self.assertFalse(_has_active_internal_need(state))
        self.assertEqual(
            "NORMAL",
            state.internal_need_state["demands"]["Hunger"]["level"],
        )
        self.assertEqual(
            "NEED_HUNGER_RECOVERED",
            state.internal_need_signal_event["event_type"],
        )

        harness._emotion_idle_goal_id = None
        harness._voice_local_goal_id = None
        harness._pending_voice_command = None
        harness._pending_manual_need = None
        harness._visual_idle_block_until = 0.0
        harness._calm_idle_index = 0
        state.action_result_at = time.time() - 1.0
        SimWindow._maybe_start_emotion_idle(harness)

        self.assertIsNotNone(runner.plan)
        self.assertNotEqual("eatNormally", runner.plan.behavior_name)

    def test_external_eating_requires_service_even_when_prefilled(self) -> None:
        state = SimState(ui_bowl_has_food=True)
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "external-food",
                    "behavior_name": "eatNormally",
                },
                "goal",
            )
        )
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "external-food",
                    "behavior_name": "eatNormally",
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_stage": "eating",
                    "current_action": "ACT_LICK_FOOD",
                },
                "eating stage",
            )
        )

        self.assertTrue(state.ui_food_waiting)
        self.assertFalse(state.ui_food_eating_authorized)
        self.assertEqual(
            "waiting_eating_authorization",
            state.action_phase,
        )
        self.assertEqual(
            "ACT_LICK_FOOD",
            state.action_current_action,
        )
        self.assertEqual(
            "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            state.action_visual_action,
        )

    def test_service_authorization_releases_exact_eating_action(self) -> None:
        state = SimState(
            ui_bowl_has_food=True,
            active_behavior="eatNormally",
            action_status="running",
            action_goal_id="external-food",
            action_current_action="ACT_LICK_AND_SWALLOW",
            action_visual_action="ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            ui_food_waiting=True,
            ui_food_wait_goal_id="external-food",
            ui_food_wait_resume_action="ACT_LICK_AND_SWALLOW",
        )
        state.apply_event(
            SimEvent(
                "feeding_authorized",
                config.FEEDING_TRY_START_SERVICE,
                {"activeGoalId": "external-food"},
                "authorized",
            )
        )
        self.assertFalse(state.ui_food_waiting)
        self.assertTrue(state.ui_food_eating_authorized)
        self.assertEqual(
            "ACT_LICK_AND_SWALLOW",
            state.action_current_action,
        )

    def test_new_goal_clears_food_gate_but_waits_for_feedback_to_switch_card(self) -> None:
        state = SimState(
            active_behavior="eatNormally",
            action_status="running",
            action_goal_id="food-goal",
            action_execution_sequence=1,
            action_active_sequence=1,
            action_executions={
                "food-goal": {
                    "sequence": 1,
                    "behavior_name": "eatNormally",
                }
            },
            ui_food_waiting=True,
            ui_food_wait_goal_id="food-goal",
        )
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "stop-goal",
                    "behavior_name": "emergency_stop",
                },
                "new goal",
            )
        )
        self.assertFalse(state.ui_food_waiting)
        self.assertEqual("food-goal", state.action_goal_id)

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "stop-goal",
                    "behavior_name": "emergency_stop",
                    "status": "RUNNING",
                    "progress": 1.0,
                    "current_stage": "action",
                    "current_action": "ACT_SYSTEM_EMERGENCY_STOP",
                },
                "stop feedback",
            )
        )
        self.assertEqual("stop-goal", state.action_goal_id)


if __name__ == "__main__":
    unittest.main()
