import json
import unittest

from marsdog_sim2d.behavior.behavior_contract import load_behavior_contract
from marsdog_sim2d.controllers.left_panel_controller import LeftPanelController
from marsdog_sim2d.simevent import event_injector
from marsdog_sim2d.simevent.injection import InjectionFormState
from marsdog_sim2d.simevent.sim_state import SimState


class LocalTactileSimulationTests(unittest.TestCase):
    def test_head_pet_builds_local_tactile_event(self) -> None:
        self.assertTrue(
            hasattr(event_injector, "build_local_tactile_event"),
            "local tactile event builder is missing",
        )
        event = event_injector.build_local_tactile_event(
            "EVT_TACTILE_HEAD_PET"
        )

        self.assertEqual("tactile_event", event.kind)
        self.assertEqual("local://tactile", event.topic)
        self.assertEqual("摸狗头", event.payload["label"])
        self.assertEqual(
            {"Joy": 25, "Calm": 15, "Excite": 5},
            event.payload["emotion_delta"],
        )
        self.assertEqual("expressCalmAlone", event.payload["local_behavior"])
        self.assertEqual("ACT_YAWN", event.payload["preferred_action"])

    def test_all_documented_tactile_events_have_runnable_local_reactions(self) -> None:
        expected_event_types = {
            "EVT_TACTILE_HEAD_PET",
            "EVT_TACTILE_NOSE_TOUCH",
            "EVT_TACTILE_EAR_TOUCH",
            "EVT_TACTILE_CHIN_RUB",
            "EVT_TACTILE_FACE_TOUCH",
            "EVT_TACTILE_MUZZLE_GRAB",
            "EVT_TACTILE_PUT_IN_MOUTH",
            "EVT_TACTILE_BODY_STROKE",
            "EVT_TACTILE_BELLY_TRUST",
            "EVT_TACTILE_BELLY_TENSE",
            "EVT_TACTILE_PAW_HOLD",
            "EVT_TACTILE_PAW_PAD_SLEEP",
            "EVT_TACTILE_PAW_PAD_WAKE",
            "EVT_TACTILE_HIP_ACCEPT",
            "EVT_TACTILE_HIP_RESIST",
            "EVT_TACTILE_TAIL_GRAB",
        }

        self.assertEqual(
            expected_event_types,
            set(event_injector.TACTILE_EVENT_SPECS),
        )

        contract = load_behavior_contract()
        for event_type in expected_event_types:
            event = event_injector.build_local_tactile_event(event_type)
            behavior = contract[event.payload["local_behavior"]]
            declared_actions = {
                action
                for stage in behavior.stages
                for action in stage.candidates
            }
            self.assertIn(event.payload["preferred_action"], declared_actions)

        tail_event = event_injector.build_local_tactile_event(
            "EVT_TACTILE_TAIL_GRAB"
        )
        self.assertEqual(
            {"Fear": 30, "Anxiety": 20, "Disgust": 10},
            tail_event.payload["emotion_delta"],
        )

    def test_tactile_panel_effect_is_local_only(self) -> None:
        form = InjectionFormState(
            group="Tactile",
            fields={"tactile_event_type": "EVT_TACTILE_BELLY_TRUST"},
        )
        controller = LeftPanelController(form)

        effect = controller.prepare_injection("Tactile")

        self.assertIsNone(effect.command)
        local_event = getattr(effect, "local_event", None)
        self.assertIsNotNone(local_event)
        self.assertEqual("EVT_TACTILE_BELLY_TRUST", local_event.payload["event_type"])
        self.assertEqual("expressJoyWithHuman", effect.local_behavior)
        self.assertEqual("ACT_SHOW_BELLY", effect.preferred_action)

    def test_sim_state_records_tactile_event_as_tac(self) -> None:
        state = SimState()
        event = event_injector.build_local_tactile_event(
            "EVT_TACTILE_MUZZLE_GRAB"
        )

        state.apply_event(event)

        tactile = getattr(state, "latest_tactile_event", None)
        self.assertIsNotNone(tactile)
        self.assertEqual("抓嘴筒子", tactile["label"])
        self.assertEqual("TAC", state.event_records[-1]["source"])
        self.assertIn("TAC", state.ui_log_filters)
        self.assertNotIn(event_injector.LOCAL_TACTILE_TOPIC, state.topic_stats)

    def test_edited_preview_rejects_unknown_tactile_event(self) -> None:
        form = InjectionFormState(
            group="Tactile",
            fields={"tactile_event_type": "EVT_TACTILE_HEAD_PET"},
        )
        controller = LeftPanelController(form)
        controller.refresh_payload_preview()
        preview = json.loads(form.payload_preview)
        preview[0]["payload"]["event_type"] = "EVT_TACTILE_UNKNOWN"
        form.payload_preview = json.dumps(preview)
        form.payload_preview_dirty = True

        try:
            effect = controller.prepare_injection("Tactile")
        except Exception as exc:  # test reports the missing boundary behavior
            self.fail(f"unknown tactile input escaped the controller: {exc}")

        self.assertIsNone(effect.local_event)
        self.assertEqual("Payload 无效", effect.confirmation["title"])


if __name__ == "__main__":
    unittest.main()
