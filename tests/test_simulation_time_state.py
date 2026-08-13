import unittest

from marsdog_sim2d import config
from marsdog_sim2d.parsers import parse_simulation_time_state
from marsdog_sim2d.sim_state import SimState
from marsdog_sim2d.widgets import _endpoint_status, _virtual_time_display


class SimulationTimeStateTests(unittest.TestCase):
    def test_parser_preserves_authoritative_time_context(self) -> None:
        event = parse_simulation_time_state(
            {
                "event_type": "TIME_TICK",
                "tickSequence": 1234,
                "timeContext": {
                    "scale": 24,
                    "effectiveScale": 24,
                    "virtualDateTime": "2026-07-26T08:30:15+08:00",
                    "virtualTimestamp": 1785025815.0,
                },
            }
        )

        self.assertEqual(event.topic, config.TOPICS["simulation_time_state"])
        self.assertEqual(event.payload["timeContext"]["effectiveScale"], 24)
        self.assertIn("2026-07-26T08:30:15+08:00", event.summary)

    def test_tick_updates_state_without_flooding_event_table(self) -> None:
        state = SimState()
        event = parse_simulation_time_state(
            {
                "event_type": "TIME_TICK",
                "timeContext": {"virtualDateTime": "2026-07-26T08:30:15+08:00"},
            }
        )

        state.apply_event(event)

        self.assertEqual(state.simulation_time_state, event.payload)
        self.assertEqual(len(state.event_records), 0)

    def test_display_uses_virtual_datetime_and_effective_scale(self) -> None:
        state = SimState()
        state.simulation_time_state = {
            "event_type": "TIME_ACCELERATED_STEP",
            "timeContext": {
                "scale": 24,
                "effectiveScale": 720,
                "virtualDateTime": "2026-07-26T05:40:00+08:00",
            },
        }

        text, color = _virtual_time_display(state)

        self.assertEqual(text, "虚拟时间  2026-07-26 05:40:00  ×720")
        self.assertEqual(color, config.COLORS["warning"])

    def test_time_display_distinguishes_offline_from_connected_no_data(self) -> None:
        state = SimState()
        self.assertEqual("虚拟时间  离线", _virtual_time_display(state)[0])

        state.ros_time_online = True
        self.assertEqual(
            "虚拟时间  已连接，等待数据",
            _virtual_time_display(state)[0],
        )

    def test_local_autoplay_does_not_make_exec_endpoint_green(self) -> None:
        state = SimState(
            action_status="running",
            action_goal_id="local-idle",
            active_behavior="expressCalmAlone",
        )

        status, text, _detail = _endpoint_status(
            state,
            (
                config.ACTION_FEEDBACK_TOPIC,
                config.ACTION_GOAL_TOPIC,
                config.ACTION_RESULT_TOPIC,
            ),
            "EXEC",
            1.0,
        )

        self.assertEqual("waiting", status)
        self.assertEqual("Waiting", text)


if __name__ == "__main__":
    unittest.main()
