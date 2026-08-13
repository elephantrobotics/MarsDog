import unittest

from marsdog_sim2d import config
from marsdog_sim2d.sim_state import SimEvent, SimState


class MotionSmoothingTests(unittest.TestCase):
    def _start_goal(self, state: SimState) -> None:
        state.apply_event(
            SimEvent(
                "action_goal",
                config.ACTION_GOAL_TOPIC,
                {
                    "goal_id": "smooth-1",
                    "behavior_name": "eatNormally",
                },
                "goal",
                received_at=100.0,
            )
        )

    def test_feedback_pose_is_interpolated_instead_of_applied_as_jump(self) -> None:
        state = SimState()
        self._start_goal(state)
        start_x = state.dog_x
        target_x = start_x + 120.0

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "smooth-1",
                    "status": "RUNNING",
                    "progress": 0.5,
                    "current_stage": "prepare",
                    "current_action": "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
                    "dog_pose": {
                        "x": target_x,
                        "y": state.dog_y,
                        "heading": state.dog_heading,
                    },
                },
                "sparse feedback",
                received_at=101.0,
            )
        )

        self.assertEqual(start_x, state.dog_x)
        duration = state.dog_motion_duration
        state.advance_virtual_motion(duration / 2.0)
        self.assertGreater(state.dog_x, start_x)
        self.assertLess(state.dog_x, target_x)
        state.advance_virtual_motion(duration / 2.0)
        self.assertAlmostEqual(target_x, state.dog_x)

    def test_interaction_texture_waits_until_dog_reaches_target(self) -> None:
        state = SimState(
            ui_bowl_has_food=True,
            ui_food_eating_authorized=True,
        )
        self._start_goal(state)
        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "smooth-1",
                    "behavior_name": "eatNormally",
                    "status": "RUNNING",
                    "progress": 0.25,
                    "current_stage": "prepare",
                    "current_action": "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
                },
                "prepare feedback",
                received_at=100.5,
            )
        )
        target_x = state.dog_x + 100.0

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "smooth-1",
                    "status": "RUNNING",
                    "progress": 0.8,
                    "current_stage": "eating",
                    "current_action": "ACT_LICK_FOOD",
                    "dog_pose": {
                        "x": target_x,
                        "y": state.dog_y,
                        "heading": state.dog_heading,
                    },
                },
                "interaction feedback",
                received_at=101.0,
            )
        )

        self.assertEqual(
            "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
            state.action_visual_action,
        )
        self.assertEqual(
            "ACT_LICK_FOOD",
            state.action_pending_visual_action,
        )
        state.apply_event(
            SimEvent(
                "action_result",
                config.ACTION_RESULT_TOPIC,
                {
                    "goal_id": "smooth-1",
                    "behavior_name": "eatNormally",
                    "status": "SUCCESS",
                    "result": "completed",
                },
                "result without duplicate pose",
                received_at=101.01,
            )
        )
        self.assertEqual(
            "ACT_LOWER_HEAD_AND_APPROACH_BOWL",
            state.action_visual_action,
        )
        state.advance_virtual_motion(state.dog_motion_duration)
        self.assertEqual("ACT_LICK_FOOD", state.action_visual_action)
        self.assertIsNone(state.action_pending_visual_action)

    def test_unsupported_exact_action_remains_visible_as_text_only(self) -> None:
        state = SimState()
        self._start_goal(state)

        state.apply_event(
            SimEvent(
                "action_feedback",
                config.ACTION_FEEDBACK_TOPIC,
                {
                    "goal_id": "smooth-1",
                    "status": "RUNNING",
                    "progress": 0.2,
                    "behavior_name": "expressCalmAlone",
                    "current_stage": "expression",
                    "current_action": "ACT_GUARD_DOOR",
                },
                "modifier feedback",
                received_at=101.0,
            )
        )

        self.assertEqual("ACT_GUARD_DOOR", state.action_current_action)
        self.assertEqual("ACT_GUARD_DOOR", state.action_visual_action)


if __name__ == "__main__":
    unittest.main()
