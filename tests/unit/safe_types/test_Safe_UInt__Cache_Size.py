import pytest

from sgit_ai.safe_types.Safe_UInt__Cache_Size import Safe_UInt__Cache_Size, MAX_CACHE_TARGET_SIZE


class Test_Safe_UInt__Cache_Size:

    def test_accepts_sizes_past_the_file_size_cap(self):
        # the whole reason this type exists: Safe_UInt__File_Size caps at 100 MB,
        # but a pointer cache legitimately describes any vault blob (review H1)
        assert int(Safe_UInt__Cache_Size(150 * 1024 * 1024)) == 150 * 1024 * 1024

    def test_zero_is_valid(self):
        assert int(Safe_UInt__Cache_Size(0)) == 0          # a tree pointer's size

    def test_max_boundary(self):
        assert int(Safe_UInt__Cache_Size(MAX_CACHE_TARGET_SIZE)) == MAX_CACHE_TARGET_SIZE
        with pytest.raises(ValueError):
            Safe_UInt__Cache_Size(MAX_CACHE_TARGET_SIZE + 1)

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Cache_Size(-1)
