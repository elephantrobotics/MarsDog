import unittest
from unittest.mock import Mock, patch

import arcade.gui

from marsdog_sim2d import config
from marsdog_sim2d.views import left_panel as left_panel_module
from marsdog_sim2d.components import AJsonPreviewer, BBox
from marsdog_sim2d.views.left_panel import (
    LeftControlPanel,
    _cursor_name_for_widgets,
    _display_options,
)
from marsdog_sim2d.sim_state import SimState


class NativePayloadEditorTests(unittest.TestCase):
    def _panel_without_window(self, state: SimState) -> LeftControlPanel:
        panel = object.__new__(LeftControlPanel)
        panel._state = state
        panel._syncing = False
        panel._action_handler = Mock()
        return panel

    def test_payload_change_updates_editable_state(self) -> None:
        state = SimState()
        panel = self._panel_without_window(state)

        panel._update_payload("edited payload")

        self.assertEqual("edited payload", state.ui_payload_preview)
        self.assertTrue(state.ui_payload_preview_dirty)

    def test_payload_change_respects_preview_limit(self) -> None:
        state = SimState()
        panel = self._panel_without_window(state)

        panel._update_payload("x" * (config.MAX_PAYLOAD_PREVIEW_CHARS + 5))

        self.assertEqual(
            config.MAX_PAYLOAD_PREVIEW_CHARS,
            len(state.ui_payload_preview),
        )

    def test_native_field_change_keeps_existing_preview_refresh_path(self) -> None:
        state = SimState()
        panel = self._panel_without_window(state)
        widget = Mock(text="owner")

        panel._update_field("audio_speaker_id", "owner", widget)

        self.assertEqual("owner", state.event_injector_fields["audio_speaker_id"])
        panel._action_handler.assert_called_once_with(
            {"action": "field_changed", "field_id": "audio_speaker_id"}
        )

    def test_duplicate_labels_keep_distinct_dropdown_values(self) -> None:
        raw_to_display, display_to_raw = _display_options(
            ("CMD_HAND", "CMD_GIVE_PAW")
        )

        self.assertNotEqual(
            raw_to_display["CMD_HAND"],
            raw_to_display["CMD_GIVE_PAW"],
        )
        self.assertEqual(
            {"CMD_HAND", "CMD_GIVE_PAW"},
            set(display_to_raw.values()),
        )

    def test_mouse_cursor_matches_native_control_type(self) -> None:
        text_input = object.__new__(arcade.gui.UIInputText)
        button = object.__new__(arcade.gui.UIFlatButton)
        label = object.__new__(arcade.gui.UILabel)

        self.assertEqual("text", _cursor_name_for_widgets([text_input]))
        self.assertEqual("hand", _cursor_name_for_widgets([button]))
        self.assertEqual("default", _cursor_name_for_widgets([label]))

    def test_published_topics_wrap_and_reserve_each_topic_line(self) -> None:
        state = SimState()
        state.ui_preview_topics = [
            "/internal_need/state",
            "/internal_need/signal_event",
        ]
        panel = self._panel_without_window(state)
        panel._manager = Mock()
        panel._add_label = Mock(return_value=188.0)
        panel._add_label_widget = Mock(return_value=Mock())
        panel._add_button = Mock()

        with patch.object(left_panel_module, "AJsonPreviewer"):
            panel._add_payload_section(
                10.0,
                200.0,
                240.0,
                20.0,
                "发送事件",
                "send_event",
            )

        topic_call, payload_title_call = (
            panel._add_label_widget.call_args_list[:2]
        )
        self.assertEqual(
            2 * config.LINE_HEIGHT,
            topic_call.args[4],
        )
        self.assertTrue(topic_call.kwargs["multiline"])
        self.assertLessEqual(
            payload_title_call.args[2] + payload_title_call.args[4],
            topic_call.args[2],
        )

        initial_signature = panel._layout_signature()
        state.ui_preview_topics.append("/emotion/state")
        self.assertNotEqual(initial_signature, panel._layout_signature())

    def test_payload_section_uses_preview_button_without_inline_widget(self) -> None:
        state = SimState()
        state.ui_payload_preview = '{"ready": true}'
        panel = self._panel_without_window(state)
        panel._manager = Mock()
        panel._add_label = Mock(return_value=188.0)
        panel._add_label_widget = Mock(return_value=Mock())
        panel._add_button = Mock()
        with patch.object(left_panel_module, "AJsonPreviewer") as previewer_type:
            panel._add_payload_section(
                10.0,
                200.0,
                240.0,
                20.0,
                "发送事件",
                "send_event",
            )

        previewer_type.assert_not_called()
        self.assertEqual(
            config.FONT_SIZE_AUX,
            panel._add_label.call_args.kwargs["font_size"],
        )
        self.assertTrue(
            all(
                label_call.kwargs["font_size"] == config.FONT_SIZE_AUX
                for label_call in panel._add_label_widget.call_args_list
            )
        )

        self.assertEqual(
            ["预览 Payload", "发送事件"],
            [
                button_call.args[4]
                for button_call in panel._add_button.call_args_list
            ],
        )
        self.assertEqual(
            ["show_payload_preview", "send_event"],
            [
                button_call.args[5]
                for button_call in panel._add_button.call_args_list
            ],
        )
        preview_button_call = panel._add_button.call_args_list[0]
        label_width = min(82.0, 240.0 * 0.34)
        self.assertEqual(10.0 + label_width, preview_button_call.args[0])
        self.assertEqual(240.0 - label_width, preview_button_call.args[2])

    def test_payload_actions_remain_with_tight_space(self) -> None:
        state = SimState()
        panel = self._panel_without_window(state)
        panel._manager = Mock()
        panel._add_label = Mock(return_value=120.0)
        panel._add_label_widget = Mock(return_value=Mock())
        panel._add_button = Mock()

        with patch.object(left_panel_module, "AJsonPreviewer") as previewer_type:
            panel._add_payload_section(
                10.0,
                132.0,
                240.0,
                20.0,
                "发送事件",
                "send_event",
            )

        previewer_type.assert_not_called()
        self.assertEqual(2, panel._add_label_widget.call_count)
        self.assertEqual(
            ["预览 Payload", "发送事件"],
            [
                button_call.args[4]
                for button_call in panel._add_button.call_args_list
            ],
        )
        action_button_call = panel._add_button.call_args_list[-1]
        self.assertGreaterEqual(action_button_call.args[1], 20.0)

    def test_payload_preview_sync_keeps_json_formatting_path(self) -> None:
        state = SimState()
        state.ui_payload_preview = '{"ready": true}'
        panel = self._panel_without_window(state)
        panel._payload_widget = object.__new__(AJsonPreviewer)
        panel._payload_title = None
        panel._topic_label = None
        panel._input_widgets = {}
        panel._dropdown_widgets = {}

        with patch.object(AJsonPreviewer, "set_value") as set_value:
            panel._sync_dynamic_values()

        set_value.assert_called_once_with('{"ready": true}')

    def test_payload_preview_dialog_uses_json_previewer(self) -> None:
        state = SimState()
        state.ui_payload_preview = '{"ready": true}'
        panel = self._panel_without_window(state)
        panel._manager = Mock()
        panel._add_label_widget = Mock(side_effect=(Mock(), Mock()))
        panel._add_button = Mock()
        surface = Mock()
        surface.with_background.return_value = surface
        previewer = Mock(spec=AJsonPreviewer)

        with (
            patch.object(
                left_panel_module.arcade.gui,
                "UIWidget",
                return_value=surface,
            ),
            patch.object(
                left_panel_module,
                "AJsonPreviewer",
                return_value=previewer,
            ) as previewer_type,
        ):
            panel._build_payload_dialog()

        width = min(780.0, config.WINDOW_WIDTH - 80)
        height = min(
            560.0,
            config.TOP_BAR_BOTTOM - config.BOTTOM_LOG_HEIGHT - 40,
        )
        x = (config.WINDOW_WIDTH - width) / 2
        y = config.BOTTOM_LOG_HEIGHT + (
            config.TOP_BAR_BOTTOM - config.BOTTOM_LOG_HEIGHT - height
        ) / 2
        previewer_type.assert_called_once_with(
            BBox(x + 14, y + 14, width - 28, height - 82),
            '{"ready": true}',
            font_size=10,
            size_hint=None,
        )
        panel._manager.add.assert_any_call(
            previewer,
            layer=arcade.gui.UIManager.OVERLAY_LAYER,
        )

    def test_payload_dialog_keeps_base_panel_rendered(self) -> None:
        state = SimState()
        state.ui_payload_preview_expanded = True
        panel = self._panel_without_window(state)
        panel._manager = Mock()
        panel._input_widgets = {}
        panel._dropdown_widgets = {}
        panel._rebuild_requested = True
        build_order = []
        panel._build_panel = Mock(side_effect=lambda: build_order.append("panel"))
        panel._build_collapsed_panel = Mock()
        panel._build_payload_dialog = Mock(
            side_effect=lambda: build_order.append("dialog")
        )

        panel._rebuild(("payload-dialog",))

        self.assertEqual(["panel", "dialog"], build_order)
        panel._build_collapsed_panel.assert_not_called()

class NativeFormLayoutTests(unittest.TestCase):
    def _panel(self) -> LeftControlPanel:
        panel = object.__new__(LeftControlPanel)
        panel._manager = Mock()
        panel._input_widgets = {}
        panel._dropdown_widgets = {}
        panel._syncing = False
        return panel

    @staticmethod
    def _interactive_widget() -> Mock:
        widget = Mock()
        widget.with_background.return_value = widget
        widget.event.side_effect = lambda _event_name: lambda callback: callback
        return widget

    def test_input_and_dropdown_rows_use_form_tokens(self) -> None:
        panel = self._panel()
        input_widget = self._interactive_widget()
        input_widget.doc = Mock()
        input_widget.layout = Mock()
        input_label = Mock()

        with (
            patch.object(
                panel,
                "_add_label_widget",
                return_value=input_label,
            ) as add_input_label,
            patch.object(
                left_panel_module.arcade.gui,
                "UIInputText",
                return_value=input_widget,
            ) as input_type,
        ):
            input_top = panel._add_input_row(
                "audio_speaker_id",
                "说话人",
                "owner",
                10,
                200,
                240,
            )

        self.assertEqual(
            config.CONTROL_HEIGHT,
            input_type.call_args.kwargs["height"],
        )
        self.assertEqual(
            config.FONT_SIZE_AUX,
            add_input_label.call_args.kwargs["font_size"],
        )
        self.assertEqual(
            config.CONTROL_HEIGHT,
            add_input_label.call_args.args[4],
        )
        self.assertEqual(
            200 - config.CONTROL_HEIGHT - config.FORM_ROW_GAP,
            input_top,
        )

        dropdown_widget = self._interactive_widget()
        dropdown_label = Mock()
        with (
            patch.object(
                panel,
                "_add_label_widget",
                return_value=dropdown_label,
            ) as add_dropdown_label,
            patch.object(
                left_panel_module.arcade.gui,
                "UIDropdown",
                return_value=dropdown_widget,
            ) as dropdown_type,
        ):
            dropdown_top = panel._add_dropdown_row(
                "event_source",
                "事件来源",
                "Audio",
                ("Audio", "Vision"),
                10,
                200,
                240,
                target="event_group",
            )

        self.assertEqual(
            config.CONTROL_HEIGHT,
            dropdown_type.call_args.kwargs["height"],
        )
        self.assertEqual(
            config.FONT_SIZE_AUX,
            add_dropdown_label.call_args.kwargs["font_size"],
        )
        self.assertEqual(
            config.CONTROL_HEIGHT,
            add_dropdown_label.call_args.args[4],
        )
        self.assertEqual(
            200 - config.CONTROL_HEIGHT - config.FORM_ROW_GAP,
            dropdown_top,
        )

    def test_action_row_uses_form_tokens(self) -> None:
        panel = self._panel()
        panel._add_button = Mock()

        action_top = panel._add_action_row(
            10,
            200,
            240,
            "在场景中放置目标",
            "placement_mode",
            group="Vision",
        )

        self.assertEqual(
            config.BUTTON_HEIGHT,
            panel._add_button.call_args.args[3],
        )
        self.assertEqual(
            200 - config.BUTTON_HEIGHT - config.FORM_ROW_GAP,
            action_top,
        )

    def test_notice_uses_stable_title_and_detail_rows(self) -> None:
        panel = self._panel()
        background = Mock()
        background.with_background.return_value = background
        title_label = Mock()
        detail_label = Mock()
        with (
            patch.object(
                left_panel_module.arcade.gui,
                "UIWidget",
                return_value=background,
            ) as widget_type,
            patch.object(
                panel,
                "_add_label_widget",
                side_effect=(title_label, detail_label),
            ) as add_notice_label,
        ):
            notice_top = panel._add_notice(
                "推导等级：HIGH",
                "NEED_HUNGER",
                10,
                200,
                240,
            )

        notice_height = 2 * config.LINE_HEIGHT + 2 * config.SPACE_XS
        self.assertEqual(
            notice_height,
            widget_type.call_args.kwargs["height"],
        )
        self.assertEqual(
            200 - notice_height - config.FORM_ROW_GAP,
            notice_top,
        )
        self.assertEqual(
            [background, title_label, detail_label],
            [
                manager_call.args[0]
                for manager_call in panel._manager.add.call_args_list
            ],
        )
        title_call, detail_call = add_notice_label.call_args_list
        self.assertEqual("推导等级：HIGH", title_call.args[0])
        self.assertEqual("NEED_HUNGER", detail_call.args[0])
        self.assertEqual(10 + config.SPACE_SM, title_call.args[1])
        self.assertEqual(10 + config.SPACE_SM, detail_call.args[1])
        self.assertEqual(config.LINE_HEIGHT, title_call.args[4])
        self.assertEqual(config.LINE_HEIGHT, detail_call.args[4])
        self.assertEqual(config.COLORS["text"], title_call.kwargs["color"])
        self.assertEqual(
            config.COLORS["muted_text"],
            detail_call.kwargs["color"],
        )

    def test_notice_without_detail_uses_single_row(self) -> None:
        panel = self._panel()
        background = Mock()
        background.with_background.return_value = background
        title_label = Mock()
        with (
            patch.object(
                left_panel_module.arcade.gui,
                "UIWidget",
                return_value=background,
            ) as widget_type,
            patch.object(
                panel,
                "_add_label_widget",
                return_value=title_label,
            ) as add_notice_label,
        ):
            notice_top = panel._add_notice(
                "仅模拟状态快照",
                "",
                10,
                200,
                240,
            )

        self.assertEqual(
            config.CONTROL_HEIGHT,
            widget_type.call_args.kwargs["height"],
        )
        self.assertEqual(1, add_notice_label.call_count)
        self.assertEqual(
            200 - config.CONTROL_HEIGHT - config.FORM_ROW_GAP,
            notice_top,
        )

if __name__ == "__main__":
    unittest.main()
