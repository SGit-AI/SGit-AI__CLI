from sg_send_cli.schemas.Schema__Branch_Index import Schema__Branch_Index
from sg_send_cli.schemas.Schema__Branch_Meta  import Schema__Branch_Meta


class Test_Schema__Branch_Index:

    def test_create_with_defaults(self):
        idx = Schema__Branch_Index()
        assert idx.schema   is None
        assert idx.index_id is None
        assert idx.branches == []

    def test_create_with_branches(self):
        branch = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                     name          = 'current',
                                     head_ref_id   = 'ref-a1b2c3d4',
                                     public_key_id = 'key-deadbeef',
                                     created_at    = 1710412800000)
        idx = Schema__Branch_Index(schema   = 'branch_index_v1',
                                   index_id = 'idx-11223344',
                                   branches = [branch])
        assert len(idx.branches) == 1
        assert idx.branches[0].name == 'current'

    def test_round_trip(self):
        branch = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                     name          = 'current',
                                     head_ref_id   = 'ref-a1b2c3d4',
                                     public_key_id = 'key-deadbeef',
                                     created_at    = 1710412800000)
        idx      = Schema__Branch_Index(schema   = 'branch_index_v1',
                                        index_id = 'idx-11223344',
                                        branches = [branch])
        restored = Schema__Branch_Index.from_json(idx.json())
        assert restored.json() == idx.json()

    def test_round_trip_empty(self):
        idx      = Schema__Branch_Index()
        restored = Schema__Branch_Index.from_json(idx.json())
        assert restored.json() == idx.json()
