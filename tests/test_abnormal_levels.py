import importlib
import importlib.util
import unittest

from marsdog_sim2d.simevent.sim_state import SimState
from marsdog_sim2d.behavior.action_visuals import visual_for_action


class AbnormalLevelTests(unittest.TestCase):
    def setUp(self) -> None:
        module_name = "marsdog_sim2d.simevent.abnormal_simulation"
        spec = importlib.util.find_spec(module_name)
        self.assertIsNotNone(spec, "local abnormal level simulator is missing")
        self.abnormal = importlib.import_module(module_name)

    def test_levels_preserve_documented_steps_and_emotion_deltas(self) -> None:
        expected = {
            "L0": (
                "ACT_EMERGENCY_STOP",
                "ACT_ADJUST_SAFE_POSTURE",
                "ACT_CHECK_ABNORMAL_POSITION",
                "ACT_CONTINUOUS_BARK",
            ),
            "L1": (
                "ACT_EMERGENCY_STOP",
                "ACT_BODY_FLINCH",
                "ACT_QUICK_TURN_HEAD",
                "ACT_STEP_BACK",
                "ACT_EARS_BACKWARD",
                "ACT_ALERT_STATE",
            ),
            "L2": (
                "ACT_ACTION_STOP",
                "ACT_TURN_HEAD_CHECK_CAUSE",
                "ACT_CHANGE_DIRECTION_RETRY",
                "ACT_SHORT_WHIMPER",
                "ACT_SIT_LOOK_OWNER",
            ),
            "L3": (
                "ACT_PAUSE_MOMENT",
                "ACT_HEAD_TILT_CHECK_TARGET",
                "ACT_RETRY_ACTION",
            ),
        }

        for level, actions in expected.items():
            steps = self.abnormal.abnormal_steps(level, owner_visible=True)
            self.assertEqual(actions, tuple(step.action for step in steps))

        expected_emotions = {
            "L0": {"Fear": 40, "Anxiety": 30, "Excite": -30, "Joy": -40},
            "L1": {"Fear": 30, "Anxiety": 20, "Excite": -10, "Joy": -20},
            "L2": {"Anxiety": 10, "Excite": -10, "Joy": -10},
            "L3": {"Anxiety": (5, 10)},
        }
        for level, emotion_delta in expected_emotions.items():
            self.assertEqual(
                emotion_delta,
                self.abnormal.abnormal_emotion_delta(level),
            )

    def test_emotion_delta_format_keeps_signs_and_l3_range(self) -> None:
        labels = {"Anxiety": "焦虑", "Joy": "愉悦"}

        self.assertEqual(
            "焦虑+5~+10",
            self.abnormal.format_emotion_delta(
                {"Anxiety": (5, 10)},
                labels,
            ),
        )
        self.assertEqual(
            "焦虑+10 愉悦-10",
            self.abnormal.format_emotion_delta(
                {"Anxiety": 10, "Joy": -10},
                labels,
            ),
        )

    def test_l2_last_step_uses_owner_visibility(self) -> None:
        with_owner = self.abnormal.abnormal_steps("L2", owner_visible=True)
        without_owner = self.abnormal.abnormal_steps("L2", owner_visible=False)

        self.assertEqual("ACT_SIT_LOOK_OWNER", with_owner[-1].action)
        self.assertEqual("坐下看向主人", with_owner[-1].label)
        self.assertEqual("ACT_SIT_LOOK_AROUND", without_owner[-1].action)
        self.assertEqual("坐下东张西望", without_owner[-1].label)

    def test_level_selector_cycles_in_priority_order(self) -> None:
        level = "L0"
        observed = []
        for _ in range(4):
            level = self.abnormal.next_abnormal_level(level)
            observed.append(level)

        self.assertEqual(["L1", "L2", "L3", "L0"], observed)

    def test_step_advancement_updates_visible_action_and_holds_last_step(self) -> None:
        state = SimState(
            ui_abnormal_simulation_active=True,
            ui_abnormal_level="L3",
            ui_abnormal_step_started_at=10.0,
        )
        self.abnormal.apply_abnormal_step(state, 0, now=100.0)

        advanced = self.abnormal.advance_abnormal_step(
            state,
            now_monotonic=11.0,
            now=101.0,
        )

        self.assertTrue(advanced)
        self.assertEqual(1, state.ui_abnormal_step_index)
        self.assertEqual("ACT_HEAD_TILT_CHECK_TARGET", state.action_current_action)
        self.assertEqual("歪头查看目标", state.action_stage_label)
        self.assertEqual(2, state.action_stage_index)
        self.assertEqual(3, state.action_stage_total)

        state.ui_abnormal_step_index = 2
        state.ui_abnormal_step_started_at = 11.0
        self.abnormal.apply_abnormal_step(state, 2, now=102.0)
        self.assertFalse(
            self.abnormal.advance_abnormal_step(
                state,
                now_monotonic=12.0,
                now=103.0,
            )
        )
        self.assertEqual("ACT_RETRY_ACTION", state.action_current_action)

    def test_every_abnormal_action_has_an_explicit_visual(self) -> None:
        expected_poses = {
            "ACT_EMERGENCY_STOP": "stand",
            "ACT_ADJUST_SAFE_POSTURE": "lie",
            "ACT_CHECK_ABNORMAL_POSITION": "head_tilt_observe",
            "ACT_CONTINUOUS_BARK": "tentative_bark_whine",
            "ACT_BODY_FLINCH": "shake",
            "ACT_QUICK_TURN_HEAD": "head_tilt_observe",
            "ACT_STEP_BACK": "walk",
            "ACT_EARS_BACKWARD": "anxiety_cower",
            "ACT_ALERT_STATE": "stand",
            "ACT_ACTION_STOP": "stand",
            "ACT_TURN_HEAD_CHECK_CAUSE": "head_tilt_observe",
            "ACT_CHANGE_DIRECTION_RETRY": "walk",
            "ACT_SHORT_WHIMPER": "tentative_bark_whine",
            "ACT_SIT_LOOK_OWNER": "sit",
            "ACT_SIT_LOOK_AROUND": "sit",
            "ACT_PAUSE_MOMENT": "stand",
            "ACT_HEAD_TILT_CHECK_TARGET": "head_tilt_observe",
            "ACT_RETRY_ACTION": "stand",
        }

        for action, expected_pose in expected_poses.items():
            visual = visual_for_action(action)
            self.assertIsNotNone(visual, action)
            self.assertEqual(expected_pose, visual.pose, action)


if __name__ == "__main__":
    unittest.main()
