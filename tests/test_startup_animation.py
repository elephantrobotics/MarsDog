import unittest
from unittest.mock import Mock, patch

from marsdog_sim2d import config
from marsdog_sim2d.arcade_viewer_node import (
    SimWindow,
    _startup_overlay_alpha,
)


class StartupAnimationTests(unittest.TestCase):
    def test_first_draw_only_presents_startup_artwork(self) -> None:
        harness = Mock()
        harness.renderer = None
        harness._startup_frame_drawn = False
        harness._startup_frame_presented = False

        SimWindow.on_draw(harness)

        harness.clear.assert_called_once_with()
        harness._draw_startup_overlay.assert_called_once_with()
        self.assertTrue(harness._startup_frame_drawn)
        self.assertFalse(harness._startup_frame_presented)

    def test_renderer_loading_waits_for_presented_startup_frame(self) -> None:
        harness = Mock()
        harness.renderer = None
        harness._startup_frame_presented = False

        with patch(
            "marsdog_sim2d.arcade_viewer_node.WorldRenderer",
        ) as renderer_type:
            SimWindow.on_update(harness, 0.1)
            renderer_type.assert_not_called()

            harness._startup_frame_presented = True
            SimWindow.on_update(harness, 0.1)

        renderer_type.assert_called_once_with()
        self.assertIs(renderer_type.return_value, harness.renderer)

    def test_overlay_stays_opaque_then_fades_to_transparent(self) -> None:
        fade_start_sec = (
            config.STARTUP_ANIMATION_DURATION_SEC
            - config.STARTUP_ANIMATION_FADE_OUT_SEC
        )

        self.assertEqual(255, _startup_overlay_alpha(0.0))
        self.assertEqual(255, _startup_overlay_alpha(fade_start_sec))
        self.assertEqual(
            127,
            _startup_overlay_alpha(
                fade_start_sec + config.STARTUP_ANIMATION_FADE_OUT_SEC / 2,
            ),
        )
        self.assertEqual(
            0,
            _startup_overlay_alpha(config.STARTUP_ANIMATION_DURATION_SEC),
        )

    def test_animation_completion_enables_native_ui_once(self) -> None:
        harness = Mock()
        harness._startup_elapsed_sec = 0.0
        harness._startup_animation_active = lambda: (
            harness._startup_elapsed_sec
            < config.STARTUP_ANIMATION_DURATION_SEC
        )

        SimWindow._advance_startup_animation(
            harness,
            config.STARTUP_ANIMATION_DURATION_SEC,
        )
        SimWindow._advance_startup_animation(harness, 0.1)

        self.assertEqual(
            config.STARTUP_ANIMATION_DURATION_SEC,
            harness._startup_elapsed_sec,
        )
        harness.ui_manager.enable.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
