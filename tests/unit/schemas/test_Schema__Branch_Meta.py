from sg_send_cli.schemas.Schema__Branch_Meta  import Schema__Branch_Meta
from sg_send_cli.safe_types.Enum__Branch_Type import Enum__Branch_Type


class Test_Schema__Branch_Meta:

    def test_create_with_defaults(self):
        meta = Schema__Branch_Meta()
        assert meta.branch_id      is None
        assert meta.name           is None
        assert meta.branch_type    == Enum__Branch_Type.NAMED
        assert meta.head_ref_id    is None
        assert meta.public_key_id  is None
        assert meta.private_key_id is None
        assert meta.created_at     == 0
        assert meta.creator_branch is None

    def test_create_named_branch(self):
        meta = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                   name          = 'current',
                                   branch_type   = Enum__Branch_Type.NAMED,
                                   head_ref_id   = 'ref-a1b2c3d4',
                                   public_key_id = 'key-deadbeef',
                                   created_at    = 1710412800000)
        assert meta.branch_id     == 'branch-named-a1b2c3d4'
        assert meta.name          == 'current'
        assert meta.branch_type   == Enum__Branch_Type.NAMED

    def test_create_clone_branch(self):
        meta = Schema__Branch_Meta(branch_id      = 'branch-clone-c3d4e5f6',
                                   name           = 'fp_br1_3c8f',
                                   branch_type    = Enum__Branch_Type.CLONE,
                                   head_ref_id    = 'ref-c3d4e5f6',
                                   public_key_id  = 'key-11223344',
                                   creator_branch = 'branch-named-a1b2c3d4',
                                   created_at     = 1710412800000)
        assert meta.branch_type    == Enum__Branch_Type.CLONE
        assert meta.private_key_id is None

    def test_round_trip(self):
        meta     = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                       name          = 'current',
                                       head_ref_id   = 'ref-a1b2c3d4',
                                       public_key_id = 'key-deadbeef',
                                       created_at    = 1710412800000)
        restored = Schema__Branch_Meta.from_json(meta.json())
        assert restored.json() == meta.json()
