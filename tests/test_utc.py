"""E2: utc_now / utc_stamp are timezone independent."""
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from env.context import STATE_TIME_FORMAT, Context, utc_now, utc_stamp


class UtcHelperTests(unittest.TestCase):
    def _set_tz(self, tz):
        old = os.environ.get("TZ")

        def restore():
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()

        self.addCleanup(restore)
        os.environ["TZ"] = tz
        time.tzset()

    def test_utc_now_is_naive(self):
        self.assertIsNone(utc_now().tzinfo)

    def test_utc_now_matches_utc_clock_in_any_local_zone(self):
        for tz in ("UTC", "America/New_York", "Asia/Tokyo", "Pacific/Auckland"):
            with self.subTest(tz=tz):
                self._set_tz(tz)
                expected = datetime.now(timezone.utc).replace(tzinfo=None)
                self.assertLess(abs(utc_now() - expected), timedelta(seconds=5))

    def test_utc_now_uses_utc_not_local_time(self):
        fixed = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
        with patch("env.context.datetime") as dt:
            dt.now.return_value = fixed
            self.assertEqual(utc_now(), datetime(2024, 2, 29, 23, 30))
            dt.now.assert_called_once_with(timezone.utc)

    def test_utc_stamp_format(self):
        self.assertEqual(utc_stamp(datetime(2024, 5, 31, 1, 2, 3, 4)), "2024-05-31T01:02:03.000004Z")
        self.assertEqual(STATE_TIME_FORMAT, "%Y-%m-%dT%H:%M:%S.%fZ")

    def test_utc_stamp_defaults_to_now(self):
        stamp = utc_stamp()
        self.assertTrue(stamp.endswith("Z"))
        parsed = datetime.strptime(stamp, STATE_TIME_FORMAT)
        self.assertLess(abs(utc_now() - parsed), timedelta(seconds=5))

    def test_utc_stamp_independent_of_local_zone(self):
        moment = datetime(2024, 1, 1, 0, 0, 0)
        self._set_tz("Asia/Tokyo")
        a = utc_stamp(moment)
        self._set_tz("America/New_York")
        self.assertEqual(utc_stamp(moment), a)

    def test_stamp_round_trips_through_convert_dt_str(self):
        moment = datetime(2024, 7, 4, 12, 34, 56, 789012)
        self.assertEqual(Context().convert_dt_str(utc_stamp(moment)), moment)


if __name__ == "__main__":
    unittest.main()
