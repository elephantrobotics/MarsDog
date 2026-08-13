import math
import time
import unittest

from marsdog_sim2d import config
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import VirtualRoom
from marsdog_sim2d.voice_commands import OWNER_SIDE_COMMAND_BEHAVIORS


class UserAnchorTests(unittest.TestCase):
    def test_visual_detection_does_not_move_scene_user_anchor(self) -> None:
        state = SimState()
        original = (state.user_x, state.user_y)

        state.apply_event(
            SimEvent(
                "visual_event",
                config.TOPICS["visual_event"],
                {
                    "active_target": {
                        "identity": "owner",
                        "body_center": [0.15, 0.82],
                        "bbox": [0.1, 0.7, 0.2, 0.3],
                    }
                },
                "moving camera detection",
            )
        )

        self.assertEqual((state.user_x, state.user_y), original)

    def test_action_feedback_user_pose_does_not_move_scene_anchor(self) -> None:
        state = SimState()
        original = (state.user_x, state.user_y)

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "follow",
                    "behavior_name": "follow_owner",
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_action": "ACT_INTERACT_FOLLOW_OWNER",
                    "user_pose": {"x": 100.0, "y": 100.0},
                },
                "synthetic follow frame",
            )
        )

        self.assertEqual((state.user_x, state.user_y), original)


class InteractionAlignmentTests(unittest.TestCase):
    def test_default_room_objects_match_scene_state(self) -> None:
        state = SimState()
        room = VirtualRoom()

        self.assertEqual(state.room_objects, room.objects)
        self.assertIsNot(state.room_objects["bowl"], room.objects["bowl"])

    def test_toilet_stays_in_accessible_main_room_corner(self) -> None:
        room = VirtualRoom()
        pad = room.objects["pad"]
        plan = room.build_plan(
            {
                "goal_id": "toilet-test",
                "behavior_name": "barkShortAlert",
                "timeout_sec": 3.0,
            }
        )

        self.assertGreaterEqual(float(pad["x"]), 760.0)
        self.assertGreaterEqual(float(pad["y"]), 380.0)
        self.assertEqual((plan.target_x, plan.target_y), (pad["x"], pad["y"]))
        self.assertEqual(plan.active_object, "pad")

    def test_rest_behavior_uses_rest_area_instead_of_sofa(self) -> None:
        room = VirtualRoom()
        bed = room.objects["bed"]
        plan = room.build_plan(
            {
                "goal_id": "safety-test",
                "behavior_name": "restInPlace",
                "timeout_sec": 3.0,
            }
        )

        self.assertEqual((plan.target_x, plan.target_y), (bed["x"], bed["y"]))
        self.assertEqual(plan.active_object, "bed")

    def test_follow_keeps_user_fixed(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "follow-test",
                "behavior_name": "follow_owner",
                "timeout_sec": 4.0,
            }
        )

        frame = room.frame(plan, 0.5)

        self.assertEqual(frame["user_pose"], {"x": room.user_x, "y": room.user_y})

        interaction_frame = room.frame_for_action(
            plan,
            "ACT_INTERACT_FOLLOW_OWNER",
            1.0,
        )
        self.assertAlmostEqual(interaction_frame["dog_pose"]["x"], room.user_x - 112.0)
        self.assertAlmostEqual(interaction_frame["dog_pose"]["y"], room.user_y - 50.0)

    def test_hand_interaction_stops_beside_owner(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "hand-test",
                "behavior_name": "give_paw",
                "timeout_sec": 3.0,
            }
        )

        self.assertEqual(plan.current_action, "ACT_INTERACT_GIVE_PAW")
        frame = room.frame_for_action(
            plan,
            "ACT_INTERACT_GIVE_PAW",
            1.0,
        )
        self.assertAlmostEqual(
            frame["dog_pose"]["x"],
            room.user_x - 100.0,
        )
        self.assertAlmostEqual(frame["dog_pose"]["y"], room.user_y)

    def test_every_owner_side_shortcut_approaches_before_final_pose(self) -> None:
        for behavior_name in OWNER_SIDE_COMMAND_BEHAVIORS:
            with self.subTest(behavior=behavior_name):
                room = VirtualRoom(
                    dog_x=220.0,
                    dog_y=300.0,
                    user_x=720.0,
                    user_y=520.0,
                )
                plan = room.build_plan(
                    {
                        "goal_id": f"owner-side-{behavior_name}",
                        "behavior_name": behavior_name,
                        "timeout_sec": 4.0,
                    }
                )
                frame = room.frame(plan, 1.0)
                dog_pose = frame["dog_pose"]
                self.assertLessEqual(
                    (
                        (dog_pose["x"] - room.user_x) ** 2
                        + (dog_pose["y"] - room.user_y) ** 2
                    )
                    ** 0.5,
                    config.OWNER_NEAR_DISTANCE,
                )

    def test_owner_side_shortcuts_do_not_reach_owner_on_first_frame(self) -> None:
        for behavior_name in OWNER_SIDE_COMMAND_BEHAVIORS:
            with self.subTest(behavior=behavior_name):
                room = VirtualRoom(
                    dog_x=220.0,
                    dog_y=300.0,
                    user_x=720.0,
                    user_y=520.0,
                )
                plan = room.build_plan(
                    {
                        "goal_id": f"smooth-owner-{behavior_name}",
                        "behavior_name": behavior_name,
                        "timeout_sec": 4.0,
                    }
                )
                early_pose = room.frame(plan, 0.20)["dog_pose"]
                final_pose = room.frame(plan, 1.0)["dog_pose"]

                self.assertGreater(
                    math.hypot(
                        final_pose["x"] - early_pose["x"],
                        final_pose["y"] - early_pose["y"],
                    ),
                    20.0,
                )
                self.assertGreater(
                    math.hypot(
                        early_pose["x"] - room.dog_x,
                        early_pose["y"] - room.dog_y,
                    ),
                    0.0,
                )

    def test_owner_side_shortcut_stays_put_when_already_near(self) -> None:
        room = VirtualRoom(
            dog_x=610.0,
            dog_y=410.0,
            user_x=680.0,
            user_y=405.0,
        )
        plan = room.build_plan(
            {
                "goal_id": "near-owner-sit",
                "behavior_name": "sit_down",
                "timeout_sec": 4.0,
            }
        )
        frame = room.frame(plan, 1.0)

        self.assertEqual(610.0, frame["dog_pose"]["x"])
        self.assertEqual(410.0, frame["dog_pose"]["y"])

    def test_external_shortcut_uses_dragged_ui_owner_position(self) -> None:
        state = SimState(
            dog_x=300.0,
            dog_y=300.0,
            user_x=810.0,
            user_y=560.0,
            ui_user_visible=True,
        )
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "external-sit",
                    "behavior_name": "sit_down",
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
                    "progress": 1.0,
                    "current_stage": "action",
                    "current_action": "ACT_BASIC_SIT",
                },
                "external sit feedback",
            )
        )

        self.assertAlmostEqual(706.0, state.dog_motion_target_x)
        self.assertAlmostEqual(554.0, state.dog_motion_target_y)
        self.assertGreater(state.dog_motion_duration, 2.0)
        self.assertEqual(
            "ACT_BASIC_SIT",
            state.action_pending_visual_action,
        )
        total_duration = state.dog_motion_duration
        state.advance_virtual_motion(total_duration / 2.0)
        self.assertGreater(state.dog_x, 300.0)
        self.assertLess(state.dog_x, 706.0)
        self.assertEqual(
            "ACT_BASIC_SIT",
            state.action_pending_visual_action,
        )
        state.advance_virtual_motion(total_duration / 2.0)
        self.assertEqual("ACT_BASIC_SIT", state.action_visual_action)
        self.assertGreater(
            state.ui_owner_action_hold_until,
            time.monotonic(),
        )

    def test_human_play_bow_keeps_owner_as_visual_target(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "play-bow-test",
                "behavior_name": "inviteHumanToPlay",
                "timeout_sec": 3.0,
            }
        )

        frame = room.frame_for_action(plan, "ACT_PLAY_BOW", 1.0)

        self.assertAlmostEqual(frame["dog_pose"]["x"], room.user_x - 104.0)
        self.assertAlmostEqual(frame["dog_pose"]["y"], room.user_y - 6.0)

    def test_food_interaction_stops_beside_bowl(self) -> None:
        room = VirtualRoom()
        bowl = room.objects["bowl"]
        plan = room.build_plan(
            {
                "goal_id": "food-test",
                "behavior_name": "eatNormally",
                "timeout_sec": 3.0,
            }
        )

        self.assertAlmostEqual(plan.target_x, float(bowl["x"]) + 58.0)
        self.assertAlmostEqual(plan.target_y, float(bowl["y"]))
        self.assertEqual(plan.target_heading, 180.0)


if __name__ == "__main__":
    unittest.main()
