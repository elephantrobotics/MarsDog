import unittest

from marsdog_sim2d.action_visuals import (
    ACTION_VISUALS,
    is_text_only_action,
)
from marsdog_sim2d.behavior_contract import contract_action_ids
from marsdog_sim2d.renderer import (
    _dog_pose_for_action,
    _dog_sprite_angle,
    _sleep_indicator_visible,
)
from marsdog_sim2d.sim_state import SimState
from marsdog_sim2d.virtual_executor import VirtualRoom


class DogPoseMappingTests(unittest.TestCase):
    def test_side_view_sprite_stays_upright_for_every_heading(self) -> None:
        for heading in (0.0, 90.0, 180.0, 270.0, -90.0, 450.0):
            with self.subTest(heading=heading):
                self.assertEqual(0.0, _dog_sprite_angle(heading))

    def test_exact_contract_actions_choose_expected_images(self) -> None:
        cases = {
            "ACT_LICK_FOOD": "eat",
            "ACT_CHEW_OR_CARRY_FOOD": "chew_carry_food",
            "ACT_SCRATCH_FOOD": "scratch_food",
            "ACT_SQUAT_AND_ELIMINATE": "toilet",
            "ACT_SLEEP_ON_SIDE": "sleep_closed",
            "ACT_GETUP_STRETCH": "wake_stretch",
            "ACT_INTERACT_GIVE_PAW": "paw",
            "ACT_TRICK_SPIN": "spin",
            "ACT_TRICK_PLAY_DEAD": "play_dead",
            "ACT_STOP_OBSERVE_AND_TILT_HEAD": "head_tilt_observe",
        }
        for action, expected_pose in cases.items():
            with self.subTest(action=action):
                self.assertEqual(
                    expected_pose,
                    _dog_pose_for_action(
                        action,
                        progress=1.0,
                        running=True,
                    ),
                )

    def test_removed_legacy_act_is_not_approximated(self) -> None:
        self.assertEqual(
            "stand",
            _dog_pose_for_action(
                "ACT_POSTURE_TOILET_SQUAT",
                progress=1.0,
                running=True,
            ),
        )
        self.assertTrue(
            is_text_only_action("ACT_POSTURE_TOILET_SQUAT")
        )

    def test_all_visualized_upstream_actions_are_exact_catalog_keys(self) -> None:
        non_contract = set(ACTION_VISUALS) - contract_action_ids()
        self.assertEqual({"ACT_VOCAL_WHINE"}, non_contract)

    def test_elimination_stage_targets_the_toilet_pad(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "toilet",
                "behavior_name": "barkShortAlert",
                "timeout_sec": 4.0,
            }
        )
        frame = room.frame_for_action(
            plan,
            "ACT_SQUAT_AND_ELIMINATE",
            1.0,
        )
        pad = room.objects["pad"]
        self.assertEqual("ACT_SQUAT_AND_ELIMINATE", frame["current_action"])
        self.assertAlmostEqual(float(pad["x"]), frame["dog_pose"]["x"])
        self.assertAlmostEqual(float(pad["y"]), frame["dog_pose"]["y"])

    def test_sleep_indicator_follows_authoritative_sleep_state(self) -> None:
        sleeping = SimState(
            action_status="success",
            internal_need_state={"sleep": {"isSleeping": True}},
        )
        awake = SimState(
            active_behavior="sleepNow",
            action_status="success",
            action_current_action="ACT_SLEEP_ON_SIDE",
            action_visual_action="ACT_SLEEP_ON_SIDE",
            internal_need_state={"sleep": {"isSleeping": False}},
        )
        self.assertTrue(_sleep_indicator_visible(sleeping))
        self.assertFalse(_sleep_indicator_visible(awake))

    def test_wakeup_action_hides_sleep_indicator_immediately(self) -> None:
        state = SimState(
            action_status="running",
            action_current_action="ACT_GETUP_ROLL",
            action_visual_action="ACT_GETUP_ROLL",
            internal_need_state={"sleep": {"isSleeping": True}},
        )
        self.assertFalse(_sleep_indicator_visible(state))


if __name__ == "__main__":
    unittest.main()
