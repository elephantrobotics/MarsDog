import importlib
import importlib.util
import unittest

from marsdog_sim2d.simevent import event_injector
from marsdog_sim2d.simevent import abnormal_simulation
from marsdog_sim2d.simevent.sim_state import SimState
from marsdog_sim2d.behavior.action_visuals import visual_for_action


class ExternalDamageSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        module_name = "marsdog_sim2d.simevent.external_damage_simulation"
        spec = importlib.util.find_spec(module_name)
        self.assertIsNotNone(spec, "external damage simulator is missing")
        self.damage = importlib.import_module(module_name)

    def test_catalog_contains_all_documented_damage_events(self) -> None:
        expected_levels = {
            "EVT_DAMAGE_JOINT_OR_MOTOR_FAILURE": "D1",
            "EVT_DAMAGE_STRUCTURE_EXPOSED": "D1",
            "EVT_DAMAGE_RECOVERY_FAILED": "D1",
            "EVT_DAMAGE_POWER_RISK": "D1",
            "EVT_DAMAGE_PERCEPTION_FAILURE": "D1",
            "EVT_DAMAGE_JOINT_ANOMALY_AFTER_IMPACT": "D2",
            "EVT_DAMAGE_SHELL_DISPLACED": "D2",
            "EVT_DAMAGE_SUSTAINED_PRESSURE": "D2",
            "EVT_DAMAGE_FALL_RECOVERY_DIFFICULT": "D2",
            "EVT_DAMAGE_LIGHT_IMPACT": "D3",
            "EVT_DAMAGE_SHORT_PUSH_PULL": "D3",
            "EVT_DAMAGE_SLIP_IMBALANCE": "D3",
        }

        self.assertEqual(expected_levels, {
            event_type: spec.suggested_level
            for event_type, spec in self.damage.EXTERNAL_DAMAGE_SPECS.items()
        })

    def test_risk_boundaries_and_confirmation_are_unambiguous(self) -> None:
        cases = (
            (100, False, "D1"),
            (90.01, False, "D1"),
            (90, False, "D2"),
            (70.01, False, "D2"),
            (70, False, "D3"),
            (40.01, False, "D3"),
            (40, False, "NONE"),
            (0, False, "NONE"),
            (20, True, "D1"),
        )

        for score, confirmed, expected in cases:
            with self.subTest(score=score, confirmed=confirmed):
                self.assertEqual(
                    expected,
                    self.damage.resolve_damage_risk(score, confirmed),
                )

    def test_representative_events_keep_steps_duration_and_hold_mode(self) -> None:
        joint = self.damage.EXTERNAL_DAMAGE_SPECS[
            "EVT_DAMAGE_JOINT_OR_MOTOR_FAILURE"
        ]
        impact = self.damage.EXTERNAL_DAMAGE_SPECS[
            "EVT_DAMAGE_LIGHT_IMPACT"
        ]
        shell = self.damage.EXTERNAL_DAMAGE_SPECS[
            "EVT_DAMAGE_SHELL_DISPLACED"
        ]

        self.assertEqual("Fault Joint Safe Hold", joint.response_name)
        self.assertEqual("持续保持", joint.duration_label)
        self.assertEqual("manual", joint.hold_mode)
        self.assertEqual(
            (
                "ACT_EMERGENCY_STOP",
                "ACT_FAULT_JOINT_SAFE_HOLD",
                "ACT_CONTINUOUS_BARK",
            ),
            tuple(step.action for step in joint.steps),
        )

        self.assertEqual("2~8s", impact.duration_label)
        self.assertEqual("timed", impact.hold_mode)
        self.assertEqual(
            (
                "ACT_BODY_FLINCH",
                "ACT_STEP_BACK",
                "ACT_CHECK_ABNORMAL_POSITION",
            ),
            tuple(step.action for step in impact.steps),
        )

        self.assertEqual("inspection", shell.hold_mode)
        self.assertEqual("持续至检查完成", shell.duration_label)

    def test_payload_clamps_score_and_keeps_internal_level_separate(self) -> None:
        payload = self.damage.build_external_damage_payload(
            "EVT_DAMAGE_LIGHT_IMPACT",
            130,
            confirmed=False,
        )

        self.assertEqual(100.0, payload["risk_score"])
        self.assertEqual("D1", payload["risk_code"])
        self.assertEqual("损伤 L1", payload["risk_level"])
        self.assertEqual("D3", payload["suggested_risk_code"])
        self.assertEqual("损伤 L3", payload["suggested_risk_level"])
        self.assertEqual("local_external_damage_demo", payload["source"])

    def test_only_timed_damage_auto_finishes_after_last_step(self) -> None:
        self.assertTrue(
            self.damage.damage_auto_finishes("EVT_DAMAGE_LIGHT_IMPACT")
        )
        self.assertFalse(
            self.damage.damage_auto_finishes(
                "EVT_DAMAGE_JOINT_OR_MOTOR_FAILURE"
            )
        )
        self.assertFalse(
            self.damage.damage_auto_finishes("EVT_DAMAGE_SHELL_DISPLACED")
        )

    def test_damage_injection_preview_is_local_and_normalized(self) -> None:
        command = event_injector.build_custom_injection_command(
            "Damage",
            {
                "damage_event_type": "EVT_DAMAGE_LIGHT_IMPACT",
                "damage_risk_score": "75",
                "damage_confirmed": "false",
            },
        )

        self.assertEqual("custom_damage", command.template_id)
        self.assertEqual(1, len(command.messages))
        message = command.messages[0]
        self.assertEqual("local://external-damage", message.topic)
        self.assertEqual("external_damage_event", message.payload["kind"])
        self.assertEqual("D2", message.payload["risk_code"])
        self.assertFalse(message.payload["confirmed"])

        confirmed = event_injector.build_custom_injection_command(
            "Damage",
            {
                "damage_event_type": "EVT_DAMAGE_LIGHT_IMPACT",
                "damage_risk_score": "20",
                "damage_confirmed": "confirmed",
            },
        )
        self.assertTrue(confirmed.messages[0].payload["confirmed"])
        self.assertEqual("D1", confirmed.messages[0].payload["risk_code"])

    def test_sim_state_has_separate_external_damage_context(self) -> None:
        state = SimState()

        self.assertTrue(hasattr(state, "ui_external_damage"))
        self.assertIsNone(state.ui_external_damage)
        self.assertTrue(hasattr(state, "latest_external_damage_event"))
        self.assertIsNone(state.latest_external_damage_event)

    def test_sim_state_records_local_damage_without_ros_topic_stats(self) -> None:
        state = SimState()
        event = event_injector.build_local_external_damage_event(
            "EVT_DAMAGE_LIGHT_IMPACT",
            60,
            confirmed=False,
        )

        state.apply_event(event)

        self.assertIsNotNone(state.latest_external_damage_event)
        self.assertEqual(
            "EVT_DAMAGE_LIGHT_IMPACT",
            state.latest_external_damage_event["event_type"],
        )
        self.assertNotIn("local://external-damage", state.topic_stats)
        self.assertEqual("SYS", state.event_records[-1]["source"])

    def test_abnormal_player_uses_event_specific_damage_steps(self) -> None:
        payload = self.damage.build_external_damage_payload(
            "EVT_DAMAGE_LIGHT_IMPACT",
            60,
            confirmed=False,
        )
        state = SimState(
            ui_abnormal_simulation_active=True,
            ui_external_damage=payload,
            ui_abnormal_step_started_at=10.0,
        )

        abnormal_simulation.apply_abnormal_step(state, 0, now=100.0)

        self.assertEqual("ACT_BODY_FLINCH", state.action_current_action)
        self.assertEqual("身体瞬间缩紧", state.action_stage_label)
        self.assertEqual(3, state.action_stage_total)
        self.assertEqual("2~8s", state.action_params["duration_label"])
        self.assertEqual("D3", state.action_params["risk_code"])

    def test_timed_sequence_finishes_after_last_accelerated_step(self) -> None:
        self.assertTrue(
            hasattr(abnormal_simulation, "should_finish_abnormal_simulation")
        )
        timed_payload = self.damage.build_external_damage_payload(
            "EVT_DAMAGE_LIGHT_IMPACT",
            60,
            confirmed=False,
        )
        state = SimState(
            ui_abnormal_simulation_active=True,
            ui_external_damage=timed_payload,
            ui_abnormal_step_index=2,
            ui_abnormal_step_started_at=10.0,
        )

        self.assertFalse(
            abnormal_simulation.should_finish_abnormal_simulation(
                state,
                now_monotonic=10.79,
            )
        )
        self.assertTrue(
            abnormal_simulation.should_finish_abnormal_simulation(
                state,
                now_monotonic=10.8,
            )
        )

        state.ui_external_damage = self.damage.build_external_damage_payload(
            "EVT_DAMAGE_JOINT_OR_MOTOR_FAILURE",
            95,
            confirmed=True,
        )
        self.assertFalse(
            abnormal_simulation.should_finish_abnormal_simulation(
                state,
                now_monotonic=30.0,
            )
        )

    def test_damage_only_actions_have_explicit_2d_poses(self) -> None:
        expected_poses = {
            "ACT_FAULT_JOINT_SAFE_HOLD": "anxiety_cower",
            "ACT_STRUCTURAL_DAMAGE_HOLD": "lie",
            "ACT_RECOVERY_FAILED_CALL": "tentative_bark_whine",
            "ACT_POWER_DAMAGE_SAFE_HOLD": "lie",
            "ACT_PERCEPTION_FAULT_SAFE_STOP": "stand",
            "ACT_CROUCH_JOINT_PROTECT": "anxiety_cower",
            "ACT_HOLD_REQUEST_INSPECTION": "sit",
            "ACT_RELEASE_FROM_PRESSURE": "shake",
            "ACT_GUARD_INJURY": "anxiety_cower",
            "ACT_LIE_DOWN_REASSESS": "lie",
            "ACT_YIELD_FORCE": "walk",
            "ACT_REPOSITION": "walk",
            "ACT_BRACE_BALANCE": "stand",
            "ACT_TEST_GROUND": "head_tilt_observe",
        }

        for action, expected_pose in expected_poses.items():
            with self.subTest(action=action):
                visual = visual_for_action(action)
                self.assertIsNotNone(visual)
                self.assertEqual(expected_pose, visual.pose)


if __name__ == "__main__":
    unittest.main()
