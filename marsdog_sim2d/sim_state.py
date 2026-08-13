"""State owned and updated by the Arcade rendering thread."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import math
from queue import Empty, Queue
import re
import time
from typing import Any

from . import config
from .action_visuals import visual_for_action
from .behavior_contract import stage_position
from .voice_commands import behavior_runs_beside_owner


@dataclass(slots=True)
class SimEvent:
    """Normalized event passed from ROS callbacks to the Arcade thread."""

    kind: str
    topic: str
    payload: dict[str, Any]
    summary: str
    received_at: float = field(default_factory=time.time)
    format_hint: str | None = None


@dataclass(slots=True)
class TopicStats:
    """Runtime receive stats for one subscribed topic."""

    count: int = 0
    last_received_at: float | None = None
    last_summary: str = ""
    recent_received_at: deque[float] = field(default_factory=lambda: deque(maxlen=64))


@dataclass
class SimState:
    """Mutable page state. Keep this on the Arcade/main thread only."""

    dog_x: float = config.DEFAULT_DOG_X
    dog_y: float = config.DEFAULT_DOG_Y
    dog_heading: float = config.DEFAULT_DOG_HEADING
    dog_motion_start_x: float = config.DEFAULT_DOG_X
    dog_motion_start_y: float = config.DEFAULT_DOG_Y
    dog_motion_start_heading: float = config.DEFAULT_DOG_HEADING
    dog_motion_target_x: float = config.DEFAULT_DOG_X
    dog_motion_target_y: float = config.DEFAULT_DOG_Y
    dog_motion_target_heading: float = config.DEFAULT_DOG_HEADING
    dog_motion_elapsed: float = 0.0
    dog_motion_duration: float = 0.0
    dog_pose_last_received_at: float | None = None
    user_x: float = config.DEFAULT_USER_X
    user_y: float = config.DEFAULT_USER_Y
    room_objects: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            name: dict(item) for name, item in config.DEFAULT_ROOM_OBJECTS.items()
        }
    )

    active_target: dict[str, Any] | None = None
    latest_visual_event: dict[str, Any] | None = None
    latest_audio_event: dict[str, Any] | None = None
    simulation_time_state: dict[str, Any] | None = None
    simulation_time_received_at: float | None = None
    simulation_time_source: str | None = None
    ros_external_publishers: dict[str, list[dict[str, str]]] = field(
        default_factory=dict
    )
    ros_external_publisher_counts: dict[str, int] = field(default_factory=dict)
    ros_executor_online: bool = False
    ros_need_online: bool = False
    ros_emotion_online: bool = False
    ros_time_online: bool = False
    ros_graph_received_at: float | None = None

    emotion_state: dict[str, Any] | None = None
    emotion_signal_event: dict[str, Any] | None = None
    internal_need_state: dict[str, Any] | None = None
    internal_need_signal_event: dict[str, Any] | None = None
    personality_state: dict[str, Any] | None = None

    behavior_result_event: dict[str, Any] | None = None
    recent_behavior_results: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=config.MAX_BEHAVIOR_RESULTS)
    )

    active_behavior: str | None = None
    action_status: str = "waiting"
    action_goal_id: str | None = None
    action_behavior_id: str | None = None
    action_progress: float = 0.0
    action_visual_progress: float = 0.0
    action_visual_progress_start: float = 0.0
    action_current_action: str = "-"
    action_visual_action: str = "-"
    action_pending_visual_action: str | None = None
    action_unit_type: str = "-"
    action_message: str = "-"
    action_safe_to_interrupt: bool | None = None
    action_result: str = "-"
    action_reason: str = "-"
    action_reward: float | None = None
    action_priority_level: int | None = None
    action_params: dict[str, Any] = field(default_factory=dict)
    action_stage_index: int = 0
    action_stage_total: int = 0
    action_stage_label: str = "-"
    action_phase: str = "idle"
    action_target_label: str = "-"
    action_trigger_reason: str = "-"
    action_transition: str = "-"
    action_source: str = "-"
    action_intent: str = "-"
    action_level: str = "-"
    action_interaction_mode: str = "-"
    action_completed_stages: list[str] = field(default_factory=list)
    action_executed_units: list[str] = field(default_factory=list)
    action_started_at: float | None = None
    action_updated_at: float | None = None
    action_result_at: float | None = None
    action_server_available: bool = False
    action_server_message: str = "not initialized"
    recent_action_steps: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=8)
    )
    recent_action_events: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=12)
    )
    action_executions: dict[str, dict[str, Any]] = field(default_factory=dict)
    action_execution_sequence: int = 0
    action_active_sequence: int = 0
    manual_injection_count: int = 0
    last_manual_injection: dict[str, Any] | None = None
    event_injector_open: bool = False
    event_injector_group: str = "Audio"
    event_injector_fields: dict[str, str] = field(default_factory=dict)
    event_injector_focused_field: str | None = None
    audio_wake_angle: float | None = None

    # UI-only state. These fields never alter ROS topic names, message fields,
    # or the state values received from ROS2.
    ui_left_collapsed: bool = False
    ui_left_scroll: float = 0.0
    ui_input_tab: str = "Event"
    ui_open_select: str | None = None
    ui_payload_preview: str = ""
    ui_preview_topics: list[str] = field(default_factory=list)
    ui_selected_scenario: str = "high_hunger"
    ui_pending_placement: dict[str, Any] | None = None
    ui_selected_object: str | None = None
    ui_show_fov: bool = True
    ui_user_visible: bool = False
    ui_dragging_user: bool = False
    ui_follow_user_requested: bool = False
    ui_follow_user_active: bool = False
    ui_follow_goal_id: str | None = None
    ui_follow_stationary_since: float | None = None
    ui_follow_suppressed_goal_id: str | None = None
    ui_owner_approach_goal_id: str | None = None
    ui_owner_action_hold_until: float = 0.0
    ui_stopped_external_goal_ids: set[str] = field(default_factory=set)
    ui_abnormal_simulation_active: bool = False
    ui_abnormal_interrupted_goal_id: str | None = None
    ui_abnormal_paused_action: dict[str, Any] | None = None
    ui_abnormal_started_monotonic: float | None = None
    ui_abnormal_deferred_events: deque[SimEvent] = field(
        default_factory=lambda: deque(maxlen=64)
    )
    ui_abnormal_replay_active: bool = False
    ui_abnormal_replay_goal_id: str | None = None
    ui_abnormal_replay_next_at: float = 0.0
    ui_bowl_has_food: bool = False
    ui_food_waiting: bool = False
    ui_food_wait_goal_id: str | None = None
    ui_food_wait_resume_action: str | None = None
    ui_food_eating_until: float = 0.0
    ui_food_eating_authorized: bool = False
    ui_collapsed_cards: set[str] = field(default_factory=set)
    ui_right_scroll: float = 0.0
    ui_log_filters: set[str] = field(
        default_factory=lambda: {"VIS", "AUD", "NEED", "EMO", "BEH", "EXEC", "RESULT", "SYS"}
    )
    ui_log_search: str = ""
    ui_log_paused: bool = False
    ui_log_pause_snapshot: list[dict[str, Any]] = field(default_factory=list)
    ui_log_auto_scroll: bool = True
    ui_log_scroll: int = 0
    ui_selected_event_id: int | None = None
    ui_behavior_context_expanded: bool = False
    ui_pending_confirmation: dict[str, Any] | None = None
    ui_log_height: float | None = None
    ui_dragging_log: bool = False
    ui_text_focus: str | None = None

    event_log: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=config.MAX_EVENT_LOG)
    )
    event_records: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=config.MAX_STRUCTURED_EVENTS)
    )
    processed_events: int = 0
    queue_depth: int = 0
    started_at: float = field(default_factory=time.time)
    topic_stats: dict[str, TopicStats] = field(
        default_factory=lambda: {
            topic: TopicStats()
            for topic in (
                *config.TOPICS.values(),
                config.ACTION_NAME,
                config.ACTION_GOAL_TOPIC,
                config.ACTION_FEEDBACK_TOPIC,
                config.ACTION_RESULT_TOPIC,
            )
        }
    )

    def drain_queue(self, event_queue: Queue[SimEvent]) -> int:
        """Apply queued ROS events on the Arcade thread."""

        drained = 0
        while drained < config.QUEUE_DRAIN_LIMIT:
            try:
                event = event_queue.get_nowait()
            except Empty:
                break
            self.apply_event(event)
            drained += 1
        self.queue_depth = _queue_size(event_queue)
        return drained

    def advance_virtual_motion(self, delta_time: float) -> None:
        """Interpolate the rendered dog pose between sparse ROS feedback frames."""

        if self.dog_motion_duration <= 0.0:
            self._finish_pending_visual_action()
            return

        self.dog_motion_elapsed = min(
            self.dog_motion_duration,
            self.dog_motion_elapsed + max(0.0, float(delta_time)),
        )
        progress = self.dog_motion_elapsed / self.dog_motion_duration
        self.dog_x = _lerp(self.dog_motion_start_x, self.dog_motion_target_x, progress)
        self.dog_y = _lerp(self.dog_motion_start_y, self.dog_motion_target_y, progress)
        self.dog_heading = _lerp_angle(
            self.dog_motion_start_heading,
            self.dog_motion_target_heading,
            progress,
        )

        # Keep compound actions in their approach pose while the dog is still
        # travelling.  The interaction image is released at the destination.
        if self.action_visual_progress < self.action_progress:
            interpolated = _lerp(
                self.action_visual_progress_start,
                self.action_progress,
                progress,
            )
            self.action_visual_progress = min(interpolated, 0.679)

        if progress >= 1.0:
            self.dog_motion_duration = 0.0
            self.dog_motion_elapsed = 0.0
            self.action_visual_progress = self.action_progress
            completed_owner_approach = (
                bool(self.ui_owner_approach_goal_id)
                and self.ui_owner_approach_goal_id
                == self.action_goal_id
            )
            self._finish_pending_visual_action()
            if completed_owner_approach:
                self.ui_owner_approach_goal_id = None
                self.ui_owner_action_hold_until = max(
                    self.ui_owner_action_hold_until,
                    time.monotonic() + config.OWNER_ACTION_HOLD_SEC,
                )

    def virtual_motion_active(self) -> bool:
        return self.dog_motion_duration > 0.0

    def apply_event(self, event: SimEvent) -> None:
        abnormal_replay = bool(
            event.payload.get("_ui_abnormal_replay")
        )
        if not abnormal_replay:
            self.processed_events += 1
            plain_time_tick = (
                event.kind == "simulation_time_state"
                and event.payload.get("event_type") == "TIME_TICK"
            )
            if not plain_time_tick and event.kind != "ros_graph_state":
                self.event_log.append((event.received_at, event.summary))
                self._record_ui_event(event)
            local_ui_action = (
                event.kind in {"action_goal", "action_feedback", "action_result"}
                and str(event.payload.get("goal_id") or "").startswith("local-")
            )
            if not local_ui_action and event.kind != "ros_graph_state":
                topic_stats = self.topic_stats.setdefault(
                    event.topic,
                    TopicStats(),
                )
                topic_stats.count += 1
                topic_stats.last_received_at = event.received_at
                topic_stats.last_summary = event.summary
                topic_stats.recent_received_at.append(event.received_at)

        action_event_kinds = {"action_goal", "action_feedback", "action_result"}
        abnormal_deferred_kinds = {
            *action_event_kinds,
            "behavior_result_event",
        }
        if (
            self.ui_abnormal_simulation_active
            and not abnormal_replay
            and event.kind in abnormal_deferred_kinds
        ):
            # Abnormal mode owns the visible card, but the action system may
            # keep publishing. Preserve those packets so clearing the
            # simulation can continue from the paused presentation.
            self.ui_abnormal_deferred_events.append(event)
            return
        if (
            self.ui_abnormal_replay_active
            and not abnormal_replay
            and event.kind in abnormal_deferred_kinds
        ):
            incoming_goal = _first_text(event.payload.get("goal_id"))
            if (
                event.kind == "behavior_result_event"
                or incoming_goal is None
                or incoming_goal == self.ui_abnormal_replay_goal_id
            ):
                self.ui_abnormal_deferred_events.append(event)
                return
            # A genuinely new Goal preempts the paused one. Do not let an old
            # replay later overwrite this higher-priority execution.
            self.ui_abnormal_deferred_events.clear()
            self.ui_abnormal_replay_active = False
            self.ui_abnormal_replay_goal_id = None
            self.ui_abnormal_replay_next_at = 0.0

        if event.kind in action_event_kinds:
            incoming_goal = _first_text(event.payload.get("goal_id"))
            if (
                incoming_goal
                and incoming_goal in self.ui_stopped_external_goal_ids
            ):
                # Stop is authoritative for the UI presentation. The behavior
                # tree still receives CMD_STOP and owns the real Action cancel,
                # but late packets from the interrupted command must not make
                # its old movement or pose reappear.
                return
            if (
                event.kind == "action_feedback"
                and incoming_goal
                and incoming_goal == self.ui_follow_suppressed_goal_id
            ):
                # A UI follow timeout is authoritative for presentation even
                # if the external executor has not canceled its Goal yet.
                return
            interrupted_goal = self.ui_abnormal_interrupted_goal_id
            if interrupted_goal and (
                incoming_goal == interrupted_goal
                or (
                    incoming_goal is None
                    and event.kind in {"action_feedback", "action_result"}
                )
            ):
                # The action that was visible when abnormal mode began must
                # not spring back into view after the simulation is cleared.
                if event.kind == "action_result":
                    self.ui_abnormal_interrupted_goal_id = None
                return
            if (
                event.kind == "action_goal"
                and incoming_goal
                and interrupted_goal
                and incoming_goal != interrupted_goal
            ):
                self.ui_abnormal_interrupted_goal_id = None

            food_goal = self.ui_food_wait_goal_id
            if (
                event.kind == "action_goal"
                and incoming_goal
                and food_goal
                and incoming_goal != food_goal
            ):
                # A new goal is allowed to preempt food waiting/eating.
                self.clear_food_gate()
            elif (
                event.kind in {"action_feedback", "action_result"}
                and food_goal
                and (incoming_goal is None or incoming_goal == food_goal)
                and (
                    self.ui_food_waiting
                    or self.ui_food_eating_until > time.monotonic()
                )
            ):
                # Keep stale executor feedback from bypassing the empty-bowl
                # wait or ending the short resumed-eating presentation.
                return

        if event.kind == "simulation_time_state":
            self.simulation_time_state = event.payload
            self.simulation_time_received_at = event.received_at
            self.simulation_time_source = event.topic
            return

        if event.kind == "ros_graph_state":
            publishers = event.payload.get("external_publishers")
            counts = event.payload.get("publisher_counts")
            self.ros_external_publishers = (
                publishers if isinstance(publishers, dict) else {}
            )
            self.ros_external_publisher_counts = (
                {
                    str(topic): int(count)
                    for topic, count in counts.items()
                    if isinstance(count, (int, float))
                }
                if isinstance(counts, dict)
                else {}
            )
            self.ros_executor_online = bool(
                event.payload.get("executor_online")
            )
            self.ros_need_online = bool(event.payload.get("need_online"))
            self.ros_emotion_online = bool(
                event.payload.get("emotion_online")
            )
            self.ros_time_online = bool(event.payload.get("time_online"))
            self.ros_graph_received_at = event.received_at
            return

        if event.kind == "feeding_authorized":
            if not self.ui_bowl_has_food:
                return
            self.ui_food_eating_authorized = True
            if not self.ui_food_wait_goal_id:
                self.ui_food_wait_goal_id = self.action_goal_id
            if self.ui_food_waiting:
                self.release_food_wait()
            else:
                self.action_message = "Eating authorized by UI feeding service"
                self.action_phase = "eating_authorized"
            return

        if event.kind == "visual_event":
            self.latest_visual_event = {
                **event.payload,
                "received_at": event.received_at,
            }
            active_target = event.payload.get("active_target")
            if isinstance(active_target, dict):
                self.active_target = active_target
            return

        if event.kind == "audio_event":
            self.latest_audio_event = {
                **event.payload,
                "received_at": event.received_at,
            }
            self.audio_wake_angle = None
            if (
                event.payload.get("event_type") == "EVT_VOICE_CALL_NAME"
                and event.payload.get("wake_angle") is not None
            ):
                self.audio_wake_angle = _to_float(event.payload.get("wake_angle"))
            return

        if event.kind == "manual_injection":
            self.manual_injection_count += 1
            self.last_manual_injection = {
                **event.payload,
                "received_at": event.received_at,
            }
            return

        if event.kind == "internal_need_state":
            self.internal_need_state = _merge_named_state_payload(
                self.internal_need_state,
                event.payload,
                "demands",
            )
            self._adopt_embedded_virtual_time(event)
            return

        if event.kind == "internal_need_signal_event":
            self.internal_need_signal_event = {
                **event.payload,
                "received_at": event.received_at,
            }
            self.internal_need_state = _merge_need_signal_into_state(
                self.internal_need_state,
                event.payload,
            )
            self._adopt_embedded_virtual_time(event)
            return

        if event.kind == "emotion_state":
            self.emotion_state = _merge_named_state_payload(
                self.emotion_state,
                event.payload,
                "emotions",
            )
            self._adopt_embedded_virtual_time(event)
            return

        if event.kind == "emotion_signal_event":
            self.emotion_signal_event = {
                **event.payload,
                "received_at": event.received_at,
            }
            self._adopt_embedded_virtual_time(event)
            return

        if event.kind == "personality_state":
            self.personality_state = event.payload
            return

        if event.kind == "behavior_result_event":
            self.behavior_result_event = event.payload
            self.recent_behavior_results.appendleft(event.payload)
            if (
                self.ui_food_waiting
                or self.ui_food_eating_until > time.monotonic()
            ):
                # The action system/behavior tree may consider the original
                # food goal complete even though the UI bowl was empty. Keep
                # the result in diagnostics, but do not let it release the
                # dog from its bowl-side wait or resumed eating presentation.
                self.action_status = "running"
                self.action_result_at = None
                self._append_action_event(
                    event,
                    "food_wait",
                    "empty bowl; continue waiting for food",
                )
                return
            behavior_name = event.payload.get("behavior_name")
            action_type = event.payload.get("action_type")
            self.active_behavior = _first_text(behavior_name, action_type)
            self.action_status = _derive_action_status(event.payload)
            self.action_trigger_reason = _behavior_result_reason(event.payload)
            self._append_action_event(event, "behavior_result", self.action_trigger_reason)

        if event.kind == "action_server_state":
            self.action_server_available = bool(event.payload.get("available"))
            self.action_server_message = str(event.payload.get("message") or "-")
            return

        if event.kind == "action_goal":
            previous_goal = self.action_goal_id
            previous_behavior = self.active_behavior
            incoming_goal = _first_text(event.payload.get("goal_id"))
            if incoming_goal:
                if incoming_goal not in self.action_executions:
                    self.action_execution_sequence += 1
                self.action_executions[incoming_goal] = {
                    **event.payload,
                    "status": "pending",
                    "received_at": event.received_at,
                    "sequence": self.action_executions.get(
                        incoming_goal,
                        {},
                    ).get(
                        "sequence",
                        self.action_execution_sequence,
                    ),
                }
            if (
                incoming_goal
                and previous_goal
                and incoming_goal != previous_goal
                and self.action_status in {"pending", "running"}
            ):
                # Keep the active execution card stable.  The new Goal remains
                # pending in the per-goal map until its first Feedback proves
                # that the executor has switched to it.
                self._append_action_event(
                    event,
                    "queued",
                    f"{event.payload.get('behavior_name') or '-'} pending",
                )
                return
            if self.action_status == "running" and previous_goal and previous_goal != _first_text(event.payload.get("goal_id")):
                self.action_transition = f"preempt {previous_behavior or '-'}"
                self._append_action_event(event, "preempt", self.action_transition)
            else:
                self.action_transition = "started"
            self.action_goal_id = _first_text(event.payload.get("goal_id"))
            if self.action_goal_id:
                self.action_active_sequence = _to_int(
                    self.action_executions.get(
                        self.action_goal_id,
                        {},
                    ).get("sequence")
                ) or self.action_active_sequence
            self.action_behavior_id = _first_text(event.payload.get("behavior_id"))
            self.active_behavior = _first_text(event.payload.get("behavior_name"))
            self.action_status = str(
                event.payload.get("status") or "pending"
            ).lower()
            self.action_progress = 0.0
            self.action_visual_progress = 0.0
            self.action_visual_progress_start = 0.0
            self.action_current_action = _first_text(event.payload.get("current_action")) or "-"
            self.action_unit_type = _infer_unit_type(self.action_current_action)
            if self.action_unit_type not in {"policy", "modifier"}:
                self.action_visual_action = self.action_current_action
            else:
                self.action_visual_action = "-"
            self.action_pending_visual_action = None
            self.action_message = "goal accepted; waiting for Stage feedback"
            self.action_result = "-"
            self.action_reason = "-"
            self.action_reward = None
            self.action_priority_level = _to_int(event.payload.get("priority_level"))
            self.action_params = _dict(event.payload.get("params"))
            if not self.action_params:
                self.action_params = _json_dict(event.payload.get("params_json"))
            self._apply_action_context()
            self.action_completed_stages = []
            self.action_executed_units = []
            self.action_started_at = event.received_at
            self.action_updated_at = event.received_at
            self.action_result_at = None
            self.action_phase = "pending"
            self.action_target_label = _infer_target_label(self.active_behavior, self.action_current_action)
            self.action_trigger_reason = _infer_trigger_reason(self, event.payload)
            self.action_stage_index, self.action_stage_total, self.action_stage_label = _extract_stage(
                event.payload,
                self.action_progress,
                self.action_current_action,
                self.active_behavior,
            )
            self.recent_action_steps.clear()
            if self.action_current_action != "-":
                self.recent_action_steps.append((event.received_at, self.action_current_action))
            self._append_action_event(event, "goal", f"{self.active_behavior or '-'} <- {self.action_trigger_reason}")
            return

        if event.kind == "action_feedback":
            incoming_goal = _first_text(event.payload.get("goal_id"))
            execution: dict[str, Any] | None = None
            if incoming_goal:
                execution = self.action_executions.get(incoming_goal)
                if execution is None:
                    # Goal debug packets are volatile and may be emitted before
                    # the UI starts. A live Feedback packet is authoritative
                    # enough to reconstruct that execution and preempt a local
                    # autonomous preview.
                    if (
                        self.action_goal_id
                        and incoming_goal != self.action_goal_id
                        and not str(self.action_goal_id).startswith("local-")
                    ):
                        return
                    self.action_execution_sequence += 1
                    execution = {
                        "sequence": self.action_execution_sequence,
                    }
                    self.action_executions[incoming_goal] = execution
                execution.update(event.payload)
                execution["status"] = "running"
                execution["received_at"] = event.received_at
            if (
                incoming_goal
                and self.action_goal_id
                and incoming_goal != self.action_goal_id
            ):
                incoming_sequence = _to_int(
                    (execution or {}).get("sequence")
                ) or 0
                if incoming_sequence <= self.action_active_sequence:
                    return
                pending_goal = execution or {}
                self.action_goal_id = incoming_goal
                self.action_active_sequence = incoming_sequence
                self.action_behavior_id = _first_text(
                    pending_goal.get("behavior_id")
                )
                self.active_behavior = _first_text(
                    pending_goal.get("behavior_name")
                )
                self.action_priority_level = _to_int(
                    pending_goal.get("priority_level")
                )
                self.action_params = _dict(pending_goal.get("params"))
                if not self.action_params:
                    self.action_params = _json_dict(
                        pending_goal.get("params_json")
                    )
                self._apply_action_context()
                self.action_started_at = _to_float(
                    pending_goal.get("received_at")
                ) or event.received_at
                self.action_transition = "activated by feedback"
                self.action_result = "-"
                self.action_reason = "-"
            motion_queued = self._apply_virtual_motion(event.payload, event.received_at)
            self.action_goal_id = _first_text(event.payload.get("goal_id"), self.action_goal_id)
            if incoming_goal and not self.action_active_sequence:
                self.action_active_sequence = _to_int(
                    (execution or {}).get("sequence")
                ) or 0
            self.action_behavior_id = _first_text(
                event.payload.get("behavior_id"), self.action_behavior_id
            )
            self.active_behavior = _first_text(
                event.payload.get("behavior_name"), self.active_behavior
            )
            self.action_status = str(event.payload.get("status") or "running").lower()
            self.action_progress = _normalized_progress(event.payload.get("progress"))
            current_action = _first_text(
                event.payload.get("current_action"), self.action_current_action
            ) or "-"
            if current_action != "-" and current_action != self.action_current_action:
                self.recent_action_steps.append((event.received_at, current_action))
                self._append_action_event(event, "stage", current_action)
            self.action_current_action = current_action
            self.action_unit_type = _infer_unit_type(current_action)
            self._update_visual_action(current_action, motion_queued)
            if not motion_queued:
                self.action_visual_progress = self.action_progress
            self.action_message = _first_text(event.payload.get("message")) or "-"
            safe_to_interrupt = event.payload.get("safe_to_interrupt")
            self.action_safe_to_interrupt = (
                _to_bool(safe_to_interrupt) if safe_to_interrupt is not None else None
            )
            self.action_updated_at = event.received_at
            self.action_stage_index, self.action_stage_total, self.action_stage_label = _extract_stage(
                event.payload,
                self.action_progress,
                self.action_current_action,
                self.active_behavior,
            )
            self.action_phase = (
                _first_text(event.payload.get("phase"))
                or "stage_completed"
            )
            self.action_target_label = (
                _first_text(event.payload.get("target_label"))
                or _infer_target_label(self.active_behavior, self.action_current_action)
            )
            if not self.action_trigger_reason or self.action_trigger_reason == "-":
                self.action_trigger_reason = _infer_trigger_reason(self, event.payload)
            self.gate_food_action(current_action, motion_queued=motion_queued)
            return

        if event.kind == "action_result":
            incoming_goal = _first_text(event.payload.get("goal_id"))
            if (
                incoming_goal
                and self.action_goal_id
                and incoming_goal != self.action_goal_id
            ):
                self.action_executions.pop(incoming_goal, None)
                return
            motion_queued = self._apply_virtual_motion(event.payload, event.received_at)
            self.action_goal_id = _first_text(event.payload.get("goal_id"), self.action_goal_id)
            self.action_behavior_id = _first_text(
                event.payload.get("behavior_id"), self.action_behavior_id
            )
            self.active_behavior = _first_text(
                event.payload.get("behavior_name"), self.active_behavior
            )
            result_action = _first_text(
                event.payload.get("failed_action"),
                event.payload.get("current_action"),
                self.action_current_action,
            ) or "-"
            self.action_current_action = result_action
            self.action_unit_type = _infer_unit_type(result_action)
            self._update_visual_action(result_action, motion_queued)
            status = str(event.payload.get("status") or "").upper()
            result = str(event.payload.get("result") or status or "").lower()
            self.action_status = _result_status(status, result)
            self.action_result = result or "-"
            self.action_reason = _first_text(event.payload.get("reason")) or "-"
            self.action_reward = _to_float(event.payload.get("reward"))
            self.action_progress = 1.0 if self.action_status == "success" else self.action_progress
            if not motion_queued:
                self.action_visual_progress = self.action_progress
            self.action_result_at = event.received_at
            self.action_updated_at = event.received_at
            self.action_phase = _result_phase(status, result)
            self.action_transition = _result_transition(status, result)
            self.action_completed_stages = _string_list(event.payload.get("completed_stages"))
            self.action_executed_units = _string_list(event.payload.get("executed_units"))
            if self.action_status == "success" and self.action_stage_total:
                self.action_stage_index = self.action_stage_total
            self.action_stage_label = self.action_result or self.action_phase
            self._append_action_event(event, self.action_phase, self.action_reason)
            for room_object in self.room_objects.values():
                room_object["active"] = False
            self.gate_food_action(result_action, motion_queued=motion_queued)
            if (
                not self.ui_food_waiting
                and self.ui_food_eating_until <= 0.0
                and self.ui_food_wait_goal_id
                and self.ui_food_wait_goal_id
                == _first_text(event.payload.get("goal_id"), self.action_goal_id)
            ):
                self.clear_food_gate()
            if incoming_goal:
                self.action_executions.pop(incoming_goal, None)
            return

    def _adopt_embedded_virtual_time(self, event: SimEvent) -> None:
        """Use the shared timeContext only while the authority Topic is absent."""

        context = event.payload.get("timeContext")
        if not isinstance(context, dict) or not context.get("virtualDateTime"):
            return
        direct_time_is_fresh = (
            self.simulation_time_source
            == config.TOPICS["simulation_time_state"]
            and self.simulation_time_received_at is not None
            and event.received_at - self.simulation_time_received_at <= 2.5
        )
        if direct_time_is_fresh:
            return
        self.simulation_time_state = {
            "event_type": event.payload.get("event_type") or "EMBEDDED_TIME_CONTEXT",
            "tickSequence": None,
            "timeContext": dict(context),
            "raw": event.payload.get("raw"),
        }
        self.simulation_time_received_at = event.received_at
        self.simulation_time_source = event.topic

    def gate_food_action(
        self,
        action: str,
        *,
        motion_queued: bool = False,
    ) -> None:
        """Hold food interaction at the bowl until UI food is available."""

        local_food_goal = str(self.action_goal_id or "").startswith("local-")
        if self.ui_bowl_has_food and (
            self.ui_food_eating_authorized or local_food_goal
        ):
            if local_food_goal:
                self.ui_food_eating_authorized = True
            return
        normalized = str(action or "").upper().replace("-", "_")
        waiting_action = normalized in {
            "ACT_CARRY_BOWL_AND_FOLLOW_OWNER",
            "ACT_PAW_AT_BOWL_FOR_FOOD",
            "ACT_PAW_AT_BOWL_AND_WAIT_FOR_FOOD",
            "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD",
            "ACT_SNIFF_BOWL_RIM_AND_WAIT_FOR_FOOD",
            "ACT_WHINE_AND_WAIT_FOR_FOOD",
        }
        food_dependent_action = _is_food_dependent_action(normalized)
        if not waiting_action and not food_dependent_action:
            return
        if waiting_action and self.ui_bowl_has_food:
            # Seeking/waiting units are not eating units.  A pre-filled bowl
            # lets the behavior tree advance; the confirmation service is
            # required only before a food-dependent eating unit starts.
            return

        if food_dependent_action:
            self.ui_food_wait_resume_action = normalized
        self.ui_food_wait_goal_id = self.action_goal_id
        self.ui_food_waiting = True
        self.ui_food_eating_until = 0.0
        self.ui_food_eating_authorized = False
        self.action_status = "running"
        waiting_visual_action = (
            normalized
            if waiting_action
            else "ACT_SNIFF_BOWL_AND_WAIT_FOR_FOOD"
        )
        self.action_unit_type = _infer_unit_type(self.action_current_action)
        if motion_queued or self.virtual_motion_active():
            self.action_pending_visual_action = waiting_visual_action
        else:
            self.action_visual_action = waiting_visual_action
            self.action_pending_visual_action = None
        if self.ui_bowl_has_food:
            self.action_message = (
                "Food detected; waiting for action-system eating authorization"
            )
            self.action_reason = "Waiting for eating authorization"
            self.action_phase = "waiting_eating_authorization"
            self.action_stage_label = "发现狗粮，等待动作系统确认进食"
        else:
            self.action_message = "Food bowl is empty; sniffing and waiting"
            self.action_reason = "Waiting for food"
            self.action_phase = "waiting_for_food"
            self.action_stage_label = "嗅闻食盆，等待放粮"
        self.action_safe_to_interrupt = True
        self.action_result = "-"
        self.action_result_at = None
        bowl = self.room_objects.get("bowl")
        if isinstance(bowl, dict):
            bowl["active"] = True

    def release_food_wait(self, *, eating_display_sec: float = 0.0) -> None:
        """Switch a waiting food action back to eating after food is added."""

        if not self.ui_food_waiting:
            return
        resume_action = (
            self.ui_food_wait_resume_action
            or self.action_current_action
            or "ACT_LICK_FOOD"
        )
        self.ui_food_waiting = False
        self.action_status = "running"
        self.action_current_action = resume_action
        if self.virtual_motion_active():
            self.action_pending_visual_action = resume_action
        else:
            self.action_visual_action = resume_action
            self.action_pending_visual_action = None
        self.action_unit_type = _infer_unit_type(resume_action)
        resuming_consumption = _is_food_dependent_action(resume_action)
        self.action_message = (
            "Food detected; continue eating"
            if resuming_consumption
            else "Food detected; continue food-seeking Stage"
        )
        self.action_safe_to_interrupt = True
        self.action_result = "-"
        self.action_reason = "-"
        self.action_phase = "interacting"
        self.action_stage_label = (
            "发现狗粮，开始进食"
            if resuming_consumption
            else "发现狗粮，继续当前觅食动作"
        )
        self.action_result_at = None
        self.ui_food_eating_until = (
            time.monotonic() + max(0.0, float(eating_display_sec))
            if eating_display_sec > 0.0
            else 0.0
        )

    def finish_food_eating_display(self) -> None:
        """Complete an external food action after its resumed UI animation."""

        if self.ui_food_eating_until <= 0.0:
            return
        now = time.time()
        self.active_behavior = None
        self.action_status = "success"
        self.action_progress = 1.0
        self.action_visual_progress = 1.0
        self.action_current_action = "-"
        self.action_visual_action = "-"
        self.action_pending_visual_action = None
        self.action_unit_type = "-"
        self.action_message = "Eating completed"
        self.action_safe_to_interrupt = None
        self.action_result = "completed"
        self.action_reason = "Food supplied from UI"
        self.action_phase = "completed"
        self.action_transition = "completed"
        self.action_stage_label = "completed"
        self.action_result_at = now
        self.action_updated_at = now
        bowl = self.room_objects.get("bowl")
        if isinstance(bowl, dict):
            bowl["active"] = False
        self.clear_food_gate()

    def clear_food_gate(self) -> None:
        self.ui_food_waiting = False
        self.ui_food_wait_goal_id = None
        self.ui_food_wait_resume_action = None
        self.ui_food_eating_until = 0.0
        self.ui_food_eating_authorized = False

    def _apply_action_context(self) -> None:
        self.action_source = _first_text(self.action_params.get("source")) or "-"
        self.action_intent = _first_text(self.action_params.get("intent")) or "-"
        self.action_level = _first_text(
            self.action_params.get("level"), self.action_params.get("variant")
        ) or "-"
        mode = _first_text(self.action_params.get("interaction_mode"))
        if mode is None and self.action_params.get("interactive") is not None:
            mode = "interactive" if _to_bool(self.action_params.get("interactive")) else "solo"
        self.action_interaction_mode = mode or "-"

    def _apply_virtual_motion(
        self,
        payload: dict[str, Any],
        received_at: float | None = None,
    ) -> bool:
        # A result or policy feedback may omit dog_pose while interpolation
        # from the preceding feedback is still in progress.
        motion_queued = self.virtual_motion_active()
        dog_pose = payload.get("dog_pose")
        follow_text = " ".join(
            (
                str(payload.get("behavior_name") or self.active_behavior or ""),
                str(payload.get("current_action") or self.action_current_action or ""),
            )
        ).upper()
        goal_id = str(payload.get("goal_id") or self.action_goal_id or "")
        bound_follow_goal = (
            bool(self.ui_follow_goal_id)
            and goal_id == self.ui_follow_goal_id
        )
        if (
            self.ui_follow_user_active
            and not goal_id.startswith("local-")
            and (
                bound_follow_goal
                or "FOLLOW" in follow_text
                or "MATCH_OWNER" in follow_text
            )
        ):
            # External executors only know the owner position captured when the
            # goal started. The Arcade thread owns the draggable UI person's
            # live pose, so its per-frame follow controller must own dog_pose.
            dog_pose = None
        behavior_name = str(
            payload.get("behavior_name")
            or self.active_behavior
            or ""
        )
        owner_side_behavior = (
            self.ui_user_visible
            and behavior_runs_beside_owner(behavior_name)
        )
        if (
            self.ui_owner_approach_goal_id
            and goal_id
            and goal_id != self.ui_owner_approach_goal_id
        ):
            self.ui_owner_approach_goal_id = None
        external_owner_approach = False
        owner_distance = math.hypot(
            self.user_x - self.dog_x,
            self.user_y - self.dog_y,
        )
        if owner_side_behavior and not goal_id.startswith("local-"):
            if owner_distance <= config.OWNER_NEAR_DISTANCE:
                dog_pose = {
                    "x": self.dog_x,
                    "y": self.dog_y,
                    "heading": self.dog_heading,
                }
            else:
                external_owner_approach = True
                target_x = self.user_x - 104.0
                target_y = self.user_y - 6.0
                dog_pose = {
                    "x": target_x,
                    "y": target_y,
                    "heading": math.degrees(
                        math.atan2(
                            self.user_y - target_y,
                            self.user_x - target_x,
                        )
                    )
                    % 360.0,
                }
        if isinstance(dog_pose, dict):
            target_x = _float_or_default(dog_pose.get("x"), self.dog_x)
            target_y = _float_or_default(dog_pose.get("y"), self.dog_y)
            target_heading = _float_or_default(
                dog_pose.get("heading"),
                self.dog_heading,
            )
            distance = math.hypot(target_x - self.dog_x, target_y - self.dog_y)
            heading_delta = abs(_angle_delta(self.dog_heading, target_heading))
            motion_queued = (
                distance > config.MOTION_POSITION_EPSILON
                or heading_delta > config.MOTION_HEADING_EPSILON
            )

            if motion_queued:
                self.action_visual_progress_start = self.action_visual_progress
                sample_period = config.MOTION_DEFAULT_SMOOTH_SEC
                if (
                    received_at is not None
                    and self.dog_pose_last_received_at is not None
                ):
                    sample_period = max(
                        config.MOTION_MIN_SMOOTH_SEC,
                        received_at - self.dog_pose_last_received_at,
                    )
                self.dog_motion_start_x = self.dog_x
                self.dog_motion_start_y = self.dog_y
                self.dog_motion_start_heading = self.dog_heading
                self.dog_motion_target_x = target_x
                self.dog_motion_target_y = target_y
                self.dog_motion_target_heading = target_heading
                self.dog_motion_elapsed = 0.0
                self.dog_motion_duration = (
                    max(
                        config.MOTION_MIN_SMOOTH_SEC,
                        distance / config.OWNER_APPROACH_SPEED,
                    )
                    if external_owner_approach
                    else min(
                        config.MOTION_MAX_SMOOTH_SEC,
                        max(
                            config.MOTION_MIN_SMOOTH_SEC,
                            sample_period
                            * config.MOTION_FEEDBACK_PERIOD_SCALE,
                        ),
                    )
                )
            else:
                self.dog_x = target_x
                self.dog_y = target_y
                self.dog_heading = target_heading
                self.dog_motion_target_x = target_x
                self.dog_motion_target_y = target_y
                self.dog_motion_target_heading = target_heading
                self.dog_motion_duration = 0.0
                self.dog_motion_elapsed = 0.0

            if received_at is not None:
                self.dog_pose_last_received_at = received_at
        if (
            owner_side_behavior
            and owner_distance > config.OWNER_NEAR_DISTANCE
            and goal_id
        ):
            self.ui_owner_approach_goal_id = goal_id

        objects = payload.get("objects")
        if isinstance(objects, dict):
            self.room_objects = {
                str(name): dict(value)
                for name, value in objects.items()
                if isinstance(value, dict)
            }
        return motion_queued

    def _update_visual_action(self, current_action: str, motion_queued: bool) -> None:
        unit_type = _infer_unit_type(current_action)
        if not current_action or current_action == "-" or unit_type in {"policy", "modifier"}:
            return

        exact_visual = visual_for_action(current_action)
        should_wait_for_arrival = (
            exact_visual is not None
            and (
                exact_visual.defer_pose_until_arrival
                or not exact_visual.moves
            )
        )
        motion_in_progress = motion_queued or self.virtual_motion_active()
        if motion_in_progress and (
            should_wait_for_arrival
            or (
                exact_visual is None
                and not _is_locomotion_action(current_action)
            )
        ):
            self.action_pending_visual_action = current_action
            return

        self.action_visual_action = current_action
        self.action_pending_visual_action = None

    def _finish_pending_visual_action(self) -> None:
        if self.action_pending_visual_action is None:
            return
        distance = math.hypot(
            self.dog_motion_target_x - self.dog_x,
            self.dog_motion_target_y - self.dog_y,
        )
        if distance > config.MOTION_VISUAL_SWITCH_DISTANCE:
            return
        self.action_visual_action = self.action_pending_visual_action
        self.action_pending_visual_action = None
        if behavior_runs_beside_owner(self.active_behavior):
            self.ui_owner_approach_goal_id = None
            self.ui_owner_action_hold_until = max(
                self.ui_owner_action_hold_until,
                time.monotonic() + config.OWNER_ACTION_HOLD_SEC,
            )

    def _append_action_event(self, event: SimEvent, kind: str, label: str) -> None:
        self.recent_action_events.appendleft(
            {
                "at": event.received_at,
                "kind": kind,
                "label": label or "-",
                "goal_id": self.action_goal_id or event.payload.get("goal_id"),
                "behavior": self.active_behavior or event.payload.get("behavior_name"),
            }
        )

    def _record_ui_event(self, event: SimEvent) -> None:
        """Maintain a compact presentation cache for the structured event table."""

        source = _ui_event_source(event)
        level = _ui_event_level(event)
        collapse_key = f"{source}|{event.kind}|{event.summary}"
        if self.event_records:
            previous = self.event_records[-1]
            if previous.get("collapse_key") == collapse_key:
                previous["count"] = int(previous.get("count") or 1) + 1
                previous["at"] = event.received_at
                previous["payload"] = event.payload.get("raw", event.payload)
                return

        self.event_records.append(
            {
                "id": self.processed_events,
                "at": event.received_at,
                "first_at": event.received_at,
                "source": source,
                "event": event.kind,
                "level": level,
                "summary": event.summary,
                "topic": event.topic,
                "payload": event.payload.get("raw", event.payload),
                "count": 1,
                "collapse_key": collapse_key,
            }
        )


def _derive_action_status(payload: dict[str, Any]) -> str:
    result_type = _upper_or_none(payload.get("result_type"))
    status = _upper_or_none(payload.get("status"))
    result = _upper_or_none(payload.get("result"))

    if result_type == "STARTED":
        return "running"
    if result_type in {"COMPLETED"} or status == "SUCCESS" or result == "COMPLETED":
        return "success"
    if result_type == "TIMEOUT" or status == "TIMEOUT":
        return "timeout"
    if result_type == "INTERRUPTED":
        return "interrupted"
    if result_type in {"CANCELLED", "CANCELED"} or status in {"CANCELED", "CANCELLED"}:
        return "canceled"
    if result_type == "FAILED" or status == "FAILURE":
        return "failed"
    return "waiting"


def _upper_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).upper()


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_or_default(value: Any, default: float) -> float:
    parsed = _to_float(value)
    return default if parsed is None else parsed


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalized_progress(value: Any) -> float:
    progress = _to_float(value) or 0.0
    if progress > 1.0:
        progress /= 100.0
    return _clamp01(progress)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _extract_stage(
    payload: dict[str, Any],
    progress: float,
    current_action: str,
    behavior_name: str | None = None,
) -> tuple[int, int, str]:
    for key in ("stage_index", "step_index"):
        stage_index = _to_int(payload.get(key))
        stage_total = _to_int(payload.get("stage_total") or payload.get("step_total"))
        if stage_index is not None and stage_total:
            return max(1, stage_index), max(1, stage_total), _stage_label(payload, current_action)

    reported_stage = _first_text(payload.get("current_stage"))
    contract_position = stage_position(behavior_name, reported_stage)
    if contract_position is not None:
        return (
            contract_position[0],
            contract_position[1],
            str(reported_stage),
        )

    if reported_stage:
        return 0, 0, str(reported_stage)
    if current_action and current_action != "-":
        return 0, 0, _compact_action_label(current_action)
    return 0, 0, "waiting feedback"


def _stage_label(payload: dict[str, Any], current_action: str) -> str:
    explicit = _first_text(
        payload.get("current_stage"),
        payload.get("stage_label"),
        payload.get("step_label"),
    )
    if explicit:
        return explicit
    return _compact_action_label(current_action) or "-"


def _infer_target_label(behavior: Any, current_action: Any) -> str:
    text = f"{behavior or ''} {current_action or ''}".upper()
    rules = (
        ("food bowl", ("FOOD", "BOWL", "EAT", "WATER")),
        (
            "toilet pad",
            (
                "PAD",
                "TOILET",
                "PEE",
                "POOP",
                "EXCRETION",
                "SQUAT",
                "URINAT",
                "BLADDER_RELIEF",
                "RELIEVE_BLADDER",
            ),
        ),
        ("sleep mat", ("BED", "SLEEP", "NAP", "CURLED")),
        ("toy ball", ("TOY", "BALL", "FETCH", "POUNCE", "OBJECT", "CARRY")),
        ("charger", ("CHARGE", "RECHARGE", "DOCK")),
        ("groom mat", ("GROOM", "CLEAN", "LICK")),
        ("owner", ("OWNER", "USER", "PERSON", "HUMAN", "ANIMAL", "SOCIAL", "INTERACTION", "RESOURCE", "GREET", "INVITE", "HAND", "FOLLOW", "COME", "CUDDLE", "NUDGE")),
        ("safe zone", ("FLEE", "HIDE", "AVOID", "DANGER", "STOP")),
    )
    for label, needles in rules:
        if any(needle in text for needle in needles):
            return label
    return "room"


def _infer_trigger_reason(state: SimState, payload: dict[str, Any]) -> str:
    params = _dict(payload.get("params")) or _json_dict(payload.get("params_json"))
    for key in ("source_event", "trigger_event", "command_id", "intent", "category"):
        value = _first_text(params.get(key), payload.get(key))
        if value:
            return str(value)
    if state.internal_need_signal_event:
        return str(state.internal_need_signal_event.get("event_type") or "need signal")
    if state.emotion_signal_event:
        return str(state.emotion_signal_event.get("event_type") or "emotion signal")
    if state.latest_audio_event:
        return str(state.latest_audio_event.get("command_id") or state.latest_audio_event.get("event_type") or "audio")
    latest_visual = state.latest_visual_event or {}
    events = latest_visual.get("events")
    if isinstance(events, list) and events:
        return ",".join(str(item) for item in events[:2])
    if state.behavior_result_event:
        return _behavior_result_reason(state.behavior_result_event)
    return "-"


def _behavior_result_reason(payload: dict[str, Any]) -> str:
    return (
        _first_text(
            payload.get("source_event"),
            payload.get("action_type"),
            payload.get("demand_type"),
            payload.get("result_type"),
            payload.get("reason"),
        )
        or "-"
    )


def _result_phase(status: str, result: str) -> str:
    normalized_status = str(status or "").upper()
    normalized_result = str(result or "").lower()
    if (
        normalized_status == "SUCCESS"
        and normalized_result == "completed"
    ):
        return "completed"
    text = f"{normalized_status} {normalized_result}".upper()
    if "CANCEL" in text:
        return "canceled"
    if "INTERRUPT" in text or "PREEMPT" in text:
        return "interrupted"
    if "TIMEOUT" in text:
        return "timeout"
    return "failed"


def _result_transition(status: str, result: str) -> str:
    phase = _result_phase(status, result)
    if phase in {"canceled", "interrupted", "timeout", "failed"}:
        return phase
    return "completed"


def _result_status(status: str, result: str) -> str:
    phase = _result_phase(status, result)
    if phase == "completed":
        return "success"
    return phase


def _infer_unit_type(action: str) -> str:
    key = str(action or "").upper()
    if not key or key == "-":
        return "-"
    if any(token in key for token in ("IGNORE_", "POLICY", "NO_MOTION", "COMPLETE_STAGE")):
        return "policy"
    if any(
        token in key
        for token in (
            "MODIFIER",
            "SPEED_SCALE",
            "SLOW_MOVEMENT",
            "ACCELERATION_SCALE",
            "AMPLITUDE_SCALE",
            "DURATION_SCALE",
        )
    ):
        return "modifier"
    if any(
        token in key
        for token in (
            "RETURN_TO_",
            "NAV_",
            "NAVIGATE",
            "SEARCH_",
            "EXPLORE_",
            "FOLLOW_",
            "RETRIEVE_",
            "SEEK_",
            "CHARGE",
        )
    ):
        return "task"
    if "COMPOSITE" in key or "SEQUENCE" in key:
        return "composite"
    return "atomic"


def _merge_named_state_payload(
    current: dict[str, Any] | None,
    incoming: dict[str, Any],
    collection_key: str,
) -> dict[str, Any]:
    """Merge full snapshots and partial deltas without losing other meters."""

    if not isinstance(current, dict):
        return dict(incoming)
    incoming_collection = incoming.get(collection_key)
    if not isinstance(incoming_collection, dict) or not incoming_collection:
        return {**current, **incoming}
    current_collection = current.get(collection_key)
    merged_collection = {
        **(current_collection if isinstance(current_collection, dict) else {}),
        **incoming_collection,
    }
    return {
        **current,
        **incoming,
        collection_key: merged_collection,
    }


def _merge_need_signal_into_state(
    current: dict[str, Any] | None,
    signal: dict[str, Any],
) -> dict[str, Any] | None:
    """Reflect per-demand updates immediately while awaiting the next snapshot."""

    demand = str(signal.get("demand") or "").strip()
    if not demand:
        return current
    state = dict(current) if isinstance(current, dict) else {}
    demands = dict(state.get("demands")) if isinstance(state.get("demands"), dict) else {}
    demand_state = (
        dict(demands.get(demand))
        if isinstance(demands.get(demand), dict)
        else {}
    )
    for key, source_key in (
        ("value", "value"),
        ("level", "level"),
        ("levelEvent", "event_type"),
    ):
        value = signal.get(source_key)
        if value is not None:
            demand_state[key] = value
    demands[demand] = demand_state
    state["demands"] = demands
    context = signal.get("timeContext")
    if isinstance(context, dict) and context:
        state["timeContext"] = dict(context)
    return state


def _compact_action_label(action: str) -> str:
    label = str(action or "-")
    if label.startswith("ACT_"):
        label = label[4:]
    return label.lower().replace("_", " ")


def _is_locomotion_action(action: str) -> bool:
    key = str(action or "").upper()
    return any(
        token in key
        for token in (
            "LOCO_",
            "NAV_",
            "WALK",
            "TROT",
            "RUN",
            "APPROACH",
            "FOLLOW",
            "MATCH_OWNER",
            "FLEE",
            "AVOID",
            "RETURN_TO",
            "NAVIGATE",
            "SEARCH",
            "SEEK",
            "EXPLORE",
            "COME_HERE",
            "FETCH_TO",
        )
    ) and "DOCKED" not in key


def _is_food_dependent_action(action: str) -> bool:
    key = str(action or "").upper().replace("-", "_")
    return key in {
        "ACT_LICK_FOOD",
        "ACT_LICK_AND_SWALLOW",
        "ACT_CHEW_OR_CARRY_FOOD",
        "ACT_SCRATCH_FOOD",
    }


def _is_food_behavior(behavior: Any) -> bool:
    key = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        "_",
        str(behavior or ""),
    )
    key = key.replace("-", "_").replace(" ", "_").upper()
    return key in {
        "SEEK_FOOD",
        "SEEK_FOOD_URGENTLY",
        "EAT_NORMALLY",
        "EAT_EXCITEDLY",
    }


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * min(1.0, max(0.0, progress))


def _angle_delta(start: float, end: float) -> float:
    return (end - start + 180.0) % 360.0 - 180.0


def _lerp_angle(start: float, end: float, progress: float) -> float:
    return (start + _angle_delta(start, end) * min(1.0, max(0.0, progress))) % 360.0


def _queue_size(event_queue: Queue[SimEvent]) -> int:
    try:
        return event_queue.qsize()
    except NotImplementedError:
        return 0


def _ui_event_source(event: SimEvent) -> str:
    if event.kind == "visual_event":
        return "VIS"
    if event.kind == "audio_event":
        return "AUD"
    if event.kind.startswith("internal_need"):
        return "NEED"
    if event.kind.startswith("emotion"):
        return "EMO"
    if event.kind == "behavior_result_event":
        return "RESULT"
    if event.kind.startswith("action_"):
        return "EXEC"
    if event.kind == "manual_injection":
        return "BEH"
    return "SYS"


def _ui_event_level(event: SimEvent) -> str:
    summary = event.summary.upper()
    if any(token in summary for token in ("FAILED", "ERROR", "TIMEOUT", "OVERFLOW")):
        return "ERROR"
    if any(token in summary for token in ("TRIGGERED", "INTERRUPT", "CANCEL", "STALE")):
        return "WARN"
    if any(token in summary for token in ("SUCCESS", "COMPLETED", "LIVE", "STARTED")):
        return "OK"
    return "INFO"
