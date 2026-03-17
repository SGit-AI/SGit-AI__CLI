from sg_send_cli.schemas.Schema__Object_Commit import Schema__Object_Commit


class Test_Schema__Object_Commit:

    def test_create_with_defaults(self):
        commit = Schema__Object_Commit()
        assert commit.tree_id      is None
        assert commit.parents      == []
        assert commit.timestamp_ms == 0
        assert commit.message_enc  is None
        assert commit.schema       is None

    def test_create_initial_commit(self):
        commit = Schema__Object_Commit(tree_id      = 'obj-cas-imm-a1b2c3d4e5f6',
                                       schema       = 'commit_v1',
                                       timestamp_ms = 1710412800000,
                                       message_enc  = 'ZW5jLW1zZw==')
        assert commit.tree_id      == 'obj-cas-imm-a1b2c3d4e5f6'
        assert commit.timestamp_ms == 1710412800000
        assert commit.message_enc  == 'ZW5jLW1zZw=='

    def test_create_with_parents(self):
        commit = Schema__Object_Commit(parents      = ['obj-cas-imm-b2c3d4e5f6a1'],
                                       tree_id      = 'obj-cas-imm-c3d4e5f6a1b2',
                                       schema       = 'commit_v1',
                                       timestamp_ms = 1710412800000)
        assert len(commit.parents) == 1
        assert commit.parents[0]   == 'obj-cas-imm-b2c3d4e5f6a1'

    def test_round_trip(self):
        commit   = Schema__Object_Commit(parents      = ['obj-cas-imm-b2c3d4e5f6a1'],
                                          tree_id      = 'obj-cas-imm-c3d4e5f6a1b2',
                                          schema       = 'commit_v1',
                                          timestamp_ms = 1710412800000,
                                          message_enc  = 'ZW5jLW1zZw==',
                                          branch_id    = 'branch-named-a1b2c3d4')
        restored = Schema__Object_Commit.from_json(commit.json())
        assert restored.json() == commit.json()

    def test_round_trip_initial_commit(self):
        commit   = Schema__Object_Commit(tree_id='obj-cas-imm-a1b2c3d4e5f6',
                                          schema='commit_v1',
                                          timestamp_ms=1710412800000)
        restored = Schema__Object_Commit.from_json(commit.json())
        assert restored.json() == commit.json()

    def test_field_types_preserved(self):
        commit = Schema__Object_Commit(tree_id='obj-cas-imm-a1b2c3d4e5f6')
        assert type(commit.tree_id).__name__ == 'Safe_Str__Object_Id'
