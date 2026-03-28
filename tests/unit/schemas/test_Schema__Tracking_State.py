from sgit_ai.schemas.Schema__Tracking_State import Schema__Tracking_State, Schema__Tracking_Entry


class Test_Schema__Tracking_State:

    def test_create_empty(self):
        ts = Schema__Tracking_State()
        assert ts.entries == []

    def test_create_with_entries(self):
        entry = Schema__Tracking_Entry(ref_id='ref-pid-muw-a1b2c3d4e5f6', commit_id='obj-cas-imm-a1b2c3d4e5f6')
        ts    = Schema__Tracking_State(entries=[entry])
        assert len(ts.entries) == 1
        assert ts.entries[0].ref_id    == 'ref-pid-muw-a1b2c3d4e5f6'
        assert ts.entries[0].commit_id == 'obj-cas-imm-a1b2c3d4e5f6'

    def test_round_trip(self):
        entry    = Schema__Tracking_Entry(ref_id='ref-pid-muw-a1b2c3d4e5f6', commit_id='obj-cas-imm-a1b2c3d4e5f6')
        ts       = Schema__Tracking_State(entries=[entry])
        restored = Schema__Tracking_State.from_json(ts.json())
        assert restored.json() == ts.json()
