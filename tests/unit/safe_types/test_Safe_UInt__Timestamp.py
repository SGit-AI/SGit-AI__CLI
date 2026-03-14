import pytest
from sg_send_cli.safe_types.Safe_UInt__Timestamp import Safe_UInt__Timestamp


class Test_Safe_UInt__Timestamp:

    def test_valid_timestamp(self):
        ts = Safe_UInt__Timestamp(1710412800000)
        assert ts == 1710412800000

    def test_zero_allowed(self):
        ts = Safe_UInt__Timestamp(0)
        assert ts == 0

    def test_max_value(self):
        ts = Safe_UInt__Timestamp(99999999999999)
        assert ts == 99999999999999

    def test_over_max_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Timestamp(100000000000000)

    def test_type_preserved(self):
        ts = Safe_UInt__Timestamp(1710412800000)
        assert type(ts).__name__ == 'Safe_UInt__Timestamp'
