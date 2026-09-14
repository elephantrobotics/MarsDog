import unittest

from marsdog_sim2d import config
from marsdog_sim2d.simevent.events import SimEvent
from marsdog_sim2d.simevent.sim_state import SimState


class SimStateEventDispatchTests(unittest.TestCase):
    def test_dispatches_each_non_action_event_group(self) -> None:
        state = SimState(ui_bowl_has_food=True)

        state.apply_event(
            SimEvent(
                "action_server_state",
                config.ACTION_NAME,
                {"available": True, "message": "ready"},
                "server ready",
            )
        )
        state.apply_event(
            SimEvent(
                "visual_event",
                config.TOPICS["visual_event"],
                {"active_target": {"identity": "owner"}},
                "owner visible",
            )
        )
        state.apply_event(
            SimEvent(
                "internal_need_state",
                config.TOPICS["internal_need_state"],
                {"demands": {"Hunger": {"value": 82, "level": "TRIGGERED"}}},
                "hunger triggered",
            )
        )
        state.apply_event(
            SimEvent(
                "behavior_result_event",
                config.TOPICS["behavior_result_event"],
                {"behavior_name": "seekFood", "status": "COMPLETED"},
                "seekFood completed",
            )
        )

        self.assertTrue(state.action_server_available)
        self.assertEqual("owner", state.active_target["identity"])
        self.assertEqual(
            82,
            state.internal_need_state["demands"]["Hunger"]["value"],
        )
        self.assertEqual("seekFood", state.active_behavior)
        self.assertEqual(4, state.processed_events)

    def test_abnormal_mode_still_defers_action_events(self) -> None:
        state = SimState(ui_abnormal_simulation_active=True)
        event = SimEvent(
            "action_feedback",
            config.ACTION_FEEDBACK_TOPIC,
            {"goal_id": "external-goal", "progress": 0.5},
            "external feedback",
        )

        state.apply_event(event)

        self.assertEqual([event], list(state.ui_abnormal_deferred_events))
        self.assertEqual("waiting", state.action_status)


if __name__ == "__main__":
    unittest.main()
