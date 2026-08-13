"""Virtual /execute_behavior Action server for the Arcade simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from queue import Queue
import random
import re
import threading
import time
import uuid
from typing import Any, Callable

from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from std_msgs.msg import String

from . import config
from .action_visuals import visual_for_action
from .behavior_contract import (
    SelectedStage,
    direct_behavior_names,
    load_behavior_contract,
    select_behavior_stages,
)
from .sim_state import SimEvent
from .voice_commands import OWNER_SIDE_COMMAND_BEHAVIORS

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
    priority_level: int
    source: str
    target_x: float
    target_y: float
    target_heading: float
    current_action: str
    active_object: str | None = None
    object_target: tuple[float, float] | None = None
    duration: float = 3.0
    reward: float = 1.0
    selected_stages: tuple[SelectedStage, ...] = ()
    local_preview_random_target: bool = False


_VOICE_FETCH_BEHAVIORS = {"BRING_OBJECT", "FETCH_OBJECT"}
_VOICE_FOLLOW_BEHAVIORS = {"FOLLOW_OWNER"}
_FOLLOW_USER_OFFSET_X = 112.0
_FOLLOW_USER_OFFSET_Y = 50.0
_FOLLOW_USER_SPEED = 185.0
_FOLLOW_USER_ARRIVAL_DISTANCE = 8.0
_CALM_IDLE_SAFE_AREAS = (
    (340.0, 340.0, 500.0, 440.0),
    (360.0, 480.0, 500.0, 610.0),
    (520.0, 500.0, 620.0, 630.0),
    (610.0, 450.0, 720.0, 560.0),
)
_CONTRACT_BEHAVIOR_TARGETS = {
    "eatNormally": "bowl",
    "seekFood": "bowl",
    "eatExcitedly": "bowl",
    "seekFoodUrgently": "bowl",
    "barkShortAlert": "pad",
    "lickPaws": "groom",
    "sleepOnSide": "bed",
    "sleepNow": "bed",
    "restInPlace": "bed",
    "recharge": "charger",
    "seekHumanInteraction": "owner",
    "seekInteraction": "owner",
    "inviteHumanToPlay": "owner",
    "exploreRoom": "random",
    "inspectObject": "toy",
    "inspectFamiliarPlayItem": "toy",
    "inspectDogFood": "owner",
    "expressCalmWithHuman": "owner",
    "expressCalmAlone": "random",
    "expressJoyWithHuman": "owner",
    "expressJoyAlone": "random",
    "expressCuriosityWithHuman": "owner",
    "expressCuriosityAlone": "random",
    "expressExcitementWithHuman": "owner",
    "expressExcitementAlone": "random",
    "expressAnxietyWithHuman": "owner",
    "expressAnxietyAlone": "random",
    "expressFearWithHuman": "owner",
    "expressFearAlone": "random",
    "respond_owner_call": "owner",
    "come_to_owner": "owner",
    "follow_owner": "owner",
    "give_paw": "owner",
    "high_five": "owner",
    "return_to_owner": "owner",
    "bring_object": "toy",
    "fetch_object": "toy",
}
_CONTRACT_BEHAVIOR_TARGETS.update(
    {
        behavior_name: "owner"
        for behavior_name in OWNER_SIDE_COMMAND_BEHAVIORS
    }
)


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
        params = goal.get("params") if isinstance(goal.get("params"), dict) else {}
        selected_stages = select_behavior_stages(behavior_name)
        if selected_stages:
            return self._build_contract_plan(
                goal,
                params,
                selected_stages,
            )
        # The new executor accepts only the 53 case-sensitive direct behavior
        # names in the packaged contract.  Keep an invalid external Goal
        # visible as text, but never revive the former alias/guessing rules.
        return BehaviorPlan(
            behavior_name=str(behavior_name),
            goal_id=str(goal.get("goal_id") or ""),
            behavior_id=str(goal.get("behavior_id") or ""),
            priority_level=_int_value(goal.get("priority_level"), 5),
            source=str(params.get("source") or goal.get("source") or ""),
            target_x=self.dog_x,
            target_y=self.dog_y,
            target_heading=self.dog_heading,
            current_action="-",
            duration=_duration(goal.get("timeout_sec"), 1.0),
        )

    def _build_contract_plan(
        self,
        goal: dict[str, Any],
        params: dict[str, Any],
        selected_stages: tuple[SelectedStage, ...],
    ) -> BehaviorPlan:
        """Build a local plan directly from the packaged 53-behavior contract."""

        behavior_name = str(goal["behavior_name"])
        target = _CONTRACT_BEHAVIOR_TARGETS.get(behavior_name)
        target_x = self.dog_x
        target_y = self.dog_y
        target_heading = self.dog_heading
        active_object: str | None = None
        object_target: tuple[float, float] | None = None

        if target in self.objects:
            target_x, target_y, target_heading = _object_interaction_pose(
                self.objects,
                str(target),
            )
            active_object = str(target)
        elif target == "owner":
            if (
                behavior_name in OWNER_SIDE_COMMAND_BEHAVIORS
                and self.owner_is_near()
            ):
                target_x = self.dog_x
                target_y = self.dog_y
                target_heading = self.dog_heading
            else:
                target_x = self.user_x - 104.0
                target_y = self.user_y - 6.0
                target_heading = _heading_to(
                    target_x,
                    target_y,
                    self.user_x,
                    self.user_y,
                )
        elif target == "random":
            target_x, target_y = _random_calm_idle_target(
                self.dog_x,
                self.dog_y,
            )
            target_heading = _heading_to(
                self.dog_x,
                self.dog_y,
                target_x,
                target_y,
            )

        if behavior_name in {"bring_object", "fetch_object"}:
            target_x, target_y, target_heading = _object_interaction_pose(
                self.objects,
                "toy",
            )
            active_object = "toy"
            object_target = (self.user_x - 28.0, self.user_y - 26.0)

        default_duration = max(2.0, len(selected_stages) * 1.8)
        return BehaviorPlan(
            behavior_name=behavior_name,
            goal_id=str(goal.get("goal_id") or ""),
            behavior_id=str(goal.get("behavior_id") or ""),
            priority_level=_int_value(goal.get("priority_level"), 5),
            source=str(params.get("source") or goal.get("source") or ""),
            target_x=target_x,
            target_y=target_y,
            target_heading=target_heading,
            current_action=selected_stages[0].action_id,
            active_object=active_object,
            object_target=object_target,
            duration=_duration(goal.get("timeout_sec"), default_duration),
            selected_stages=selected_stages,
        )

    def owner_is_near(self) -> bool:
        return (
            math.hypot(
                self.user_x - self.dog_x,
                self.user_y - self.dog_y,
            )
            <= config.OWNER_NEAR_DISTANCE
        )

    def frame(self, plan: BehaviorPlan, progress: float) -> dict[str, Any]:
        if plan.selected_stages:
            return self._contract_frame(plan, progress)
        return self._base_frame(plan, progress)

    def _contract_frame(
        self,
        plan: BehaviorPlan,
        progress: float,
    ) -> dict[str, Any]:
        progress = _clamp(progress, 0.0, 1.0)
        stages = plan.selected_stages
        stage_total = len(stages)
        # A feedback packet is emitted after a Stage completes.  At an exact
        # boundary such as 1/4, the completed Stage is still Stage 1 rather
        # than the next Stage that has not executed yet.
        stage_offset = min(
            stage_total - 1,
            max(0, math.ceil(progress * stage_total) - 1),
        )
        stage = stages[stage_offset]
        stage_start = stage_offset / stage_total
        stage_end = (stage_offset + 1) / stage_total
        stage_progress = (
            1.0
            if progress >= 1.0
            else _clamp(
                (progress - stage_start) / max(0.001, stage_end - stage_start),
                0.0,
                1.0,
            )
        )
        frame = self.frame_for_action(
            plan,
            stage.action_id,
            stage_progress,
        )
        stage_visual = visual_for_action(stage.action_id)
        if (
            plan.behavior_name in OWNER_SIDE_COMMAND_BEHAVIORS
            and (stage_visual is None or not stage_visual.moves)
        ):
            final_pose = frame.get("dog_pose")
            if isinstance(final_pose, dict):
                final_x = float(final_pose.get("x", self.dog_x))
                final_y = float(final_pose.get("y", self.dog_y))
                approach_distance = math.hypot(
                    final_x - self.dog_x,
                    final_y - self.dog_y,
                )
                if approach_distance > config.MOTION_POSITION_EPSILON:
                    approach_duration = (
                        approach_distance / config.OWNER_APPROACH_SPEED
                    )
                    approach_fraction = _clamp(
                        approach_duration / max(plan.duration, 0.1),
                        0.25,
                        0.80,
                    )
                    approach_progress = _clamp(
                        progress / approach_fraction,
                        0.0,
                        1.0,
                    )
                    eased_approach = _ease(approach_progress)
                    final_heading = float(
                        final_pose.get("heading", self.dog_heading)
                    )
                    frame["dog_pose"] = {
                        "x": _lerp(
                            self.dog_x,
                            final_x,
                            eased_approach,
                        ),
                        "y": _lerp(
                            self.dog_y,
                            final_y,
                            eased_approach,
                        ),
                        "heading": _lerp_angle(
                            self.dog_heading,
                            final_heading,
                            eased_approach,
                        ),
                    }
                    if approach_progress < 1.0:
                        frame["phase"] = "approaching_owner"
        frame["progress"] = progress
        frame["current_stage"] = stage.stage_id
        frame["stage_index"] = stage_offset + 1
        frame["stage_total"] = stage_total
        frame["stage_label"] = stage.stage_id
        frame["current_action"] = stage.action_id
        frame["message"] = (
            f"Stage {stage_offset + 1}/{stage_total}: "
            f"{stage.action_id}"
        )
        return frame

    def _base_frame(self, plan: BehaviorPlan, progress: float) -> dict[str, Any]:
        current_action = plan.current_action
        eased = _ease(progress)
        dog_x = _lerp(self.dog_x, plan.target_x, eased)
        dog_y = _lerp(self.dog_y, plan.target_y, eased)
        heading = _lerp_angle(self.dog_heading, plan.target_heading, eased)
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
            "message": current_action,
            "stage_index": 0,
            "stage_total": 0,
            "stage_label": "-",
            "phase": "visualizing",
            "target_label": target_label,
            "dog_pose": {"x": dog_x, "y": dog_y, "heading": heading},
            "user_pose": {"x": self.user_x, "y": self.user_y},
            "objects": objects,
        }

    def follow_frame(
        self,
        plan: BehaviorPlan,
        delta_time: float,
    ) -> dict[str, Any]:
        """Advance a continuous follow plan toward the latest owner position."""

        target_x = _clamp(
            self.user_x - _FOLLOW_USER_OFFSET_X,
            config.SCENE_LOGICAL_LEFT + 36.0,
            config.SCENE_LOGICAL_RIGHT - 36.0,
        )
        target_y = _clamp(
            self.user_y - _FOLLOW_USER_OFFSET_Y,
            config.SCENE_LOGICAL_BOTTOM + 36.0,
            config.SCENE_LOGICAL_TOP - 36.0,
        )
        owner_distance = math.hypot(
            self.user_x - self.dog_x,
            self.user_y - self.dog_y,
        )
        moving = owner_distance > config.OWNER_NEAR_DISTANCE
        distance = math.hypot(target_x - self.dog_x, target_y - self.dog_y)
        step = (
            min(
                distance,
                _FOLLOW_USER_SPEED * max(0.0, min(float(delta_time), 0.12)),
            )
            if moving
            else 0.0
        )
        if distance > 0.0 and step > 0.0:
            ratio = step / distance
            self.dog_x = _lerp(self.dog_x, target_x, ratio)
            self.dog_y = _lerp(self.dog_y, target_y, ratio)

        remaining = math.hypot(target_x - self.dog_x, target_y - self.dog_y)
        moving = (
            moving
            and remaining > _FOLLOW_USER_ARRIVAL_DISTANCE
        )
        self.dog_heading = _heading_to(
            self.dog_x,
            self.dog_y,
            self.user_x,
            self.user_y,
        )
        plan.target_x = target_x
        plan.target_y = target_y
        plan.target_heading = self.dog_heading
        current_action = "ACT_INTERACT_FOLLOW_OWNER"
        progress = (
            max(0.05, min(0.85, 1.0 - remaining / 320.0))
            if moving
            else 0.9
        )
        stage_label = "following moving owner" if moving else "waiting near owner"

        return {
            "goal_id": plan.goal_id,
            "behavior_id": plan.behavior_id,
            "behavior_name": plan.behavior_name,
            "status": "RUNNING",
            "progress": progress,
            "safe_to_interrupt": True,
            "current_action": current_action,
            "message": f"Follow owner: {stage_label}",
            "stage_index": 1,
            "stage_total": 1,
            "stage_label": stage_label,
            "phase": "moving" if moving else "holding",
            "target_label": "owner",
            "dog_pose": {
                "x": self.dog_x,
                "y": self.dog_y,
                "heading": self.dog_heading,
            },
            "user_pose": {"x": self.user_x, "y": self.user_y},
            "objects": {
                name: dict(obj)
                for name, obj in self.objects.items()
            },
        }

    def _fetch_frame(self, plan: BehaviorPlan, progress: float) -> dict[str, Any]:
        """Animate one exact fetch ACT over a four-part 2D route.

        The route is purely a visual decomposition.  Every frame continues to
        expose the single ACT reported by the executor; no synthetic legacy
        ACT labels are emitted for its approach/grab/return segments.
        """

        progress = max(0.0, min(1.0, progress))
        toy_x, toy_y = _object_xy(self.objects, "toy")
        pickup_x, pickup_y = plan.target_x, plan.target_y
        owner_x = self.user_x - 104.0
        owner_y = self.user_y - 6.0

        if progress < 0.36:
            leg_progress = _ease(progress / 0.36)
            dog_x = _lerp(self.dog_x, pickup_x, leg_progress)
            dog_y = _lerp(self.dog_y, pickup_y, leg_progress)
            heading = _lerp_angle(
                self.dog_heading,
                _heading_to(self.dog_x, self.dog_y, pickup_x, pickup_y),
                leg_progress,
            )
            current_action = plan.current_action
            phase = "moving"
            stage_index, stage_label = 1, "approach toy"
            carried_toy_x, carried_toy_y = toy_x, toy_y
        elif progress < 0.50:
            leg_progress = _ease((progress - 0.36) / 0.14)
            dog_x, dog_y = pickup_x, pickup_y
            heading = _heading_to(pickup_x, pickup_y, toy_x, toy_y)
            current_action = plan.current_action
            phase = "interacting"
            stage_index, stage_label = 2, "grab toy"
            carried_toy_x = _lerp(toy_x, dog_x + 46.0, leg_progress)
            carried_toy_y = _lerp(toy_y, dog_y + 4.0, leg_progress)
        elif progress < 0.90:
            leg_progress = _ease((progress - 0.50) / 0.40)
            dog_x = _lerp(pickup_x, owner_x, leg_progress)
            dog_y = _lerp(pickup_y, owner_y, leg_progress)
            heading = _heading_to(dog_x, dog_y, self.user_x, self.user_y)
            current_action = plan.current_action
            phase = "moving"
            stage_index, stage_label = 3, "carry toy to owner"
            carried_toy_x = dog_x + 46.0
            carried_toy_y = dog_y + 4.0
        else:
            leg_progress = _ease((progress - 0.90) / 0.10)
            dog_x, dog_y = owner_x, owner_y
            heading = _heading_to(owner_x, owner_y, self.user_x, self.user_y)
            current_action = plan.current_action
            phase = "interacting"
            stage_index, stage_label = 4, "release toy"
            release_x, release_y = plan.object_target or (
                self.user_x - 28.0,
                self.user_y - 26.0,
            )
            carried_toy_x = _lerp(dog_x + 46.0, release_x, leg_progress)
            carried_toy_y = _lerp(dog_y + 4.0, release_y, leg_progress)

        objects = {name: dict(obj) for name, obj in self.objects.items()}
        if "toy" in objects:
            objects["toy"]["active"] = True
            objects["toy"]["x"] = carried_toy_x
            objects["toy"]["y"] = carried_toy_y

        return {
            "goal_id": plan.goal_id,
            "behavior_id": plan.behavior_id,
            "behavior_name": plan.behavior_name,
            "status": "RUNNING",
            "progress": progress,
            "safe_to_interrupt": progress < 0.85,
            "current_action": current_action,
            "message": f"Step {stage_index}/4: {current_action}",
            "stage_index": stage_index,
            "stage_total": 4,
            "stage_label": stage_label,
            "phase": phase,
            "target_label": "owner" if progress >= 0.50 else "toy ball",
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
        if _behavior_key(plan.behavior_name) in _VOICE_FETCH_BEHAVIORS:
            fetch_progress = _fetch_progress_for_action(current_action, progress)
            frame = self._fetch_frame(plan, fetch_progress)
            frame["progress"] = progress
            frame["current_action"] = current_action
            frame["message"] = current_action
            frame["stage_index"] = 0
            frame["stage_total"] = 0
            frame["stage_label"] = "-"
            frame["phase"] = "visualizing"
            return frame

        visual_plan = self._visual_plan_for_action(plan, current_action)
        # External executors often switch to an interaction ACT only after
        # navigation has completed.  Treat that ACT's pose as the destination;
        # SimState then interpolates toward it instead of sliding an eating,
        # sleeping, or grooming sprite across the room.
        exact_visual = visual_for_action(current_action)
        frame_progress = (
            progress
            if (
                exact_visual is not None
                and (
                    exact_visual.moves
                    or plan.local_preview_random_target
                )
            )
            else 1.0
        )
        frame = self._base_frame(visual_plan, frame_progress)
        frame["progress"] = progress
        frame["current_action"] = current_action
        frame["message"] = current_action
        frame["stage_index"] = 0
        frame["stage_total"] = 0
        frame["stage_label"] = "-"
        frame["phase"] = "visualizing"
        frame["target_label"] = (
            _target_label_for_plan(visual_plan)
            if exact_visual is not None
            else "text only"
        )
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
        return self._contract_visual_plan_for_action(
            plan,
            current_action,
        )

    def _contract_visual_plan_for_action(
        self,
        plan: BehaviorPlan,
        current_action: str,
    ) -> BehaviorPlan:
        """Resolve only exact, declared 2D metadata for a contract ACT."""

        visual = visual_for_action(current_action)
        target_x = self.dog_x
        target_y = self.dog_y
        heading = self.dog_heading
        active_object: str | None = None
        object_target: tuple[float, float] | None = None

        if visual is not None and plan.local_preview_random_target:
            # Autonomous UI play may stage a non-locomotion pose at a fresh
            # safe location.  This per-plan override must not change where
            # the same ACT runs for a real voice/behavior-tree Goal.
            target_x = plan.target_x
            target_y = plan.target_y
            heading = plan.target_heading
        elif visual is not None:
            target = visual.target
            if target in self.objects:
                target_x, target_y, heading = _object_interaction_pose(
                    self.objects,
                    str(target),
                )
                active_object = str(target)
            elif target == "owner":
                if (
                    plan.behavior_name in OWNER_SIDE_COMMAND_BEHAVIORS
                    and self.owner_is_near()
                ):
                    target_x = self.dog_x
                    target_y = self.dog_y
                    heading = self.dog_heading
                else:
                    offset_x, offset_y = _user_action_offset(current_action)
                    target_x = self.user_x - offset_x
                    target_y = self.user_y - offset_y
                    heading = _heading_to(
                        target_x,
                        target_y,
                        self.user_x,
                        self.user_y,
                    )
            elif target == "random":
                target_x = plan.target_x
                target_y = plan.target_y
                heading = _heading_to(
                    self.dog_x,
                    self.dog_y,
                    target_x,
                    target_y,
                )
            elif visual.moves:
                # Ambiguous movement such as ACT_CIRCLE_AROUND uses the exact
                # behavior's contract target selected when the goal arrived.
                target_x = plan.target_x
                target_y = plan.target_y
                heading = plan.target_heading
                active_object = plan.active_object
            elif _CONTRACT_BEHAVIOR_TARGETS.get(plan.behavior_name):
                # Some ACT keys (for example ACT_PLAY_BOW or ACT_YAWN) are
                # valid in more than one behavior and therefore do not carry
                # a global target.  The selected behavior supplies that
                # context without changing or inventing an ACT label.
                target_x = plan.target_x
                target_y = plan.target_y
                heading = plan.target_heading
                active_object = plan.active_object

            if current_action in {
                "ACT_OBJECT_BRING",
                "ACT_OBJECT_FETCH",
                "ACT_FETCH_TOY",
            }:
                active_object = "toy"
                object_target = (
                    self.user_x - 28.0,
                    self.user_y - 26.0,
                )

        return BehaviorPlan(
            behavior_name=plan.behavior_name,
            goal_id=plan.goal_id,
            behavior_id=plan.behavior_id,
            priority_level=plan.priority_level,
            source=plan.source,
            target_x=target_x,
            target_y=target_y,
            target_heading=heading,
            current_action=current_action,
            active_object=active_object,
            object_target=object_target,
            duration=plan.duration,
            reward=plan.reward,
            selected_stages=(),
            local_preview_random_target=plan.local_preview_random_target,
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
        ]
        self._feedback_subscriptions = [
            self._subscribe_debug_topic(
                config.ACTION_FEEDBACK_TOPIC,
                self._feedback_topic_callback,
            ),
        ]
        self._result_subscriptions = [
            self._subscribe_debug_topic(
                config.ACTION_RESULT_TOPIC,
                self._result_topic_callback,
            ),
        ]
        self._goal_publishers: list[Any] = []
        self._feedback_publishers: list[Any] = []
        self._result_publishers: list[Any] = []
        self._mirror_plan: BehaviorPlan | None = None
        self._mirror_plans: dict[str, BehaviorPlan] = {}
        self._mirror_plan_sequence: dict[str, int] = {}
        self._mirror_sequence = 0
        self._mirror_active_sequence = 0
        self._mirror_last_frame: dict[str, Any] | None = None
        self._mirror_progress = 0.0
        self.local_room = self._room
        self._put_state(False, "debug topic mirror ready; Action unavailable")

        if not _action_server_enabled():
            self._put_state(False, "debug topic mirror ready; Action server disabled")
            node.get_logger().info(
                "Virtual Action server disabled by MARSDOG_SIM2D_ACTION_SERVER; "
                "only /debug/execute_behavior/* visualization is active."
            )
            return

        if ExecuteBehavior is None:
            node.get_logger().warning(
                "Virtual ROS2 Action server disabled: "
                "ExecuteBehavior action type is unavailable. "
                "Only /debug/execute_behavior/* visualization is active."
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
            "publishing debug topics under /debug/execute_behavior/*"
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
        qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=config.EVENT_TOPIC_DEPTH,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        return self._node.create_subscription(
            String,
            topic,
            lambda msg: callback(msg, topic),
            qos,
        )

    def _goal_topic_callback(self, msg: String, topic: str) -> None:
        decoded = self._decode_topic_json(topic, msg)
        if decoded is not None:
            decoded = _normalize_action_debug_payload(decoded, "goal")
        if (
            decoded is None
            or _is_own_debug_message(decoded)
            or self._is_duplicate_debug_event("goal", decoded, topic)
        ):
            return

        goal = _goal_topic_to_dict(decoded)
        if not goal["goal_id"]:
            goal["goal_id"] = f"debug-{uuid.uuid4().hex}"
        with self._lock:
            plan = self._room.build_plan(goal)
            if plan.goal_id:
                self._mirror_plans[plan.goal_id] = plan
                if plan.goal_id not in self._mirror_plan_sequence:
                    self._mirror_sequence += 1
                    self._mirror_plan_sequence[plan.goal_id] = (
                        self._mirror_sequence
                    )
            if self._mirror_plan is None:
                self._mirror_plan = plan
                self._mirror_active_sequence = (
                    self._mirror_plan_sequence.get(plan.goal_id, 0)
                )
                self._mirror_last_frame = None
                self._mirror_progress = 0.0
        self._node.get_logger().info(
            f"Mirroring external execute_behavior goal: {goal['behavior_name']}"
        )
        self._put_event(
            "action_goal",
            {
                **goal,
                "status": "PENDING",
                "progress": 0.0,
            },
            f"execute_behavior_mirror: {goal['behavior_name']} PENDING",
            topic=topic,
        )

    def _feedback_topic_callback(self, msg: String, topic: str) -> None:
        decoded = self._decode_topic_json(topic, msg)
        if decoded is not None:
            decoded = _normalize_action_debug_payload(decoded, "feedback")
        if (
            decoded is None
            or _is_own_debug_message(decoded)
            or self._is_duplicate_debug_event("feedback", decoded, topic)
        ):
            return

        reported_progress = _normalized_progress(decoded.get("progress"))
        current_action = str(decoded.get("current_action") or "")
        with self._lock:
            goal_id = str(decoded.get("goal_id") or "")
            plan = (
                self._mirror_plans.get(goal_id)
                if goal_id
                else self._mirror_plan
            )
            if not goal_id and plan is not None:
                goal_id = plan.goal_id
                decoded["goal_id"] = goal_id
            if plan is None and decoded.get("behavior_name"):
                if not goal_id:
                    goal_id = f"debug-{uuid.uuid4().hex}"
                    decoded["goal_id"] = goal_id
                recovered_goal = _goal_topic_to_dict(decoded)
                plan = self._room.build_plan(recovered_goal)
                self._mirror_plans[goal_id] = plan
                self._mirror_sequence += 1
                self._mirror_plan_sequence[goal_id] = self._mirror_sequence
                self._mirror_plan = plan
                self._mirror_active_sequence = self._mirror_sequence
                self._mirror_last_frame = None
                self._mirror_progress = 0.0
                self._node.get_logger().info(
                    "Recovered execute_behavior visualization from Feedback "
                    f"without a prior Goal: {decoded.get('behavior_name')}"
                )
            if plan is not None and plan is not self._mirror_plan:
                incoming_sequence = self._mirror_plan_sequence.get(
                    goal_id,
                    0,
                )
                if incoming_sequence <= self._mirror_active_sequence:
                    plan = None
                else:
                    if self._mirror_last_frame is not None:
                        self._room.commit(self._mirror_last_frame)
                    self._mirror_plan = plan
                    self._mirror_active_sequence = incoming_sequence
                    self._mirror_last_frame = None
                    self._mirror_progress = 0.0
            progress = (
                max(self._mirror_progress, reported_progress)
                if plan is not None
                else reported_progress
            )
            self._mirror_progress = progress
            if (
                plan is not None
                and current_action
                and _action_is_non_motion_unit(_behavior_key(current_action))
                and self._mirror_last_frame is not None
            ):
                frame = dict(self._mirror_last_frame)
                frame["progress"] = progress
                frame["current_action"] = current_action
            elif plan is not None and current_action:
                # The documented executor publishes one feedback packet after
                # each Stage has completed.  Animate the reported ACT toward
                # its completed destination; keep the payload's overall
                # progress solely for the progress bar.
                frame = self._room.frame_for_action(plan, current_action, 1.0)
            elif plan is not None:
                frame = self._room.frame(plan, progress)
            else:
                frame = {}
            if frame:
                self._mirror_last_frame = frame
        payload = {**frame, **decoded} if frame else dict(decoded)
        payload["progress"] = progress
        if frame and not any(
            decoded.get(key) is not None
            for key in ("stage_index", "stage_total", "step_index", "step_total")
        ):
            payload.pop("stage_index", None)
            payload.pop("stage_total", None)
            payload.pop("stage_label", None)
        if decoded.get("phase") is None:
            payload.pop("phase", None)
        self._put_event(
            "action_feedback",
            payload,
            f"execute_behavior_mirror: {decoded.get('goal_id', '-')} {progress * 100:.0f}% {decoded.get('current_action', '-')}",
            topic=topic,
        )

    def _result_topic_callback(self, msg: String, topic: str) -> None:
        decoded = self._decode_topic_json(topic, msg)
        if decoded is not None:
            decoded = _normalize_action_debug_payload(decoded, "result")
        if (
            decoded is None
            or _is_own_debug_message(decoded)
            or self._is_duplicate_debug_event("result", decoded, topic)
        ):
            return

        final_frame: dict[str, Any] = {}
        with self._lock:
            goal_id = str(decoded.get("goal_id") or "")
            result_plan = (
                self._mirror_plans.pop(goal_id, None)
                if goal_id
                else self._mirror_plan
            )
            if not goal_id and result_plan is not None:
                goal_id = result_plan.goal_id
                decoded["goal_id"] = goal_id
                self._mirror_plans.pop(goal_id, None)
            if goal_id:
                self._mirror_plan_sequence.pop(goal_id, None)
            if self._mirror_plan is not None and result_plan is self._mirror_plan:
                if self._mirror_last_frame is not None:
                    final_frame = self._mirror_last_frame
                    self._room.commit(final_frame)
                self._mirror_plan = None
                self._mirror_last_frame = None
                self._mirror_progress = 0.0
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
        if behavior_name not in direct_behavior_names():
            self._node.get_logger().warning(
                "Rejecting unsupported virtual behavior goal: "
                f"{behavior_name!r}"
            )
            return GoalResponse.REJECT
        try:
            priority_level = int(
                getattr(goal_request, "priority_level", 0)
            )
        except (TypeError, ValueError):
            priority_level = -1
        if not 0 <= priority_level <= 6:
            self._node.get_logger().warning(
                "Rejecting virtual behavior goal with invalid priority: "
                f"{priority_level}"
            )
            return GoalResponse.REJECT
        params_json = str(
            getattr(goal_request, "params_json", "") or "{}"
        )
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError:
            params = None
        if not isinstance(params, dict):
            self._node.get_logger().warning(
                "Rejecting virtual behavior goal with invalid params_json"
            )
            return GoalResponse.REJECT
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
                "status": "PENDING",
                "progress": 0.0,
            },
            f"execute_behavior: {plan.behavior_name} PENDING",
            topic=config.ACTION_GOAL_TOPIC,
        )

        last_frame: dict[str, Any] | None = None
        stage_total = max(1, len(plan.selected_stages))
        stage_duration = max(0.1, plan.duration / stage_total)
        for stage_index in range(1, stage_total + 1):
            stage_deadline = time.monotonic() + stage_duration
            while time.monotonic() < stage_deadline:
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
                time.sleep(
                    min(
                        config.ACTION_CANCEL_POLL_PERIOD_SEC,
                        max(0.0, stage_deadline - time.monotonic()),
                    )
                )

            progress = stage_index / stage_total
            with self._lock:
                frame = self._room.frame(plan, progress)
            last_frame = frame
            goal_handle.publish_feedback(_make_feedback(frame))
            feedback_payload = _topic_feedback_payload(frame)
            self._publish_json(self._feedback_publishers, feedback_payload)
            ui_feedback_payload = {
                **frame,
                **feedback_payload,
            }
            for internal_key in (
                "stage_index",
                "stage_total",
                "stage_label",
                "phase",
            ):
                ui_feedback_payload.pop(internal_key, None)
            self._put_event(
                "action_feedback",
                ui_feedback_payload,
                (
                    f"execute_behavior: {plan.behavior_name} "
                    f"Stage {stage_index}/{stage_total} "
                    f"{frame['current_action']}"
                ),
                topic=config.ACTION_FEEDBACK_TOPIC,
            )

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
        result_payload.setdefault("goal_id", plan.goal_id)
        result_payload.setdefault("behavior_id", plan.behavior_id)
        result_payload.setdefault("behavior_name", plan.behavior_name)
        result_payload.setdefault("duration_sec", plan.duration)
        result_payload.setdefault("failed_action", "")
        result_payload.setdefault("interrupted_by", "")
        result_payload.setdefault("emotion_delta_json", "{}")
        result_payload.setdefault("need_delta_json", "{}")
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
        self.last_updated_at: float = 0.0
        self.paused_at: float | None = None
        self.last_frame: dict[str, Any] | None = None
        self.food_wait_started_at: float | None = None
        self.food_wait_progress: float | None = None

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

    def start(
        self,
        behavior_name: str,
        timeout_sec: float = 3.0,
        *,
        preferred_action: str | None = None,
        random_preview_target: bool = False,
    ) -> SimEvent:
        self.plan = self.room.build_plan(
            {
                "goal_id": f"local-{uuid.uuid4().hex}",
                "behavior_name": behavior_name,
                "timeout_sec": timeout_sec,
            }
        )
        if preferred_action is not None:
            self._select_preferred_contract_action(preferred_action)
        if random_preview_target:
            target_x, target_y = _random_calm_idle_target(
                self.room.dog_x,
                self.room.dog_y,
            )
            self.plan.target_x = target_x
            self.plan.target_y = target_y
            self.plan.target_heading = _heading_to(
                self.room.dog_x,
                self.room.dog_y,
                target_x,
                target_y,
            )
            self.plan.local_preview_random_target = True
        self.started_at = time.monotonic()
        self.last_updated_at = self.started_at
        self.paused_at = None
        self.last_frame = None
        self.food_wait_started_at = None
        self.food_wait_progress = None
        return SimEvent(
            "action_goal",
            config.ACTION_GOAL_TOPIC,
            {
                "goal_id": self.plan.goal_id,
                "behavior_name": self.plan.behavior_name,
                "status": "PENDING",
                "progress": 0.0,
            },
            f"local_execute_behavior: {self.plan.behavior_name} PENDING",
        )

    def _select_preferred_contract_action(self, action_id: str) -> None:
        """Select one declared ACT for a deterministic local UI preview."""

        if self.plan is None:
            raise RuntimeError("cannot select an ACT without an active plan")
        behavior = load_behavior_contract().get(self.plan.behavior_name)
        if behavior is None:
            raise ValueError(
                f"unsupported behavior for local preview: {self.plan.behavior_name}"
            )

        selected = list(self.plan.selected_stages)
        for stage_index, stage in enumerate(behavior.stages):
            if action_id not in stage.candidates:
                continue
            selected[stage_index] = SelectedStage(
                stage_id=stage.stage_id,
                order=stage.order,
                action_id=action_id,
            )
            self.plan.selected_stages = tuple(selected)
            if stage_index == 0:
                self.plan.current_action = action_id
            return
        raise ValueError(
            f"{action_id!r} is not declared by behavior "
            f"{self.plan.behavior_name!r}"
        )

    def pause(self) -> None:
        """Freeze an active local plan without losing its remaining progress."""

        if self.plan is None or self.paused_at is not None:
            return
        self.paused_at = time.monotonic()

    def resume(self) -> None:
        """Continue a paused plan while excluding time spent paused."""

        if self.paused_at is None:
            return
        now = time.monotonic()
        paused_duration = max(0.0, now - self.paused_at)
        self.started_at += paused_duration
        if self.food_wait_started_at is not None:
            self.food_wait_started_at += paused_duration
        self.last_updated_at = now
        self.paused_at = None

    def cancel(self, reason: str = "Local virtual behavior interrupted") -> SimEvent | None:
        if self.plan is None:
            return None
        plan = self.plan
        if self.last_frame is not None:
            self.room.commit(self.last_frame)
        self.plan = None
        self.paused_at = None
        self.last_frame = None
        self.food_wait_started_at = None
        self.food_wait_progress = None
        return SimEvent(
            "action_result",
            config.ACTION_RESULT_TOPIC,
            {
                "goal_id": plan.goal_id,
                "behavior_name": plan.behavior_name,
                "status": "CANCELED",
                "result": "interrupted",
                "reason": reason,
                "reward": 0.0,
            },
            f"local_execute_behavior: {plan.behavior_name} interrupted",
        )

    def update(self, state: Any | None = None) -> list[SimEvent]:
        if self.plan is None or self.paused_at is not None:
            return []
        now = time.monotonic()
        if _plan_follows_user(self.plan):
            if state is not None:
                self.room.user_x = float(
                    getattr(state, "user_x", self.room.user_x)
                )
                self.room.user_y = float(
                    getattr(state, "user_y", self.room.user_y)
                )
            delta_time = max(1.0 / 120.0, now - self.last_updated_at)
            self.last_updated_at = now
            frame = self.room.follow_frame(self.plan, delta_time)
            self.last_frame = frame
            return [
                SimEvent(
                    "action_feedback",
                    config.ACTION_FEEDBACK_TOPIC,
                    frame,
                    (
                        "local_execute_behavior: "
                        f"{self.plan.behavior_name} {frame['current_action']}"
                    ),
                )
            ]

        if _plan_requires_bowl_food(self.plan):
            has_food = bool(
                getattr(state, "ui_bowl_has_food", False)
                if state is not None
                else False
            )
            if has_food and self.food_wait_started_at is not None:
                # Exclude time spent waiting from behavior progress so adding
                # food resumes the interaction instead of completing at once.
                self.started_at += now - self.food_wait_started_at
                self.food_wait_started_at = None
                self.food_wait_progress = None

        elapsed = now - self.started_at
        self.last_updated_at = now
        progress = min(1.0, elapsed / max(self.plan.duration, 0.1))

        frame = self.room.frame(self.plan, progress)
        has_food = bool(
            getattr(state, "ui_bowl_has_food", False)
            if state is not None
            else False
        )
        if (
            _plan_requires_bowl_food(self.plan)
            and not has_food
            and _action_requires_food(frame.get("current_action"))
        ):
            if self.food_wait_started_at is None:
                self.food_wait_started_at = now
                self.food_wait_progress = progress
            progress = self.food_wait_progress or progress
            frame = self.room.frame(self.plan, progress)
            frame["progress"] = progress
            frame["safe_to_interrupt"] = True
            frame["message"] = "Food bowl is empty; waiting before consumption"
            frame["phase"] = "waiting_for_food"
            frame["target_label"] = "food bowl"
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
            self.paused_at = None
            self.food_wait_started_at = None
            self.food_wait_progress = None
        return events


def _goal_to_dict(goal: Any) -> dict[str, Any]:
    behavior_name = str(getattr(goal, "behavior_name", "") or "")
    goal_id = str(
        getattr(goal, "goal_id", "")
        or f"virtual-{uuid.uuid4().hex}"
    )
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
    behavior_name = str(data.get("behavior_name") or "")
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


def _normalize_action_debug_payload(
    data: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    """Normalize flat/nested and snake/camel debug JSON to one UI contract."""

    source = dict(data)
    for container_key in (kind, "payload", "data", "message"):
        nested = source.get(container_key)
        if isinstance(nested, dict):
            source = {**source, **nested}
            break

    aliases = {
        "goal_id": ("goal_id", "goalId", "request_id", "requestId"),
        "behavior_id": ("behavior_id", "behaviorId"),
        "behavior_name": ("behavior_name", "behaviorName", "behavior"),
        "priority_level": ("priority_level", "priorityLevel", "priority"),
        "params_json": ("params_json", "paramsJson"),
        "timeout_sec": ("timeout_sec", "timeoutSec", "timeout"),
        "status": ("status", "state"),
        "progress": ("progress", "completion", "completionRate"),
        "safe_to_interrupt": ("safe_to_interrupt", "safeToInterrupt"),
        "current_stage": (
            "current_stage",
            "currentStage",
            "stage_id",
            "stageId",
            "stage",
        ),
        "current_action": (
            "current_action",
            "currentAction",
            "action_id",
            "actionId",
            "action",
        ),
        "message": ("message", "detail", "description"),
        "reason": ("reason", "failureReason"),
        "reward": ("reward",),
        "failed_action": ("failed_action", "failedAction"),
        "completed_stages": ("completed_stages", "completedStages"),
        "executed_units": ("executed_units", "executedUnits"),
        "timestamp": ("timestamp", "timeStamp"),
        "source": ("source",),
    }
    normalized = dict(source)
    for canonical, names in aliases.items():
        value = _first_debug_value(source, names)
        if value is not None:
            normalized[canonical] = value

    result_value = _first_debug_value(
        source,
        ("result", "result_status", "resultStatus", "outcome"),
        scalar_only=True,
    )
    if result_value is not None:
        normalized["result"] = result_value
    elif isinstance(normalized.get("result"), dict):
        normalized.pop("result", None)

    params = source.get("params")
    if not isinstance(params, dict):
        params = source.get("parameters")
    if isinstance(params, dict):
        normalized["params"] = params
    return normalized


def _first_debug_value(
    source: dict[str, Any],
    names: tuple[str, ...],
    *,
    scalar_only: bool = False,
) -> Any:
    for name in names:
        value = source.get(name)
        if value is None:
            continue
        if scalar_only and isinstance(value, (dict, list, tuple, set)):
            continue
        return value
    return None


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
        "current_stage": str(
            frame.get("current_stage")
            or frame.get("stage_label")
            or ""
        ),
        "current_action": frame["current_action"],
        "message": frame["message"],
        "timestamp": time.time(),
        "source": config.VIEWER_SOURCE,
    }


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
            "PERCEPT_",
            "ACCELERATION_SCALE",
            "AMPLITUDE_SCALE",
            "DURATION_SCALE",
        )
    )


def _fetch_progress_for_action(action: str, reported_progress: float) -> float:
    """Place external fetch ACT feedback on the four-leg UI route."""

    key = _behavior_key(action)
    progress = max(0.0, min(1.0, reported_progress))
    if "RELEASE" in key or "DROP" in key or "PRESENT" in key:
        return max(0.90, progress)
    if "RETURN_TO_OWNER" in key or (
        ("OWNER" in key or "USER" in key) and ("CARRY" in key or "TROT" in key)
    ):
        return max(0.50, min(0.89, progress))
    if "GRAB" in key:
        return max(0.36, min(0.49, progress))
    if "APPROACH_OBJECT" in key or "APPROACH_TOY" in key:
        return min(0.35, progress)
    if "PERCEPT" in key or "SCAN" in key or "LOCATE" in key:
        return 0.0
    return progress


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


def _is_own_debug_message(data: dict[str, Any]) -> bool:
    return data.get("source") == config.VIEWER_SOURCE


def _plan_follows_user(plan: BehaviorPlan | None) -> bool:
    return (
        plan is not None
        and _behavior_key(plan.behavior_name)
        in _VOICE_FOLLOW_BEHAVIORS
    )


def _plan_requires_bowl_food(plan: BehaviorPlan | None) -> bool:
    if plan is None:
        return False
    return _behavior_key(plan.behavior_name) in {
        "EAT_NORMALLY",
        "EAT_EXCITEDLY",
        "SEEK_FOOD",
        "SEEK_FOOD_URGENTLY",
    }


def _action_requires_food(action: Any) -> bool:
    key = str(action or "").upper()
    return key in {
        "ACT_LICK_FOOD",
        "ACT_LICK_AND_SWALLOW",
        "ACT_CHEW_OR_CARRY_FOOD",
        "ACT_SCRATCH_FOOD",
        "ACT_CARRY_BOWL_AND_FOLLOW_OWNER",
        "ACT_PAW_AT_BOWL_FOR_FOOD",
        "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
        "ACT_PAW_AT_BOWL_AND_WAIT_FOR_FOOD",
        "ACT_SNIFF_BOWL_RIM_AND_WAIT_FOR_FOOD",
        "ACT_WHINE_AND_WAIT_FOR_FOOD",
    }


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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _action_server_enabled() -> bool:
    # The production action executor owns /execute_behavior.  Starting a
    # second server from the viewer would race with it during integration, so
    # the optional local server is opt-in only.
    value = os.environ.get("MARSDOG_SIM2D_ACTION_SERVER", "0").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _object_xy(objects: dict[str, dict[str, Any]], name: str) -> tuple[float, float]:
    item = objects[name]
    return float(item["x"]), float(item["y"])


def _random_calm_idle_target(
    dog_x: float,
    dog_y: float,
    *,
    rng: Any = None,
) -> tuple[float, float]:
    """Choose a fresh walkable apartment location for calm idle play."""

    generator = rng or random
    minimum_distance = 110.0
    for _attempt in range(24):
        left, bottom, right, top = generator.choice(_CALM_IDLE_SAFE_AREAS)
        target = (
            generator.uniform(left, right),
            generator.uniform(bottom, top),
        )
        if math.hypot(target[0] - dog_x, target[1] - dog_y) >= minimum_distance:
            return target

    # A valid distant area always exists for the normal scene, but use the
    # farthest safe-area center as a deterministic fallback for custom poses.
    centers = [
        ((left + right) / 2.0, (bottom + top) / 2.0)
        for left, bottom, right, top in _CALM_IDLE_SAFE_AREAS
    ]
    return max(
        centers,
        key=lambda point: math.hypot(point[0] - dog_x, point[1] - dog_y),
    )


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
