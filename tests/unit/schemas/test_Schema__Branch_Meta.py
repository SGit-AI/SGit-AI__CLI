from sgit_ai.schemas.Schema__Branch_Meta  import Schema__Branch_Meta
from sgit_ai.safe_types.Enum__Branch_Type import Enum__Branch_Type


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
        assert meta.display_name   is None

    def test_create_named_branch(self):
        meta = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                   name          = 'current',
                                   branch_type   = Enum__Branch_Type.NAMED,
                                   head_ref_id   = 'ref-pid-muw-a1b2c3d4e5f6',
                                   public_key_id = 'key-rnd-imm-deadbeefcafe',
                                   created_at    = 1710412800000)
        assert meta.branch_id     == 'branch-named-a1b2c3d4'
        assert meta.name          == 'current'
        assert meta.branch_type   == Enum__Branch_Type.NAMED

    def test_create_clone_branch(self):
        meta = Schema__Branch_Meta(branch_id      = 'branch-clone-c3d4e5f6',
                                   name           = 'fp_br1_3c8f',
                                   branch_type    = Enum__Branch_Type.CLONE,
                                   head_ref_id    = 'ref-pid-snw-c3d4e5f6a1b2',
                                   public_key_id  = 'key-rnd-imm-112233445566',
                                   creator_branch = 'branch-named-a1b2c3d4',
                                   created_at     = 1710412800000)
        assert meta.branch_type    == Enum__Branch_Type.CLONE
        assert meta.private_key_id is None

    def test_round_trip(self):
        meta     = Schema__Branch_Meta(branch_id     = 'branch-named-a1b2c3d4',
                                       name          = 'current',
                                       head_ref_id   = 'ref-pid-muw-a1b2c3d4e5f6',
                                       public_key_id = 'key-rnd-imm-deadbeefcafe',
                                       created_at    = 1710412800000)
        restored = Schema__Branch_Meta.from_json(meta.json())
        assert restored.json() == meta.json()

    # Web UI writes created_at as JS Date.toISOString() — e.g. "2026-05-07T01:28:18.495Z".
    # The CLI writes it as int ms. Both forms must deserialize cleanly through from_json
    # so that vaults created in either client can be cloned by the other.
    def test_from_json__accepts_iso_created_at__web_ui_format(self):
        web_written = {'branch_id'   : 'branch-named-14d6eaa0d640',
                       'branch_type' : 'named',
                       'head_ref_id' : 'ref-pid-muw-a7a08b989ba2',
                       'name'        : 'current',
                       'created_at'  : '2026-05-07T01:28:18.495Z'}
        meta = Schema__Branch_Meta.from_json(web_written)
        assert int(meta.created_at) == 1778117298495                                # ISO canonicalised to ms epoch
        assert meta.json()['created_at'] == 1778117298495                           # JSON output stays as int ms

    def test_from_json__accepts_int_ms_created_at__cli_format(self):
        cli_written = {'branch_id'   : 'branch-named-14d6eaa0d640',
                       'branch_type' : 'named',
                       'head_ref_id' : 'ref-pid-muw-a7a08b989ba2',
                       'name'        : 'current',
                       'created_at'  : 1710412800000}
        meta = Schema__Branch_Meta.from_json(cli_written)
        assert int(meta.created_at) == 1710412800000

    # display_name (interop contract v0): optional, additive, NEVER used for lookup.
    # The wire `name` stays the lookup key ("current" for the named branch); display_name
    # is a UI label the web can show as e.g. "main" without ever touching the wire name.

    def test_display_name_optional_and_round_trips(self):
        meta = Schema__Branch_Meta(branch_id    = 'branch-named-14d6eaa0d640',
                                   name         = 'current',
                                   head_ref_id  = 'ref-pid-muw-a7a08b989ba2',
                                   display_name = 'main')
        assert str(meta.display_name) == 'main'
        restored = Schema__Branch_Meta.from_json(meta.json())
        assert restored.json() == meta.json()
        assert str(restored.display_name) == 'main'

    def test_from_json__accepts_display_name_from_web(self):
        web_with_label = {'branch_id'    : 'branch-named-14d6eaa0d640',
                          'branch_type'  : 'named',
                          'head_ref_id'  : 'ref-pid-muw-a7a08b989ba2',
                          'name'         : 'current',
                          'display_name' : 'main'}
        meta = Schema__Branch_Meta.from_json(web_with_label)
        assert str(meta.name)         == 'current'         # still the lookup key
        assert str(meta.display_name) == 'main'            # UI label only

    def test_lookup_still_uses_wire_name_not_display_name(self):
        """get_branch_by_name MUST resolve via `name`, not `display_name` — pinning
        the contract's lookup rule directly against Vault__Branch_Manager."""
        from sgit_ai.schemas.Schema__Branch_Index    import Schema__Branch_Index
        from sgit_ai.storage.Vault__Branch_Manager   import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Storage          import Vault__Storage
        from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto

        meta = Schema__Branch_Meta(branch_id    = 'branch-named-14d6eaa0d640',
                                   name         = 'current',
                                   head_ref_id  = 'ref-pid-muw-a7a08b989ba2',
                                   display_name = 'main')
        index = Schema__Branch_Index(schema='branch_index_v1', branches=[meta])
        bm    = Vault__Branch_Manager(storage=Vault__Storage(), crypto=Vault__Crypto())

        assert bm.get_branch_by_name(index, 'current') is not None    # wire name resolves
        assert bm.get_branch_by_name(index, 'main')    is None        # display_name MUST NOT
