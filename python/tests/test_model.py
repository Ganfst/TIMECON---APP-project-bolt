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
            BASE, BASE + timedelta(minutes=55), BASE + timedelta(minutes=60), BASE + timedelta(minutes=65),
        ])
        self.assertEqual(schedule[-1].end, BASE + timedelta(minutes=70))

    def test_remaining_follows_the_clock(self):
        schedule = model.build_schedule(self.segments, BASE, BASE)
        self.assertEqual(schedule[0].remaining, 55 * 60)
        later = model.build_schedule(self.segments, BASE, BASE + timedelta(seconds=1))
        self.assertEqual(later[0].remaining, 55 * 60 - 1)
        self.assertEqual(model.format_clock(later[0].remaining), "54:59")

    def test_last_ten_seconds_flash(self):
        now = BASE + timedelta(minutes=54, seconds=50)
        schedule = model.build_schedule(self.segments, BASE, now)
        active = model.find_active(schedule)
        self.assertEqual(active.label, "EN AIRE")
        self.assertEqual(active.remaining, 10)
        self.assertTrue(model.is_flashing(active.remaining))
        self.assertFalse(model.is_flashing(active.remaining, alert_enabled=False))
        self.assertFalse(model.is_flashing(11))
        self.assertFalse(model.is_flashing(0))

    def test_chains_automatically_into_next_block(self):
        now = BASE + timedelta(minutes=55, microseconds=500_000)
        schedule = model.build_schedule(self.segments, BASE, now)
        active = model.find_active(schedule)
        self.assertEqual(active.label, "PROMOS")
        self.assertEqual(active.remaining, 299)
        self.assertTrue(schedule[0].is_done)
        self.assertTrue(schedule[2].is_pending)
        self.assertEqual(model.next_after(schedule, active).label, "CIERRE")
        self.assertEqual(model.schedule_status(schedule), "running")

    def test_independent_block_takes_its_turn_but_not_the_total(self):
        now = BASE + timedelta(minutes=66)
        schedule = model.build_schedule(self.segments, BASE, now)
        active = model.find_active(schedule)
        self.assertEqual(active.label, "CORTE")
        self.assertFalse(active.is_chain)
        self.assertEqual(model.chain_remaining(schedule), 0)
        self.assertEqual(model.chain_duration(self.segments), 65 * 60)
        self.assertIsNone(model.next_after(schedule, active))

    def test_pending_sections_keep_their_full_time(self):
        now = BASE + timedelta(minutes=54, seconds=55)
        schedule = model.build_schedule(self.segments, BASE, now)
        self.assertEqual([item.remaining for item in schedule], [5, 300, 300, 300])
        self.assertEqual(schedule[3].progress, 0.0)
        # En cadena: 5 s de EN AIRE + PROMOS + CIERRE completos; CORTE (independiente) no se suma.
        self.assertEqual(model.chain_remaining(schedule), 5 + 300 + 300)
        self.assertEqual(model.chain_remaining(model.build_schedule(self.segments, BASE, BASE)), 65 * 60)

    def test_independent_counter_only_moves_on_its_turn(self):
        before = model.build_schedule(self.segments, BASE, BASE + timedelta(minutes=30))
        self.assertEqual(before[3].remaining, 300)
        during = model.build_schedule(self.segments, BASE, BASE + timedelta(minutes=67))
        self.assertEqual(during[3].remaining, 180)

    def test_status_pending_and_done(self):
        before = model.build_schedule(self.segments, BASE, BASE - timedelta(minutes=1))
        self.assertEqual(model.schedule_status(before), "pending")
        self.assertIsNone(model.find_active(before))
        after = model.build_schedule(self.segments, BASE, BASE + timedelta(minutes=70))
        self.assertEqual(model.schedule_status(after), "done")
        self.assertEqual(model.schedule_status([]), "empty")

    def test_progress(self):
        now = BASE + timedelta(minutes=27, seconds=30)
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
