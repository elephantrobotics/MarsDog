import unittest
from unittest.mock import Mock, patch

from marsdog_sim2d import config
from marsdog_sim2d.views import widgets as widgets_module
from marsdog_sim2d.components import ATopicChip, drawing
from marsdog_sim2d.sim_state import SimState
from marsdog_sim2d.views.widgets import StatusWidgets


class TextCacheTests(unittest.TestCase):
    def test_identical_draws_reuse_arcade_text_object(self) -> None:
        window = Mock()
        window.ctx = object()

        with (
            patch.object(drawing.arcade, "get_window", return_value=window),
            patch.object(drawing.arcade, "Text") as text_type,
        ):
            drawing.draw_text("cached label", 10, 20, (1, 2, 3), 12)
            drawing.draw_text("cached label", 10, 20, (1, 2, 3), 12)

        text_type.assert_called_once()
        self.assertEqual(text_type.return_value.draw.call_count, 2)

    def test_measure_text_returns_arcade_content_size(self) -> None:
        window = Mock()
        window.ctx = object()
        text_object = Mock(content_size=(84, 27))

        with (
            patch.object(drawing.arcade, "get_window", return_value=window),
            patch.object(
                drawing,
                "_create_text",
                return_value=text_object,
            ),
        ):
            size = drawing.measure_text(
                "中英文 mixed",
                font_size=10,
                width=120,
                multiline=True,
            )

        self.assertEqual((84, 27), size)


class SceneControlLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._layout = (
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT,
            config.LEFT_PANEL_WIDTH <= config.COLLAPSED_LEFT_PANEL_WIDTH + 1,
            config.BOTTOM_LOG_HEIGHT,
        )

    def tearDown(self) -> None:
        config.update_layout(*self._layout)

    def _draw_controls(self, width: int) -> list:
        config.update_layout(width, 820, False, config.DEFAULT_LOG_HEIGHT)
        widgets = object.__new__(StatusWidgets)
        widgets._button = Mock()
        state = SimState(ui_pending_placement={"group": "Audio"})

        StatusWidgets._draw_scene_controls(widgets, state)
        return widgets._button.call_args_list

    def test_minimum_width_uses_non_overlapping_icon_controls(self) -> None:
        calls = self._draw_controls(config.MIN_WINDOW_WIDTH)

        calls_by_action = {
            call.args[5]: call
            for call in calls
        }
        toolbar_left = min(call.args[0] for call in calls)
        header_right = (
            config.WORLD_LEFT
            + config.SPACE_LG
            + config.scene_header_width()
        )
        self.assertGreaterEqual(
            toolbar_left,
            header_right + config.SPACE_MD,
        )
        self.assertTrue(all(call.kwargs["icon_only"] for call in calls))
        self.assertTrue(all(call.args[4] == "" for call in calls))
        self.assertTrue(all(call.kwargs["tooltip"] for call in calls))
        self.assertEqual(1, len({call.args[1] for call in calls}))

        food_call = calls_by_action["toggle_bowl_food"]
        audio_call = calls_by_action["placement_mode"]
        self.assertEqual(food_call.args[1], audio_call.args[1])
        self.assertLess(audio_call.args[0], food_call.args[0])
        self.assertEqual("Audio", audio_call.kwargs["group"])
        self.assertTrue(audio_call.kwargs["active"])
        self.assertEqual("sound", audio_call.kwargs["icon"])
        self.assertEqual("bowl", food_call.kwargs["icon"])

        expected_icons = {
            "toggle_abnormal_simulation": "warning",
            "toggle_virtual_user": "user",
            "toggle_fov": "eye",
        }
        for action, icon in expected_icons.items():
            self.assertEqual(icon, calls_by_action[action].kwargs["icon"])

    def test_wide_layout_keeps_icon_and_text_controls(self) -> None:
        calls = self._draw_controls(1600)

        self.assertTrue(all(not call.kwargs["icon_only"] for call in calls))
        self.assertEqual(
            ["放置声源", "放粮", "异常模拟", "添加人物", "视野开"],
            [call.args[4] for call in calls],
        )


class EventStreamLayoutTests(unittest.TestCase):
    def test_toolbar_uses_one_native_horizontal_layout(self) -> None:
        widgets = object.__new__(StatusWidgets)
        widgets._event_toolbar_layout = None
        widgets._event_toolbar_slots = {}
        widgets._hit = Mock()
        widgets._chip = Mock()
        widgets._small_button = Mock()
        widgets._search_input = Mock()

        with (
            patch.object(widgets_module, "draw_text") as draw_text,
            patch.object(widgets_module.arcade, "draw_line"),
            patch.object(
                widgets_module.arcade,
                "draw_lbwh_rectangle_filled",
            ),
        ):
            StatusWidgets._draw_event_stream(widgets, SimState())

        title_call = next(
            call
            for call in draw_text.call_args_list
            if call.args[0] == "事件流"
        )
        self.assertEqual(14, title_call.args[1])
        self.assertEqual("left", title_call.kwargs["anchor_x"])
        self.assertEqual("center", title_call.kwargs["anchor_y"])

        self.assertIsInstance(
            widgets._event_toolbar_layout,
            widgets_module.arcade.gui.UIBoxLayout,
        )
        toolbar_center_y = widgets._event_toolbar_layout.center_y
        self.assertEqual(toolbar_center_y, title_call.args[2])
        self.assertTrue(all(
            chip_call.args[1] - 23 / 2 == toolbar_center_y
            for chip_call in widgets._chip.call_args_list
        ))
        self.assertTrue(all(
            button_call.args[1] + button_call.args[3] / 2
            == toolbar_center_y
            for button_call in widgets._small_button.call_args_list
        ))
        search_call = widgets._search_input.call_args
        self.assertEqual(
            toolbar_center_y,
            search_call.args[2] + 24 / 2,
        )
        self.assertEqual(
            ["暂停", "清空", "自动"],
            [call.args[4] for call in widgets._small_button.call_args_list],
        )

    def test_toolbar_layout_stays_on_one_row_at_minimum_width(self) -> None:
        widgets = object.__new__(StatusWidgets)
        widgets._event_toolbar_layout = None
        widgets._event_toolbar_slots = {}

        with patch.object(config, "WINDOW_WIDTH", config.MIN_WINDOW_WIDTH):
            slots = widgets._sync_event_toolbar_layout(
                config.BOTTOM_LOG_HEIGHT,
            )

        ordered_slots = [
            slots["title"],
            *(slots[f"source:{source}"] for source in widgets_module.LOG_SOURCES),
            slots["search"],
            slots["pause"],
            slots["clear"],
            slots["auto"],
        ]
        center_y = widgets._event_toolbar_layout.center_y
        self.assertTrue(all(
            slot.center_y == center_y
            for slot in ordered_slots
        ))
        self.assertTrue(all(
            left_slot.right <= right_slot.left
            for left_slot, right_slot in zip(
                ordered_slots,
                ordered_slots[1:],
            )
        ))
        self.assertEqual(
            config.MIN_WINDOW_WIDTH - 14,
            slots["auto"].right,
        )


class NativeEventSearchTests(unittest.TestCase):
    def test_search_uses_native_input_and_updates_filter_state(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        widgets = StatusWidgets(manager)
        state = SimState()
        input_widget = Mock(spec=widgets_module.arcade.gui.UIInputText)
        input_widget.active = False
        input_widget.text = "搜索事件"
        callbacks = {}
        input_widget.event.side_effect = (
            lambda event_name: lambda callback: callbacks.setdefault(
                event_name,
                callback,
            )
        )

        with patch.object(
            widgets_module.arcade.gui,
            "UIInputText",
            return_value=input_widget,
        ) as input_type:
            widgets._search_input(state, 10.0, 20.0, 190.0)

        kwargs = input_type.call_args.kwargs
        self.assertEqual((10.0, 20.0), (kwargs["x"], kwargs["y"]))
        self.assertEqual((190.0, 24.0), (kwargs["width"], kwargs["height"]))
        self.assertEqual("搜索事件", kwargs["text"])
        manager.add.assert_called_once_with(input_widget)

        callbacks["on_click"](Mock())
        self.assertEqual("", input_widget.text)
        callbacks["on_change"](Mock(new_value="roll_over"))
        self.assertEqual("roll_over", state.ui_log_search)


class NativeTopStatusTests(unittest.TestCase):
    def test_top_label_is_registered_on_default_layer(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        widgets = StatusWidgets(manager)

        label = widgets._sync_top_label(
            None,
            "MarsDog",
            widgets_module.BBox(10.0, 20.0, 120.0, 30.0),
            font_size=config.FONT_SIZE_PAGE,
            color=config.COLORS["text"],
            bold=True,
        )

        self.assertEqual("MarsDog", label.text)
        manager.add.assert_called_once_with(label)

    def test_top_status_registers_native_topic_chips(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        widgets = StatusWidgets(manager)
        widgets._hits = []
        widgets._sync_top_label = Mock(side_effect=lambda label, *_args, **_kwargs: label or Mock())
        chips = [Mock(spec=ATopicChip) for _ in widgets_module.TOP_ENDPOINTS]

        with (
            patch.object(
                widgets_module,
                "_endpoint_status",
                return_value=("live", "Live", "topic detail"),
            ),
            patch.object(
                widgets_module,
                "_virtual_time_display",
                return_value=("虚拟时间", config.COLORS["success"]),
            ),
            patch.object(
                widgets_module,
                "ATopicChip",
                side_effect=chips,
            ) as chip_type,
            patch.object(config, "WINDOW_WIDTH", 2560),
            patch.object(config, "LEFT_PANEL_RIGHT", 300.0),
            patch.object(config, "RIGHT_PANEL_LEFT", 2120.0),
        ):
            widgets._sync_top_status_bar(SimState())

        self.assertEqual(len(widgets_module.TOP_ENDPOINTS), chip_type.call_count)
        self.assertEqual("VIS  正常", chip_type.call_args_list[0].args[1])
        first_bounds = chip_type.call_args_list[0].args[0]
        last_bounds = chip_type.call_args_list[-1].args[0]
        chip_area_left = 380.0
        chip_area_right = 2120.0 - 12.0
        self.assertAlmostEqual(
            first_bounds.x - chip_area_left,
            chip_area_right - (last_bounds.x + last_bounds.width),
        )
        self.assertEqual(
            len(widgets_module.TOP_ENDPOINTS),
            len([item for item in widgets._hits if item["action"] == "topic_detail"]),
        )


class NativeConfirmationTests(unittest.TestCase):
    def test_confirmation_message_box_dispatches_existing_action(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        action_handler = Mock()
        widgets = StatusWidgets(manager, None, action_handler)
        state = SimState()
        state.ui_pending_confirmation = {
            "kind": "confirm",
            "message": "此操作可能触发行为",
        }
        message_box = Mock()
        callbacks = {}
        message_box.event.side_effect = (
            lambda event_name: lambda callback: callbacks.setdefault(
                event_name,
                callback,
            )
        )

        with patch.object(
            widgets_module,
            "AMessageBox",
            return_value=message_box,
        ) as message_box_type:
            widgets._sync_confirmation(state)

        kwargs = message_box_type.call_args.kwargs
        self.assertEqual("确认调试注入", kwargs["title"])
        self.assertEqual(("取消", "确认发送"), kwargs["buttons"])
        callbacks["on_action"](Mock(action="确认发送"))
        action_handler.assert_called_once_with("confirm_action")

    def test_alert_message_box_only_dismisses(self) -> None:
        manager = Mock()
        manager.walk_widgets.return_value = ()
        action_handler = Mock()
        widgets = StatusWidgets(manager, None, action_handler)
        state = SimState()
        state.ui_pending_confirmation = {
            "kind": "alert",
            "title": "提示",
            "message": "操作暂不可用",
        }
        message_box = Mock()
        callbacks = {}
        message_box.event.side_effect = (
            lambda event_name: lambda callback: callbacks.setdefault(
                event_name,
                callback,
            )
        )

        with patch.object(
            widgets_module,
            "AMessageBox",
            return_value=message_box,
        ) as message_box_type:
            widgets._sync_confirmation(state)

        self.assertEqual(("知道了",), message_box_type.call_args.kwargs["buttons"])
        callbacks["on_action"](Mock(action="知道了"))
        action_handler.assert_called_once_with("cancel_confirmation")


class TooltipLayoutTests(unittest.TestCase):
    def test_long_topic_detail_wraps_without_truncation(self) -> None:
        widgets = object.__new__(StatusWidgets)
        detail = (
            "/internal_need/state, /internal_need/signal_event | "
            "count=999 | age=0.1s | 10 Hz"
        )
        widgets._hovered = {
            "tooltip": detail,
            "x": 632.0,
            "y": 750.0,
        }

        with (
            patch.object(
                widgets_module,
                "measure_text",
                side_effect=((640, 12), (490, 30)),
            ),
            patch.object(
                widgets_module.arcade,
                "draw_lbwh_rectangle_filled",
            ) as draw_background,
            patch.object(
                widgets_module.arcade,
                "draw_lbwh_rectangle_outline",
            ),
            patch.object(widgets_module, "draw_text") as draw_tooltip_text,
        ):
            StatusWidgets._draw_tooltip(widgets)

        background_width = draw_background.call_args.args[2]
        self.assertEqual(520.0, background_width)
        self.assertEqual(40.0, draw_background.call_args.args[3])
        draw_tooltip_text.assert_called_once()
        self.assertEqual(detail, draw_tooltip_text.call_args.args[0])
        self.assertEqual(
            int(background_width - 18.0),
            draw_tooltip_text.call_args.kwargs["width"],
        )
        self.assertTrue(draw_tooltip_text.call_args.kwargs["multiline"])


if __name__ == "__main__":
    unittest.main()
