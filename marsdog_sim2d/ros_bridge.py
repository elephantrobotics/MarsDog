"""ROS2 subscriptions that bridge String(JSON) topics into a thread-safe queue."""

from __future__ import annotations

import json
from queue import Empty, Queue
from typing import Any

from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from std_msgs.msg import String
from std_srvs.srv import Trigger

from . import config
from .event_injector import InjectionCommand, MANUAL_INJECTION_TOPIC
from .feeding_interface import FeedingCoordinator
from .parsers import PARSER_BY_TOPIC
from .sim_state import SimEvent
from .virtual_executor import VirtualActionServer


class RosBridge(Node):
    """Subscribe to documented MarsDog topics and enqueue normalized events."""

    def __init__(
        self,
        event_queue: Queue[SimEvent],
        injection_queue: Queue[InjectionCommand] | None = None,
        feeding_coordinator: FeedingCoordinator | None = None,
    ) -> None:
        super().__init__("marsdog_sim2d_bridge")
        self._event_queue = event_queue
        self._injection_queue = injection_queue
        self._topic_subscriptions = []
        self._injection_publishers: dict[str, Any] = {}
        self._virtual_action_server: VirtualActionServer | None = None
        self._last_external_graph_signature: tuple[tuple[str, int], ...] | None = None
        self._feeding_coordinator = (
            feeding_coordinator or FeedingCoordinator()
        )
        self._create_subscriptions()
        self._create_injection_publishers()
        self._feeding_state_publisher = self.create_publisher(
            String,
            config.FEEDING_STATE_TOPIC,
            QoSProfile(
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self._feeding_service = self.create_service(
            Trigger,
            config.FEEDING_TRY_START_SERVICE,
            self._handle_try_start_eating,
        )
        self._feeding_state_timer = self.create_timer(
            config.FEEDING_STATE_PUBLISH_PERIOD_SEC,
            self._publish_feeding_state,
        )
        self._injection_timer = self.create_timer(0.05, self._drain_injection_queue)
        self._virtual_action_server = VirtualActionServer(self, event_queue)
        self._graph_timer = self.create_timer(
            config.ROS_GRAPH_POLL_PERIOD_SEC,
            self._sample_external_publishers,
        )
        topics = ", ".join(PARSER_BY_TOPIC.keys())
        self.get_logger().info("ROS2 bridge started")
        self.get_logger().info(f"Subscribed topics: {topics}")
        self.get_logger().info(
            "Feeding handshake: "
            f"topic={config.FEEDING_STATE_TOPIC} "
            f"service={config.FEEDING_TRY_START_SERVICE}"
        )

    def _create_subscriptions(self) -> None:
        for topic, parser in PARSER_BY_TOPIC.items():
            qos = self._subscription_qos_for_topic(topic)
            sub = self.create_subscription(
                String,
                topic,
                self._make_callback(topic, parser),
                qos,
            )
            self._topic_subscriptions.append(sub)

    def _create_injection_publishers(self) -> None:
        for topic in {
            config.TOPICS["audio_event"],
            config.TOPICS["visual_event"],
            config.TOPICS["internal_need_state"],
            config.TOPICS["internal_need_signal_event"],
            config.TOPICS["emotion_state"],
            config.TOPICS["emotion_signal_event"],
            config.TOPICS["behavior_result_event"],
            config.TOPICS["personality_state"],
        }:
            self._injection_publishers[topic] = self.create_publisher(
                String,
                topic,
                self._publisher_qos_for_topic(topic),
            )

    def _drain_injection_queue(self) -> None:
        if self._injection_queue is None:
            return

        published = 0
        while published < 20:
            try:
                command = self._injection_queue.get_nowait()
            except Empty:
                break
            self._publish_injection(command)
            published += 1

    def _publish_injection(self, command: InjectionCommand) -> None:
        topics: list[str] = []
        for message in command.messages:
            publisher = self._injection_publishers.get(message.topic)
            if publisher is None:
                self.get_logger().warning(f"No manual injection publisher for {message.topic}")
                continue
            ros_msg = String()
            ros_msg.data = json.dumps(message.payload, ensure_ascii=False)
            publisher.publish(ros_msg)
            topics.append(message.topic)

        summary = f"manual_inject: {command.label} -> {', '.join(topics) if topics else 'none'}"
        self._event_queue.put(
            SimEvent(
                "manual_injection",
                MANUAL_INJECTION_TOPIC,
                {
                    "template_id": command.template_id,
                    "label": command.label,
                    "topics": topics,
                    "messages": [message.payload for message in command.messages],
                },
                summary,
            )
        )
        self.get_logger().info(summary)

    def _publish_feeding_state(self) -> None:
        message = String()
        message.data = self._feeding_coordinator.state_json()
        self._feeding_state_publisher.publish(message)

    def _handle_try_start_eating(
        self,
        request: Trigger.Request,
        response: Trigger.Response,
    ) -> Trigger.Response:
        del request
        decision = self._feeding_coordinator.try_start_eating()
        response.success = decision.accepted
        response.message = decision.response_message()
        self._publish_feeding_state()

        if decision.accepted:
            self._event_queue.put(
                SimEvent(
                    "feeding_authorized",
                    config.FEEDING_TRY_START_SERVICE,
                    decision.state,
                    "feeding service authorized eating",
                )
            )
            self.get_logger().info(
                "Eating authorized for goal "
                f"{decision.state.get('activeGoalId') or '-'}"
            )
        else:
            self.get_logger().info(
                f"Eating request rejected: {decision.reason}"
            )
        return response

    def _make_callback(self, topic: str, parser: Any) -> Any:
        def callback(msg: String) -> None:
            try:
                decoded = json.loads(msg.data)
            except json.JSONDecodeError as exc:
                self.get_logger().warning(
                    f"Ignoring invalid JSON on {topic}: {exc.msg}"
                )
                return

            if not isinstance(decoded, dict):
                self.get_logger().warning(
                    f"Ignoring JSON on {topic}: expected object, got "
                    f"{type(decoded).__name__}"
                )
                return

            try:
                event = parser(decoded)
            except Exception as exc:  # pragma: no cover - defensive ROS callback guard
                self.get_logger().error(f"Parser failed for {topic}: {exc}")
                return

            if event.kind == "behavior_result_event":
                self.get_logger().info(
                    "/behavior/result_event format identified as "
                    f"{event.format_hint or 'unknown'}"
                )
                if event.format_hint == "unknown":
                    self.get_logger().warning(
                        "Unknown /behavior/result_event field format; showing raw "
                        "fallback summary"
                    )
            else:
                self.get_logger().debug(f"Received {event.kind} from {topic}")

            self._event_queue.put(event)

        return callback

    def _subscription_qos_for_topic(self, topic: str) -> QoSProfile:
        if topic == config.TOPICS["personality_state"]:
            return QoSProfile(
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=config.PERSONALITY_TOPIC_DEPTH,
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            )

        # These are live visualization streams. Requesting BEST_EFFORT can
        # match publishers that offer either BEST_EFFORT or RELIABLE, whereas
        # a RELIABLE reader is rejected by a BEST_EFFORT writer at DDS level.
        # The small keep-last queue is sufficient because the UI only needs
        # the newest state/frame rather than replaying every historical tick.
        depth = (
            config.VISUAL_TOPIC_DEPTH
            if topic == config.TOPICS["visual_event"]
            else config.STATE_TOPIC_DEPTH
            if topic
            in {
                config.TOPICS["simulation_time_state"],
                config.TOPICS["internal_need_state"],
                config.TOPICS["emotion_state"],
            }
            else config.EVENT_TOPIC_DEPTH
        )
        return QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=depth,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

    def _publisher_qos_for_topic(self, topic: str) -> QoSProfile:
        if topic == config.TOPICS["personality_state"]:
            return QoSProfile(
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=config.PERSONALITY_TOPIC_DEPTH,
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            )
        return QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=config.EVENT_TOPIC_DEPTH,
            reliability=QoSReliabilityPolicy.RELIABLE,
        )

    def _sample_external_publishers(self) -> None:
        """Report only publishers owned by other ROS nodes.

        The viewer itself creates publishers for manual injection, and topic
        names also exist when there are subscribers but no publishers. Neither
        condition means the real backend is online.
        """

        monitored_topics = (
            config.TOPICS["simulation_time_state"],
            config.TOPICS["internal_need_state"],
            config.TOPICS["internal_need_signal_event"],
            config.TOPICS["emotion_state"],
            config.TOPICS["emotion_signal_event"],
            config.ACTION_GOAL_TOPIC,
            config.ACTION_FEEDBACK_TOPIC,
            config.ACTION_RESULT_TOPIC,
        )
        own_name = self.get_name()
        own_namespace = self.get_namespace()
        publishers: dict[str, list[dict[str, str]]] = {}
        for topic in monitored_topics:
            external: list[dict[str, str]] = []
            for endpoint in self.get_publishers_info_by_topic(topic):
                if (
                    endpoint.node_name == own_name
                    and endpoint.node_namespace == own_namespace
                ):
                    continue
                qos = endpoint.qos_profile
                external.append(
                    {
                        "node_name": endpoint.node_name,
                        "node_namespace": endpoint.node_namespace,
                        "topic_type": endpoint.topic_type,
                        "reliability": str(qos.reliability),
                        "durability": str(qos.durability),
                    }
                )
            publishers[topic] = external

        counts = {
            topic: len(endpoints)
            for topic, endpoints in publishers.items()
        }
        signature = tuple(sorted(counts.items()))
        if signature == self._last_external_graph_signature:
            return
        self._last_external_graph_signature = signature
        executor_online = any(
            counts.get(topic, 0) > 0
            for topic in (
                config.ACTION_GOAL_TOPIC,
                config.ACTION_FEEDBACK_TOPIC,
                config.ACTION_RESULT_TOPIC,
            )
        )
        need_online = any(
            counts.get(topic, 0) > 0
            for topic in (
                config.TOPICS["internal_need_state"],
                config.TOPICS["internal_need_signal_event"],
            )
        )
        emotion_online = any(
            counts.get(topic, 0) > 0
            for topic in (
                config.TOPICS["emotion_state"],
                config.TOPICS["emotion_signal_event"],
            )
        )
        time_online = counts.get(config.TOPICS["simulation_time_state"], 0) > 0
        active_counts = {
            topic: count for topic, count in counts.items() if count > 0
        }
        self.get_logger().info(
            "External ROS publishers changed: "
            + (
                ", ".join(
                    f"{topic}={count}"
                    for topic, count in active_counts.items()
                )
                if active_counts
                else "none"
            )
        )
        wrong_types = [
            f"{topic}={endpoint.get('topic_type')}"
            for topic, endpoints in publishers.items()
            for endpoint in endpoints
            if endpoint.get("topic_type") != "std_msgs/msg/String"
        ]
        if wrong_types:
            self.get_logger().warning(
                "UI expects std_msgs/msg/String JSON but discovered: "
                + ", ".join(wrong_types)
            )
        self._event_queue.put(
            SimEvent(
                "ros_graph_state",
                config.ROS_GRAPH_STATUS_SOURCE,
                {
                    "external_publishers": publishers,
                    "publisher_counts": counts,
                    "executor_online": executor_online,
                    "need_online": need_online,
                    "emotion_online": emotion_online,
                    "time_online": time_online,
                },
                (
                    "ros_graph: "
                    f"exec={executor_online} need={need_online} "
                    f"emotion={emotion_online} time={time_online}"
                ),
            )
        )

    def destroy_node(self) -> bool:
        if self._virtual_action_server is not None:
            self._virtual_action_server.destroy()
            self._virtual_action_server = None
        return super().destroy_node()
