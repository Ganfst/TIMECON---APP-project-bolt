import unittest
from datetime import datetime, timedelta

from radio_timer import model


BASE = datetime(2026, 9, 14, 10, 0, 0)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.segments = model.default_segments()

    def test_default_blocks(self):
        labels = [segment.label for segment in self.segments]
        self.assertEqual(labels, ["EN AIRE", "PROMOS", "CIERRE", "CORTE"])
        kinds = [segment.kind for segment in self.segments]
        self.assertEqual(kinds, ["sums", "sums", "sums", "separate"])

    def test_chain_places_segments_back_to_back(self):
        schedule = model.build_schedule(self.segments, BASE, BASE)
        self.assertEqual([item.start for item in schedule], [
            BASE, BASE + timedelta(minutes=45), BASE + timedelta(minutes=50), BASE + timedelta(minutes=55),
        ])
        # Los bloques por defecto llenan la hora justa, porque la secuencia se reinicia en cada hora en punto.
        self.assertEqual(schedule[-1].end, BASE + timedelta(minutes=60))

    def test_remaining_follows_the_clock(self):
        schedule = model.build_schedule(self.segments, BASE, BASE)
        self.assertEqual(schedule[0].remaining, 45 * 60)
        later = model.build_schedule(self.segments, BASE, BASE + timedelta(seconds=1))
        self.assertEqual(later[0].remaining, 45 * 60 - 1)
        self.assertEqual(model.format_clock(later[0].remaining), "44:59")

    def test_last_ten_seconds_flash(self):
        now = BASE + timedelta(minutes=44, seconds=50)
        schedule = model.build_schedule(self.segments, BASE, now)
        active = model.find_active(schedule)
        self.assertEqual(active.label, "EN AIRE")
        self.assertEqual(active.remaining, 10)
        self.assertTrue(model.is_flashing(active.remaining))
        self.assertFalse(model.is_flashing(active.remaining, alert_enabled=False))
        self.assertFalse(model.is_flashing(11))
        self.assertFalse(model.is_flashing(0))

    def test_chains_automatically_into_next_block(self):
        now = BASE + timedelta(minutes=45, microseconds=500_000)
        schedule = model.build_schedule(self.segments, BASE, now)
        active = model.find_active(schedule)
        self.assertEqual(active.label, "PROMOS")
        self.assertEqual(active.remaining, 299)
        self.assertTrue(schedule[0].is_done)
        self.assertTrue(schedule[2].is_pending)
        self.assertEqual(model.next_after(schedule, active).label, "CIERRE")
        self.assertEqual(model.schedule_status(schedule), "running")

    def test_independent_block_takes_its_turn_but_not_the_total(self):
        now = BASE + timedelta(minutes=56)
        schedule = model.build_schedule(self.segments, BASE, now)
        active = model.find_active(schedule)
        self.assertEqual(active.label, "CORTE")
        self.assertFalse(active.is_chain)
        self.assertEqual(model.chain_remaining(schedule), 0)
        self.assertEqual(model.chain_duration(self.segments), 55 * 60)
        self.assertIsNone(model.next_after(schedule, active))

    def test_pending_sections_keep_their_full_time(self):
        now = BASE + timedelta(minutes=44, seconds=55)
        schedule = model.build_schedule(self.segments, BASE, now)
        self.assertEqual([item.remaining for item in schedule], [5, 300, 300, 300])
        self.assertEqual(schedule[3].progress, 0.0)
        # En cadena: 5 s de EN AIRE + PROMOS + CIERRE completos; CORTE (independiente) no se suma.
        self.assertEqual(model.chain_remaining(schedule), 5 + 300 + 300)
        self.assertEqual(model.chain_remaining(model.build_schedule(self.segments, BASE, BASE)), 55 * 60)

    def test_independent_counter_only_moves_on_its_turn(self):
        before = model.build_schedule(self.segments, BASE, BASE + timedelta(minutes=30))
        self.assertEqual(before[3].remaining, 300)
        during = model.build_schedule(self.segments, BASE, BASE + timedelta(minutes=57))
        self.assertEqual(during[3].remaining, 180)

    def test_status_pending_and_done(self):
        before = model.build_schedule(self.segments, BASE, BASE - timedelta(minutes=1))
        self.assertEqual(model.schedule_status(before), "pending")
        self.assertIsNone(model.find_active(before))
        after = model.build_schedule(self.segments, BASE, BASE + timedelta(minutes=60))
        self.assertEqual(model.schedule_status(after), "done")
        self.assertEqual(model.schedule_status([]), "empty")

    def test_progress(self):
        now = BASE + timedelta(minutes=22, seconds=30)
        schedule = model.build_schedule(self.segments, BASE, now)
        self.assertAlmostEqual(schedule[0].progress, 50.0)

    def test_top_of_hour_and_start_at(self):
        now = datetime(2026, 9, 14, 10, 37, 12, 345)
        self.assertEqual(model.top_of_hour(now), datetime(2026, 9, 14, 10, 0, 0))
        self.assertEqual(model.start_at(now, 7, 30), datetime(2026, 9, 14, 7, 30, 0))


class SegmentTests(unittest.TestCase):
    def test_round_trip(self):
        segment = model.default_segments()[1]
        data = segment.to_dict()
        self.assertEqual(data["type"], "sums")
        self.assertEqual(model.Segment.from_dict(data), segment)

    def test_invalid_dicts_are_rejected(self):
        for bad in (None, {}, {"id": "x", "label": "A", "duration": 0, "color": "#000", "type": "sums"},
                    {"id": "x", "label": "A", "duration": 60, "color": "#000", "type": "otro"},
                    {"id": "x", "label": "  ", "duration": 60, "color": "#000", "type": "sums"}):
            with self.assertRaises(ValueError):
                model.Segment.from_dict(bad)

    def test_new_segment_uses_palette_and_uppercases(self):
        segment = model.new_segment("  entrevista  larga ", 3, model.KIND_SEPARATE, 4)
        self.assertEqual(segment.label, "ENTREVISTA LARGA")
        self.assertEqual(segment.duration, 180)
        self.assertEqual(segment.color, model.PALETTE[4][0])
        self.assertEqual(segment.detail, "Sección independiente")
        self.assertTrue(segment.id.startswith("seg-"))
        with self.assertRaises(ValueError):
            model.new_segment("   ", 5, model.KIND_CHAIN, 0)

    def test_names_are_limited_and_cleaned(self):
        segment = model.new_segment("a" * 40, 5, model.KIND_CHAIN, 0)
        self.assertEqual(segment.label, "A" * model.MAX_LABEL_LENGTH)
        self.assertEqual(model.clean_station("  Radio   Luz  "), "Radio Luz")
        self.assertEqual(model.clean_station("   "), "Radio")
        self.assertEqual(len(model.clean_station("z" * 100)), model.MAX_STATION_LENGTH)

    def test_clamp_int(self):
        self.assertEqual(model.clamp_int("7", 0, 23), 7)
        self.assertEqual(model.clamp_int("99", 0, 23), 23)
        self.assertEqual(model.clamp_int("-3", 0, 59), 0)
        self.assertEqual(model.clamp_int("abc", 1, 10), 1)
        self.assertEqual(model.clamp_int("", 1, 10), 1)
        self.assertEqual(model.clamp_int(4.9, 1, 10), 4)


class HourFitTests(unittest.TestCase):
    def test_default_sequence_fits_the_hour(self):
        segments = model.default_segments()
        self.assertEqual(model.sequence_duration(segments), model.HOUR_SECONDS)
        self.assertEqual(model.cut_by_hour(segments), [])

    def test_longer_sequence_reports_what_is_cut(self):
        segments = model.default_segments()
        segments[0] = model.with_minutes(segments[0], 55)
        self.assertEqual(segments[0].label, "EN AIRE")
        self.assertEqual(segments[0].duration, 55 * 60)
        self.assertEqual([segment.label for segment in model.cut_by_hour(segments)], ["CIERRE", "CORTE"])
        self.assertEqual(model.with_minutes(segments[0], "0").duration, 60)


MONDAY = datetime(2026, 9, 14, 10, 30, 0)  # lunes


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.morning = model.new_program(0, 6, 10, "  Buenos   Días Luz ")
        self.mid = model.new_program(0, 10, 12, "Palabra de Vida")
        self.tuesday = model.new_program(1, 6, 9, "Despertar")
        self.programs = [self.mid, self.tuesday, self.morning]

    def test_new_program_validates(self):
        self.assertEqual(self.morning.title, "Buenos Días Luz")
        self.assertEqual(self.morning.hours_label, "06:00–10:00")
        self.assertTrue(self.morning.id.startswith("prog-"))
        self.assertEqual(model.new_program(6, 22, 24, "Noche").hours_label, "22:00–24:00")
        with self.assertRaises(ValueError):
            model.new_program(0, 6, 6, "Vacío")
        with self.assertRaises(ValueError):
            model.new_program(0, 9, 7, "Al revés")
        with self.assertRaises(ValueError):
            model.new_program(0, 6, 7, "   ")
        self.assertEqual(len(model.new_program(0, 6, 7, "t" * 80).title), model.MAX_PROGRAM_TITLE_LENGTH)

    def test_program_at_follows_day_and_hour(self):
        self.assertEqual(model.program_at(self.programs, MONDAY), self.mid)
        self.assertEqual(model.program_at(self.programs, MONDAY.replace(hour=9, minute=59)), self.morning)
        self.assertIsNone(model.program_at(self.programs, MONDAY.replace(hour=12)))
        self.assertEqual(model.program_at(self.programs, MONDAY + timedelta(days=1, hours=-3)), self.tuesday)
        # La parrilla es semanal: el lunes siguiente vuelve el mismo programa.
        self.assertEqual(model.program_at(self.programs, MONDAY + timedelta(days=7)), self.mid)

    def test_next_program_skips_the_current_one_and_crosses_days(self):
        program, begins = model.next_program(self.programs, MONDAY.replace(hour=7))
        self.assertEqual(program, self.mid)
        self.assertEqual(begins, MONDAY.replace(hour=10, minute=0))
        program, begins = model.next_program(self.programs, MONDAY)
        self.assertEqual(program, self.tuesday)
        self.assertEqual(begins, datetime(2026, 9, 15, 6, 0, 0))
        self.assertEqual(model.format_relative_day(begins, MONDAY), "Mañana")
        self.assertEqual(model.format_relative_day(MONDAY, MONDAY), "Hoy")
        # Martes 07:00: lo siguiente es el lunes de la semana próxima.
        program, begins = model.next_program(self.programs, datetime(2026, 9, 15, 7, 0, 0))
        self.assertEqual(program, self.morning)
        self.assertEqual(model.format_relative_day(begins, datetime(2026, 9, 15, 7, 0, 0)), "Lunes")
        self.assertIsNone(model.next_program([], MONDAY))

    def test_overlap_detection(self):
        clash = model.new_program(0, 9, 11, "Cruce")
        self.assertIn(model.overlapping_program(self.programs, clash), (self.morning, self.mid))
        self.assertIsNone(model.overlapping_program(self.programs, model.new_program(0, 12, 13, "Libre")))
        self.assertIsNone(model.overlapping_program(self.programs, model.new_program(2, 9, 11, "Otro día")))

    def test_copy_day_replaces_targets(self):
        copied = model.copy_day(self.programs, 0, [0, 1, 2])
        self.assertEqual([p.title for p in model.programs_for_day(copied, 1)], ["Buenos Días Luz", "Palabra de Vida"])
        self.assertEqual([p.title for p in model.programs_for_day(copied, 2)], ["Buenos Días Luz", "Palabra de Vida"])
        self.assertEqual(model.programs_for_day(copied, 0), [self.morning, self.mid])
        self.assertEqual(len({p.id for p in copied}), len(copied))

    def test_round_trip_and_invalid(self):
        self.assertEqual(model.Program.from_dict(self.morning.to_dict()), self.morning)
        for bad in (None, {}, {"id": "p", "day": 7, "start": 1, "end": 2, "title": "X"},
                    {"id": "p", "day": 0, "start": 5, "end": 5, "title": "X"},
                    {"id": "p", "day": 0, "start": 5, "end": 25, "title": "X"},
                    {"id": "p", "day": 0, "start": 5, "end": 6, "title": "  "}):
            with self.assertRaises(ValueError):
                model.Program.from_dict(bad)


class FormatTests(unittest.TestCase):
    def test_clock_and_duration(self):
        self.assertEqual(model.format_clock(0), "00:00")
        self.assertEqual(model.format_clock(3300), "55:00")
        self.assertEqual(model.format_clock(-5), "00:00")
        self.assertEqual(model.format_duration(300), "5m")
        self.assertEqual(model.format_duration(3900), "1h 05m")

    def test_spanish_date(self):
        moment = datetime(2026, 9, 14, 10, 55, 7)
        self.assertEqual(model.format_weekday_es(moment), "Lunes")
        self.assertEqual(model.format_date_es(moment), "14 de septiembre")
        self.assertEqual(model.format_time_with_seconds(moment), "10:55:07")
        self.assertEqual(model.format_log_stamp(moment), "14/09 · 10:55:07")
        self.assertEqual(model.format_iso_date(moment), "2026-09-14")

    def test_utc_offset_label_shape(self):
        label = model.utc_offset_label(datetime(2026, 9, 14, 12, 0, 0))
        self.assertRegex(label, r"^UTC[+−]\d\d:\d\d$")


if __name__ == "__main__":
    unittest.main()
