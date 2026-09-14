import unittest

from marsdog_sim2d.behavior.feeding_behavior import select_hunger_behavior


class FeedingBehaviorTests(unittest.TestCase):
    def test_selects_behavior_from_hunger_and_food_state(self) -> None:
        cases = (
            (80.0, False, "seekFood"),
            (80.0, True, "eatNormally"),
            (95.0, False, "seekFoodUrgently"),
            (95.0, True, "eatExcitedly"),
        )

        for hunger_value, food_available, expected in cases:
            with self.subTest(
                hunger_value=hunger_value,
                food_available=food_available,
            ):
                self.assertEqual(
                    expected,
                    select_hunger_behavior(
                        hunger_value,
                        food_available=food_available,
                    ),
                )

    def test_ninety_is_not_urgent(self) -> None:
        self.assertEqual(
            "eatNormally",
            select_hunger_behavior(90.0, food_available=True),
        )


if __name__ == "__main__":
    unittest.main()
