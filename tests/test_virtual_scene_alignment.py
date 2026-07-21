import unittest

from marsdog_sim2d import config
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import VirtualRoom


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
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_action": "ACT_FOLLOW",
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
                "behavior_name": "defecate",
                "timeout_sec": 3.0,
            }
        )

        self.assertGreaterEqual(float(pad["x"]), 760.0)
        self.assertGreaterEqual(float(pad["y"]), 380.0)
        self.assertEqual((plan.target_x, plan.target_y), (pad["x"], pad["y"]))
        self.assertEqual(plan.active_object, "pad")

    def test_safety_behavior_uses_rest_area_instead_of_sofa(self) -> None:
        room = VirtualRoom()
        bed = room.objects["bed"]
        plan = room.build_plan(
            {
                "goal_id": "safety-test",
                "behavior_name": "seekSafety",
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
                "behavior_name": "CMD_FOLLOW",
                "timeout_sec": 4.0,
            }
        )

        frame = room.frame(plan, 0.5)

        self.assertEqual(frame["user_pose"], {"x": room.user_x, "y": room.user_y})

        interaction_frame = room.frame_for_action(plan, "ACT_LOCO_MATCH_OWNER", 1.0)
        self.assertAlmostEqual(interaction_frame["dog_pose"]["x"], room.user_x - 112.0)
        self.assertAlmostEqual(interaction_frame["dog_pose"]["y"], room.user_y - 50.0)

    def test_hand_interaction_stops_beside_owner(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "hand-test",
                "behavior_name": "CMD_HAND",
                "timeout_sec": 3.0,
            }
        )

        self.assertEqual(plan.current_action, "ACT_HAND_INTERACTION")
        self.assertAlmostEqual(plan.target_x, room.user_x - 100.0)
        self.assertAlmostEqual(plan.target_y, room.user_y)

    def test_play_bow_keeps_owner_as_visual_target(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "play-bow-test",
                "behavior_name": "PLAY_BOW",
                "timeout_sec": 3.0,
            }
        )

        frame = room.frame_for_action(plan, "ACT_POSTURE_PLAY_BOW", 1.0)

        self.assertAlmostEqual(frame["dog_pose"]["x"], room.user_x - 118.0)
        self.assertAlmostEqual(frame["dog_pose"]["y"], room.user_y)

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
