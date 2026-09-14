"""Behavior selection used by the viewer's local hunger preview."""

HUNGER_URGENT_THRESHOLD = 90.0

HUNGER_BEHAVIORS = {
    (False, False): "seekFood",
    (False, True): "eatNormally",
    (True, False): "seekFoodUrgently",
    (True, True): "eatExcitedly",
}

HUNGER_WAIT_ACTIONS = {
    "seekFood": "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
    "seekFoodUrgently": "ACT_SNIFF_BOWL_RIM_AND_WAIT_FOR_FOOD",
}

URGENT_HUNGER_BEHAVIORS = frozenset(
    {"seekFoodUrgently", "eatExcitedly"}
)


def select_hunger_behavior(
    hunger_value: float,
    *,
    food_available: bool,
) -> str:
    """Select the local preview behavior from hunger and bowl state."""

    return HUNGER_BEHAVIORS[
        (hunger_value > HUNGER_URGENT_THRESHOLD, food_available)
    ]
