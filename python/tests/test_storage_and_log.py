import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from radio_timer import model
from radio_timer.activity_log import ActivityLog
from radio_timer.storage import Preferences, load_preferences, save_preferences


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "prefs.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        prefs = Preferences(station="Radio Prueba 99.1", alert_enabled=False, sound_enabled=True)
        prefs.segments.append(model.new_segment("prueba", 3, model.KIND_SEPARATE, 4))
        save_preferences(prefs, self.path)
        loaded = load_preferences(self.path)
        self.assertEqual(loaded.station, "Radio Prueba 99.1")
        self.assertFalse(loaded.alert_enabled)
        self.assertTrue(loaded.sound_enabled)
        self.assertEqual([s.label for s in loaded.segments], ["EN AIRE", "PROMOS", "CIERRE", "CORTE", "PRUEBA"])
        self.assertEqual(loaded.segments[-1].duration, 180)

    def test_missing_file_gives_defaults(self):
        prefs = load_preferences(self.path)
        self.assertEqual(prefs.station, "Radio Luz 93.7 FM")
        self.assertEqual(len(prefs.segments), 4)
        self.assertTrue(prefs.alert_enabled)

    def test_corrupt_or_partial_file_is_tolerated(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{no es json", encoding="utf-8")
        self.assertEqual(len(load_preferences(self.path).segments), 4)
        self.path.write_text(json.dumps({"station": "  ", "segments": [{"bad": True}], "alertEnabled": "sí"}), encoding="utf-8")
        prefs = load_preferences(self.path)
        self.assertEqual(prefs.station, "Radio Luz 93.7 FM")
        self.assertEqual(len(prefs.segments), 4)
        self.assertTrue(prefs.alert_enabled)

    def test_web_version_json_is_compatible(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "station": "Radio Web",
            "segments": [{"id": "s1", "label": "EN AIRE", "detail": "Programa", "duration": 3300,
                          "color": "#0e8f88", "text": "#f1fffc", "type": "sums"}],
            "alertEnabled": True, "soundEnabled": False,
        }), encoding="utf-8")
        prefs = load_preferences(self.path)
        self.assertEqual(prefs.station, "Radio Web")
        self.assertEqual(prefs.segments[0].kind, "sums")


class ActivityLogTests(unittest.TestCase):
    def test_newest_first_and_capped(self):
        calls = []
        log = ActivityLog(max_entries=3, listener=lambda: calls.append(1))
        for index in range(5):
            log.add(f"evento {index}", "detalle", at=datetime(2026, 9, 14, 10, 0, index))
        self.assertEqual(len(log), 3)
        self.assertEqual([entry.title for entry in log.entries], ["evento 4", "evento 3", "evento 2"])
        self.assertEqual(len(calls), 5)

    def test_csv_export_with_bom_and_header(self):
        log = ActivityLog()
        log.add("Entrada a bloque: EN AIRE", "Bloque en curso", "Programación", at=datetime(2026, 9, 14, 10, 54, 49))
        log.add('Sección "rara"', "con, coma", "Configuración", at=datetime(2026, 9, 14, 10, 55, 0))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ActivityLog.suggested_filename(datetime(2026, 9, 14))
            self.assertEqual(path.name, "historial-radio-timer-2026-09-14.csv")
            self.assertEqual(log.export_csv(path), 2)
            raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        lines = raw.decode("utf-8-sig").split("\r\n")
        self.assertEqual(lines[0], '"fecha","hora","evento","detalle","origen"')
        self.assertEqual(lines[1], '"2026-09-14","10:54:49","Entrada a bloque: EN AIRE","Bloque en curso","Programación"')
        self.assertEqual(lines[2], '"2026-09-14","10:55:00","Sección ""rara""","con, coma","Configuración"')


if __name__ == "__main__":
    unittest.main()
