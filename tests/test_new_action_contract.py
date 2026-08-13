from __future__ import annotations

import random
import unittest

from marsdog_sim2d import config
from marsdog_sim2d.action_visuals import ACTION_VISUALS, visual_for_action
from marsdog_sim2d.behavior_contract import (
    contract_action_ids,
    direct_behavior_names,
    load_behavior_contract,
    select_behavior_stages,
    stage_position,
)
from marsdog_sim2d.event_injector import build_custom_injection_command
from marsdog_sim2d.renderer import _dog_pose_for_action
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import VirtualRoom
from marsdog_sim2d.voice_commands import resolve_voice_command


class BehaviorContractTests(unittest.TestCase):
    def test_packaged_yaml_is_the_complete_runtime_contract(self) -> None:
        self.assertEqual(53, len(direct_behavior_names()))
        self.assertEqual(188, len(contract_action_ids()))
        self.assertEqual(
            (1, 4),
            stage_position("eatNormally", "prepare"),
        )
        self.assertIsNone(stage_position("EatNormally", "prepare"))

    def test_each_stage_selects_one_exact_candidate_in_order(self) -> None:
        contract = load_behavior_contract()["eatNormally"]
        selected = select_behavior_stages(
            "eatNormally",
            rng=random.Random(7),
        )
        self.assertEqual(len(contract.stages), len(selected))
        self.assertEqual(
            [stage.stage_id for stage in contract.stages],
            [stage.stage_id for stage in selected],
        )
        for declared, resolved in zip(contract.stages, selected):
            self.assertIn(resolved.action_id, declared.candidates)

    def test_local_plan_uses_contract_actions_without_legacy_aliases(self) -> None:
        plan = VirtualRoom().build_plan(
            {
                "goal_id": "contract-sit",
                "behavior_name": "sit_down",
                "priority_level": 5,
                "timeout_sec": 5.0,
            }
        )
        self.assertEqual("ACT_BASIC_SIT", plan.current_action)
        self.assertEqual("ACT_BASIC_SIT", plan.selected_stages[0].action_id)
        self.assertEqual(
            "ACT_BASIC_SIT",
            VirtualRoom().frame(plan, 0.5)["current_action"],
        )

    def test_exact_stage_boundary_reports_the_stage_that_completed(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "eat",
                "behavior_name": "eatNormally",
                "timeout_sec": 4.0,
            }
        )
        frame = room.frame(plan, 0.25)
        self.assertEqual("prepare", frame["current_stage"])
        self.assertEqual(
            "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
            frame["current_action"],
        )


class ExactActionPresentationTests(unittest.TestCase):
    def test_generated_assets_are_selected_by_exact_new_action_ids(self) -> None:
        expected = {
            "ACT_CHEW_OR_CARRY_FOOD": "chew_carry_food",
            "ACT_SCRATCH_FOOD": "scratch_food",
            "ACT_BURP": "burp",
            "ACT_LICK_LIPS_OR_NOSE": "lick_lips_nose",
            "ACT_CARRY_BOWL_AND_FOLLOW_OWNER": "carry_bowl",
            "ACT_SCRATCH_SOIL_OR_GROUND": "scratch_ground",
            "ACT_RUB_BODY_AGAINST_OBJECT": "body_rub_object",
            "ACT_SCRATCH_EAR_WITH_HIND_LEG": "scratch_ear",
            "ACT_STRETCH_BODY": "stretch",
            "ACT_YAWN": "yawn",
            "ACT_SPLoot_LIE_DOWN": "sploot",
            "ACT_GETUP_CRAWL": "wake_crawl",
            "ACT_GETUP_ROLL": "wake_roll",
            "ACT_GETUP_BOUNCE": "wake_spring",
            "ACT_GETUP_STRETCH": "wake_stretch",
            "ACT_GETUP_SIT": "wake_sit_up",
            "ACT_BARK_AND_LIE_DOWN_IF_NO_CHARGER": "bark_lying",
            "ACT_BARK_OR_WHINE_BRIEFLY": "tentative_bark_whine",
            "ACT_STOP_OBSERVE_AND_TILT_HEAD": "head_tilt_observe",
        }
        for action_id, pose in expected.items():
            with self.subTest(action_id=action_id):
                self.assertEqual(
                    pose,
                    _dog_pose_for_action(
                        action_id,
                        progress=1.0,
                        running=True,
                    ),
                )

    def test_unimplemented_contract_action_is_text_only_not_approximated(self) -> None:
        action_id = "ACT_GUARD_DOOR"
        self.assertIn(action_id, contract_action_ids())
        self.assertIsNone(visual_for_action(action_id))
        self.assertEqual("stand", _dog_pose_for_action(action_id))

    def test_visual_and_text_only_coverage_is_explicit(self) -> None:
        contract_ids = contract_action_ids()
        self.assertEqual(135, len(contract_ids & set(ACTION_VISUALS)))
        self.assertEqual(53, len(contract_ids - set(ACTION_VISUALS)))


class DebugProtocolTests(unittest.TestCase):
    def test_goal_waits_for_feedback_instead_of_guessing_an_action(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "goal-1",
                    "behavior_id": "behavior-1",
                    "behavior_name": "eatNormally",
                    "priority_level": 3,
                    "params": {},
                },
                "goal",
            )
        )
        self.assertEqual("pending", state.action_status)
        self.assertEqual("-", state.action_current_action)
        self.assertEqual((0, 0), (state.action_stage_index, state.action_stage_total))

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "goal-1",
                    "behavior_id": "behavior-1",
                    "behavior_name": "eatNormally",
                    "status": "RUNNING",
                    "progress": 0.25,
                    "current_stage": "prepare",
                    "current_action": "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
                    "safe_to_interrupt": True,
                    "message": "Stage 1/4: ACT_LOWER_HEAD_AND_APPROACH_BOWL",
                },
                "feedback",
            )
        )
        self.assertEqual("ACT_LOWER_HEAD_AND_APPROACH_BOWL", state.action_current_action)
        self.assertEqual((1, 4), (state.action_stage_index, state.action_stage_total))

    def test_stale_feedback_does_not_replace_the_current_goal_card(self) -> None:
        state = SimState(action_goal_id="new-goal", active_behavior="sleepNow")
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "old-goal",
                    "behavior_name": "eatNormally",
                    "current_stage": "eating",
                    "current_action": "ACT_LICK_FOOD",
                    "progress": 0.5,
                },
                "stale feedback",
            )
        )
        self.assertEqual("new-goal", state.action_goal_id)
        self.assertEqual("sleepNow", state.active_behavior)

    def test_pending_goal_waits_for_its_feedback_before_replacing_running_card(self) -> None:
        state = SimState(
            action_goal_id="running-goal",
            active_behavior="sleepNow",
            action_status="running",
            action_execution_sequence=1,
            action_active_sequence=1,
            action_executions={
                "running-goal": {
                    "sequence": 1,
                    "behavior_name": "sleepNow",
                    "status": "running",
                }
            },
        )
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "next-goal",
                    "behavior_name": "sit_down",
                    "priority_level": 5,
                },
                "pending goal",
            )
        )
        self.assertEqual("running-goal", state.action_goal_id)
        self.assertIn("next-goal", state.action_executions)

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "next-goal",
                    "behavior_name": "sit_down",
                    "status": "RUNNING",
                    "progress": 1.0,
                    "current_stage": "action",
                    "current_action": "ACT_BASIC_SIT",
                    "message": "Stage 1/1: ACT_BASIC_SIT",
                },
                "new active feedback",
            )
        )
        self.assertEqual("next-goal", state.action_goal_id)
        self.assertEqual("ACT_BASIC_SIT", state.action_current_action)

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "running-goal",
                    "behavior_name": "sleepNow",
                    "status": "RUNNING",
                    "progress": 0.75,
                    "current_stage": "sleeping",
                    "current_action": "ACT_FLIP_BODY",
                },
                "late old feedback",
            )
        )
        self.assertEqual("next-goal", state.action_goal_id)
        self.assertEqual("ACT_BASIC_SIT", state.action_current_action)

    def test_second_goal_does_not_replace_a_pending_goal_card(self) -> None:
        state = SimState()
        for goal_id, behavior_name in (
            ("first", "sit_down"),
            ("second", "stand_up"),
        ):
            state.apply_event(
                SimEvent(
                    "action_goal",
                    config.ACTION_GOAL_TOPIC,
                    {
                        "goal_id": goal_id,
                        "behavior_name": behavior_name,
                    },
                    "goal",
                )
            )
        self.assertEqual("first", state.action_goal_id)
        self.assertEqual("sit_down", state.active_behavior)
        self.assertIn("second", state.action_executions)

    def test_result_requires_success_and_completed_together(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "inconsistent",
                    "behavior_name": "sit_down",
                },
                "goal",
            )
        )
        state.apply_event(
            SimEvent(
                "action_result",
                config.ACTION_RESULT_TOPIC,
                {
                    "goal_id": "inconsistent",
                    "behavior_name": "sit_down",
                    "status": "SUCCESS",
                    "result": "failed",
                },
                "inconsistent result",
            )
        )
        self.assertEqual("failed", state.action_status)

    def test_message_is_not_parsed_as_structured_stage_data(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "message-only",
                    "behavior_name": "sit_down",
                },
                "goal",
            )
        )
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "message-only",
                    "behavior_name": "sit_down",
                    "status": "RUNNING",
                    "progress": 1.0,
                    "current_action": "ACT_BASIC_SIT",
                    "message": "untrusted Stage 9/9: fake",
                },
                "feedback",
            )
        )
        self.assertEqual(
            (0, 0),
            (state.action_stage_index, state.action_stage_total),
        )

    def test_failed_action_is_kept_for_text_only_result_display(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "failed-action",
                    "behavior_name": "expressCalmAlone",
                },
                "goal",
            )
        )
        state.apply_event(
            SimEvent(
                "action_result",
                config.ACTION_RESULT_TOPIC,
                {
                    "goal_id": "failed-action",
                    "behavior_name": "expressCalmAlone",
                    "status": "FAILED",
                    "result": "failed",
                    "failed_action": "ACT_GUARD_DOOR",
                },
                "result",
            )
        )
        self.assertEqual("ACT_GUARD_DOOR", state.action_current_action)

    def test_legacy_debug_topic_constants_are_removed(self) -> None:
        self.assertFalse(hasattr(config, "LEGACY_ACTION_GOAL_TOPIC"))
        self.assertFalse(hasattr(config, "LEGACY_ACTION_FEEDBACK_TOPIC"))
        self.assertFalse(hasattr(config, "LEGACY_ACTION_RESULT_TOPIC"))


class AudioProtocolTests(unittest.TestCase):
    def test_full_event_type_resolves_to_new_direct_behavior(self) -> None:
        command = resolve_voice_command(
            {
                "event_type": "EVT_VOICE_COMMAND_FOLLOW",
                "asr_text": "跟着我",
                "intent_confidence": 0.98,
            }
        )
        self.assertIsNotNone(command)
        self.assertEqual("follow_owner", command.behavior_name)

    def test_ui_command_publishes_full_behavior_tree_event_type(self) -> None:
        command = build_custom_injection_command(
            "Audio",
            {
                "audio_event_type": "EVT_VOICE_COMMAND_KNOWN",
                "audio_command_id": "CMD_SIT",
                "audio_asr_text": "坐下",
                "audio_confidence": "0.98",
            },
        )
        payload = command.messages[0].payload
        self.assertEqual("EVT_VOICE_COMMAND_SIT", payload["event_type"])
        self.assertTrue(payload["is_executable"])


if __name__ == "__main__":
    unittest.main()
