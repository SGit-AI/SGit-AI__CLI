import datetime

from sgit_ai.cli._helpers import format_ms_to_iso


class Test_format_ms_to_iso:

    def test_known_value(self):
        # 2026-03-10T12:00:00Z = 1773144000000 ms
        assert format_ms_to_iso(1773144000000) == '2026-03-10T12:00:00Z'

    def test_zero_returns_empty_string(self):
        assert format_ms_to_iso(0) == ''

    def test_none_returns_empty_string(self):
        assert format_ms_to_iso(None) == ''

    def test_round_trip_with_datetime(self):
        ms = int(datetime.datetime(2026, 5, 13, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)
        assert format_ms_to_iso(ms) == '2026-05-13T12:00:00Z'

    def test_accepts_timestamp_now_instance(self):
        from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now import Timestamp_Now
        ts = Timestamp_Now('2026-03-10T12:00:00Z')
        assert format_ms_to_iso(ts) == '2026-03-10T12:00:00Z'
