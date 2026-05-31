from sgit_ai.schemas.Schema__Branch_Index import Schema__Branch_Index
from sgit_ai.schemas.Schema__Branch_Meta  import Schema__Branch_Meta
class Test_Schema__Branch_Index:
    def test_create_with_defaults(self):
        idx = Schema__Branch_Index()
        assert idx.schema   is None
        assert idx.branches == []
    def test_create_with_branches(self):
        branch = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                     name          = 'current',
                                     head_ref_id   = 'ref-pid-muw-a1b2c3d4e5f6',
                                     public_key_id = 'key-rnd-imm-deadbeefcafe',
                                     created_at    = 1710412800000)
        idx = Schema__Branch_Index(schema   = 'branch_index_v1',
                                   branches = [branch])
        assert len(idx.branches) == 1
        assert idx.branches[0].name == 'current'
    def test_round_trip(self):
        branch = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                     name          = 'current',
                                     head_ref_id   = 'ref-pid-muw-a1b2c3d4e5f6',
                                     public_key_id = 'key-rnd-imm-deadbeefcafe',
                                     created_at    = 1710412800000)
        idx      = Schema__Branch_Index(schema   = 'branch_index_v1',
                                        branches = [branch])
        restored = Schema__Branch_Index.from_json(idx.json())
        assert restored.json() == idx.json()
    def test_round_trip_empty(self):
        idx      = Schema__Branch_Index()
        restored = Schema__Branch_Index.from_json(idx.json())
        assert restored.json() == idx.json()

    # Verbatim payload captured from a web-UI-created vault (coral-bank-5246).
    # Locks the wire-format gap that previously broke `sgit clone` on any vault
    # whose branch index was written by the browser (ISO timestamps).
    def test_from_json__web_ui_written_branch_index(self):
        web_payload = {'schema'  : 'branch_index_v1',
                       'branches': [{'branch_id'  : 'branch-named-14d6eaa0d640',
                                     'branch_type': 'named',
                                     'head_ref_id': 'ref-pid-muw-a7a08b989ba2',
                                     'name'       : 'current',
                                     'created_at' : '2026-05-07T01:28:18.495Z'},
                                    {'branch_id'  : 'branch-clone-9e801834292a',
                                     'branch_type': 'clone',
                                     'head_ref_id': 'ref-pid-snw-449cd0c04762',
                                     'name'       : 'web-ui',
                                     'created_at' : '2026-05-07T01:28:18.495Z'}]}
        idx = Schema__Branch_Index.from_json(web_payload)
        assert len(idx.branches)              == 2
        assert str(idx.branches[0].name)      == 'current'
        assert int(idx.branches[0].created_at) == 1778117298495
        assert str(idx.branches[1].name)      == 'web-ui'
        assert int(idx.branches[1].created_at) == 1778117298495
