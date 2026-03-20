from sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Test_Schema__Object_Tree_Entry:

    def test_create_with_defaults(self):
        entry = Schema__Object_Tree_Entry()
        assert entry.blob_id          is None
        assert entry.tree_id          is None
        assert entry.name_enc         is None
        assert entry.content_type_enc is None

    def test_create_with_values(self):
        entry = Schema__Object_Tree_Entry(blob_id='obj-cas-imm-a1b2c3d4e5f6',
                                          name_enc='ZW5jLW5hbWU=',
                                          size_enc='ZW5jLXNpemU=',
                                          content_hash_enc='ZW5jLWhhc2g=',
                                          content_type_enc='ZW5jLXR5cGU=')
        assert entry.blob_id          == 'obj-cas-imm-a1b2c3d4e5f6'
        assert entry.name_enc         == 'ZW5jLW5hbWU='
        assert entry.content_type_enc == 'ZW5jLXR5cGU='

    def test_create_directory_entry(self):
        entry = Schema__Object_Tree_Entry(tree_id='obj-cas-imm-aabbccddeeff',
                                          name_enc='ZW5jLWRpcg==')
        assert entry.tree_id  == 'obj-cas-imm-aabbccddeeff'
        assert entry.blob_id  is None

    def test_round_trip(self):
        entry    = Schema__Object_Tree_Entry(blob_id='obj-cas-imm-a1b2c3d4e5f6',
                                             name_enc='ZW5jLW5hbWU=',
                                             size_enc='ZW5jLXNpemU=')
        restored = Schema__Object_Tree_Entry.from_json(entry.json())
        assert restored.json() == entry.json()


class Test_Schema__Object_Tree:

    def test_create_empty(self):
        tree = Schema__Object_Tree()
        assert tree.entries == []

    def test_add_entry(self):
        tree  = Schema__Object_Tree()
        entry = Schema__Object_Tree_Entry(blob_id='obj-cas-imm-a1b2c3d4e5f6',
                                          name_enc='ZW5jLXJlYWRtZQ==')
        tree.entries.append(entry)
        assert len(tree.entries) == 1

    def test_add_multiple_entries(self):
        tree = Schema__Object_Tree()
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-a1b2c3d4e5f6',
                                                      name_enc='ZW5jLWZpbGUx'))
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-b2c3d4e5f6a1',
                                                      name_enc='ZW5jLWZpbGUy'))
        assert len(tree.entries) == 2

    def test_mixed_file_and_dir_entries(self):
        tree = Schema__Object_Tree()
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-a1b2c3d4e5f6',
                                                      name_enc='ZW5jLWZpbGU='))
        tree.entries.append(Schema__Object_Tree_Entry(tree_id='obj-cas-imm-c3d4e5f6a1b2',
                                                      name_enc='ZW5jLXN1YmRpcg=='))
        assert len(tree.entries) == 2
        assert tree.entries[0].blob_id is not None
        assert tree.entries[1].tree_id is not None

    def test_round_trip(self):
        tree = Schema__Object_Tree()
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-a1b2c3d4e5f6',
                                                      name_enc='ZW5jLWE='))
        tree.entries.append(Schema__Object_Tree_Entry(tree_id='obj-cas-imm-b2c3d4e5f6a1',
                                                      name_enc='ZW5jLWI='))
        restored = Schema__Object_Tree.from_json(tree.json())
        assert restored.json() == tree.json()

    def test_round_trip_empty(self):
        tree     = Schema__Object_Tree()
        restored = Schema__Object_Tree.from_json(tree.json())
        assert restored.json() == tree.json()
