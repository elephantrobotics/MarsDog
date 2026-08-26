import math
import unittest

from marsdog_sim2d.action_visuals import visual_for_action
from marsdog_sim2d.virtual_executor import VirtualRoom


class FoodExitVisualTests(unittest.TestCase):
    ACTION_POSES = {
        "ACT_WALK_AWAY_OR_LIE_DOWN": "walk_away_lie_down",
        "ACT_SNIFF_GROUND_FOR_CRUMBS_AND_LEAVE": "sniff_crumbs_leave",
        "ACT_LICK_LIPS_OR_NOSE_AND_LEAVE": "lick_lips_leave",
    }

    def test_food_exit_actions_have_moving_visuals(self) -> None:
        for action_id, expected_pose in self.ACTION_POSES.items():
            with self.subTest(action=action_id):
                visual = visual_for_action(action_id)

                self.assertIsNotNone(visual)
                self.assertEqual(expected_pose, visual.pose)
                self.assertEqual("away", visual.target)
                self.assertTrue(visual.moves)

    def test_food_exit_actions_move_away_from_bowl(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "food-exit",
                "behavior_name": "eatExcitedly",
                "timeout_sec": 4.0,
            }
        )
        bowl = room.objects["bowl"]
        bowl_start_x = float(bowl["x"]) + 58.0
        bowl_start_y = float(bowl["y"])

        for action_id in self.ACTION_POSES:
            with self.subTest(action=action_id):
                start_frame = room.frame_for_action(plan, action_id, 0.0)
                end_frame = room.frame_for_action(plan, action_id, 1.0)
                start_pose = start_frame["dog_pose"]
                end_pose = end_frame["dog_pose"]
                distance = math.hypot(
                    float(end_pose["x"]) - float(bowl["x"]),
                    float(end_pose["y"]) - float(bowl["y"]),
                )

                self.assertAlmostEqual(bowl_start_x, float(start_pose["x"]))
                self.assertAlmostEqual(bowl_start_y, float(start_pose["y"]))
                self.assertGreaterEqual(distance, 110.0)


if __name__ == "__main__":
    unittest.main()
