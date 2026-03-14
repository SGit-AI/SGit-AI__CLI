import pytest
from sg_send_cli.safe_types.Safe_UInt__Lock_Timeout import Safe_UInt__Lock_Timeout, MAX_LOCK_TIMEOUT


class Test_Safe_UInt__Lock_Timeout:

    def test_valid_timeout(self):
        timeout = Safe_UInt__Lock_Timeout(1800)
        assert timeout == 1800

    def test_zero_allowed(self):
        timeout = Safe_UInt__Lock_Timeout(0)
        assert timeout == 0

    def test_max_allowed(self):
        timeout = Safe_UInt__Lock_Timeout(MAX_LOCK_TIMEOUT)
        assert timeout == MAX_LOCK_TIMEOUT

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Lock_Timeout(-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Lock_Timeout(MAX_LOCK_TIMEOUT + 1)

    def test_type_preserved(self):
        timeout = Safe_UInt__Lock_Timeout(1800)
        assert type(timeout).__name__ == 'Safe_UInt__Lock_Timeout'
