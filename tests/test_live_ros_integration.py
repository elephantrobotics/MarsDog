from __future__ import annotations

import unittest

from rclpy.qos import QoSReliabilityPolicy

from marsdog_sim2d import config
from marsdog_sim2d.parsers import (
    parse_internal_need_signal_event,
    parse_internal_need_state,
    parse_simulation_time_state,
)
from marsdog_sim2d.ros_bridge import RosBridge
from marsdog_sim2d.sim_state import SimEvent, SimState
from marsdog_sim2d.virtual_executor import _normalize_action_debug_payload


class LiveStateProtocolTests(unittest.TestCase):
    def test_nested_camel_time_payload_is_normalized(self) -> None:
        event = parse_simulation_time_state(
            {
                "eventType": "TIME_TICK",
                "payload": {
                    "tick_sequence": 42,
                    "time_context": {
                        "virtual_datetime": "2026-07-30T15:10:20+08:00",
                        "effective_scale": 24,
                    },
                },
            }
        )

        self.assertEqual("TIME_TICK", event.payload["event_type"])
        self.assertEqual(42, event.payload["tickSequence"])
        self.assertEqual(
            "2026-07-30T15:10:20+08:00",
            event.payload["timeContext"]["virtualDateTime"],
        )
        self.assertEqual(24, event.payload["timeContext"]["effectiveScale"])

    def test_need_list_and_camel_fields_are_normalized_for_ui_meters(self) -> None:
        event = parse_internal_need_state(
            {
                "payload": {
                    "needStates": [
                        {
                            "name": "HUNGER",
                            "currentValue": 81.5,
                            "state": "TRIGGERED",
                            "isTriggered": True,
                        },
                        {
                            "need": "energy",
                            "current_value": 17,
                            "status": "TRIGGERED",
                        },
                    ],
                    "time_context": {
                        "virtual_datetime": "2026-07-30T15:11:00+08:00",
                    },
                }
            }
        )

        hunger = event.payload["demands"]["Hunger"]
        energy = event.payload["demands"]["Energy"]
        self.assertEqual(81.5, hunger["value"])
        self.assertEqual("TRIGGERED", hunger["level"])
        self.assertTrue(hunger["triggered"])
        self.assertEqual(17, energy["value"])
        self.assertEqual(
            "2026-07-30T15:11:00+08:00",
            event.payload["timeContext"]["virtualDateTime"],
        )

    def test_signal_updates_one_meter_without_erasing_other_demands(self) -> None:
        state = SimState(
            internal_need_state={
                "demands": {
                    "Hunger": {"value": 40, "level": "NORMAL"},
                    "Energy": {"value": 75, "level": "NORMAL"},
                }
            }
        )
        signal = parse_internal_need_signal_event(
            {
                "eventType": "NEED_HUNGER_TRIGGERED",
                "need": "hunger",
                "currentValue": 82,
                "state": "TRIGGERED",
            }
        )

        state.apply_event(signal)

        self.assertEqual(
            82,
            state.internal_need_state["demands"]["Hunger"]["value"],
        )
        self.assertEqual(
            75,
            state.internal_need_state["demands"]["Energy"]["value"],
        )

    def test_embedded_time_context_is_fallback_for_missing_time_topic(self) -> None:
        state = SimState()
        event = parse_internal_need_state(
            {
                "demands": {"Hunger": {"value": 35, "level": "NORMAL"}},
                "timeContext": {
                    "virtualDateTime": "2026-07-30T15:12:00+08:00",
                    "effectiveScale": 24,
                },
            }
        )

        state.apply_event(event)

        self.assertEqual(
            "2026-07-30T15:12:00+08:00",
            state.simulation_time_state["timeContext"]["virtualDateTime"],
        )
        self.assertEqual(config.TOPICS["internal_need_state"], state.simulation_time_source)

    def test_graph_state_tracks_only_external_backend_availability(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "ros_graph_state",
                config.ROS_GRAPH_STATUS_SOURCE,
                {
                    "external_publishers": {
                        config.ACTION_FEEDBACK_TOPIC: [
                            {
                                "node_name": "marsdog_action_executor",
                                "node_namespace": "/",
                                "topic_type": "std_msgs/msg/String",
                            }
                        ]
                    },
                    "publisher_counts": {
                        config.ACTION_FEEDBACK_TOPIC: 1,
                    },
                    "executor_online": True,
                    "need_online": False,
                    "emotion_online": False,
                    "time_online": False,
                },
                "graph",
            )
        )

        self.assertTrue(state.ros_executor_online)
        self.assertEqual(
            1,
            state.ros_external_publisher_counts[config.ACTION_FEEDBACK_TOPIC],
        )


class LiveActionProtocolTests(unittest.TestCase):
    def test_nested_camel_feedback_is_normalized(self) -> None:
        payload = _normalize_action_debug_payload(
            {
                "goalId": "goal-7",
                "feedback": {
                    "behaviorName": "eatNormally",
                    "currentStage": "eating",
                    "currentAction": "ACT_LICK_FOOD",
                    "safeToInterrupt": True,
                    "completionRate": 0.5,
                },
            },
            "feedback",
        )

        self.assertEqual("goal-7", payload["goal_id"])
        self.assertEqual("eatNormally", payload["behavior_name"])
        self.assertEqual("eating", payload["current_stage"])
        self.assertEqual("ACT_LICK_FOOD", payload["current_action"])
        self.assertEqual(0.5, payload["progress"])

    def test_feedback_without_seen_goal_preempts_local_autoplay(self) -> None:
        state = SimState()
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "local-idle",
                    "behavior_name": "expressCalmAlone",
                },
                "local idle",
            )
        )

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "external-need",
                    "behavior_name": "sleepNow",
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_action": "ACT_POSTURE_SLEEP_ON_SIDE",
                },
                "external feedback",
            )
        )

        self.assertEqual("external-need", state.action_goal_id)
        self.assertEqual("sleepNow", state.active_behavior)
        self.assertEqual("ACT_POSTURE_SLEEP_ON_SIDE", state.action_current_action)


class VisualizationQosTests(unittest.TestCase):
    def test_live_stream_subscribers_accept_best_effort_publishers(self) -> None:
        for topic in (
            config.TOPICS["simulation_time_state"],
            config.TOPICS["internal_need_state"],
            config.TOPICS["internal_need_signal_event"],
            config.TOPICS["behavior_result_event"],
        ):
            with self.subTest(topic=topic):
                profile = RosBridge._subscription_qos_for_topic(object(), topic)
                self.assertEqual(
                    QoSReliabilityPolicy.BEST_EFFORT,
                    profile.reliability,
                )


if __name__ == "__main__":
    unittest.main()
