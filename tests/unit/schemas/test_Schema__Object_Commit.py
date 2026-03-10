from sg_send_cli.schemas.Schema__Object_Commit import Schema__Object_Commit


class Test_Schema__Object_Commit:

    def test_create_with_defaults(self):
        commit = Schema__Object_Commit()
        assert commit.parent    is None
        assert commit.tree_id   is None
        assert commit.timestamp is None
        assert commit.message   is None
        assert commit.version   == 0

    def test_create_initial_commit(self):
        commit = Schema__Object_Commit(parent    = None,
                                       tree_id   = 'a1b2c3d4e5f6',
                                       timestamp = '2026-03-04T12:00:00.000Z',
                                       message   = 'Initial commit',
                                       version   = 1)
        assert commit.parent  is None
        assert commit.tree_id == 'a1b2c3d4e5f6'
        assert commit.version == 1

    def test_create_with_parent(self):
        commit = Schema__Object_Commit(parent    = 'b2c3d4e5f6a1',
                                       tree_id   = 'c3d4e5f6a1b2',
                                       timestamp = '2026-03-04T13:00:00Z',
                                       message   = 'Add files',
                                       version   = 2)
        assert commit.parent == 'b2c3d4e5f6a1'

    def test_round_trip(self):
        commit   = Schema__Object_Commit(parent    = 'b2c3d4e5f6a1',
                                         tree_id   = 'c3d4e5f6a1b2',
                                         timestamp = '2026-03-04T12:00:00.000Z',
                                         message   = 'Test commit',
                                         version   = 3)
        restored = Schema__Object_Commit.from_json(commit.json())
        assert restored.json() == commit.json()

    def test_round_trip_initial_commit(self):
        commit   = Schema__Object_Commit(tree_id   = 'a1b2c3d4e5f6',
                                         timestamp = '2026-03-04T12:00:00Z',
                                         version   = 1)
        restored = Schema__Object_Commit.from_json(commit.json())
        assert restored.json() == commit.json()

    def test_round_trip_empty(self):
        commit   = Schema__Object_Commit()
        restored = Schema__Object_Commit.from_json(commit.json())
        assert restored.json() == commit.json()

    def test_field_types_preserved(self):
        commit = Schema__Object_Commit(tree_id='a1b2c3d4e5f6')
        assert type(commit.tree_id).__name__ == 'Safe_Str__Object_Id'

    def test_auto_generated_message(self):
        commit = Schema__Object_Commit(message='Push: 2 added, 1 modified, 0 deleted')
        assert 'Push:' in str(commit.message)
