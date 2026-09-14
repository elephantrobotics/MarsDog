import math
from pathlib import Path
import struct
import unittest

from PIL import Image

from marsdog_sim2d.behavior.action_visuals import visual_for_action
from marsdog_sim2d.behavior.behavior_contract import contract_action_ids
from bridge.virtual_executor import LocalVirtualRunner, VirtualRoom


class ToiletActionVisualTests(unittest.TestCase):
    ACTION_POSES = {
        "ACT_SNIFF_AND_CIRCLE": "sniff_circle",
        "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT": "sniff_circle",
        "ACT_SQUAT_AND_ELIMINATE": "toilet",
        "ACT_SCRATCH_SOIL_OR_GROUND": "scratch_ground_leave",
        "ACT_SNIFF_EXCREMENT": "sniff_excrement_leave",
        "ACT_WALK_AWAY_OR_SHAKE_HEAD": "walk_away_shake_head",
    }
    EXIT_ACTIONS = (
        "ACT_SCRATCH_SOIL_OR_GROUND",
        "ACT_SNIFF_EXCREMENT",
        "ACT_WALK_AWAY_OR_SHAKE_HEAD",
    )

    def setUp(self) -> None:
        self.room = VirtualRoom(dog_x=420.0, dog_y=340.0)
        self.plan = self.room.build_plan(
            {
                "goal_id": "toilet-visual",
                "behavior_name": "barkShortAlert",
                "timeout_sec": 5.0,
            }
        )

    def test_every_toilet_action_has_an_exact_ui_pose(self) -> None:
        contract_actions = contract_action_ids()

        for action_id, expected_pose in self.ACTION_POSES.items():
            with self.subTest(action=action_id):
                visual = visual_for_action(action_id)

                self.assertIn(action_id, contract_actions)
                self.assertIsNotNone(visual)
                self.assertEqual(expected_pose, visual.pose)

    def test_goal_boolean_selects_the_prepare_action(self) -> None:
        cases = (
            ({"toilet_spot_taught": True}, "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT"),
            ({"toilet_spot_taught": False}, "ACT_SNIFF_AND_CIRCLE"),
            ({}, "ACT_SNIFF_AND_CIRCLE"),
            ({"toilet_spot_taught": "true"}, "ACT_SNIFF_AND_CIRCLE"),
            ({"toilet_spot_taught": 1}, "ACT_SNIFF_AND_CIRCLE"),
        )

        for params, expected_action in cases:
            with self.subTest(params=params):
                plan = self.room.build_plan(
                    {
                        "goal_id": "toilet",
                        "behavior_name": "barkShortAlert",
                        "params": params,
                        "timeout_sec": 5.0,
                    }
                )

                self.assertEqual(expected_action, plan.current_action)
                self.assertEqual(expected_action, plan.selected_stages[0].action_id)
                self.assertEqual(
                    "ACT_SQUAT_AND_ELIMINATE",
                    plan.selected_stages[1].action_id,
                )
                self.assertIn(plan.selected_stages[2].action_id, self.EXIT_ACTIONS)

    def test_local_runner_accepts_params_and_compresses_stage_ratios(self) -> None:
        runner = LocalVirtualRunner()
        goal_event = runner.start(
            "barkShortAlert",
            timeout_sec=5.0,
            params={"toilet_spot_taught": True},
        )
        plan = runner.plan
        self.assertIsNotNone(plan)
        self.assertEqual(
            {"toilet_spot_taught": True},
            goal_event.payload["params"],
        )

        durations = [stage.duration_sec for stage in plan.selected_stages]
        self.assertTrue(all(duration is not None for duration in durations))
        total_duration = sum(float(duration) for duration in durations)
        first_stage_fraction = float(durations[0]) / total_duration
        self.assertLess(plan.duration, total_duration)
        self.assertEqual(
            "ACT_SQUAT_AND_ELIMINATE",
            runner.room.frame(plan, first_stage_fraction + 1e-6)[
                "current_action"
            ],
        )

    def test_untaught_prepare_action_circles_in_place(self) -> None:
        start = self.room.frame_for_action(
            self.plan,
            "ACT_SNIFF_AND_CIRCLE",
            0.0,
        )["dog_pose"]
        quarter = self.room.frame_for_action(
            self.plan,
            "ACT_SNIFF_AND_CIRCLE",
            0.25,
        )["dog_pose"]
        end = self.room.frame_for_action(
            self.plan,
            "ACT_SNIFF_AND_CIRCLE",
            1.0,
        )["dog_pose"]

        self.assertEqual((420.0, 340.0), (start["x"], start["y"]))
        self.assertNotEqual((start["x"], start["y"]), (quarter["x"], quarter["y"]))
        self.assertAlmostEqual(start["x"], end["x"])
        self.assertAlmostEqual(start["y"], end["y"])

    def test_taught_prepare_action_approaches_and_circles_pad(self) -> None:
        pad = self.room.objects["pad"]
        start = self.room.frame_for_action(
            self.plan,
            "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT",
            0.0,
        )["dog_pose"]
        circle = self.room.frame_for_action(
            self.plan,
            "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT",
            0.75,
        )["dog_pose"]
        end = self.room.frame_for_action(
            self.plan,
            "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT",
            1.0,
        )["dog_pose"]

        self.assertEqual((420.0, 340.0), (start["x"], start["y"]))
        self.assertNotEqual((float(pad["x"]), float(pad["y"])), (circle["x"], circle["y"]))
        self.assertAlmostEqual(float(pad["x"]), end["x"])
        self.assertAlmostEqual(float(pad["y"]), end["y"])

    def test_exit_actions_leave_the_toilet_pad(self) -> None:
        pad = self.room.objects["pad"]

        for action_id in self.EXIT_ACTIONS:
            with self.subTest(action=action_id):
                start = self.room.frame_for_action(
                    self.plan,
                    action_id,
                    0.0,
                )["dog_pose"]
                end = self.room.frame_for_action(
                    self.plan,
                    action_id,
                    1.0,
                )["dog_pose"]
                distance = math.hypot(
                    float(end["x"]) - float(pad["x"]),
                    float(end["y"]) - float(pad["y"]),
                )

                self.assertAlmostEqual(float(pad["x"]), start["x"])
                self.assertAlmostEqual(float(pad["y"]), start["y"])
                self.assertGreaterEqual(distance, 110.0)

    def test_generated_toilet_assets_are_transparent_256_pngs(self) -> None:
        asset_dir = (
            Path(__file__).parents[1]
            / "marsdog_sim2d"
            / "assets"
            / "dog"
        )
        asset_names = {
            pose
            for pose in self.ACTION_POSES.values()
            if pose not in {"toilet"}
        }

        for pose in asset_names:
            with self.subTest(pose=pose):
                asset_path = asset_dir / f"marsdog_{pose}.png"
                data = asset_path.read_bytes()

                self.assertEqual(b"\x89PNG\r\n\x1a\n", data[:8])
                self.assertEqual((256, 256), struct.unpack(">II", data[16:24]))
                self.assertEqual(6, data[25])

                with Image.open(asset_path) as image:
                    alpha = image.getchannel("A")

                    self.assertEqual((0, 255), alpha.getextrema())
                    self.assertEqual(0, alpha.getpixel((0, 0)))


if __name__ == "__main__":
    unittest.main()
