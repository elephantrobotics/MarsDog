import unittest

from marsdog_sim2d.event_injector import (
    InjectionCommand,
    InjectionMessage,
    command_from_payload_preview,
)


class PayloadPreviewCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.command = InjectionCommand(
            "custom_audio",
            "Audio event",
            (
                InjectionMessage("/edited/one", {"value": 1}),
                InjectionMessage("/edited/two", {"active": False}),
            ),
        )

    def test_edited_preview_replaces_messages_and_preserves_command_metadata(
        self,
    ) -> None:
        edited = command_from_payload_preview(
            self.command,
            """[
                {"topic": "/edited/one", "payload": {"value": 2}},
                {"topic": "/edited/two", "payload": {"active": true}}
            ]""",
        )

        self.assertEqual(self.command.template_id, edited.template_id)
        self.assertEqual(self.command.label, edited.label)
        self.assertEqual(
            (
                InjectionMessage("/edited/one", {"value": 2}),
                InjectionMessage("/edited/two", {"active": True}),
            ),
            edited.messages,
        )

    def test_invalid_json_reports_line_and_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON 格式错误"):
            command_from_payload_preview(self.command, "[{")

    def test_preview_requires_topic_and_object_payload(self) -> None:
        invalid_previews = (
            "[]",
            '[{"payload": {}}]',
            '[{"topic": "/unknown", "payload": {}}]',
            '[{"topic": "/edited/one", "payload": []}]',
        )

        for preview in invalid_previews:
            with self.subTest(preview=preview):
                with self.assertRaises(ValueError):
                    command_from_payload_preview(self.command, preview)


if __name__ == "__main__":
    unittest.main()
