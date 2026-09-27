import unittest
from datetime import datetime

from radio_timer import model, schedule_sync

# Recorte real de la respuesta de https://radioluz937fm.com/weekSchedule (con campos de sobra).
SAMPLE = {
    "Martes": [
        {"id": 8, "name": "Vida Consagrada", "day": "Martes", "start_time": "07:30", "end_time": "08:00",
         "is_active": True, "is_deleted": 0},
        {"id": 42, "name": "Hoy es el día", "day": "Martes", "start_time": "08:00", "end_time": "09:00",
         "is_active": True, "is_deleted": 0},
    ],
    "Miércoles": [
        {"id": 12, "name": "La voz del Clero", "start_time": "07:30:00", "end_time": "08:00:00", "is_active": True},
        {"id": 99, "name": "Programa borrado", "start_time": "09:00", "end_time": "10:00", "is_deleted": 1},
        {"id": 98, "name": "Programa inactivo", "start_time": "10:00", "end_time": "11:00", "is_active": False},
    ],
    "Domingo": [
        {"id": 73, "name": "Santa Eucaristía", "start_time": "18:00", "end_time": "19:00", "is_active": True},
        {"id": 78, "name": "Misa Catedral", "start_time": "18:00", "end_time": "19:00", "is_active": True},
        {"id": 90, "name": "Se cruza", "start_time": "18:30", "end_time": "20:00", "is_active": True},
        {"id": 91, "name": "Cierre de la noche", "start_time": "23:00", "end_time": "00:00", "is_active": True},
        {"id": 92, "name": "Hora rota", "start_time": "25:00", "end_time": "26:00", "is_active": True},
    ],
    "Feriado": [],
}


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.result = schedule_sync.parse_week_schedule(SAMPLE)
        self.by_title = {program.title: program for program in self.result.programs}

    def test_days_with_accents_and_half_hours(self):
        vida = self.by_title["Vida Consagrada"]
        self.assertEqual((vida.day, vida.hours_label), (1, "07:30–08:00"))
        clero = self.by_title["La voz del Clero"]
        self.assertEqual((clero.day, clero.hours_label), (2, "07:30–08:00"))
        self.assertTrue(clero.contains(datetime(2026, 9, 16, 7, 45)))  # miércoles
        self.assertFalse(clero.contains(datetime(2026, 9, 16, 7, 29)))

    def test_inactive_and_deleted_are_ignored(self):
        self.assertNotIn("Programa borrado", self.by_title)
        self.assertNotIn("Programa inactivo", self.by_title)

    def test_same_slot_is_merged_and_overlaps_are_reported(self):
        self.assertIn("Santa Eucaristía / Misa Catedral", self.by_title)
        self.assertNotIn("Se cruza", self.by_title)
        self.assertTrue(any("Se cruza" in warning for warning in self.result.skipped))
        self.assertTrue(any("Hora rota" in warning for warning in self.result.skipped))
        self.assertTrue(any("Feriado" in warning for warning in self.result.skipped))

    def test_midnight_end(self):
        self.assertEqual(self.by_title["Cierre de la noche"].hours_label, "23:00–24:00")

    def test_invalid_payload(self):
        with self.assertRaises(schedule_sync.SyncError):
            schedule_sync.parse_week_schedule(["no", "es", "un", "dict"])

    def test_unreachable_site_gives_a_readable_error(self):
        with self.assertRaises(schedule_sync.SyncError) as ctx:
            schedule_sync.fetch_week_schedule("http://127.0.0.1:9/weekSchedule", timeout=2)
        self.assertIn("No se pudo conectar", str(ctx.exception))


class ProgramMinutesTests(unittest.TestCase):
    def test_legacy_whole_hours_are_read(self):
        old = model.Program.from_dict({"id": "p", "day": 5, "start": 10, "end": 11, "title": "Con la gracia de dios"})
        self.assertEqual((old.start, old.end, old.hours_label), (600, 660, "10:00–11:00"))
        self.assertEqual(old.to_dict()["start"], "10:00")
        self.assertEqual(model.Program.from_dict(old.to_dict()), old)

    def test_parse_clock_minutes(self):
        self.assertEqual(model.parse_clock_minutes("07:30"), 450)
        self.assertEqual(model.parse_clock_minutes("24:00"), 1440)
        for bad in ("7", "24:30", "10:75", "aa:bb"):
            with self.assertRaises(ValueError):
                model.parse_clock_minutes(bad)


if __name__ == "__main__":
    unittest.main()
