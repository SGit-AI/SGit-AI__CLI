import pytest
from sgit_ai.safe_types.Safe_UInt__File_Count import Safe_UInt__File_Count


class Test_Safe_UInt__File_Count:

    def test_zero(self):
        c = Safe_UInt__File_Count(0)
        assert c == 0

    def test_positive(self):
        c = Safe_UInt__File_Count(42)
        assert c == 42

    def test_large_value(self):
        c = Safe_UInt__File_Count(999_999)
        assert c == 999_999

    def test_type_preserved(self):
        c = Safe_UInt__File_Count(5)
        assert type(c).__name__ == 'Safe_UInt__File_Count'

    def test_negative_raises(self):
        with pytest.raises((ValueError, Exception)):
            Safe_UInt__File_Count(-1)
