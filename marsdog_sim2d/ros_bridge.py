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

from . import config
from .event_injector import InjectionCommand, MANUAL_INJECTION_TOPIC, MANUAL_SOURCE
from .parsers import PARSER_BY_TOPIC
from .sim_state import SimEvent
from .virtual_executor import VirtualActionServer


class RosBridge(Node):
    """Subscribe to documented MarsDog topics and enqueue normalized events."""

    def __init__(
        self,
        event_queue: Queue[SimEvent],
        injection_queue: Queue[InjectionCommand] | None = None,
    ) -> None:
        super().__init__("marsdog_sim2d_bridge")
        self._event_queue = event_queue
        self._injection_queue = injection_queue
        self._topic_subscriptions = []
        self._injection_publishers: dict[str, Any] = {}
        self._virtual_action_server: VirtualActionServer | None = None
        self._create_subscriptions()
        self._create_injection_publishers()
        self._injection_timer = self.create_timer(0.05, self._drain_injection_queue)
        self._virtual_action_server = VirtualActionServer(self, event_queue)
        topics = ", ".join(PARSER_BY_TOPIC.keys())
        self.get_logger().info("ROS2 bridge started")
        self.get_logger().info(f"Subscribed topics: {topics}")

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

            if _is_manual_state_echo(topic, decoded):
                self.get_logger().debug(f"Ignoring self-published manual state echo on {topic}")
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
        if topic == config.TOPICS["visual_event"]:
            return QoSProfile(
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=config.VISUAL_TOPIC_DEPTH,
                reliability=QoSReliabilityPolicy.BEST_EFFORT,
            )

        if topic in {
            config.TOPICS["internal_need_state"],
            config.TOPICS["internal_need_signal_event"],
            config.TOPICS["emotion_state"],
            config.TOPICS["emotion_signal_event"],
            config.TOPICS["audio_event"],
            config.TOPICS["behavior_result_event"],
        }:
            return QoSProfile(
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=(
                    config.STATE_TOPIC_DEPTH
                    if topic in {
                        config.TOPICS["internal_need_state"],
                        config.TOPICS["emotion_state"],
                    }
                    else config.EVENT_TOPIC_DEPTH
                ),
                reliability=QoSReliabilityPolicy.RELIABLE,
            )

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

    def destroy_node(self) -> bool:
        if self._virtual_action_server is not None:
            self._virtual_action_server.destroy()
            self._virtual_action_server = None
        return super().destroy_node()


def _is_manual_state_echo(topic: str, data: dict[str, Any]) -> bool:
    if data.get("manual_source") != MANUAL_SOURCE:
        return False
    return topic in {
        config.TOPICS["internal_need_state"],
        config.TOPICS["emotion_state"],
    }
