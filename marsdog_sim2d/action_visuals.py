"""Exact ACT-to-2D presentation metadata.

The action executor's ``current_action`` is the animation key.  This module
never rewrites an unknown ACT into a similar-looking action: registered keys
receive a concrete sprite/movement description, while every other key is
explicitly text-only in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionVisual:
    pose: str
    target: str | None = None
    moves: bool = False
    defer_pose_until_arrival: bool = False


ACTION_VISUALS: dict[str, ActionVisual] = {}


def _register(
    pose: str,
    *action_ids: str,
    target: str | None = None,
    moves: bool = False,
    defer_pose_until_arrival: bool = False,
) -> None:
    visual = ActionVisual(
        pose=pose,
        target=target,
        moves=moves,
        defer_pose_until_arrival=defer_pose_until_arrival,
    )
    for action_id in action_ids:
        if action_id in ACTION_VISUALS:
            raise ValueError(f"duplicate 2D action mapping: {action_id}")
        ACTION_VISUALS[action_id] = visual


# Food and bowl interaction.
_register(
    "eat",
    "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
    target="bowl",
    moves=True,
    defer_pose_until_arrival=True,
)
_register(
    "eat",
    "ACT_LICK_FOOD",
    "ACT_LICK_AND_SWALLOW",
    "ACT_SNIFF_GROUND_FOR_CRUMBS",
    "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
    "ACT_SNIFF_BOWL_RIM_AND_WAIT_FOR_FOOD",
    "ACT_WAIT_BY_BOWL_OR_TREAT_CABINET",
    "ACT_CIRCLE_EMPTY_BOWL_OR_WATER_DISH",
    target="bowl",
)
_register(
    "chew_carry_food",
    "ACT_CHEW_OR_CARRY_FOOD",
    target="bowl",
)
_register(
    "scratch_food",
    "ACT_SCRATCH_FOOD",
    "ACT_PAW_AT_BOWL_FOR_FOOD",
    "ACT_PAW_AT_BOWL_AND_WAIT_FOR_FOOD",
    "ACT_PAW_AT_BOWL_OR_TREAT_CABINET",
    target="bowl",
)
_register(
    "carry_bowl",
    "ACT_CARRY_BOWL_AND_FOLLOW_OWNER",
    target="owner",
    moves=True,
    defer_pose_until_arrival=False,
)
_register("burp", "ACT_BURP", target="bowl")
_register(
    "lick_lips_nose",
    "ACT_LICK_LIPS_OR_NOSE",
    target="bowl",
)
_register("head_tilt_observe", "ACT_PAUSE_AND_LOOK_AT_OWNER")
_register("sit", "ACT_CHANGE_POSTURE", target="bowl")

# Elimination and grooming.
_register(
    "walk",
    "ACT_SNIFF_AND_CIRCLE_AT_TOILET_SPOT",
    target="pad",
    moves=True,
)
_register("toilet", "ACT_SQUAT_AND_ELIMINATE", target="pad")
_register("scratch_ground", "ACT_SCRATCH_SOIL_OR_GROUND", target="pad")
_register("play_bow", "ACT_SNIFF_EXCREMENT", target="pad")
_register("groom", "ACT_LICK_PAWS_OR_FUR", target="groom")
_register("groom", "ACT_LICK_FUR_OR_PAWS")
_register("body_rub_object", "ACT_RUB_BODY_AGAINST_OBJECT", target="groom")
_register("paw", "ACT_PAW_AT_MUZZLE", target="groom")
_register("shake", "ACT_SHAKE_OFF_WATER", target="groom")
_register("shake", "ACT_SHAKE_HEAD")
_register("scratch_ear", "ACT_SCRATCH_EAR_WITH_HIND_LEG", target="groom")

# Sleep preparation, sleeping, and all documented wake-up variants.
_register("walk", "ACT_CIRCLE_AROUND", moves=True)
_register("scratch_ground", "ACT_SCRATCH_BED_OR_GROUND", target="bed")
_register("stretch", "ACT_STRETCH_BODY", target="bed")
_register("stretch", "ACT_STRETCH", "ACT_COMFY_STRETCH")
_register("yawn", "ACT_YAWN")
_register("sploot", "ACT_SPLoot_LIE_DOWN", "ACT_SPLOOT", target="bed")
_register(
    "sleep_closed",
    "ACT_SLEEP_CURLED_UP",
    "ACT_SLEEP_ON_STOMACH",
    "ACT_SLEEP_ON_SIDE_CURLED_UP",
    "ACT_SLEEP_ON_SIDE",
    "ACT_SLEEP_ON_BACK",
    "ACT_FLIP_BODY",
    "ACT_TWITCH_OR_KICK_LEGS",
    target="bed",
)
_register("tentative_bark_whine", "ACT_WHINE_SOFTLY", target="bed")
_register("wake_crawl", "ACT_GETUP_CRAWL", target="bed")
_register("wake_roll", "ACT_GETUP_ROLL", target="bed")
_register("wake_spring", "ACT_GETUP_BOUNCE", target="bed")
_register("wake_stretch", "ACT_GETUP_STRETCH", target="bed")
_register("wake_sit_up", "ACT_GETUP_SIT", target="bed")

# Short vocal/observation actions requested for animal interaction.
_register(
    "tentative_bark_whine",
    "ACT_BARK_OR_WHINE_BRIEFLY",
    "ACT_WHINE",
    "ACT_WHIMPER",
    "ACT_WHINE_OR_VOCALIZE_SOFTLY",
    "ACT_WHINE_AND_WAIT_FOR_FOOD",
)
_register(
    "head_tilt_observe",
    "ACT_STOP_OBSERVE_AND_TILT_HEAD",
)
_register("head_tilt_observe", "ACT_CHECK_OWNER", target="owner")
_register("bark_lying", "ACT_BARK_AND_LIE_DOWN_IF_NO_CHARGER")
_register(
    "whine",
    "ACT_BARK_TENSE",
    "ACT_FREEZE_SHAKE",
    "ACT_VOCAL_WHINE",
)

# Direct commands: these are the exact keys from the new contract.
_register("sit", "ACT_BASIC_SIT")
_register("lie", "ACT_BASIC_LIE_DOWN")
_register("stand", "ACT_BASIC_STAND", "ACT_BASIC_WAIT", "ACT_SYSTEM_EMERGENCY_STOP")
_register(
    "walk",
    "ACT_INTERACT_APPROACH_OWNER",
    "ACT_INTERACT_RETURN_OWNER",
    target="owner",
    moves=True,
)
_register("walk", "ACT_INTERACT_FOLLOW_OWNER", target="owner", moves=True)
_register(
    "walk",
    "ACT_FOLLOW_AND_STAY_CLOSE_TO_OWNER",
    "ACT_CIRCLE_AROUND_OWNER",
    target="owner",
    moves=True,
)
_register(
    "paw",
    "ACT_INTERACT_GIVE_PAW",
    "ACT_INTERACT_HIGH_FIVE",
    "ACT_PAW_AT_OWNER",
    "ACT_PAW_LEG",
    "ACT_STAND_UP_AND_PAW_AT_OWNER_LEG",
    "ACT_PLACE_FRONT_PAWS_ON_OWNER_FOR_ATTENTION",
    "ACT_JUMP_PAW",
    target="owner",
    moves=True,
    defer_pose_until_arrival=True,
)
_register("head_tilt_observe", "ACT_INTERACT_RESPOND_CALL", target="owner")
_register("joy_belly", "ACT_TRICK_ROLL_OVER", "ACT_SHOW_BELLY", "ACT_ROLL_OVER_FOR_BELLY_RUB")
_register("spin", "ACT_TRICK_SPIN", "ACT_SPIN_FRONT", "ACT_SPIN_IN_PLACE")
_register("spin", "ACT_CHASE_TAIL")
_register("play_dead", "ACT_TRICK_PLAY_DEAD")
_register("stand", "ACT_OBJECT_DROP")
_register(
    "excite_toy",
    "ACT_OBJECT_BRING",
    "ACT_OBJECT_FETCH",
    "ACT_FETCH_TOY",
    target="toy",
    moves=True,
)

# Calm/emotion and common room-scale movements with unambiguous 2D meaning.
_register("walk", "ACT_PATROL", "ACT_PATROL_ALONG_WALL", target="random", moves=True)
_register(
    "walk",
    "ACT_TROT_STOP_AND_SNIFF",
    "ACT_WALK_SLOWLY_AND_SNIFF_GROUND",
    "ACT_RUN_AWAY_AND_LOOK_BACK",
    "ACT_RUN_IN_CIRCLES_OR_CHASE",
    "ACT_RUN_IN_CIRCLES_OR_ZOOMIES",
    "ACT_ZOOMIE_CIRCLE",
    "ACT_ZOOMIES",
    "ACT_PACE",
    target="random",
    moves=True,
)
_register("lie", "ACT_FIND_PLACE_TO_LIE_DOWN", target="random", moves=True, defer_pose_until_arrival=True)
_register(
    "wake_crawl",
    "ACT_CRAWL_THROUGH_LOW_GAP",
    target="random",
    moves=True,
)
_register(
    "walk",
    "ACT_TROT_BOUNCE",
    target="random",
    moves=True,
)
_register("play_bow", "ACT_PLAY_BOW")
_register("joy_belly", "ACT_NUZZLE_HEAD", "ACT_NUZZLE_BODY", target="owner")
_register("groom", "ACT_LICK", "ACT_LICK_SELF", "ACT_LICK_FACE")
_register("stand", "ACT_WINK", "ACT_WAG_TAIL", "ACT_PURR")
_register("anxiety_cower", "ACT_HIDE_SHRINK", "ACT_TUCK_TAIL")
_register("fear_cover", "ACT_COVER_EYES")
_register("curious_paw", "ACT_INTERACT_EXPLORE", "ACT_NON_INTERACT_EXPLORE")
_register("excite_toy", "ACT_BAT_TOY", "ACT_SHAKE_TOY", "ACT_BITE_AND_SHAKE_SLIPPERS_SOCKS_OR_TOY", target="toy")
_register(
    "body_rub_object",
    "ACT_RUB_AGAINST_LEG_OR_LEAN_ON_OWNER",
    target="owner",
    moves=True,
    defer_pose_until_arrival=True,
)
_register(
    "sit",
    "ACT_SIT_IN_FRONT_OF_OWNER_AND_LOOK_UP",
    target="owner",
    moves=True,
    defer_pose_until_arrival=True,
)
_register(
    "sleep_closed",
    "ACT_SLEEP_BY_FEET",
    target="owner",
    moves=True,
    defer_pose_until_arrival=True,
)

# Object inspection actions that can be represented with existing assets.
_register(
    "play_bow",
    "ACT_SNIFF_OBJECT",
    "ACT_SNIFF_SLIPPERS_SOCKS_OR_TOY",
    target="toy",
)
_register(
    "paw",
    "ACT_PUSH_OBJECT_WITH_PAW",
    "ACT_SCRATCH_OBJECT_GENTLY",
    "ACT_PAW_AT_SLIPPERS_SOCKS_OR_TOY",
    "ACT_POUNCE_ON_SLIPPERS_SOCKS_OR_TOY",
    target="toy",
)
_register(
    "excite_toy",
    "ACT_TOUCH_OR_CARRY_OBJECT_WITH_MOUTH",
    "ACT_NIBBLE_OBJECT",
    "ACT_CARRY_AND_DROP_OBJECT_AGAIN",
    "ACT_CARRY_AND_HIDE_OBJECT",
    target="toy",
)

# Resource movement.
_register(
    "walk",
    "ACT_RETURN_TO_CHARGER",
    "ACT_RETURN_TO_DOG_BED_FOR_CHARGING",
    target="charger",
    moves=True,
)


def visual_for_action(action_id: str | None) -> ActionVisual | None:
    """Return an exact 2D mapping, or ``None`` for an explicit text-only ACT."""

    return ACTION_VISUALS.get(str(action_id or ""))


def is_text_only_action(action_id: str | None) -> bool:
    action_id = str(action_id or "")
    return bool(action_id and action_id != "-" and action_id not in ACTION_VISUALS)
