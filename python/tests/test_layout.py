"""Los tamaños calculados respetan los rangos del documento (radio-timer.md)."""
import unittest

from radio_timer import layout
from radio_timer.layout import MODE_COMPACT, MODE_FULLSCREEN, MODE_NORMAL, MODE_STACKED


class ModeTests(unittest.TestCase):
    def test_pick_mode(self):
        self.assertEqual(layout.pick_mode(1440, False, False), MODE_NORMAL)
        self.assertEqual(layout.pick_mode(700, False, False), MODE_STACKED)
        self.assertEqual(layout.pick_mode(700, True, False), MODE_COMPACT)
        self.assertEqual(layout.pick_mode(700, True, True), MODE_FULLSCREEN)

    def test_scale_moves_the_breakpoint(self):
        self.assertEqual(layout.pick_mode(1000, False, False, scale=1.5), MODE_STACKED)

    def test_right_panel_hides_on_medium_windows(self):
        self.assertTrue(layout.show_right_panel(MODE_NORMAL, 1440))
        self.assertFalse(layout.show_right_panel(MODE_NORMAL, 1100))
        self.assertFalse(layout.show_right_panel(MODE_STACKED, 1440))
        self.assertFalse(layout.show_right_panel(MODE_COMPACT, 1920))


class DateTimeFontTests(unittest.TestCase):
    def test_document_ranges(self):
        for width, height in ((680, 560), (1366, 697), (1440, 900), (1920, 1009), (3840, 2100)):
            fonts = layout.datetime_fonts(width, height, fullscreen=False)
            self.assertGreaterEqual(fonts.weekday, 20)
            self.assertGreaterEqual(fonts.date, 20)
            self.assertLessEqual(max(fonts.weekday, fonts.date), 32)
            self.assertGreaterEqual(fonts.time, 40)
            self.assertLessEqual(fonts.time, 68)

    def test_grow_with_the_window(self):
        small = layout.datetime_fonts(680, 560, fullscreen=False)
        large = layout.datetime_fonts(1920, 1009, fullscreen=False)
        tall = layout.datetime_fonts(2560, 1400, fullscreen=False)
        self.assertEqual((small.weekday, small.date, small.time), (20, 22, 40))
        self.assertEqual((large.weekday, large.date, large.time), (24, 28, 59))
        self.assertEqual((tall.weekday, tall.date, tall.time), (28, 32, 68))

    def test_fullscreen_is_larger(self):
        fonts = layout.datetime_fonts(1920, 1080, fullscreen=True)
        self.assertEqual((fonts.weekday, fonts.date, fonts.time), (40, 44, 84))


class ClockSizeTests(unittest.TestCase):
    def test_clock_font_within_document_range(self):
        for ring in range(240, 441, 20):
            size = layout.clock_font_px(MODE_NORMAL, ring)
            self.assertGreaterEqual(size, 64)
            self.assertLessEqual(size, 110)

    def test_fullscreen_reaches_160(self):
        self.assertEqual(layout.clock_font_px(MODE_FULLSCREEN, 600), 160)
        self.assertEqual(layout.clock_font_px(MODE_FULLSCREEN, 280), 84)

    def test_ring_uses_free_height_within_limits(self):
        self.assertEqual(layout.ring_size(MODE_NORMAL, 1200, 900, 500), 400)
        self.assertEqual(layout.ring_size(MODE_NORMAL, 1200, 600, 500), 240)
        self.assertEqual(layout.ring_size(MODE_NORMAL, 1200, 1400, 500), 440)
        self.assertEqual(layout.ring_size(MODE_FULLSCREEN, 1920, 1035, 290), 600)
        self.assertEqual(layout.ring_size(MODE_COMPACT, 1920, 950, 0), 620)

    def test_scale(self):
        self.assertEqual(layout.ring_size(MODE_NORMAL, 1200, 600, 500, scale=1.5), 360)
        self.assertEqual(layout.clock_font_px(MODE_FULLSCREEN, 900, scale=1.5), 240)

    def test_stage_width(self):
        self.assertEqual(layout.stage_width(MODE_NORMAL, 1200, 400), 640)
        self.assertEqual(layout.stage_width(MODE_NORMAL, 450, 300), 420)
        self.assertEqual(layout.stage_width(MODE_COMPACT, 1200, 500), 540)
        self.assertEqual(layout.stage_width(MODE_STACKED, 680, 400), 632)


if __name__ == "__main__":
    unittest.main()
