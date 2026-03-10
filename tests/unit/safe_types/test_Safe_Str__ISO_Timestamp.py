import pytest
from sg_send_cli.safe_types.Safe_Str__ISO_Timestamp import Safe_Str__ISO_Timestamp


class Test_Safe_Str__ISO_Timestamp:

    def test_valid_with_milliseconds(self):
        ts = Safe_Str__ISO_Timestamp('2026-03-04T12:00:00.000Z')
        assert ts == '2026-03-04T12:00:00.000Z'

    def test_valid_without_milliseconds(self):
        ts = Safe_Str__ISO_Timestamp('2026-03-04T12:00:00Z')
        assert ts == '2026-03-04T12:00:00Z'

    def test_valid_with_single_digit_ms(self):
        ts = Safe_Str__ISO_Timestamp('2026-03-04T12:00:00.5Z')
        assert ts == '2026-03-04T12:00:00.5Z'

    def test_empty_allowed(self):
        ts = Safe_Str__ISO_Timestamp('')
        assert ts == ''

    def test_missing_z_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__ISO_Timestamp('2026-03-04T12:00:00.000')

    def test_invalid_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__ISO_Timestamp('March 4, 2026')

    def test_timezone_offset_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__ISO_Timestamp('2026-03-04T12:00:00+00:00')

    def test_type_preserved(self):
        ts = Safe_Str__ISO_Timestamp('2026-03-04T12:00:00Z')
        assert type(ts).__name__ == 'Safe_Str__ISO_Timestamp'
