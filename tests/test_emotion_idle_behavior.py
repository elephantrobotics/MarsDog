import random
import time
import unittest
from unittest.mock import patch

from marsdog_sim2d.arcade_viewer_node import (
    CALM_IDLE_PLAY_DELAY_OPTIONS_SEC,
    CALM_IDLE_SEQUENCE,
    EMOTION_IDLE_BEHAVIORS,
    MANUAL_NEED_BEHAVIORS,
    MANUAL_NEED_RECOVERY,
    SimWindow,
    _dominant_emotion_name,
    _has_active_internal_need,
    _has_pending_action_execution,
    _newest_external_goal_id,
    _random_calm_idle_delay,
    _recover_manual_need_state,
)
from marsdog_sim2d.action_visuals import visual_for_action
from marsdog_sim2d.event_injector import build_custom_injection_command
from marsdog_sim2d.parsers import (
    parse_internal_need_signal_event,
    parse_internal_need_state,
)
from marsdog_sim2d.behavior_contract import direct_behavior_names
from marsdog_sim2d.sim_state import SimState
from marsdog_sim2d.sim_state import SimEvent
from marsdog_sim2d.virtual_executor import LocalVirtualRunner, VirtualRoom


class EmotionIdleBehaviorTests(unittest.TestCase):
    @staticmethod
    def _window_harness():
        class Harness:
            pass

        harness = Harness()
        harness.sim_state = SimState()
        harness.local_runner = LocalVirtualRunner()
        harness._emotion_idle_goal_id = None
        harness._voice_local_goal_id = None
        harness._pending_voice_command = None
        harness._last_manual_need_signal_at = None
        harness._pending_manual_need = None
        harness._manual_need_local_goal_id = None
        harness._manual_need_local_demand = None
        harness._manual_need_triggered_at = None
        harness._manual_hunger_phase = None
        harness._calm_idle_index = 0
        harness._next_emotion_idle_at = 0.0
        harness._last_visual_event_at = None
        harness._last_visual_activity_signature = None
        harness._visual_idle_block_until = 0.0
        return harness

    def test_every_emotion_uses_a_direct_contract_behavior(self) -> None:
        self.assertEqual(
            {"CALM", "JOY", "EXCITE", "ANXIETY", "FEAR", "CURIOUS"},
            set(EMOTION_IDLE_BEHAVIORS),
        )
        contract_names = set(direct_behavior_names())
        for behavior_name, _duration in EMOTION_IDLE_BEHAVIORS.values():
            self.assertIn(behavior_name, contract_names)

    def test_calm_cycle_uses_contract_instead_of_removed_ui_behaviors(self) -> None:
        self.assertEqual(
            (
                ("expressCalmAlone", 4.5, None),
                ("roll_over", 3.2, "ACT_TRICK_ROLL_OVER"),
                (
                    "expressExcitementAlone",
                    3.8,
                    "ACT_SHAKE_TOY",
                ),
            ),
            CALM_IDLE_SEQUENCE,
        )
        plan = VirtualRoom().build_plan(
            {
                "goal_id": "calm",
                "behavior_name": "expressCalmAlone",
                "timeout_sec": 4.5,
            }
        )
        self.assertTrue(plan.selected_stages)
        self.assertIn(
            plan.current_action,
            {
                "ACT_GUARD_DOOR",
                "ACT_YAWN",
                "ACT_STRETCH",
                "ACT_PATROL",
                "ACT_SPLOOT",
            },
        )

    def test_calm_cycle_adds_belly_and_toy_sprite_actions(self) -> None:
        harness = self._window_harness()
        harness.sim_state.emotion_state = {"dominantEmotion": "Calm"}

        harness._calm_idle_index = 1
        SimWindow._maybe_start_emotion_idle(harness)
        self.assertEqual(
            "ACT_TRICK_ROLL_OVER",
            harness.local_runner.plan.current_action,
        )
        self.assertTrue(
            harness.local_runner.plan.local_preview_random_target,
        )
        self.assertNotEqual(
            (
                harness.local_runner.room.dog_x,
                harness.local_runner.room.dog_y,
            ),
            (
                harness.local_runner.plan.target_x,
                harness.local_runner.plan.target_y,
            ),
        )
        self.assertEqual(
            "joy_belly",
            visual_for_action("ACT_TRICK_ROLL_OVER").pose,
        )

        harness = self._window_harness()
        harness.sim_state.emotion_state = {"dominantEmotion": "Calm"}
        harness._calm_idle_index = 2
        SimWindow._maybe_start_emotion_idle(harness)
        self.assertEqual(
            "ACT_SHAKE_TOY",
            harness.local_runner.plan.current_action,
        )
        self.assertTrue(
            harness.local_runner.plan.local_preview_random_target,
        )
        self.assertEqual(
            "excite_toy",
            visual_for_action("ACT_SHAKE_TOY").pose,
        )

    def test_calm_target_is_a_new_safe_random_position(self) -> None:
        room = VirtualRoom()
        targets = set()
        for index in range(8):
            plan = room.build_plan(
                {
                    "goal_id": f"calm-{index}",
                    "behavior_name": "expressCalmAlone",
                    "timeout_sec": 4.5,
                }
            )
            targets.add((round(plan.target_x, 2), round(plan.target_y, 2)))
        self.assertGreater(len(targets), 1)

    def test_calm_idle_gap_is_randomly_one_two_or_three_seconds(self) -> None:
        generator = random.Random(20260729)
        delays = {
            _random_calm_idle_delay(generator)
            for _index in range(30)
        }
        self.assertEqual(set(CALM_IDLE_PLAY_DELAY_OPTIONS_SEC), delays)

    def test_calm_idle_schedules_gap_after_selected_behavior(self) -> None:
        harness = self._window_harness()
        harness.sim_state.emotion_state = {"dominantEmotion": "Calm"}
        before = time.monotonic()
        with patch(
            "marsdog_sim2d.arcade_viewer_node._random_calm_idle_delay",
            return_value=2.0,
        ):
            SimWindow._maybe_start_emotion_idle(harness)
        self.assertIsNotNone(harness.local_runner.plan)
        gap = (
            harness._next_emotion_idle_at
            - before
            - harness.local_runner.plan.duration
        )
        self.assertGreaterEqual(gap, 2.0)
        self.assertLess(gap, 2.1)

    def test_need_and_empty_bowl_wait_block_idle(self) -> None:
        state = SimState(
            ui_food_waiting=True,
            internal_need_state={
                "triggered": [],
                "demands": {
                    "Hunger": {
                        "triggered": False,
                        "level": "NORMAL",
                    }
                },
            },
        )
        self.assertTrue(_has_active_internal_need(state))

        harness = self._window_harness()
        harness.sim_state = state
        SimWindow._maybe_start_emotion_idle(harness)
        self.assertIsNone(harness.local_runner.plan)

    def test_external_executor_connection_blocks_local_autoplay(self) -> None:
        harness = self._window_harness()
        harness.sim_state.ros_executor_online = True

        SimWindow._maybe_start_emotion_idle(harness)

        self.assertIsNone(harness.local_runner.plan)
        self.assertIsNone(harness._emotion_idle_goal_id)

    def test_external_executor_connection_stops_running_autoplay(self) -> None:
        harness = self._window_harness()
        event = harness.local_runner.start("expressCalmAlone")
        harness.sim_state.apply_event(event)
        harness._emotion_idle_goal_id = harness.local_runner.plan.goal_id
        harness.sim_state.ros_executor_online = True

        SimWindow._yield_emotion_idle_to_external_action(harness)

        self.assertIsNone(harness.local_runner.plan)
        self.assertIsNone(harness._emotion_idle_goal_id)

    def test_manual_cleanliness_interrupts_idle_and_runs_groom_fallback(self) -> None:
        harness = self._window_harness()
        idle_goal = harness.local_runner.start("expressCalmAlone")
        harness.sim_state.apply_event(idle_goal)
        harness._emotion_idle_goal_id = harness.local_runner.plan.goal_id

        command = build_custom_injection_command(
            "Need",
            {
                "need_demand": "Cleanliness",
                "need_value": "82",
            },
        )
        state_event = parse_internal_need_state(command.messages[0].payload)
        signal_event = parse_internal_need_signal_event(
            command.messages[1].payload
        )
        signal_event.received_at = time.time() - 1.0
        harness.sim_state.apply_event(state_event)
        harness.sim_state.apply_event(signal_event)

        SimWindow._capture_latest_manual_need(harness)
        SimWindow._yield_emotion_idle_to_external_action(harness)
        self.assertIsNone(harness.local_runner.plan)
        SimWindow._maybe_start_manual_need(harness)

        self.assertIsNotNone(harness.local_runner.plan)
        self.assertEqual(
            "lickPaws",
            harness.local_runner.plan.behavior_name,
        )
        self.assertEqual(
            harness.local_runner.plan.goal_id,
            harness._manual_need_local_goal_id,
        )

        harness.local_runner.started_at = (
            time.monotonic() - harness.local_runner.plan.duration - 0.1
        )
        for event in harness.local_runner.update(harness.sim_state):
            harness.sim_state.apply_event(event)
        SimWindow._advance_manual_need_completion(harness)

        self.assertEqual(
            "NORMAL",
            harness.sim_state.internal_need_state["demands"][
                "Cleanliness"
            ]["level"],
        )
        self.assertFalse(_has_active_internal_need(harness.sim_state))

        harness._next_emotion_idle_at = 0.0
        harness.sim_state.action_result_at = time.time() - 1.0
        SimWindow._maybe_start_emotion_idle(harness)
        self.assertIsNotNone(harness.local_runner.plan)

    def test_every_manual_need_fallback_is_a_direct_contract_behavior(self) -> None:
        contract_names = set(direct_behavior_names())
        self.assertEqual(
            {
                "HUNGER",
                "BLADDER",
                "SLEEPINESS",
                "CLEANLINESS",
                "ENERGY",
                "SOCIAL",
                "EXPLORATION",
            },
            set(MANUAL_NEED_BEHAVIORS),
        )
        for behavior_name, _duration in MANUAL_NEED_BEHAVIORS.values():
            self.assertIn(behavior_name, contract_names)
        self.assertEqual(
            set(MANUAL_NEED_BEHAVIORS),
            set(MANUAL_NEED_RECOVERY),
        )

    def test_manual_need_recovery_covers_all_seven_demands(self) -> None:
        for demand_key, (demand_name, recovery_value) in (
            MANUAL_NEED_RECOVERY.items()
        ):
            with self.subTest(demand=demand_key):
                state = SimState(
                    internal_need_state={
                        "schema_version": "1.0",
                        "raw": {"manual_source": "marsdog_sim2d"},
                        "triggered": [{"type": demand_name}],
                        "levelEvents": {
                            demand_name: f"NEED_{demand_key}_TRIGGERED",
                        },
                        "demands": {
                            demand_name: {
                                "value": 82.0,
                                "triggered": True,
                                "overflow": False,
                                "level": "TRIGGERED",
                                "levelActive": True,
                            },
                        },
                        "sleep": {
                            "isSleeping": demand_key == "SLEEPINESS",
                        },
                    }
                )

                self.assertTrue(
                    _recover_manual_need_state(state, demand_key)
                )

                recovered = state.internal_need_state["demands"][
                    demand_name
                ]
                self.assertEqual("NORMAL", recovered["level"])
                self.assertEqual(recovery_value, recovered["value"])
                self.assertFalse(recovered["triggered"])
                self.assertFalse(_has_active_internal_need(state))
                if demand_key == "SLEEPINESS":
                    self.assertFalse(
                        state.internal_need_state["sleep"]["isSleeping"]
                    )

    def test_recovering_one_need_does_not_release_another_trigger(self) -> None:
        state = SimState(
            internal_need_state={
                "raw": {"manual_source": "marsdog_sim2d"},
                "triggered": [
                    {"type": "Cleanliness"},
                    {"type": "Bladder"},
                ],
                "demands": {
                    "Cleanliness": {
                        "value": 82.0,
                        "triggered": True,
                        "level": "TRIGGERED",
                    },
                    "Bladder": {
                        "value": 82.0,
                        "triggered": True,
                        "level": "TRIGGERED",
                    },
                },
            }
        )

        self.assertTrue(
            _recover_manual_need_state(state, "CLEANLINESS")
        )

        self.assertEqual(
            "NORMAL",
            state.internal_need_state["demands"]["Cleanliness"]["level"],
        )
        self.assertEqual(
            "TRIGGERED",
            state.internal_need_state["demands"]["Bladder"]["level"],
        )
        self.assertTrue(_has_active_internal_need(state))

    def test_external_goal_prevents_duplicate_manual_need_fallback(self) -> None:
        harness = self._window_harness()
        triggered_at = time.time() - 1.0
        harness._pending_manual_need = (
            "lickPaws",
            4.5,
            triggered_at,
            "CLEANLINESS",
        )
        harness.sim_state.apply_event(
            SimEvent(
                "action_goal",
                "/debug/execute_behavior/goal",
                {
                    "goal_id": "external-clean-goal",
                    "behavior_name": "lickPaws",
                    "status": "PENDING",
                },
                "external clean goal",
                received_at=triggered_at + 0.1,
            )
        )

        SimWindow._maybe_start_manual_need(harness)

        self.assertIsNone(harness.local_runner.plan)
        self.assertIsNone(harness._pending_manual_need)

    def test_older_external_follow_cannot_preempt_new_internal_need(self) -> None:
        harness = self._window_harness()
        triggered_at = time.time() - 1.0
        harness.sim_state.apply_event(
            SimEvent(
                "action_goal",
                "/debug/execute_behavior/goal",
                {
                    "goal_id": "older-follow-goal",
                    "behavior_name": "follow_owner",
                    "status": "PENDING",
                },
                "older follow goal",
                received_at=triggered_at - 1.0,
            )
        )
        harness._pending_manual_need = (
            "lickPaws",
            4.5,
            triggered_at,
            "CLEANLINESS",
        )

        SimWindow._maybe_start_manual_need(harness)
        SimWindow._yield_local_need_to_external_action(harness)

        self.assertIsNotNone(harness.local_runner.plan)
        self.assertEqual(
            "lickPaws",
            harness.local_runner.plan.behavior_name,
        )

    def test_pending_external_goal_blocks_idle_and_supersedes_preview(self) -> None:
        state = SimState(
            action_executions={
                "local-preview": {
                    "sequence": 1,
                    "status": "running",
                },
                "external-goal": {
                    "sequence": 2,
                    "status": "pending",
                },
            }
        )
        self.assertTrue(_has_pending_action_execution(state))
        self.assertEqual(
            "external-goal",
            _newest_external_goal_id(state, {"local-preview"}),
        )

    def test_dominant_emotion_uses_authoritative_field(self) -> None:
        state = SimState(
            emotion_state={
                "dominantEmotion": "Excite",
                "emotions": {"Joy": {"value": 100}},
            }
        )
        self.assertEqual("EXCITE", _dominant_emotion_name(state))
        self.assertEqual("CALM", _dominant_emotion_name(SimState()))


if __name__ == "__main__":
    unittest.main()
