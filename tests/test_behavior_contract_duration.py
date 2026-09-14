import random
import unittest

from marsdog_sim2d.behavior.action_visuals import visual_for_action
from marsdog_sim2d.behavior.behavior_contract import (
    load_behavior_contract,
    select_behavior_stages,
)


class BehaviorContractDurationTests(unittest.TestCase):
    def test_feeding_action_duration_comes_from_contract(self) -> None:
        contract = load_behavior_contract()["eatNormally"]
        selected = select_behavior_stages(
            "eatNormally",
            rng=random.Random(7),
        )

        for declared, resolved in zip(contract.stages, selected):
            candidate_index = declared.candidates.index(resolved.action_id)
            duration_range = declared.duration_ranges[candidate_index]
            self.assertIsNotNone(duration_range)
            self.assertIsNotNone(resolved.duration_sec)
            minimum, maximum = duration_range
            self.assertLessEqual(minimum, resolved.duration_sec)
            self.assertLessEqual(resolved.duration_sec, maximum)

    def test_toilet_action_duration_ranges_match_the_contract(self) -> None:
        expected_ranges = {
            "ACT_SNIFF_AND_CIRCLE": (10.0, 60.0),
            "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT": (10.0, 60.0),
            "ACT_SQUAT_AND_ELIMINATE": (5.0, 30.0),
            "ACT_SCRATCH_SOIL_OR_GROUND": (3.0, 15.0),
            "ACT_SNIFF_EXCREMENT": (3.0, 15.0),
            "ACT_WALK_AWAY_OR_SHAKE_HEAD": (2.0, 8.0),
        }
        contract = load_behavior_contract()["barkShortAlert"]

        actual_ranges = {
            action_id: stage.duration_ranges[index]
            for stage in contract.stages
            for index, action_id in enumerate(stage.candidates)
        }

        self.assertEqual(expected_ranges, actual_ranges)

        selected = select_behavior_stages(
            "barkShortAlert",
            rng=random.Random(11),
            stage_preferences={
                "prepare": "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT",
            },
        )
        for stage in selected:
            minimum, maximum = expected_ranges[stage.action_id]
            self.assertIsNotNone(stage.duration_sec)
            self.assertLessEqual(minimum, stage.duration_sec)
            self.assertLessEqual(stage.duration_sec, maximum)

    def test_groom_selects_one_timed_action_with_an_exact_pose(self) -> None:
        expected = {
            "ACT_LICK_PAWS_OR_FUR": ((5.0, 30.0), "groom"),
            "ACT_RUB_BODY_AGAINST_OBJECT": (
                (5.0, 30.0),
                "body_rub_object",
            ),
            "ACT_PAW_AT_MUZZLE": ((5.0, 30.0), "paw"),
            "ACT_SHAKE_OFF_WATER": ((5.0, 30.0), "shake"),
            "ACT_SCRATCH_EAR_WITH_HIND_LEG": (
                (20.0, 180.0),
                "scratch_ear",
            ),
        }
        contract = load_behavior_contract()["lickPaws"]
        self.assertEqual(1, len(contract.stages))
        self.assertEqual(set(expected), set(contract.stages[0].candidates))

        actual_ranges = {
            action_id: contract.stages[0].duration_ranges[index]
            for index, action_id in enumerate(contract.stages[0].candidates)
        }
        self.assertEqual(
            {action_id: details[0] for action_id, details in expected.items()},
            actual_ranges,
        )

        selected = select_behavior_stages(
            "lickPaws",
            rng=random.Random(17),
        )
        self.assertEqual(1, len(selected))
        selected_action = selected[0]
        minimum, maximum = expected[selected_action.action_id][0]
        self.assertIsNotNone(selected_action.duration_sec)
        self.assertLessEqual(minimum, selected_action.duration_sec)
        self.assertLessEqual(selected_action.duration_sec, maximum)

        for action_id, (_duration_range, expected_pose) in expected.items():
            with self.subTest(action=action_id):
                visual = visual_for_action(action_id)
                self.assertIsNotNone(visual)
                self.assertEqual(expected_pose, visual.pose)

    def test_energy_contracts_select_one_timed_action_with_exact_targets(
        self,
    ) -> None:
        expected = {
            "restInPlace": (
                (
                    "ACT_SLOW_DOWN_IN_RESPONSE_TO_OWNER",
                    (5.0, 30.0),
                    ("walk", "current", True),
                ),
                (
                    "ACT_RETURN_TO_DOG_BED_FOR_CHARGING",
                    (5.0, 30.0),
                    ("walk", "bed", True),
                ),
            ),
            "recharge": (
                (
                    "ACT_RETURN_TO_CHARGER",
                    (60.0, 600.0),
                    ("walk", "charger", True),
                ),
                (
                    "ACT_BARK_AND_LIE_DOWN_IF_NO_CHARGER",
                    (3.0, 15.0),
                    ("bark_lying", "current", False),
                ),
            ),
        }

        for behavior_name, candidates in expected.items():
            with self.subTest(behavior=behavior_name):
                contract = load_behavior_contract()[behavior_name]
                self.assertEqual(1, len(contract.stages))
                stage = contract.stages[0]
                self.assertEqual(
                    [candidate[0] for candidate in candidates],
                    list(stage.candidates),
                )
                self.assertEqual(
                    [candidate[1] for candidate in candidates],
                    list(stage.duration_ranges),
                )

                selected = select_behavior_stages(
                    behavior_name,
                    rng=random.Random(29),
                )
                self.assertEqual(1, len(selected))
                action = selected[0]
                expected_range = dict(
                    (action_id, duration_range)
                    for action_id, duration_range, _visual in candidates
                )[action.action_id]
                self.assertIsNotNone(action.duration_sec)
                self.assertLessEqual(expected_range[0], action.duration_sec)
                self.assertLessEqual(action.duration_sec, expected_range[1])

                for action_id, _duration_range, visual_details in candidates:
                    visual = visual_for_action(action_id)
                    self.assertIsNotNone(visual)
                    self.assertEqual(
                        visual_details,
                        (visual.pose, visual.target, visual.moves),
                    )

    def test_sleep_contracts_match_all_stages_and_durations(self) -> None:
        prepare = {
            "ACT_CIRCLE_AROUND": (5.0, 30.0),
            "ACT_SCRATCH_BED_OR_GROUND": (5.0, 30.0),
            "ACT_STRETCH_BODY": (5.0, 30.0),
            "ACT_YAWN": (5.0, 30.0),
            "ACT_SPLoot_LIE_DOWN": (5.0, 30.0),
            "ACT_LICK_FUR_OR_PAWS": (20.0, 180.0),
        }
        sleeping = {
            "ACT_FLIP_BODY": (5.0, 30.0),
            "ACT_WHINE_SOFTLY": (5.0, 30.0),
            "ACT_TWITCH_OR_KICK_LEGS": (5.0, 30.0),
        }
        expected = {
            "sleepOnSide": {
                "prepare": prepare,
                "sleep_pose": {
                    "ACT_SLEEP_CURLED_UP": (60.0, 600.0),
                    "ACT_SLEEP_ON_STOMACH": (60.0, 600.0),
                    "ACT_SLEEP_ON_SIDE_CURLED_UP": (60.0, 600.0),
                },
                "sleeping": sleeping,
                "wakeup": {
                    "ACT_GETUP_CRAWL": (5.0, 30.0),
                    "ACT_GETUP_ROLL": (5.0, 30.0),
                    "ACT_GETUP_BOUNCE": (5.0, 30.0),
                    "ACT_GETUP_STRETCH": (3.0, 15.0),
                    "ACT_GETUP_SIT": (5.0, 30.0),
                },
            },
            "sleepNow": {
                "prepare": prepare,
                "sleep_pose": {
                    "ACT_SLEEP_ON_SIDE": (60.0, 600.0),
                    "ACT_SLEEP_ON_BACK": (60.0, 600.0),
                },
                "sleeping": sleeping,
                "wakeup": {
                    "ACT_GETUP_ROLL": (5.0, 30.0),
                    "ACT_GETUP_STRETCH": (5.0, 30.0),
                    "ACT_GETUP_SIT": (5.0, 30.0),
                },
            },
        }

        for behavior_name, expected_stages in expected.items():
            with self.subTest(behavior=behavior_name):
                contract = load_behavior_contract()[behavior_name]
                self.assertEqual(
                    list(expected_stages),
                    [stage.stage_id for stage in contract.stages],
                )
                for stage in contract.stages:
                    stage_expected = expected_stages[stage.stage_id]
                    self.assertEqual(
                        list(stage_expected),
                        list(stage.candidates),
                    )
                    self.assertEqual(
                        list(stage_expected.values()),
                        list(stage.duration_ranges),
                    )

                selected = select_behavior_stages(
                    behavior_name,
                    rng=random.Random(23),
                )
                self.assertEqual(4, len(selected))
                for stage in selected:
                    minimum, maximum = expected_stages[stage.stage_id][
                        stage.action_id
                    ]
                    self.assertIsNotNone(stage.duration_sec)
                    self.assertLessEqual(minimum, stage.duration_sec)
                    self.assertLessEqual(stage.duration_sec, maximum)


if __name__ == "__main__":
    unittest.main()
