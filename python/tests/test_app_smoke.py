"""Pruebas de la interfaz: requieren un entorno con pantalla (Tk)."""
import tempfile
import tkinter as tk
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from radio_timer import layout, widgets
from radio_timer.app import RadioTimerApp
from radio_timer.storage import Preferences, load_preferences


class FakeClock:
    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


BASE = datetime(2026, 9, 14, 10, 44, 50)


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:  # sin pantalla
            raise unittest.SkipTest(f"Tk no disponible: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prefs_path = Path(self.tmp.name) / "prefs.json"
        self.clock = FakeClock(BASE)
        self.app = RadioTimerApp(self.root, clock=self.clock, prefs_path=self.prefs_path,
                                 preferences=Preferences(), autostart=False)
        self.app.play_cue = lambda: None  # sin pitidos durante las pruebas
        self.app._apply_layout((1440, 900))
        self.root.update_idletasks()

    def tearDown(self):
        self.app.shutdown()
        for child in list(self.root.winfo_children()):
            child.destroy()
        self.root.update()
        self.tmp.cleanup()

    # --------------------------------------------------------- reloj real ---

    def test_alert_then_automatic_chain(self):
        app = self.app
        self.assertEqual(app.program_start, datetime(2026, 9, 14, 10, 0, 0))
        self.assertEqual(app.active.label, "EN AIRE")
        self.assertEqual(app.remaining, 10)
        self.assertTrue(app.flashing)
        caption = app.clock_canvas.itemcget(app._clock_items["caption"], "text")
        self.assertEqual(caption, "ATENCIÓN")
        self.assertEqual(app.clock_canvas.itemcget(app._clock_items["glow"], "state"), "normal")
        self.assertEqual(app.log.entries[0].title, "Entrada a bloque: EN AIRE")

        self.clock.moment = BASE + timedelta(seconds=10, microseconds=500_000)
        app.step(self.clock.moment)
        self.assertEqual(app.active.label, "PROMOS")
        self.assertEqual(app.remaining, 299)
        self.assertFalse(app.flashing)
        self.assertEqual(app.clock_canvas.itemcget(app._clock_items["glow"], "state"), "hidden")
        self.assertEqual(app.clock_canvas.itemcget(app._clock_items["time"], "text"), "04:59")
        self.assertEqual(app.next_segment.label, "CIERRE")
        self.assertEqual(app.log.entries[0].title, "Entrada a bloque: PROMOS")
        self.assertEqual(app.log.entries[0].detail, "Cambio automático por reloj")
        self.assertEqual(app.active_title.cget("text"), "PROMOS")
        self.assertEqual(app.active_block.cget("bg"), "#ec8d2d")

    def test_flash_alternates_every_half_second(self):
        app = self.app
        colors = set()
        for tenths in range(0, 10, 5):
            app.step(BASE + timedelta(milliseconds=tenths * 100))
            colors.add(app.clock_canvas.itemcget(app._clock_items["time"], "fill"))
        self.assertEqual(len(colors), 2)

    def test_alert_can_be_disabled(self):
        self.app.set_alert_enabled(False)
        self.assertFalse(self.app.flashing)
        self.assertFalse(load_preferences(self.prefs_path).alert_enabled)
        self.app.set_alert_enabled(True)
        self.assertTrue(self.app.flashing)

    # ---------------------------------------------- parrilla y cambio de hora ---

    def test_sequence_restarts_every_hour_with_its_program(self):
        app = self.app
        self.assertEqual(app.program_block.winfo_manager(), "")  # sin parrilla no se muestra
        app.add_program(0, 10, 11, "Palabra de Vida")  # BASE es lunes
        app.add_program(0, 11, 13, "Música del Recuerdo")
        self.root.update_idletasks()
        self.assertEqual(app.program_block.winfo_manager(), "grid")
        self.assertEqual(app.program_title.cget("text"), "Palabra de Vida")
        self.assertEqual(app.program_caption.cget("text"), "PROGRAMA  ·  10:00–11:00")
        self.assertEqual(app.next_program_title.cget("text"), "Música del Recuerdo")
        self.assertEqual(app.next_program_meta.cget("text"), "Hoy · 11:00–13:00")
        self.assertIn("Palabra de Vida", self.root.title())
        with self.assertRaises(ValueError):
            app.add_program(0, 12, 14, "Cruce")

        self.clock.moment = datetime(2026, 9, 14, 11, 0, 0, 200_000)
        app.step(self.clock.moment)
        self.assertEqual(app.program_start, datetime(2026, 9, 14, 11, 0, 0))
        self.assertEqual(app.active.label, "EN AIRE")
        self.assertEqual(app.remaining, 45 * 60 - 1)
        self.assertEqual(app.program_title.cget("text"), "Música del Recuerdo")
        self.assertEqual(app.start_chip.cget("text"), "11:00 hrs")
        titles = [entry.title for entry in app.log.entries[:3]]
        self.assertEqual(titles, ["Entrada a bloque: EN AIRE", "Programa: Música del Recuerdo", "Nueva hora"])

        self.clock.moment = datetime(2026, 9, 14, 13, 5, 0)
        app.step(self.clock.moment)
        self.assertEqual(app.program_start, datetime(2026, 9, 14, 13, 0, 0))
        self.assertEqual(app.program_title.cget("text"), "Sin programa asignado")
        self.assertEqual(app.next_program_meta.cget("text"), "Lunes · 10:00–11:00")

        app.toggle_fullscreen()
        self.root.update_idletasks()
        self.assertEqual(app.program_block.winfo_manager(), "grid")
        app.toggle_fullscreen()

        for program in list(app.programs):
            self.assertTrue(app.delete_program(program.id))
        self.root.update_idletasks()
        self.assertEqual(app.program_block.winfo_manager(), "")
        self.assertEqual(app.next_program_box.winfo_manager(), "")
        self.assertEqual(load_preferences(self.prefs_path).programs, [])

    def test_manual_start_holds_until_the_next_hour(self):
        app = self.app
        app.apply_start_time(10, 30)
        app.step(datetime(2026, 9, 14, 10, 59, 59))
        self.assertEqual(app.program_start, datetime(2026, 9, 14, 10, 30, 0))
        app.step(datetime(2026, 9, 14, 11, 0, 0))
        self.assertEqual(app.program_start, datetime(2026, 9, 14, 11, 0, 0))

    def test_long_program_title_fits_the_stage(self):
        app = self.app
        app.add_program(0, 0, 24, "W" * 40)
        app._apply_layout((1440, 900))
        width = int(app.stage.grid_columnconfigure(0)["minsize"])
        self.assertLessEqual(app.f["program_title"].measure(app.program_title.cget("text")), width)
        low, _high = layout.PROGRAM_TITLE_PX[layout.MODE_NORMAL]
        self.assertGreaterEqual(-int(app.f["program_title"].cget("size")), app.px(low))

    def test_settings_program_editor(self):
        app = self.app
        dialog = app.open_settings()
        self.root.update_idletasks()
        self.assertEqual(dialog.program_day, 0)
        self.assertEqual(dialog.program_day_title.cget("text"), "Lunes (hoy)")
        dialog.program_start_var.set("10")
        dialog.program_end_var.set("12")
        dialog._add_program()
        self.assertEqual(dialog.program_error.cget("text"), "El programa necesita un título")
        dialog.program_title_entry.set_value("Palabra de Vida")
        dialog._add_program()
        self.assertEqual(dialog.program_error.cget("text"), "")
        self.assertEqual([p.title for p in app.programs], ["Palabra de Vida"])
        self.assertEqual((dialog.program_start_var.get(), dialog.program_end_var.get()), ("12", "13"))
        self.assertEqual(app.program_title.cget("text"), "Palabra de Vida")

        dialog.program_start_var.set("11")
        dialog.program_title_entry.set_value("Cruce")
        dialog._add_program()
        self.assertIn("Palabra de Vida", dialog.program_error.cget("text"))

        dialog.copy_target_var.set("Lunes a viernes")
        dialog._copy_day()
        self.assertEqual(len(app.programs), 5)
        dialog.select_day(6)
        self.assertEqual(dialog.program_day_title.cget("text"), "Domingo")
        self.assertEqual(len(load_preferences(self.prefs_path).programs), 5)

    def test_section_minutes_and_hour_warning(self):
        app = self.app
        dialog = app.open_settings()
        self.root.update_idletasks()
        self.assertEqual(dialog.overflow_label.cget("text"), "")
        variable = dialog.minute_vars["s1"]
        variable.set("55")
        dialog._apply_minutes("s1", variable)
        self.assertEqual(app.segments[0].duration, 55 * 60)
        self.assertEqual(app.segments[0].label, "EN AIRE")
        self.assertIn("CIERRE, CORTE", dialog.overflow_label.cget("text"))
        self.assertEqual(load_preferences(self.prefs_path).segments[0].duration, 55 * 60)
        variable.set("45")
        dialog._queue_minutes("s1", variable)  # como al pulsar la flecha: espera una pausa
        dialog.close()  # los minutos pendientes se aplican al cerrar
        self.assertEqual(app.segments[0].duration, 45 * 60)

    # ------------------------------------------------------ tamaños del doc ---

    def test_clock_and_date_sizes_follow_document(self):
        app = self.app
        low, high = layout.CLOCK_FONT_RANGE[layout.MODE_NORMAL]
        self.assertGreaterEqual(app.clock_font_px, app.px(low))
        self.assertLessEqual(app.clock_font_px, app.px(high))
        self.assertLessEqual(app.f["clock"].measure("00:00"), app.ring_size * layout.CLOCK_TEXT_MAX_FRACTION)
        self.assertGreaterEqual(-int(app.f["dt_time"].cget("size")), app.px(40))
        self.assertLessEqual(-int(app.f["dt_time"].cget("size")), app.px(68))
        self.assertGreaterEqual(-int(app.f["dt_weekday"].cget("size")), app.px(20))

        app.fullscreen = True
        app._apply_layout((1920, 1080))
        self.assertEqual(app.clock_font_px, app.px(160))
        app.fullscreen = False

    # ------------------------------------------------------------- modos ---

    def test_modes(self):
        app = self.app
        app.toggle_compact()
        self.root.update_idletasks()
        self.assertEqual(app.left_panel.winfo_manager(), "")
        self.assertEqual(app.right_panel.winfo_manager(), "")
        self.assertEqual(app.datetime_block.winfo_manager(), "")
        self.assertEqual(app.clock_canvas.winfo_manager(), "grid")
        self.assertEqual(app.compact_button.cget("text"), "Salir de compacto")
        app.toggle_compact()
        self.root.update_idletasks()
        self.assertEqual(app.left_panel.winfo_manager(), "grid")
        self.assertEqual(app.right_panel.winfo_manager(), "grid")

        app.toggle_fullscreen()
        self.root.update_idletasks()
        self.assertTrue(app.fullscreen)
        self.assertEqual(app.topbar.winfo_manager(), "")
        self.assertEqual(app.left_panel.winfo_manager(), "")
        self.assertEqual(app.reset_bar.winfo_manager(), "")
        self.assertEqual(app.datetime_block.winfo_manager(), "grid")
        self.assertEqual(app.footer.winfo_manager(), "grid")
        self.assertIn("Esc", app.footer_version.cget("text"))
        app._on_escape()
        self.root.update_idletasks()
        self.assertFalse(app.fullscreen)
        self.assertEqual(app.topbar.winfo_manager(), "grid")

    def test_medium_and_narrow_windows(self):
        app = self.app
        app._apply_layout((1000, 800))
        self.assertEqual(app.mode, layout.MODE_NORMAL)
        self.assertEqual(app.right_panel.winfo_manager(), "")
        self.assertIs(app.left_panel.master, app.content)

        app._apply_layout((700, 800))
        self.assertEqual(app.mode, layout.MODE_STACKED)
        self.assertIs(app.left_panel.master, app.stage)
        self.assertEqual(int(app.left_panel.grid_info()["row"]), 6)
        self.assertEqual(len(app._timeline_rows), 4)
        self.assertEqual(app.start_chip.cget("text"), "10:00 hrs")
        self.assertEqual(app._topbar_mode, "wrapped")

        app._apply_layout((1440, 900))
        self.assertEqual(app.mode, layout.MODE_NORMAL)
        self.assertIs(app.left_panel.master, app.content)
        self.assertEqual(app.right_panel.winfo_manager(), "grid")

    def test_panic(self):
        app = self.app
        app.toggle_panic()
        self.root.update_idletasks()
        self.assertEqual(app.panic_banner.winfo_manager(), "grid")
        self.assertEqual(app.panic_button.cget("bg"), "#b62f49")
        self.assertEqual(app.log.entries[0].title, "Modo pánico activado")
        app.toggle_panic()
        self.root.update_idletasks()
        self.assertEqual(app.panic_banner.winfo_manager(), "")

    # ------------------------------------------------ nada se corta ---

    def test_side_panel_scrolls_when_many_sections(self):
        app = self.app
        app._apply_layout((1920, 1200))
        self.root.update_idletasks()
        self.assertFalse(app.left_scroll.can_scroll())
        for index in range(8):
            app.add_segment(f"extra {index}", 5, "sums")
        app._apply_layout((1920, 1200))
        self.root.update_idletasks()
        app.left_scroll.sync()
        self.assertTrue(app.left_scroll.can_scroll())
        self.assertTrue(widgets.scroll_widget(app._timeline_rows[-1]["title"], 3))
        self.assertGreater(app.left_scroll.canvas.yview()[0], 0.0)

    # ----------------------------------------------------- configuración ---

    def test_settings_actions(self):
        app = self.app
        app.set_station("  Radio   Prueba 99.1 ")
        self.assertEqual(app.station_label.cget("text"), "Radio Prueba 99.1")
        self.assertEqual(app.set_station("   "), "Radio")
        app.set_station("Radio Prueba 99.1")
        segment = app.add_segment("prueba", "3", "separate")
        self.assertEqual(segment.label, "PRUEBA")
        self.assertEqual(len(app.schedule), 5)
        self.assertEqual(len(app._separate_cards), 2)
        stored = load_preferences(self.prefs_path)
        self.assertEqual(stored.station, "Radio Prueba 99.1")
        self.assertEqual(stored.segments[-1].label, "PRUEBA")
        self.assertTrue(app.delete_segment(segment.id))
        self.assertEqual(len(app.schedule), 4)
        self.assertFalse(app.delete_segment("no-existe"))

        start = app.apply_start_time("7", "30")
        self.assertEqual((start.hour, start.minute), (7, 30))
        self.assertEqual(app.start_chip.cget("text"), "07:30 hrs")
        self.assertEqual(app.status, "done")
        self.assertIsNone(app.active)
        app.reset_program()
        self.assertEqual(app.log.entries[0].source, "Reiniciar al inicio")

    def test_placeholder_is_never_added_as_a_section(self):
        app = self.app
        dialog = app.open_settings()
        self.root.update_idletasks()
        self.assertTrue(dialog.name_entry.showing_placeholder)
        self.assertEqual(dialog.name_entry.value(), "")
        dialog._add_segment()
        self.assertEqual(len(app.segments), 4)
        self.assertEqual(dialog.error_label.cget("text"), "La sección necesita un nombre")

        dialog.name_entry.set_value("entrevista")
        dialog._add_segment()
        self.assertEqual(app.segments[-1].label, "ENTREVISTA")
        self.assertEqual(dialog.error_label.cget("text"), "")
        self.assertEqual(dialog.name_entry.value(), "")

    def test_switches_change_preferences(self):
        app = self.app
        dialog = app.open_settings()
        self.root.update_idletasks()
        self.assertTrue(dialog.alert_var.get())
        dialog.alert_switch.toggle()
        self.assertFalse(app.alert_enabled)
        self.assertFalse(load_preferences(self.prefs_path).alert_enabled)
        dialog.sound_switch.toggle()
        self.assertTrue(app.sound_enabled)
        self.assertTrue(load_preferences(self.prefs_path).sound_enabled)

    def test_name_lengths_are_limited(self):
        app = self.app
        segment = app.add_segment("x" * 60, 5, "sums")
        self.assertEqual(len(segment.label), 24)
        self.assertEqual(len(app.set_station("y" * 80)), 40)

    def test_dialogs_open_and_history_exports(self):
        app = self.app
        settings = app.open_settings()
        self.root.update_idletasks()
        self.assertTrue(settings.winfo_exists())
        self.assertIs(app.open_settings(), settings)
        history = app.open_history()
        self.root.update_idletasks()
        self.assertIn("Entrada a bloque: EN AIRE", history.text.get("1.0", "end"))
        target = Path(self.tmp.name) / "historial.csv"
        self.assertEqual(app.export_history(target), target)
        self.assertTrue(target.exists())
        self.assertIn("Historial exportado", history.text.get("1.0", "end"))
        app.close_dialogs()
        self.root.update_idletasks()
        self.assertFalse(settings.winfo_exists())
        self.assertFalse(history.winfo_exists())


if __name__ == "__main__":
    unittest.main()
