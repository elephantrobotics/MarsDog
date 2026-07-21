import unittest

from marsdog_sim2d import config
from marsdog_sim2d.event_injector import (
    build_custom_injection_command,
    resolve_emotion_output,
    resolve_need_output,
)


class NeedOutputMappingTests(unittest.TestCase):
    def test_need_boundaries_follow_documented_operators(self) -> None:
        cases = (
            ("Hunger", 70, "NORMAL"),
            ("Hunger", 71, "TRIGGERED"),
            ("Hunger", 90, "TRIGGERED"),
            ("Hunger", 91, "OVERFLOW"),
            ("Bladder", 75, "NORMAL"),
            ("Bladder", 76, "TRIGGERED"),
            ("Sleepiness", 65, "NORMAL"),
            ("Sleepiness", 66, "TRIGGERED"),
            ("Cleanliness", 70, "NORMAL"),
            ("Cleanliness", 71, "TRIGGERED"),
            ("Social", 60, "NORMAL"),
            ("Social", 61, "TRIGGERED"),
            ("Exploration", 60, "NORMAL"),
            ("Exploration", 61, "TRIGGERED"),
            ("Energy", 20, "NORMAL"),
            ("Energy", 19, "TRIGGERED"),
            ("Energy", 10, "TRIGGERED"),
            ("Energy", 9, "OVERFLOW"),
        )
        for demand, value, expected_level in cases:
            with self.subTest(demand=demand, value=value):
                level, _event_type = resolve_need_output(demand, value)
                self.assertEqual(expected_level, level)

    def test_manual_level_cannot_conflict_with_value(self) -> None:
        command = build_custom_injection_command(
            "Need",
            {"need_demand": "Hunger", "need_value": "82", "need_level": "NORMAL"},
        )
        signal = command.messages[1]
        self.assertEqual(config.TOPICS["internal_need_signal_event"], signal.topic)
        self.assertEqual("TRIGGERED", signal.payload["level"])
        self.assertEqual("NEED_HUNGER_TRIGGERED", signal.payload["event_type"])


class EmotionOutputMappingTests(unittest.TestCase):
    def test_emotion_ranges_match_documentation(self) -> None:
        cases = (
            ("Joy", 29, "NONE"),
            ("Joy", 30, "LOW"),
            ("Joy", 60, "LOW"),
            ("Joy", 61, "MID"),
            ("Joy", 85, "MID"),
            ("Joy", 86, "HIGH"),
            ("Excite", 39, "NONE"),
            ("Excite", 40, "LOW"),
            ("Excite", 70, "LOW"),
            ("Excite", 71, "HIGH"),
            ("Anxiety", 24, "NONE"),
            ("Anxiety", 25, "LOW"),
            ("Anxiety", 50, "LOW"),
            ("Anxiety", 51, "HIGH"),
            ("Fear", 29, "NONE"),
            ("Fear", 30, "LOW"),
            ("Fear", 60, "LOW"),
            ("Fear", 61, "HIGH"),
            ("Curious", 19, "NONE"),
            ("Curious", 20, "LOW"),
            ("Curious", 50, "LOW"),
            ("Curious", 51, "HIGH"),
            ("Calm", 0, "NORMAL"),
            ("Calm", 60, "NORMAL"),
            ("Calm", 61, "HIGH"),
        )
        for emotion, value, expected_level in cases:
            with self.subTest(emotion=emotion, value=value):
                level, _event_type, _level_range = resolve_emotion_output(emotion, value)
                self.assertEqual(expected_level, level)

    def test_joy_mid_payload_uses_documented_range(self) -> None:
        command = build_custom_injection_command(
            "Emotion",
            {"emotion_name": "Joy", "emotion_value": "72", "emotion_level": "HIGH"},
        )
        self.assertEqual(2, len(command.messages))
        signal = command.messages[1]
        self.assertEqual(config.TOPICS["emotion_signal_event"], signal.topic)
        self.assertEqual("MID", signal.payload["level"])
        self.assertEqual("EMO_JOY_MID", signal.payload["event_type"])
        self.assertEqual([61, 85], signal.payload["range"])

    def test_none_interval_publishes_state_without_fake_signal(self) -> None:
        command = build_custom_injection_command(
            "Emotion",
            {"emotion_name": "Joy", "emotion_value": "20"},
        )
        self.assertEqual(1, len(command.messages))
        self.assertEqual(config.TOPICS["emotion_state"], command.messages[0].topic)
        joy = command.messages[0].payload["emotions"]["Joy"]
        self.assertEqual("NONE", joy["level"])
        self.assertIsNone(joy["levelEvent"])


if __name__ == "__main__":
    unittest.main()
