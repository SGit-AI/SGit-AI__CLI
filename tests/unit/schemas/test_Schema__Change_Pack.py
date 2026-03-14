from sg_send_cli.schemas.Schema__Change_Pack import Schema__Change_Pack


class Test_Schema__Change_Pack:

    def test_create_with_defaults(self):
        cp = Schema__Change_Pack()
        assert cp.schema       is None
        assert cp.branch_id    is None
        assert cp.created_at   == 0
        assert cp.creator_key  is None
        assert cp.signature    is None
        assert cp.payload_hash is None
        assert cp.payload      == []

    def test_create_with_values(self):
        cp = Schema__Change_Pack(schema       = 'change_pack_v1',
                                 branch_id    = 'branch-clone-a1b2c3d4',
                                 created_at   = 1710412800000,
                                 creator_key  = 'key-deadbeef',
                                 payload      = ['bare/data/obj-abc123', 'bare/refs/ref-def456'])
        assert len(cp.payload) == 2

    def test_round_trip(self):
        cp       = Schema__Change_Pack(schema     = 'change_pack_v1',
                                       branch_id  = 'branch-clone-a1b2c3d4',
                                       created_at = 1710412800000)
        restored = Schema__Change_Pack.from_json(cp.json())
        assert restored.json() == cp.json()
