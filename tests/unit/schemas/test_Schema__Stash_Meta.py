import time

from sgit_ai.safe_types.Safe_UInt__Timestamp import Safe_UInt__Timestamp
from sgit_ai.schemas.Schema__Stash_Meta      import Schema__Stash_Meta


class Test_Schema__Stash_Meta:

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_default_construction(self):
        meta = Schema__Stash_Meta()
        assert int(meta.created_at)     == 0
        assert meta.base_commit         is None
        assert meta.files_added         == []
        assert meta.files_modified      == []
        assert meta.files_deleted       == []

    def test_created_at_is_uint(self):
        now  = int(time.time() * 1000)
        meta = Schema__Stash_Meta(created_at=Safe_UInt__Timestamp(now))
        assert int(meta.created_at) == now

    def test_created_at_type(self):
        now  = int(time.time() * 1000)
        meta = Schema__Stash_Meta(created_at=Safe_UInt__Timestamp(now))
        # created_at must be integral (milliseconds)
        assert isinstance(int(meta.created_at), int)

    def test_files_lists_default_empty(self):
        meta = Schema__Stash_Meta()
        assert isinstance(meta.files_added,    list)
        assert isinstance(meta.files_modified, list)
        assert isinstance(meta.files_deleted,  list)
        assert len(meta.files_added)    == 0
        assert len(meta.files_modified) == 0
        assert len(meta.files_deleted)  == 0

    def test_files_lists_populated(self):
        meta = Schema__Stash_Meta(
            created_at     = Safe_UInt__Timestamp(1000),
            files_added    = ['new.txt'],
            files_modified = ['changed.txt'],
            files_deleted  = ['old.txt'],
        )
        assert meta.files_added    == ['new.txt']
        assert meta.files_modified == ['changed.txt']
        assert meta.files_deleted  == ['old.txt']

    # ------------------------------------------------------------------
    # Round-trip invariant
    # ------------------------------------------------------------------

    def test_round_trip_empty(self):
        meta      = Schema__Stash_Meta()
        restored  = Schema__Stash_Meta.from_json(meta.json())
        assert restored.json() == meta.json()

    def test_round_trip_with_values(self):
        now  = int(time.time() * 1000)
        meta = Schema__Stash_Meta(
            created_at     = Safe_UInt__Timestamp(now),
            files_added    = ['a.txt', 'b.txt'],
            files_modified = ['c.txt'],
            files_deleted  = ['d.txt'],
        )
        restored = Schema__Stash_Meta.from_json(meta.json())
        assert restored.json() == meta.json()

    def test_round_trip_preserves_lists(self):
        now  = int(time.time() * 1000)
        meta = Schema__Stash_Meta(
            created_at     = Safe_UInt__Timestamp(now),
            files_added    = ['x.txt'],
            files_modified = [],
            files_deleted  = ['y.txt'],
        )
        restored = Schema__Stash_Meta.from_json(meta.json())
        assert restored.files_added    == ['x.txt']
        assert restored.files_modified == []
        assert restored.files_deleted  == ['y.txt']

    # ------------------------------------------------------------------
    # JSON structure
    # ------------------------------------------------------------------

    def test_json_contains_expected_keys(self):
        meta = Schema__Stash_Meta()
        data = meta.json()
        assert 'created_at'     in data
        assert 'base_commit'    in data
        assert 'files_added'    in data
        assert 'files_modified' in data
        assert 'files_deleted'  in data

    def test_json_created_at_is_int(self):
        now  = int(time.time() * 1000)
        meta = Schema__Stash_Meta(created_at=Safe_UInt__Timestamp(now))
        data = meta.json()
        assert isinstance(data['created_at'], int)

    def test_json_lists_are_lists(self):
        meta = Schema__Stash_Meta()
        data = meta.json()
        assert isinstance(data['files_added'],    list)
        assert isinstance(data['files_modified'], list)
        assert isinstance(data['files_deleted'],  list)

    # ------------------------------------------------------------------
    # setup() helper
    # ------------------------------------------------------------------

    def test_setup_sets_created_at_when_zero(self):
        meta = Schema__Stash_Meta()
        assert int(meta.created_at) == 0
        before = int(time.time() * 1000)
        meta.setup()
        after = int(time.time() * 1000)
        ts    = int(meta.created_at)
        assert before <= ts <= after

    def test_setup_does_not_override_existing_timestamp(self):
        fixed = 9_000_000_000_000
        meta  = Schema__Stash_Meta(created_at=Safe_UInt__Timestamp(fixed))
        meta.setup()
        assert int(meta.created_at) == fixed
