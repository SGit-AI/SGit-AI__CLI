from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt

MAX_CACHE_TARGET_SIZE = 1024 ** 4        # 1 TB


class Safe_UInt__Cache_Size(Safe_UInt):
    """Byte size recorded inside a cache object.

    Deliberately NOT Safe_UInt__File_Size: that type caps at 100 MB, but a
    pointer cache legitimately describes any blob or tree the vault holds, and
    vault blobs have no 100 MB limit (large ones ride presigned URLs). Reusing
    the capped type made `build_pointer` raise for a >100 MB file, which took
    down the whole push reconcile and crashed `cache repair` (review 08/14 H1).
    """
    max_value = MAX_CACHE_TARGET_SIZE
