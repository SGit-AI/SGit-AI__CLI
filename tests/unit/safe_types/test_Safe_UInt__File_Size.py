import pytest
from sg_send_cli.safe_types.Safe_UInt__File_Size import Safe_UInt__File_Size, MAX_FILE_SIZE


class Test_Safe_UInt__File_Size:

    def test_valid_size(self):
        size = Safe_UInt__File_Size(1024)
        assert size == 1024

    def test_zero_allowed(self):
        size = Safe_UInt__File_Size(0)
        assert size == 0

    def test_max_size_allowed(self):
        size = Safe_UInt__File_Size(MAX_FILE_SIZE)
        assert size == MAX_FILE_SIZE

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__File_Size(-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__File_Size(MAX_FILE_SIZE + 1)

    def test_type_preserved(self):
        size = Safe_UInt__File_Size(42)
        assert type(size).__name__ == 'Safe_UInt__File_Size'
