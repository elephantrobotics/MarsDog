import json
import unittest

from marsdog_sim2d import config
from marsdog_sim2d.controllers.left_panel_controller import (
    LeftPanelController,
    show_toilet_training_control,
)
from marsdog_sim2d.simevent.injection import InjectionFormState


class LeftPanelControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.form = InjectionFormState()
        self.controller = LeftPanelController(self.form)

    def test_field_change_updates_form_and_preview(self) -> None:
        effect = self.controller.handle_action(
            {
                "action": "field_changed",
                "field_id": "audio_speaker_id",
                "value": "owner",
            }
        )

        self.assertIsNotNone(effect)
        self.assertEqual("owner", self.form.fields["audio_speaker_id"])
        self.assertFalse(self.form.payload_preview_dirty)

    def test_payload_change_is_owned_by_controller(self) -> None:
        self.controller.handle_action(
            {
                "action": "payload_changed",
                "value": "x" * (config.MAX_PAYLOAD_PREVIEW_CHARS + 5),
            }
        )

        self.assertEqual(
            config.MAX_PAYLOAD_PREVIEW_CHARS,
            len(self.form.payload_preview),
        )
        self.assertTrue(self.form.payload_preview_dirty)

    def test_safe_scenario_returns_command_without_confirmation(self) -> None:
        effect = self.controller.handle_action(
            {"action": "scenario", "scenario_id": "owner_calls"}
        )

        self.assertIsNotNone(effect)
        self.assertIsNone(effect.confirmation)
        self.assertIsNotNone(effect.command)

    def test_known_voice_command_requires_visible_owner(self) -> None:
        self.form.fields.update(
            audio_event_type="EVT_VOICE_COMMAND_KNOWN",
            audio_command_id="CMD_FOLLOW",
        )

        effect = self.controller.prepare_injection("Audio")

        self.assertIsNone(effect.command)
        self.assertEqual("没有识别到主人", effect.confirmation["message"])

    def test_stop_during_internal_need_is_not_returned_for_queueing(self) -> None:
        self.form.fields.update(
            audio_event_type="EVT_VOICE_COMMAND_KNOWN",
            audio_command_id="CMD_STOP",
        )

        effect = self.controller.prepare_injection(
            "Audio",
            user_visible=True,
            internal_need_active=True,
        )

        self.assertTrue(effect.stop_requested)
        self.assertIsNone(effect.command)
        self.assertEqual(
            "内部需求正在执行，停止指令已忽略",
            effect.confirmation["message"],
        )

    def test_toilet_training_control_is_local_only(self) -> None:
        self.assertTrue(show_toilet_training_control("Need", "Bladder"))
        self.assertFalse(show_toilet_training_control("Need", "Hunger"))
        self.assertFalse(show_toilet_training_control("Emotion", "Bladder"))
        self.assertEqual("false", self.form.fields["toilet_spot_taught"])

        self.form.fields.update(
            need_demand="Bladder",
            need_value="82",
            toilet_spot_taught="true",
        )
        effect = self.controller.prepare_injection("Need")

        self.assertIsNotNone(effect.command)
        for message in effect.command.messages:
            self.assertNotIn(
                "toilet_spot_taught",
                json.dumps(message.payload, ensure_ascii=False),
            )

    def test_damage_above_threshold_requests_local_safety_takeover(self) -> None:
        self.form.fields.update(
            damage_event_type="EVT_DAMAGE_LIGHT_IMPACT",
            damage_risk_score="75",
            damage_confirmed="false",
        )

        effect = self.controller.prepare_injection("Damage")

        self.assertIsNone(effect.command)
        self.assertEqual("external_damage_event", effect.local_event.kind)
        self.assertEqual("D2", effect.local_event.payload["risk_code"])
        self.assertEqual(
            effect.local_event.payload,
            getattr(effect, "external_damage", None),
        )

    def test_damage_at_or_below_40_only_records_local_event(self) -> None:
        self.form.fields.update(
            damage_event_type="EVT_DAMAGE_SHORT_PUSH_PULL",
            damage_risk_score="40",
            damage_confirmed="false",
        )

        effect = self.controller.prepare_injection("Damage")

        self.assertIsNotNone(effect.local_event)
        self.assertEqual("NONE", effect.local_event.payload["risk_code"])
        self.assertIsNone(getattr(effect, "external_damage", None))

    def test_edited_damage_preview_does_not_treat_false_text_as_true(self) -> None:
        self.form.group = "Damage"
        self.form.fields.update(
            damage_event_type="EVT_DAMAGE_LIGHT_IMPACT",
            damage_risk_score="20",
            damage_confirmed="unconfirmed",
        )
        self.controller.refresh_payload_preview()
        preview = json.loads(self.form.payload_preview)
        preview[0]["payload"]["confirmed"] = "false"
        self.form.payload_preview = json.dumps(preview)
        self.form.payload_preview_dirty = True

        effect = self.controller.prepare_injection("Damage")

        self.assertIsNotNone(effect.local_event)
        self.assertFalse(effect.local_event.payload["confirmed"])
        self.assertEqual("NONE", effect.local_event.payload["risk_code"])
        self.assertIsNone(effect.external_damage)


if __name__ == "__main__":
    unittest.main()
