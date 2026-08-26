import unittest
from unittest.mock import Mock, call, patch

from marsdog_sim2d.views import widgets as widgets_module
from marsdog_sim2d.components import widget as widget_module
from marsdog_sim2d.components.widget import (
    AButton,
    AJsonEditor,
    AJsonPreviewer,
    AMessageBox,
    ATopicChip,
    BBox,
    _format_json,
)
from marsdog_sim2d.sim_state import SimState
from marsdog_sim2d.views.widgets import StatusWidgets


class JsonPreviewFormattingTests(unittest.TestCase):
    def test_formats_json_with_unicode_and_indentation(self) -> None:
        formatted = _format_json({"message": "你好", "count": 2}, 200)

        self.assertIn('"message": "你好"', formatted)
        self.assertIn('\n  "count": 2', formatted)

    def test_plain_diagnostic_text_is_preserved(self) -> None:
        self.assertEqual(
            "Preview unavailable: invalid payload",
            _format_json("Preview unavailable: invalid payload", 200),
        )

    def test_long_preview_is_bounded_and_marked(self) -> None:
        formatted = _format_json({"payload": "x" * 200}, 60)

        self.assertEqual(60, len(formatted))
        self.assertTrue(formatted.endswith("…（内容已截断）"))


class JsonPreviewWidgetTests(unittest.TestCase):
    def test_message_box_applies_cjk_font_to_all_text(self) -> None:
        title_label = Mock()
        message_area = Mock()
        frame = Mock()
        button_group = Mock()
        buttons = (Mock(), Mock())

        with (
            patch.object(
                widget_module.arcade.gui.UIAnchorLayout,
                "__init__",
                return_value=None,
            ),
            patch.object(AMessageBox, "register_event_type"),
            patch.object(AMessageBox, "with_background"),
            patch.object(AMessageBox, "add"),
            patch.object(
                widget_module.arcade.gui,
                "UIAnchorLayout",
                return_value=frame,
            ) as layout_type,
            patch.object(
                widget_module.arcade.gui,
                "UILabel",
                return_value=title_label,
            ) as label_type,
            patch.object(
                widget_module.arcade.gui,
                "UITextArea",
                return_value=message_area,
            ) as text_area_type,
            patch.object(
                widget_module.arcade.gui,
                "UIBoxLayout",
                return_value=button_group,
            ),
            patch.object(
                widget_module,
                "AButton",
                side_effect=buttons,
            ) as button_type,
            patch.object(
                widget_module,
                "measure_text",
                side_effect=lambda _text, **kwargs: (
                    80,
                    120 if kwargs.get("multiline") else 18,
                ),
            ),
        ):
            AMessageBox(
                width=390.0,
                height=190.0,
                title="确认调试注入",
                message_text="此操作可能触发行为",
                buttons=("取消", "确认发送"),
            )

        self.assertEqual(
            widget_module.config.FONT_NAMES,
            label_type.call_args.kwargs["font_name"],
        )
        self.assertEqual(
            widget_module.config.FONT_NAMES,
            text_area_type.call_args.kwargs["font_name"],
        )
        rendered_message = text_area_type.call_args.kwargs["text"]
        self.assertNotIn("\u200b", rendered_message)
        self.assertEqual("此操作可能触发行为", rendered_message)
        self.assertEqual(
            float(widget_module.config.LINE_HEIGHT),
            text_area_type.call_args.kwargs["scroll_speed"],
        )
        frame_size = layout_type.call_args.kwargs
        self.assertEqual(320.0, frame_size["width"])
        self.assertGreater(frame_size["height"], 190.0)
        self.assertEqual(2, button_type.call_count)
        self.assertTrue(button_type.call_args_list[-1].kwargs["primary"])

    def test_message_box_wraps_with_newlines_without_hidden_glyphs(self) -> None:
        with patch.object(
            widget_module,
            "measure_text",
            side_effect=lambda text, **_kwargs: (len(text) * 10, 18),
        ):
            wrapped = widget_module._wrap_message_text(
                "中文换行",
                maximum_width=25,
                font_size=12,
            )

        self.assertEqual("中文\n换行", wrapped)
        self.assertNotIn("\u200b", wrapped)

    def test_topic_chip_builds_native_dot_and_text_labels(self) -> None:
        bounds = BBox(10.0, 20.0, 118.0, 31.0)
        dot_label = Mock()
        text_label = Mock()

        with (
            patch.object(
                widget_module.arcade.gui.UIAnchorLayout,
                "__init__",
                return_value=None,
            ) as layout_init,
            patch.object(widget_module.arcade.gui.UIAnchorLayout, "add") as add,
            patch.object(
                widget_module.arcade.gui.UIAnchorLayout,
                "with_background",
            ),
            patch.object(
                widget_module.arcade.gui.UIAnchorLayout,
                "with_border",
            ),
            patch.object(
                widget_module.arcade.gui,
                "UILabel",
                side_effect=(dot_label, text_label),
            ) as label_type,
        ):
            chip = ATopicChip(bounds, "VIS  正常", (10, 20, 30))

        layout_kwargs = layout_init.call_args.kwargs
        self.assertEqual((10.0, 20.0), (layout_kwargs["x"], layout_kwargs["y"]))
        self.assertEqual(
            (118.0, 31.0),
            (layout_kwargs["width"], layout_kwargs["height"]),
        )
        dot_kwargs = label_type.call_args_list[0].kwargs
        text_kwargs = label_type.call_args_list[1].kwargs
        self.assertEqual("●", dot_kwargs["text"])
        self.assertEqual((10, 20, 30, 255), dot_kwargs["text_color"])
        self.assertNotIn("height", dot_kwargs)
        self.assertEqual("VIS  正常", text_kwargs["text"])
        self.assertEqual("center", text_kwargs["align"])
        self.assertNotIn("height", text_kwargs)
        self.assertEqual(2, add.call_count)
        self.assertTrue(
            all(
                call.kwargs["anchor_y"] == "center"
                for call in add.call_args_list
            )
        )
        self.assertEqual(("VIS  正常", (10, 20, 30)), chip.appearance)

    def test_editor_constructor_builds_native_multiline_input(self) -> None:
        bounds = BBox(10.0, 20.0, 320.0, 180.0)
        payload = '{"editing":'

        with (
            patch.object(
                widget_module.arcade.gui.UIInputText,
                "__init__",
                return_value=None,
            ) as input_init,
            patch.object(
                widget_module.arcade.gui.UIInputText,
                "with_background",
            ),
        ):
            AJsonEditor(bounds, payload)

        kwargs = input_init.call_args.kwargs
        self.assertEqual((10.0, 20.0), (kwargs["x"], kwargs["y"]))
        self.assertEqual((320.0, 180.0), (kwargs["width"], kwargs["height"]))
        self.assertEqual(payload, kwargs["text"])
        self.assertTrue(kwargs["multiline"])

    def test_button_constructor_builds_native_flat_button(self) -> None:
        bounds = BBox(10.0, 20.0, 92.0, 26.0)

        with patch.object(
            widget_module.arcade.gui.UIFlatButton,
            "__init__",
            return_value=None,
        ) as flat_button_init:
            AButton(bounds, "复制 JSON")

        kwargs = flat_button_init.call_args.kwargs
        self.assertEqual((10.0, 20.0), (kwargs["x"], kwargs["y"]))
        self.assertEqual((92.0, 26.0), (kwargs["width"], kwargs["height"]))
        self.assertEqual("复制 JSON", kwargs["text"])
        self.assertEqual(
            {"normal", "hover", "press", "disabled"},
            set(kwargs["style"]),
        )

    def test_constructor_builds_native_scrollable_text_area(self) -> None:
        bounds = BBox(10.0, 20.0, 320.0, 180.0)

        with (
            patch.object(
                widget_module.arcade.gui.UITextArea,
                "__init__",
                return_value=None,
            ) as text_area_init,
            patch.object(
                widget_module.arcade.gui.UITextArea,
                "with_background",
            ),
            patch.object(
                widget_module.arcade.gui.UITextArea,
                "with_border",
            ),
            patch.object(
                widget_module.arcade.gui.UITextArea,
                "with_padding",
            ),
        ):
            AJsonPreviewer(bounds, {"ready": True})

        kwargs = text_area_init.call_args.kwargs
        self.assertEqual((10.0, 20.0), (kwargs["x"], kwargs["y"]))
        self.assertEqual((320.0, 180.0), (kwargs["width"], kwargs["height"]))
        self.assertTrue(kwargs["multiline"])
        self.assertEqual(24.0, kwargs["scroll_speed"])
        self.assertIn('"ready": true', kwargs["text"])

    def test_set_value_skips_unchanged_glyph_layout(self) -> None:
        previewer = Mock(
            text='{\n  "ready": true\n}',
            _max_chars=200,
        )

        changed = AJsonPreviewer.set_value(previewer, {"ready": True})

        self.assertFalse(changed)

    def test_event_detail_registers_json_previewer_on_overlay_layer(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        widgets = StatusWidgets(manager)
        state = SimState()
        state.ui_selected_event_id = 7
        state.event_records = [
            {
                "id": 7,
                "payload": {"message": "你好"},
            }
        ]
        previewer = Mock(spec=AJsonPreviewer)

        with patch.object(
            widgets_module,
            "AJsonPreviewer",
            return_value=previewer,
        ) as previewer_type:
            widgets._sync_event_payload_previewer(state)

        x, top, width, height = widgets_module._event_detail_bounds()
        previewer_type.assert_called_once_with(
            BBox(x + 14, top - height + 12, width - 28, height - 78),
            {"message": "你好"},
        )
        manager.add.assert_called_once_with(
            previewer,
            layer=widget_module.arcade.gui.UIManager.OVERLAY_LAYER,
        )

        previewer.bbox = BBox(
            x + 14,
            top - height + 12,
            width - 28,
            height - 78,
        )
        manager.reset_mock()
        manager.walk_widgets.return_value = ()

        widgets._sync_event_payload_previewer(state)

        manager.add.assert_called_once_with(
            previewer,
            layer=widget_module.arcade.gui.UIManager.OVERLAY_LAYER,
        )

    def test_event_detail_actions_use_native_buttons(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        action_handler = Mock()
        widgets = StatusWidgets(manager, action_handler)
        state = SimState()
        state.ui_selected_event_id = 7
        state.event_records = [
            {
                "id": 7,
                "source": "EXEC",
                "event": "action_feedback",
                "topic": "/debug/execute_behavior/feedback",
            }
        ]
        callbacks = {}

        class FakeNativeButton:
            def __init__(self) -> None:
                self.bbox = None

            def event(self, event_name: str):
                self.assert_event_name(event_name)

                def register(callback):
                    callbacks[id(self)] = callback
                    return callback

                return register

            @staticmethod
            def assert_event_name(event_name: str) -> None:
                if event_name != "on_click":
                    raise AssertionError(f"Unexpected event: {event_name}")

        copy_button = FakeNativeButton()
        close_button = FakeNativeButton()

        with patch.object(
            widgets_module,
            "AButton",
            side_effect=(copy_button, close_button),
        ) as button_type:
            widgets._sync_event_detail_buttons(state)

        x, top, width, _height = widgets_module._event_detail_bounds()
        close_bounds = BBox(x + width - 72.0, top - 39.0, 58.0, 26.0)
        copy_bounds = BBox(
            close_bounds.x - widgets_module.config.SPACE_SM - 92.0,
            top - 39.0,
            92.0,
            26.0,
        )
        button_type.assert_has_calls(
            [
                call(copy_bounds, "复制到剪切板"),
                call(close_bounds, "关闭"),
            ]
        )
        self.assertEqual(2, manager.add.call_count)

        callbacks[id(copy_button)](Mock())
        callbacks[id(close_button)](Mock())

        action_handler.assert_has_calls(
            [
                call("copy_event_payload"),
                call("close_event_detail"),
            ]
        )


if __name__ == "__main__":
    unittest.main()
