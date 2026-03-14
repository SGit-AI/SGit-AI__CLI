import pytest
from sg_send_cli.safe_types.Safe_UInt__Key_Size import Safe_UInt__Key_Size


class Test_Safe_UInt__Key_Size:

    def test_valid_size(self):
        size = Safe_UInt__Key_Size(4096)
        assert size == 4096

    def test_zero_allowed(self):
        size = Safe_UInt__Key_Size(0)
        assert size == 0

    def test_common_sizes(self):
        assert Safe_UInt__Key_Size(2048) == 2048
        assert Safe_UInt__Key_Size(4096) == 4096
        assert Safe_UInt__Key_Size(8192) == 8192

    def test_max_allowed(self):
        size = Safe_UInt__Key_Size(16384)
        assert size == 16384

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Key_Size(-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Key_Size(16385)

    def test_type_preserved(self):
        size = Safe_UInt__Key_Size(4096)
        assert type(size).__name__ == 'Safe_UInt__Key_Size'
