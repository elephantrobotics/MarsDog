"""Virtual /execute_behavior Action server for the Arcade simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from queue import Queue
import re
import threading
import time
from typing import Any, Callable

from rclpy.action import ActionServer, CancelResponse, GoalResponse
from std_msgs.msg import String

from . import config
from .sim_state import SimEvent

try:  # The real action type is available only when the MarsDog ROS2 workspace is sourced.
    from marsdog_interfaces.action import ExecuteBehavior

    _ACTION_TYPE_SOURCE = "marsdog_interfaces"
except ImportError:  # pragma: no cover - depends on external ROS2 workspace
    try:
        from marsdog_action_executor.action import ExecuteBehavior

        _ACTION_TYPE_SOURCE = "marsdog_action_executor"
    except ImportError:
        try:
            from marsdog_ros2.action import ExecuteBehavior

            _ACTION_TYPE_SOURCE = "marsdog_ros2"
        except ImportError:
            ExecuteBehavior = None  # type: ignore[assignment]
            _ACTION_TYPE_SOURCE = "unavailable"


@dataclass(slots=True)
class BehaviorPlan:
    behavior_name: str
    goal_id: str
    behavior_id: str
    target_x: float
    target_y: float
    target_heading: float
    current_action: str
    active_object: str | None = None
    object_target: tuple[float, float] | None = None
    duration: float = 3.0
    reward: float = 1.0


@dataclass
class VirtualRoom:
    dog_x: float = config.DEFAULT_DOG_X
    dog_y: float = config.DEFAULT_DOG_Y
    dog_heading: float = config.DEFAULT_DOG_HEADING
    user_x: float = config.DEFAULT_USER_X
    user_y: float = config.DEFAULT_USER_Y
    objects: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            name: dict(item) for name, item in config.DEFAULT_ROOM_OBJECTS.items()
        }
    )

    def build_plan(self, goal: dict[str, Any]) -> BehaviorPlan:
        behavior_name = goal["behavior_name"]
        key = _canonical_behavior_key(behavior_name)
        params = goal.get("params") if isinstance(goal.get("params"), dict) else {}
        target_x = self.user_x - 70.0
        target_y = self.user_y - 10.0
        heading = _heading_to(self.dog_x, self.dog_y, self.user_x, self.user_y)
        current_action = "ACT_APPROACH_TARGET"
        active_object: str | None = None
        object_target: tuple[float, float] | None = None
        duration = _duration(goal.get("timeout_sec"), 3.2)

        if key in {
            "SEEK_FOOD_OR_WATER",
            "SEEK_FOOD",
            "EAT_IMMEDIATELY",
            "EAT_NORMALLY",
            "EAT_EXCITEDLY",
            "ACTION_EAT",
        }:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "bowl")
            current_action = "ACT_LOCO_WALK_TO_BOWL"
            active_object = "bowl"
        elif key in {"EXCRETION_REQUEST", "DEFECATE", "ACTION_DEFECATE"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "pad")
            current_action = "ACT_LOCO_WALK_TO_PAD"
            active_object = "pad"
        elif key in {"SLEEP_REQUEST", "SLEEP_NOW", "ACTION_SLEEP"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "bed")
            current_action = "ACT_LOCO_WALK_TO_BED"
            active_object = "bed"
            duration = _duration(goal.get("timeout_sec"), 4.0)
        elif key in {"CLEAN_SELF", "LICK_PAWS", "ACTION_GROOM"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "groom")
            current_action = "ACT_GROOM_SELF" if key != "LICK_PAWS" else "ACT_MOUTH_LICK_PAWS"
            active_object = "groom"
        elif key in {
            "EXPRESS_CALM",
            "EXPRESS_JOY",
            "EXPRESS_EXCITE",
            "EXPRESS_FEAR",
            "EXPRESS_CURIOUS",
            "EXPRESS_ANXIETY",
        }:
            if _interactive_target_requested(params):
                target_x = self.user_x - 82.0
                target_y = self.user_y - 8.0
                heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
                active_object = "owner"
            else:
                target_x = self.dog_x
                target_y = self.dog_y
                heading = self.dog_heading
            current_action = _expression_action(key)
            duration = _duration(goal.get("timeout_sec"), 2.8)
        elif key in {"WAG_TAIL_GENTLY", "WAG_TAIL_FAST", "TAIL_UP_AND_WAG"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            current_action = "ACT_TAIL_WAG_FAST" if "FAST" in key else "ACT_TAIL_WAG_GENTLE"
            duration = _duration(goal.get("timeout_sec"), 2.2)
        elif key in {"HOP_IN_PLACE"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            current_action = "ACT_LOCO_HOP_IN_PLACE"
            duration = _duration(goal.get("timeout_sec"), 2.0)
        elif key in {"PLAY_BOW"}:
            target_x = self.user_x - 118.0
            target_y = self.user_y
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_POSTURE_PLAY_BOW"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 2.5)
        elif key in {"POUNCE_FORWARD"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            current_action = "ACT_LOCO_POUNCE_FORWARD"
            active_object = "toy"
            duration = _duration(goal.get("timeout_sec"), 2.0)
        elif key in {"ROLL_OVER_SHOW_BELLY", "ROLL_OVER"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading + 180.0
            current_action = "ACT_POSTURE_ROLL_OVER"
            duration = _duration(goal.get("timeout_sec"), 2.8)
        elif key in {"NUDGE_WITH_NOSE"}:
            target_x = self.user_x - 84.0
            target_y = self.user_y - 8.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_HEAD_NUDGE_OWNER"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 2.4)
        elif key in {"CARRY_AND_SHAKE", "RETRIEVE_TOY"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            object_target = (
                (self.user_x - 28.0, self.user_y - 26.0)
                if key == "RETRIEVE_TOY"
                else (self.dog_x + 18.0, self.dog_y + 10.0)
            )
            current_action = "ACT_FETCH_TO_USER" if key == "RETRIEVE_TOY" else "ACT_MOUTH_CARRY_AND_SHAKE"
            active_object = "toy"
            duration = _duration(goal.get("timeout_sec"), 3.0)
        elif key in {"SPIT_OUT"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            current_action = "ACT_MOUTH_SPIT_OUT"
            active_object = "toy"
            duration = _duration(goal.get("timeout_sec"), 1.8)
        elif key in {"PLAY_DEAD"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading + 90.0
            current_action = "ACT_POSTURE_PLAY_DEAD"
            duration = _duration(goal.get("timeout_sec"), 2.6)
        elif key in {"ZOOMIES_RUN"}:
            target_x = 720.0 if self.dog_x < 500.0 else 390.0
            target_y = 470.0 if self.dog_y < 420.0 else 365.0
            heading = _heading_to(self.dog_x, self.dog_y, target_x, target_y)
            current_action = "ACT_LOCO_ZOOMIES_RUN"
            duration = _duration(goal.get("timeout_sec"), 3.2)
        elif key in {"JUMP_ON_PERSON"}:
            target_x = self.user_x - 48.0
            target_y = self.user_y - 8.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_LOCO_JUMP_ON_PERSON"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 2.0)
        elif key in {"FREEZE_ALERT"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            current_action = "ACT_POSTURE_FREEZE_ALERT"
            duration = _duration(goal.get("timeout_sec"), 1.8)
        elif key in {"FLEE_QUICKLY", "HIDE_AWAY"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "bed")
            current_action = "ACT_LOCO_HIDE_AWAY" if key == "HIDE_AWAY" else "ACT_LOCO_FLEE_QUICKLY"
            active_object = "bed"
            duration = _duration(goal.get("timeout_sec"), 2.6)
        elif key in {"TREMBLE_SHAKE"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            current_action = "ACT_POSTURE_TREMBLE_SHAKE"
            duration = _duration(goal.get("timeout_sec"), 2.0)
        elif key in {"HEAD_TILT"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = _heading_to(self.dog_x, self.dog_y, self.user_x, self.user_y)
            current_action = "ACT_HEAD_TILT"
            duration = _duration(goal.get("timeout_sec"), 1.8)
        elif key in {"APPROACH_SLOWLY", "APPROACH_USER", "WALK_TO_OWNER", "TROT_TO_OWNER"}:
            target_x = self.user_x - 92.0
            target_y = self.user_y - 6.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_LOCO_TROT_TO_OWNER" if key == "TROT_TO_OWNER" else "ACT_LOCO_APPROACH_SLOWLY"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 3.2 if key != "APPROACH_SLOWLY" else 4.0)
        elif key in {"SNIFF_GROUND", "SNIFF_OBJECT"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            current_action = "ACT_HEAD_SNIFF_GROUND"
            active_object = "toy"
            duration = _duration(goal.get("timeout_sec"), 3.0)
        elif key in {"PAW_AT_OBJECT", "INSPECT_TOY"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            current_action = "ACT_PAW_AT_OBJECT" if key == "PAW_AT_OBJECT" else "ACT_HEAD_INSPECT_TOY"
            active_object = "toy"
            duration = _duration(goal.get("timeout_sec"), 2.4)
        elif key in {"PACE_BACK_AND_FORTH"}:
            target_x = 620.0 if self.dog_x < 500.0 else 380.0
            target_y = 380.0
            heading = _heading_to(self.dog_x, self.dog_y, target_x, target_y)
            current_action = "ACT_LOCO_PACE_BACK_AND_FORTH"
            duration = _duration(goal.get("timeout_sec"), 3.6)
        elif key in {"REST_IN_PLACE", "IDLE_REST", "STRETCH_LAZILY", "YAWN_SLOWLY"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            if key == "STRETCH_LAZILY":
                current_action = "ACT_POSTURE_STRETCH_LAZILY"
            elif key == "YAWN_SLOWLY":
                current_action = "ACT_MOUTH_YAWN_SLOWLY"
            else:
                current_action = "ACT_POSTURE_REST_IN_PLACE"
            duration = _duration(goal.get("timeout_sec"), 2.8)
        elif key in {"SLEEP_ON_SIDE"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "bed")
            current_action = "ACT_POSTURE_SLEEP_ON_SIDE"
            active_object = "bed"
            duration = _duration(goal.get("timeout_sec"), 4.0)
        elif key in {"CUDDLE_POSE"}:
            target_x = self.user_x - 72.0
            target_y = self.user_y - 12.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_POSTURE_CUDDLE_POSE"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 3.0)
        elif key in {"IDLE_LOOK_AROUND"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading + 45.0
            current_action = "ACT_HEAD_LOOK_AROUND"
            duration = _duration(goal.get("timeout_sec"), 2.2)
        elif key in {
            "SEEK_SOCIAL_INTERACTION",
            "SEEK_INTERACTION",
            "SEEK_HUMAN_INTERACTION",
            "REQUEST_RESOURCE_FROM_HUMAN",
            "INVITE_HUMAN_TO_PLAY",
            "TEST_ANIMAL_BOUNDARY",
            "GREET_ANIMAL",
            "INVITE_ANIMAL_TO_PLAY",
            "ACTION_ATTENTION_SEEK",
            "RESPOND_TOUCH_HEAD",
            "HAND_SHAKE",
            "HIGH_FIVE",
        }:
            target_x = self.user_x - (100.0 if key in {"RESPOND_TOUCH_HEAD", "HAND_SHAKE", "HIGH_FIVE"} else 110.0)
            target_y = self.user_y
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_HAND_INTERACTION" if key in {"RESPOND_TOUCH_HEAD", "HAND_SHAKE", "HIGH_FIVE"} else "ACT_SOCIAL_APPROACH"
            active_object = "owner"
        elif key in {
            "EXPLORE_ENVIRONMENT",
            "EXPLORE_ROOM",
            "INSPECT_OBJECT",
            "ACTION_EXPLORE",
        }:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            current_action = "ACT_EXPLORE_OBJECT"
            active_object = "toy"
        elif key in {"RESPOND_OWNER_CALL", "COME_HERE", "CMD_COME_HERE"}:
            target_x = self.user_x - 104.0
            target_y = self.user_y - 6.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_COME_HERE"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 2.4)
        elif key in {"SPIN_IN_CIRCLE", "SPIN_ONCE", "CMD_SPIN"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading + 360.0
            current_action = "ACT_SPIN"
            duration = _duration(goal.get("timeout_sec"), 2.0)
        elif key in {"ACTION_RECHARGE", "RECHARGE"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "charger")
            current_action = "ACT_RECHARGE"
            active_object = "charger"
        elif key in {"CMD_SIT", "SIT", "SIT_POLITELY"}:
            target_x = self.dog_x
            target_y = self.dog_y
            current_action = "ACT_SIT"
            duration = _duration(goal.get("timeout_sec"), 1.5)
        elif key in {"CMD_HAND", "CMD_FIVE", "HAND_SHAKE", "HIGH_FIVE"}:
            target_x = self.user_x - 100.0
            target_y = self.user_y
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_HAND_INTERACTION"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 2.6)
        elif key in {"CMD_FOLLOW", "FOLLOW_USER"}:
            target_x = self.user_x - 112.0
            target_y = self.user_y - 50.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_FOLLOW"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 4.0)
        elif key in {"CMD_BACK", "RETRIEVE_TOY"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "toy")
            object_target = (self.user_x - 28.0, self.user_y - 26.0)
            current_action = "ACT_FETCH_TO_USER"
            active_object = "toy"
            duration = _duration(goal.get("timeout_sec"), 4.8)
        elif key in {"EMERGENCY_STOP", "CMD_STOP"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            current_action = "ACT_HOLD_POSITION"
            duration = 0.8
        elif key in {"AVOID_DANGER", "SEEK_SAFETY"}:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "bed")
            current_action = "ACT_LOCO_AVOID_DANGER"
            active_object = "bed"
            duration = _duration(goal.get("timeout_sec"), 2.2)
        elif key in {"ALERT_AND_APPROACH"}:
            target_x = self.user_x - 96.0
            target_y = self.user_y - 12.0
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)
            current_action = "ACT_POSTURE_ALERT_AND_APPROACH"
            active_object = "owner"
            duration = _duration(goal.get("timeout_sec"), 3.0)
        elif key in {"BARK_SHORT_ALERT"}:
            target_x = self.dog_x
            target_y = self.dog_y
            heading = self.dog_heading
            current_action = "ACT_VOCAL_BARK_SHORT_ALERT"
            duration = _duration(goal.get("timeout_sec"), 1.6)

        return BehaviorPlan(
            behavior_name=behavior_name,
            goal_id=goal["goal_id"],
            behavior_id=str(goal.get("behavior_id") or ""),
            target_x=target_x,
            target_y=target_y,
            target_heading=heading,
            current_action=current_action,
            active_object=active_object,
            object_target=object_target,
            duration=duration,
        )

    def frame(self, plan: BehaviorPlan, progress: float) -> dict[str, Any]:
        eased = _ease(progress)
        dog_x = _lerp(self.dog_x, plan.target_x, eased)
        dog_y = _lerp(self.dog_y, plan.target_y, eased)
        heading = _lerp_angle(self.dog_heading, plan.target_heading, eased)
        current_action = _phase_action(plan.current_action, progress)
        stage_index, stage_total, stage_label = _stage_for_progress(current_action, progress)
        phase = _phase_for_action(current_action, progress)
        target_label = _target_label_for_plan(plan)

        objects = {name: dict(obj) for name, obj in self.objects.items()}
        if plan.active_object and plan.active_object in objects:
            objects[plan.active_object]["active"] = True
        if plan.active_object and plan.object_target and plan.active_object in objects:
            obj = objects[plan.active_object]
            obj["x"] = _lerp(float(obj["x"]), plan.object_target[0], eased)
            obj["y"] = _lerp(float(obj["y"]), plan.object_target[1], eased)

        return {
            "goal_id": plan.goal_id,
            "behavior_id": plan.behavior_id,
            "behavior_name": plan.behavior_name,
            "status": "RUNNING",
            "progress": progress,
            "safe_to_interrupt": progress < 0.85,
            "current_action": current_action,
            "message": f"Step {stage_index}/{stage_total}: {current_action}",
            "stage_index": stage_index,
            "stage_total": stage_total,
            "stage_label": stage_label,
            "phase": phase,
            "target_label": target_label,
            "dog_pose": {"x": dog_x, "y": dog_y, "heading": heading},
            "user_pose": {"x": self.user_x, "y": self.user_y},
            "objects": objects,
        }

    def frame_for_action(
        self,
        plan: BehaviorPlan,
        current_action: str,
        progress: float,
    ) -> dict[str, Any]:
        visual_plan = self._visual_plan_for_action(plan, current_action)
        frame = self.frame(visual_plan, progress)
        stage_index, stage_total, stage_label = _stage_for_progress(current_action, progress)
        frame["current_action"] = current_action
        frame["message"] = f"Step {stage_index}/{stage_total}: {current_action}"
        frame["stage_index"] = stage_index
        frame["stage_total"] = stage_total
        frame["stage_label"] = stage_label
        frame["phase"] = _phase_for_action(current_action, progress)
        frame["target_label"] = _target_label_for_plan(visual_plan)
        return frame

    def commit(self, frame: dict[str, Any]) -> None:
        dog_pose = frame.get("dog_pose", {})
        user_pose = frame.get("user_pose", {})
        self.dog_x = float(dog_pose.get("x", self.dog_x))
        self.dog_y = float(dog_pose.get("y", self.dog_y))
        self.dog_heading = float(dog_pose.get("heading", self.dog_heading)) % 360.0
        self.user_x = float(user_pose.get("x", self.user_x))
        self.user_y = float(user_pose.get("y", self.user_y))
        objects = frame.get("objects")
        if isinstance(objects, dict):
            self.objects = {name: dict(obj) for name, obj in objects.items()}
            for obj in self.objects.values():
                obj["active"] = False

    def _visual_plan_for_action(
        self,
        plan: BehaviorPlan,
        current_action: str,
    ) -> BehaviorPlan:
        key = _behavior_key(current_action)
        target_x = plan.target_x
        target_y = plan.target_y
        heading = plan.target_heading
        active_object = plan.active_object
        object_target = plan.object_target

        object_name = _object_name_for_action(key)
        if object_name is not None:
            target_x, target_y, heading = _object_interaction_pose(
                self.objects,
                object_name,
            )
            active_object = object_name
            object_target = None

        if _action_targets_user(key):
            offset_x, offset_y = _user_action_offset(key)
            target_x = self.user_x - offset_x
            target_y = self.user_y - offset_y
            active_object = None
            object_target = None
            heading = _heading_to(target_x, target_y, self.user_x, self.user_y)

        non_motion_unit = _action_is_non_motion_unit(key)
        if non_motion_unit:
            target_x = self.dog_x
            target_y = self.dog_y
            object_target = None
            heading = self.dog_heading
        elif _action_is_stationary(key) and object_name is None and not _action_targets_user(key):
            if plan.active_object is not None:
                target_x = plan.target_x
                target_y = plan.target_y
                active_object = plan.active_object
                object_target = plan.object_target
                heading = plan.target_heading
            else:
                target_x = self.dog_x
                target_y = self.dog_y
                active_object = None
                object_target = None
                if "LOOK" in key or "TILT" in key:
                    heading = _heading_to(self.dog_x, self.dog_y, self.user_x, self.user_y)
                else:
                    heading = self.dog_heading

        if "HIDE" in key or "FLEE" in key or "AVOID" in key or "DANGER" in key:
            target_x, target_y, heading = _object_interaction_pose(self.objects, "bed")
            active_object = "bed"
            object_target = None

        if "ZOOMIES" in key or ("RUN" in key and "FLEE" not in key):
            target_x = 720.0 if self.dog_x < 500.0 else 390.0
            target_y = 470.0 if self.dog_y < 420.0 else 365.0
            active_object = None
            object_target = None
            heading = _heading_to(self.dog_x, self.dog_y, target_x, target_y)

        if "CARRY" in key or "SHAKE" in key or "FETCH" in key or "PRESENT" in key:
            active_object = "toy"
            if "PRESENT" in key or "USER" in key or "OWNER" in key:
                object_target = (self.user_x - 28.0, self.user_y - 26.0)
            else:
                object_target = (self.dog_x + 20.0, self.dog_y + 8.0)

        return BehaviorPlan(
            behavior_name=plan.behavior_name,
            goal_id=plan.goal_id,
            behavior_id=plan.behavior_id,
            target_x=target_x,
            target_y=target_y,
            target_heading=heading,
            current_action=current_action,
            active_object=active_object,
            object_target=object_target,
            duration=plan.duration,
            reward=plan.reward,
        )


class VirtualActionServer:
    """Optional Action server that turns behavior goals into virtual room motion."""

    def __init__(self, node: Any, event_queue: Queue[SimEvent]) -> None:
        self._node = node
        self._event_queue = event_queue
        self._room = VirtualRoom()
        self._lock = threading.Lock()
        self._server: ActionServer | None = None
        self._recent_debug_events: dict[str, tuple[float, str]] = {}
        self._goal_subscriptions = [
            self._subscribe_debug_topic(
                config.ACTION_GOAL_TOPIC,
                self._goal_topic_callback,
            ),
            self._subscribe_debug_topic(
                config.LEGACY_ACTION_GOAL_TOPIC,
                self._goal_topic_callback,
            ),
        ]
        self._feedback_subscriptions = [
            self._subscribe_debug_topic(
                config.ACTION_FEEDBACK_TOPIC,
                self._feedback_topic_callback,
            ),
            self._subscribe_debug_topic(
                config.LEGACY_ACTION_FEEDBACK_TOPIC,
                self._feedback_topic_callback,
            ),
        ]
        self._result_subscriptions = [
            self._subscribe_debug_topic(
                config.ACTION_RESULT_TOPIC,
                self._result_topic_callback,
            ),
            self._subscribe_debug_topic(
                config.LEGACY_ACTION_RESULT_TOPIC,
                self._result_topic_callback,
            ),
        ]
        self._goal_publishers: list[Any] = []
        self._feedback_publishers: list[Any] = []
        self._result_publishers: list[Any] = []
        self._mirror_plan: BehaviorPlan | None = None
        self._mirror_last_frame: dict[str, Any] | None = None
        self.local_room = self._room
        self._put_state(False, "debug topic mirror ready; Action unavailable")

        if not _action_server_enabled():
            self._put_state(False, "debug topic mirror ready; Action server disabled")
            node.get_logger().info(
                "Virtual Action server disabled by MARSDOG_SIM2D_ACTION_SERVER; "
                f"only {_debug_topic_label()} debug topic visualization is active."
            )
            return

        if ExecuteBehavior is None:
            node.get_logger().warning(
                "Virtual ROS2 Action server disabled: "
                "ExecuteBehavior action type is unavailable. "
                f"Only {_debug_topic_label()} debug topic visualization is active."
            )
            return

        self._create_debug_publishers()
        self._server = ActionServer(
            node,
            ExecuteBehavior,
            config.ACTION_NAME,
            execute_callback=self._execute_callback,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
        )
        self._put_state(True, "Action server ready; debug topics published")
        node.get_logger().info(
            f"Virtual Action server started on {config.ACTION_NAME}; "
            f"action type from {_ACTION_TYPE_SOURCE}; "
            f"publishing debug topics under {_debug_topic_label()}"
        )

    def destroy(self) -> None:
        if self._server is not None:
            self._server.destroy()

    def _create_debug_publishers(self) -> None:
        topic_sets = [
            (
                config.ACTION_GOAL_TOPIC,
                config.ACTION_FEEDBACK_TOPIC,
                config.ACTION_RESULT_TOPIC,
            )
        ]
        if _legacy_debug_topics_enabled():
            topic_sets.append(
                (
                    config.LEGACY_ACTION_GOAL_TOPIC,
                    config.LEGACY_ACTION_FEEDBACK_TOPIC,
                    config.LEGACY_ACTION_RESULT_TOPIC,
                )
            )
        for goal_topic, feedback_topic, result_topic in topic_sets:
            self._goal_publishers.append(
                self._node.create_publisher(String, goal_topic, config.EVENT_TOPIC_DEPTH)
            )
            self._feedback_publishers.append(
                self._node.create_publisher(String, feedback_topic, config.EVENT_TOPIC_DEPTH)
            )
            self._result_publishers.append(
                self._node.create_publisher(String, result_topic, config.EVENT_TOPIC_DEPTH)
            )

    def _subscribe_debug_topic(
        self,
        topic: str,
        callback: Callable[[String, str], None],
    ) -> Any:
        return self._node.create_subscription(
            String,
            topic,
            lambda msg: callback(msg, topic),
            config.EVENT_TOPIC_DEPTH,
        )

    def _goal_topic_callback(self, msg: String, topic: str) -> None:
        decoded = self._decode_topic_json(topic, msg)
        if (
            decoded is None
            or _is_own_debug_message(decoded)
            or self._is_duplicate_debug_event("goal", decoded, topic)
        ):
            return

        goal = _goal_topic_to_dict(decoded)
        with self._lock:
            if self._mirror_last_frame is not None:
                self._room.commit(self._mirror_last_frame)
            self._mirror_plan = self._room.build_plan(goal)
            self._mirror_last_frame = None
        self._node.get_logger().info(
            f"Mirroring external execute_behavior goal: {goal['behavior_name']}"
        )
        self._put_event(
            "action_goal",
            {
                **goal,
                "status": "RUNNING",
                "progress": 0.0,
                "current_action": self._mirror_plan.current_action,
            },
            f"execute_behavior_mirror: {goal['behavior_name']} STARTED",
            topic=topic,
        )

    def _feedback_topic_callback(self, msg: String, topic: str) -> None:
        decoded = self._decode_topic_json(topic, msg)
        if (
            decoded is None
            or _is_own_debug_message(decoded)
            or self._is_duplicate_debug_event("feedback", decoded, topic)
        ):
            return

        progress = _normalized_progress(decoded.get("progress"))
        current_action = str(decoded.get("current_action") or "")
        with self._lock:
            plan = self._mirror_plan
            if plan is not None and not _goal_matches_plan(decoded, plan):
                self._node.get_logger().debug(
                    f"Ignoring stale feedback for goal {decoded.get('goal_id')}"
                )
                return
            if plan is not None and current_action:
                frame = self._room.frame_for_action(plan, current_action, progress)
            elif plan is not None:
                frame = self._room.frame(plan, progress)
            else:
                frame = {}
            if frame:
                self._mirror_last_frame = frame
        payload = {**frame, **decoded} if frame else dict(decoded)
        if frame and not any(
            decoded.get(key) is not None
            for key in ("stage_index", "stage_total", "step_index", "step_total")
        ):
            payload.pop("stage_index", None)
            payload.pop("stage_total", None)
            payload.pop("stage_label", None)
        self._put_event(
            "action_feedback",
            payload,
            f"execute_behavior_mirror: {decoded.get('goal_id', '-')} {progress * 100:.0f}% {decoded.get('current_action', '-')}",
            topic=topic,
        )

    def _result_topic_callback(self, msg: String, topic: str) -> None:
        decoded = self._decode_topic_json(topic, msg)
        if (
            decoded is None
            or _is_own_debug_message(decoded)
            or self._is_duplicate_debug_event("result", decoded, topic)
        ):
            return

        final_frame: dict[str, Any] = {}
        with self._lock:
            if self._mirror_plan is not None:
                if not _goal_matches_plan(decoded, self._mirror_plan):
                    self._node.get_logger().debug(
                        f"Ignoring stale result for goal {decoded.get('goal_id')}"
                    )
                    return
                if self._mirror_last_frame is not None:
                    final_frame = self._mirror_last_frame
                    self._room.commit(final_frame)
                elif _is_success_result(decoded):
                    final_frame = self._room.frame(self._mirror_plan, 1.0)
                    self._room.commit(final_frame)
                self._mirror_plan = None
                self._mirror_last_frame = None
        payload = {**final_frame, **decoded} if final_frame else dict(decoded)
        self._put_event(
            "action_result",
            payload,
            f"execute_behavior_mirror: {decoded.get('behavior_name', '-')} {decoded.get('result', '-')}",
            topic=topic,
        )

    def _decode_topic_json(self, topic: str, msg: String) -> dict[str, Any] | None:
        try:
            decoded = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self._node.get_logger().warning(f"Ignoring invalid JSON on {topic}: {exc.msg}")
            return None

        if not isinstance(decoded, dict):
            self._node.get_logger().warning(f"Ignoring JSON on {topic}: expected object")
            return None
        return decoded

    def _is_duplicate_debug_event(
        self,
        kind: str,
        data: dict[str, Any],
        topic: str,
    ) -> bool:
        identity = {
            key: data.get(key)
            for key in (
                "goal_id",
                "behavior_id",
                "behavior_name",
                "status",
                "progress",
                "current_stage",
                "current_action",
                "result",
                "timestamp",
            )
        }
        fingerprint = f"{kind}:{json.dumps(identity, sort_keys=True, default=str)}"
        now = time.monotonic()
        previous = self._recent_debug_events.get(fingerprint)
        if previous is not None and previous[1] != topic and now - previous[0] <= 0.2:
            return True

        self._recent_debug_events[fingerprint] = (now, topic)
        if len(self._recent_debug_events) > 256:
            self._recent_debug_events = {
                key: value
                for key, value in self._recent_debug_events.items()
                if now - value[0] <= 2.0
            }
        return False

    def _goal_callback(self, goal_request: Any) -> GoalResponse:
        behavior_name = getattr(goal_request, "behavior_name", "")
        self._node.get_logger().info(f"Accepting virtual behavior goal: {behavior_name}")
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle: Any) -> CancelResponse:
        del goal_handle
        self._node.get_logger().info("Accepting virtual behavior cancel request")
        return CancelResponse.ACCEPT

    def _execute_callback(self, goal_handle: Any) -> Any:
        goal = _goal_to_dict(goal_handle.request)
        with self._lock:
            plan = self._room.build_plan(goal)

        goal_payload = _topic_goal_payload(goal)
        self._publish_json(self._goal_publishers, goal_payload)
        self._put_event(
            "action_goal",
            {
                **goal,
                "status": "RUNNING",
                "progress": 0.0,
                "current_action": plan.current_action,
            },
            f"execute_behavior: {plan.behavior_name} STARTED",
            topic=config.ACTION_GOAL_TOPIC,
        )

        start_time = time.monotonic()
        last_frame: dict[str, Any] | None = None
        while True:
            elapsed = time.monotonic() - start_time
            progress = min(1.0, elapsed / max(plan.duration, 0.1))

            with self._lock:
                frame = self._room.frame(plan, progress)
            last_frame = frame
            goal_handle.publish_feedback(_make_feedback(frame))
            feedback_payload = _topic_feedback_payload(frame)
            self._publish_json(self._feedback_publishers, feedback_payload)
            self._put_event(
                "action_feedback",
                frame,
                f"execute_behavior: {plan.behavior_name} {progress * 100:.0f}% {frame['current_action']}",
                topic=config.ACTION_FEEDBACK_TOPIC,
            )

            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result = _make_result(
                    plan,
                    "CANCELED",
                    "interrupted",
                    "Goal canceled by client",
                    0.0,
                )
                self._put_result(plan, result, "canceled")
                return result

            if progress >= 1.0:
                break
            time.sleep(config.ACTION_FEEDBACK_PERIOD_SEC)

        if last_frame is not None:
            with self._lock:
                self._room.commit(last_frame)

        goal_handle.succeed()
        result = _make_result(
            plan,
            "SUCCESS",
            "completed",
            "Virtual behavior completed",
            plan.reward,
        )
        self._put_result(plan, result, "completed")
        return result

    def _put_state(self, available: bool, message: str) -> None:
        self._put_event(
            "action_server_state",
            {"available": available, "message": message},
            f"execute_behavior_server: {'ready' if available else 'unavailable'} {message}",
        )

    def _put_result(self, plan: BehaviorPlan, result: Any, result_text: str) -> None:
        result_payload = _message_to_dict(result)
        result_payload["source"] = config.VIEWER_SOURCE
        result_payload["timestamp"] = time.time()
        self._publish_json(self._result_publishers, result_payload)
        self._put_event(
            "action_result",
            result_payload,
            f"execute_behavior: {plan.behavior_name} {result_text}",
            topic=config.ACTION_RESULT_TOPIC,
        )

    def _put_event(
        self,
        kind: str,
        payload: dict[str, Any],
        summary: str,
        topic: str = config.ACTION_NAME,
    ) -> None:
        self._event_queue.put(
            SimEvent(
                kind=kind,
                topic=topic,
                payload=payload,
                summary=summary,
            )
        )

    def _publish_json(self, publishers: list[Any], payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        for publisher in publishers:
            publisher.publish(msg)


class LocalVirtualRunner:
    """Frame-by-frame local action runner used for UI self-tests."""

    def __init__(self) -> None:
        self.room = VirtualRoom()
        self.plan: BehaviorPlan | None = None
        self.started_at: float = 0.0
        self.last_frame: dict[str, Any] | None = None

    def sync_from_state(self, state: Any) -> None:
        self.room.dog_x = float(getattr(state, "dog_x", self.room.dog_x))
        self.room.dog_y = float(getattr(state, "dog_y", self.room.dog_y))
        self.room.dog_heading = float(getattr(state, "dog_heading", self.room.dog_heading))
        self.room.user_x = float(getattr(state, "user_x", self.room.user_x))
        self.room.user_y = float(getattr(state, "user_y", self.room.user_y))
        room_objects = getattr(state, "room_objects", None)
        if isinstance(room_objects, dict):
            self.room.objects = {
                str(name): dict(value)
                for name, value in room_objects.items()
                if isinstance(value, dict)
            }

    def start(self, behavior_name: str, timeout_sec: float = 3.0) -> SimEvent:
        self.plan = self.room.build_plan(
            {
                "goal_id": f"local-{int(time.time() * 1000)}",
                "behavior_name": behavior_name,
                "timeout_sec": timeout_sec,
            }
        )
        self.started_at = time.monotonic()
        self.last_frame = None
        return SimEvent(
            "action_goal",
            config.ACTION_GOAL_TOPIC,
            {
                "goal_id": self.plan.goal_id,
                "behavior_name": self.plan.behavior_name,
                "status": "RUNNING",
                "progress": 0.0,
                "current_action": self.plan.current_action,
            },
            f"local_execute_behavior: {self.plan.behavior_name} STARTED",
        )

    def update(self) -> list[SimEvent]:
        if self.plan is None:
            return []
        elapsed = time.monotonic() - self.started_at
        progress = min(1.0, elapsed / max(self.plan.duration, 0.1))
        frame = self.room.frame(self.plan, progress)
        self.last_frame = frame
        events = [
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                frame,
                f"local_execute_behavior: {self.plan.behavior_name} {progress * 100:.0f}% {frame['current_action']}",
            )
        ]
        if progress >= 1.0:
            self.room.commit(frame)
            events.append(
                SimEvent(
                    "action_result",
                    config.ACTION_RESULT_TOPIC,
                    {
                        "goal_id": self.plan.goal_id,
                        "behavior_name": self.plan.behavior_name,
                        "status": "SUCCESS",
                        "result": "completed",
                        "reason": "Local virtual behavior completed",
                        "reward": self.plan.reward,
                    },
                    f"local_execute_behavior: {self.plan.behavior_name} completed",
                )
            )
            self.plan = None
        return events


def _goal_to_dict(goal: Any) -> dict[str, Any]:
    behavior_name = str(getattr(goal, "behavior_name", "") or "idle_look_around")
    goal_id = str(getattr(goal, "goal_id", "") or f"virtual-{int(time.time() * 1000)}")
    behavior_id = str(getattr(goal, "behavior_id", "") or "")
    raw_params = getattr(goal, "params", None)
    if isinstance(raw_params, dict):
        params = raw_params
        params_json = json.dumps(params, ensure_ascii=False)
    else:
        params_json = str(getattr(goal, "params_json", raw_params) or "{}")
        try:
            decoded_params = json.loads(params_json)
        except json.JSONDecodeError:
            decoded_params = {}
        params = decoded_params if isinstance(decoded_params, dict) else {}
    return {
        "goal_id": goal_id,
        "behavior_id": behavior_id,
        "behavior_name": behavior_name,
        "priority_level": _int_value(getattr(goal, "priority_level", 0), 0),
        "params_json": params_json,
        "params": params,
        "timeout_sec": _float_value(getattr(goal, "timeout_sec", 0.0), 0.0),
        "timestamp": time.time(),
    }


def _goal_topic_to_dict(data: dict[str, Any]) -> dict[str, Any]:
    behavior_name = str(data.get("behavior_name") or "idle_look_around")
    goal_id = str(data.get("goal_id") or "")
    params = data.get("params")
    if not isinstance(params, dict):
        params_json = str(data.get("params_json") or "{}")
        try:
            decoded_params = json.loads(params_json)
        except json.JSONDecodeError:
            decoded_params = {}
        params = decoded_params if isinstance(decoded_params, dict) else {}
    else:
        params_json = json.dumps(params, ensure_ascii=False)

    return {
        "goal_id": goal_id,
        "behavior_id": str(data.get("behavior_id") or ""),
        "behavior_name": behavior_name,
        "priority_level": _int_value(data.get("priority_level"), 0),
        "params_json": params_json,
        "params": params,
        "timeout_sec": _float_value(data.get("timeout_sec"), 0.0),
        "timestamp": _float_value(data.get("timestamp"), time.time()),
    }


def _topic_goal_payload(goal: dict[str, Any]) -> dict[str, Any]:
    params = goal.get("params") if isinstance(goal.get("params"), dict) else {}
    return {
        "goal_id": goal["goal_id"],
        "behavior_id": str(goal.get("behavior_id") or ""),
        "behavior_name": goal["behavior_name"],
        "priority_level": int(goal.get("priority_level") or 0),
        "params": params,
        "params_json": str(goal.get("params_json") or json.dumps(params, ensure_ascii=False)),
        "timeout_sec": float(goal.get("timeout_sec") or 0.0),
        "timestamp": float(goal.get("timestamp") or time.time()),
        "source": config.VIEWER_SOURCE,
    }


def _topic_feedback_payload(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal_id": frame["goal_id"],
        "behavior_id": str(frame.get("behavior_id") or ""),
        "behavior_name": frame["behavior_name"],
        "status": frame["status"],
        "progress": float(frame["progress"]),
        "safe_to_interrupt": bool(frame["safe_to_interrupt"]),
        "current_action": frame["current_action"],
        "message": frame["message"],
        "stage_index": int(frame.get("stage_index") or 0),
        "stage_total": int(frame.get("stage_total") or 0),
        "stage_label": str(frame.get("stage_label") or ""),
        "phase": str(frame.get("phase") or ""),
        "target_label": str(frame.get("target_label") or ""),
        "source": config.VIEWER_SOURCE,
    }


def _topic_result_payload(
    plan: BehaviorPlan,
    status: str,
    result: str,
    reward: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "goal_id": plan.goal_id,
        "behavior_id": plan.behavior_id,
        "behavior_name": plan.behavior_name,
        "status": status,
        "result": result,
        "reward": float(reward),
        "reason": reason,
        "timestamp": time.time(),
        "source": config.VIEWER_SOURCE,
    }


def _object_name_for_action(action_key: str) -> str | None:
    object_rules = (
        ("bowl", ("BOWL", "FOOD", "EAT", "DRINK", "WATER")),
        ("pad", ("PAD", "TOILET", "PEE", "POOP", "EXCRETION", "SQUAT")),
        ("bed", ("BED", "SLEEP", "NAP", "CURLED")),
        ("charger", ("CHARGER", "CHARGE", "RECHARGE", "DOCK")),
        ("groom", ("GROOM", "CLEAN", "BRUSH", "LICK_PAWS")),
        ("toy", ("TOY", "BALL", "OBJECT", "POUNCE", "CARRY", "SHAKE", "FETCH", "PRESENT")),
    )
    for object_name, needles in object_rules:
        if any(needle in action_key for needle in needles):
            return object_name
    return None


def _action_targets_user(action_key: str) -> bool:
    return any(
        needle in action_key
        for needle in (
            "OWNER",
            "PERSON",
            "USER",
            "HUMAN",
            "ANIMAL",
            "SOCIAL",
            "INTERACTION",
            "RESOURCE",
            "GREET",
            "INVITE",
            "CUDDLE",
            "NUDGE",
            "HAND",
            "TOUCH",
            "COME",
            "FOLLOW",
            "CALL",
            "ATTENTION",
            "GREETING",
            "PLAY_BOW",
        )
    )


def _user_action_offset(action_key: str) -> tuple[float, float]:
    if any(token in action_key for token in ("HAND", "HIGH_FIVE", "PAW", "TOUCH")):
        return 100.0, 0.0
    if any(token in action_key for token in ("PLAY_BOW", "INVITE")):
        return 118.0, 0.0
    if any(token in action_key for token in ("FOLLOW", "MATCH_OWNER")):
        return 112.0, 50.0
    if "NUDGE" in action_key:
        return 84.0, 8.0
    if "CUDDLE" in action_key:
        return 72.0, 12.0
    return 104.0, 6.0


def _action_is_stationary(action_key: str) -> bool:
    return any(
        needle in action_key
        for needle in (
            "POSTURE",
            "TAIL",
            "HEAD",
            "EAR",
            "VOCAL",
            "LIGHT",
            "GIMBAL",
            "WAG",
            "HOP",
            "SPIN",
            "FREEZE",
            "TREMBLE",
            "ROLL",
            "STRETCH",
            "SIT",
            "LOOK",
            "TILT",
            "REST",
            "IGNORE",
            "MODIFIER",
            "SPEED_SCALE",
            "ACCELERATION_SCALE",
            "AMPLITUDE_SCALE",
            "DURATION_SCALE",
            "NO_MOTION",
        )
    )


def _action_is_non_motion_unit(action_key: str) -> bool:
    return any(
        token in action_key
        for token in (
            "IGNORE_",
            "POLICY",
            "NO_MOTION",
            "COMPLETE_STAGE",
            "MODIFIER",
            "SPEED_SCALE",
            "SLOW_MOVEMENT",
            "ACCELERATION_SCALE",
            "AMPLITUDE_SCALE",
            "DURATION_SCALE",
        )
    )


def _phase_action(action: str, progress: float) -> str:
    if progress < 0.68:
        return action
    phase_actions = {
        "ACT_LOCO_WALK_TO_BOWL": "ACT_MOUTH_EAT_FROM_BOWL",
        "ACT_LOCO_WALK_TO_PAD": "ACT_POSTURE_USE_TOILET_PAD",
        "ACT_LOCO_WALK_TO_BED": "ACT_POSTURE_SLEEP_ON_SIDE",
        "ACT_LOCO_POUNCE_FORWARD": "ACT_PAW_POUNCE_TOY",
        "ACT_LOCO_JUMP_ON_PERSON": "ACT_POSTURE_GREETING_JUMP",
        "ACT_LOCO_APPROACH_SLOWLY": "ACT_HEAD_SNIFF_OWNER",
        "ACT_LOCO_HIDE_AWAY": "ACT_POSTURE_HIDE_AWAY",
        "ACT_LOCO_AVOID_DANGER": "ACT_POSTURE_SAFE_DISTANCE",
        "ACT_FOLLOW": "ACT_LOCO_MATCH_OWNER",
        "ACT_SOCIAL_APPROACH": "ACT_TAIL_SOCIAL_WAG",
        "ACT_COME_HERE": "ACT_POSTURE_OWNER_ATTENTION",
        "ACT_RECHARGE": "ACT_NAV_DOCKED_CHARGER",
        "ACT_FETCH_TO_USER": "ACT_MOUTH_PRESENT_TO_USER",
    }
    return phase_actions.get(action, action)


def _stage_for_progress(action: str, progress: float) -> tuple[int, int, str]:
    if progress < 0.34:
        return 1, 3, "approach"
    if progress < 0.76:
        return 2, 3, _compact_action_label(action)
    return 3, 3, "settle"


def _phase_for_action(action: str, progress: float) -> str:
    key = _behavior_key(action)
    if any(token in key for token in ("LOCO", "NAV", "WALK", "RUN", "APPROACH", "FOLLOW", "FLEE")):
        return "moving" if progress < 0.78 else "arriving"
    if any(token in key for token in ("MOUTH", "PAW", "POSTURE", "TAIL", "HEAD", "VOCAL", "GROOM")):
        return "interacting"
    if progress < 0.34:
        return "approach"
    if progress < 0.82:
        return "execute"
    return "settle"


def _target_label_for_plan(plan: BehaviorPlan) -> str:
    if plan.active_object:
        labels = {
            "bowl": "food bowl",
            "bed": "sleep mat",
            "pad": "toilet pad",
            "toy": "toy ball",
            "charger": "charger",
            "groom": "groom mat",
        }
        return labels.get(plan.active_object, plan.active_object)
    key = _behavior_key(f"{plan.behavior_name} {plan.current_action}")
    if _action_targets_user(key):
        return "owner"
    if "HIDE" in key or "FLEE" in key or "AVOID" in key or "DANGER" in key:
        return "safe zone"
    return "room"


def _compact_action_label(action: str) -> str:
    label = str(action or "-")
    for prefix in ("ACT_POSTURE_", "ACT_LOCO_", "ACT_HEAD_", "ACT_TAIL_", "ACT_MOUTH_", "ACT_PAW_", "ACT_NAV_", "ACT_"):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    return label.lower().replace("_", " ")


def _is_own_debug_message(data: dict[str, Any]) -> bool:
    return data.get("source") == config.VIEWER_SOURCE


def _is_success_result(data: dict[str, Any]) -> bool:
    status = str(data.get("status") or "").upper()
    result = str(data.get("result") or data.get("result_type") or "").upper()
    return status in {"SUCCESS", "SUCCEEDED"} or result in {"SUCCESS", "COMPLETED"}


def _goal_matches_plan(data: dict[str, Any], plan: BehaviorPlan) -> bool:
    goal_id = str(data.get("goal_id") or "")
    return not goal_id or not plan.goal_id or goal_id == plan.goal_id


def _make_feedback(frame: dict[str, Any]) -> Any:
    feedback = ExecuteBehavior.Feedback()  # type: ignore[union-attr]
    _assign_fields(
        feedback,
        {
            "goal_id": frame["goal_id"],
            "behavior_id": str(frame.get("behavior_id") or ""),
            "behavior_name": frame["behavior_name"],
            "status": frame["status"],
            "progress": float(frame["progress"]),
            "safe_to_interrupt": bool(frame["safe_to_interrupt"]),
            "current_action": frame["current_action"],
            "message": frame["message"],
        },
    )
    return feedback


def _make_result(
    plan: BehaviorPlan,
    status: str,
    result: str,
    reason: str,
    reward: float,
) -> Any:
    result_msg = ExecuteBehavior.Result()  # type: ignore[union-attr]
    _assign_fields(
        result_msg,
        {
            "goal_id": plan.goal_id,
            "behavior_id": plan.behavior_id,
            "behavior_name": plan.behavior_name,
            "status": status,
            "result": result,
            "reason": reason,
            "reward": float(reward),
            "emotion_delta_json": "{}",
            "need_delta_json": "{}",
        },
    )
    return result_msg


def _assign_fields(message: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if hasattr(message, key):
            setattr(message, key, value)


def _message_to_dict(message: Any) -> dict[str, Any]:
    slots = getattr(message, "__slots__", [])
    return {slot.lstrip("_"): getattr(message, slot.lstrip("_"), None) for slot in slots}


def _behavior_key(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return value.replace("-", "_").replace(" ", "_").upper()


_VISUAL_BEHAVIOR_ALIASES = {
    "SEEK_FOOD_OR_WATER": "EAT_NORMALLY",
    "SEEK_FOOD": "EAT_NORMALLY",
    "EAT_IMMEDIATELY": "EAT_EXCITEDLY",
    "EXCRETION_REQUEST": "DEFECATE",
    "SLEEP_REQUEST": "SLEEP_NOW",
    "SEEK_SOCIAL_INTERACTION": "SEEK_HUMAN_INTERACTION",
    "SEEK_INTERACTION": "SEEK_HUMAN_INTERACTION",
    "RESPOND_OWNER_CALL": "COME_HERE",
    "EXPLORE_ENVIRONMENT": "EXPLORE_ROOM",
    "IDLE_LOOK_AROUND": "EXPLORE_ROOM",
    "INSPECT_TOY": "INSPECT_OBJECT",
    "IDLE_REST": "REST_IN_PLACE",
}


def _canonical_behavior_key(value: str) -> str:
    key = _behavior_key(value)
    return _VISUAL_BEHAVIOR_ALIASES.get(key, key)


def _interactive_target_requested(params: dict[str, Any]) -> bool:
    mode = str(params.get("interaction_mode") or "").strip().lower()
    interactive = params.get("interactive") is True or mode == "interactive"
    target = params.get("target")
    return interactive and isinstance(target, dict) and target.get("visible") is not False


def _expression_action(behavior_key: str) -> str:
    return {
        "EXPRESS_CALM": "ACT_POSTURE_RELAX_CALM",
        "EXPRESS_JOY": "ACT_TAIL_WAG_JOY",
        "EXPRESS_EXCITE": "ACT_LOCO_BOUNCE_EXCITED",
        "EXPRESS_FEAR": "ACT_POSTURE_FREEZE_FEAR",
        "EXPRESS_CURIOUS": "ACT_HEAD_TILT_CURIOUS",
        "EXPRESS_ANXIETY": "ACT_POSTURE_TREMBLE_ANXIETY",
    }.get(behavior_key, "ACT_POSTURE_EXPRESS")


def _action_server_enabled() -> bool:
    value = os.environ.get("MARSDOG_SIM2D_ACTION_SERVER", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _legacy_debug_topics_enabled() -> bool:
    value = os.environ.get(
        "MARSDOG_LEGACY_DEBUG_TOPICS",
        os.environ.get("MARSDOG_COMPAT_DEBUG_TOPICS", "0"),
    ).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _debug_topic_label() -> str:
    if _legacy_debug_topics_enabled():
        return "/debug/execute_behavior/* and legacy /execute_behavior/*"
    return "/debug/execute_behavior/* (legacy mirror also subscribed)"


def _object_xy(objects: dict[str, dict[str, Any]], name: str) -> tuple[float, float]:
    item = objects[name]
    return float(item["x"]), float(item["y"])


def _object_interaction_pose(
    objects: dict[str, dict[str, Any]],
    name: str,
) -> tuple[float, float, float]:
    x, y = _object_xy(objects, name)
    offsets = {
        "bowl": (58.0, 0.0, 180.0),
        "bed": (0.0, 0.0, 180.0),
        "pad": (0.0, 0.0, 0.0),
        "toy": (-52.0, 0.0, 0.0),
        "charger": (48.0, 0.0, 180.0),
        "groom": (0.0, 8.0, 90.0),
    }
    dx, dy, heading = offsets.get(name, (0.0, 0.0, 0.0))
    return x + dx, y + dy, heading


def _duration(value: Any, default: float) -> float:
    timeout = _float_value(value, 0.0)
    if timeout <= 0.0:
        return default
    return min(max(timeout * 0.65, 0.8), 6.0)


def _normalized_progress(value: Any) -> float:
    progress = _float_value(value, 0.0)
    if progress > 1.0:
        progress /= 100.0
    return max(0.0, min(1.0, progress))


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _heading_to(start_x: float, start_y: float, end_x: float, end_y: float) -> float:
    return math.degrees(math.atan2(end_y - start_y, end_x - start_x))


def _ease(progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    return progress * progress * (3.0 - 2.0 * progress)


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def _lerp_angle(start: float, end: float, progress: float) -> float:
    delta = (end - start + 180.0) % 360.0 - 180.0
    if abs(end - start) >= 300.0:
        delta = end - start
    return start + delta * progress
