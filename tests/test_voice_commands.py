import unittest

from marsdog_sim2d.event_injector import build_custom_injection_command
from marsdog_sim2d.voice_commands import (
    VOICE_COMMAND_SPECS,
    resolve_voice_command,
)
from marsdog_sim2d.virtual_executor import VirtualRoom


class VoiceCommandTests(unittest.TestCase):
    def test_all_17_direct_commands_resolve_to_contract_behaviors(self) -> None:
        self.assertEqual(17, len(VOICE_COMMAND_SPECS))
        for spec in VOICE_COMMAND_SPECS:
            with self.subTest(behavior=spec.behavior_name):
                plan = VirtualRoom().build_plan(
                    {
                        "goal_id": spec.behavior_name,
                        "behavior_name": spec.behavior_name,
                        "timeout_sec": spec.timeout_sec,
                    }
                )
                self.assertTrue(plan.selected_stages)

    def test_complete_audio_event_names_map_one_to_one(self) -> None:
        cases = {
            "EVT_VOICE_CALL_NAME": "respond_owner_call",
            "EVT_VOICE_COMMAND_SIT": "sit_down",
            "EVT_VOICE_COMMAND_LIE_DOWN": "lie_down",
            "EVT_VOICE_COMMAND_STAND": "stand_up",
            "EVT_VOICE_COMMAND_WAIT": "wait_in_place",
            "EVT_VOICE_COMMAND_COME": "come_to_owner",
            "EVT_VOICE_COMMAND_FOLLOW": "follow_owner",
            "EVT_VOICE_COMMAND_GIVE_PAW": "give_paw",
            "EVT_VOICE_COMMAND_HIGH_FIVE": "high_five",
            "EVT_VOICE_COMMAND_ROLL": "roll_over",
            "EVT_VOICE_COMMAND_SPIN": "spin_around",
            "EVT_VOICE_COMMAND_RETURN": "return_to_owner",
            "EVT_VOICE_COMMAND_DROP": "drop_object",
            "EVT_VOICE_COMMAND_PLAY_DEAD": "play_dead",
            "EVT_VOICE_COMMAND_BRING": "bring_object",
            "EVT_VOICE_COMMAND_FETCH": "fetch_object",
            "EVT_VOICE_COMMAND_STOP": "emergency_stop",
        }
        for event_type, behavior_name in cases.items():
            with self.subTest(event_type=event_type):
                spec = resolve_voice_command(
                    {
                        "event_type": event_type,
                        "intent_confidence": 0.99,
                    }
                )
                self.assertIsNotNone(spec)
                self.assertEqual(behavior_name, spec.behavior_name)

    def test_event_type_takes_precedence_over_mismatched_asr_text(self) -> None:
        spec = resolve_voice_command(
            {
                "event_type": "EVT_VOICE_COMMAND_SIT",
                "asr_text": "跟着我",
                "intent_confidence": 0.99,
            }
        )
        self.assertEqual("sit_down", spec.behavior_name)

    def test_ui_generic_command_is_published_as_full_event_type(self) -> None:
        command = build_custom_injection_command(
            "Audio",
            {
                "audio_event_type": "EVT_VOICE_COMMAND_KNOWN",
                "audio_command_id": "CMD_GIVE_PAW",
                "audio_asr_text": "握手",
                "audio_confidence": "0.98",
            },
        )
        payload = command.messages[0].payload
        self.assertEqual(
            "EVT_VOICE_COMMAND_GIVE_PAW",
            payload["event_type"],
        )

    def test_fetch_route_never_emits_synthetic_sub_actions(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "fetch",
                "behavior_name": "fetch_object",
                "timeout_sec": 6.0,
            }
        )
        for progress in (0.1, 0.4, 0.7, 1.0):
            with self.subTest(progress=progress):
                self.assertEqual(
                    "ACT_OBJECT_FETCH",
                    room.frame(plan, progress)["current_action"],
                )

    def test_follow_uses_exact_action_while_owner_moves(self) -> None:
        room = VirtualRoom()
        plan = room.build_plan(
            {
                "goal_id": "follow",
                "behavior_name": "follow_owner",
                "timeout_sec": 30.0,
            }
        )
        room.user_x += 80.0
        frame = room.follow_frame(plan, 0.1)
        self.assertEqual(
            "ACT_INTERACT_FOLLOW_OWNER",
            frame["current_action"],
        )


if __name__ == "__main__":
    unittest.main()
