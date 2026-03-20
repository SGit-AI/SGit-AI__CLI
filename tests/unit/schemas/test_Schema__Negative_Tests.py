from sgit_ai.schemas.Schema__Vault_Meta        import Schema__Vault_Meta
from sgit_ai.schemas.Schema__Vault_Config      import Schema__Vault_Config
from sgit_ai.schemas.Schema__Vault_Index       import Schema__Vault_Index
from sgit_ai.schemas.Schema__Vault_Index_Entry import Schema__Vault_Index_Entry
from sgit_ai.schemas.Schema__Secret_Entry      import Schema__Secret_Entry
from sgit_ai.schemas.Schema__Object_Commit     import Schema__Object_Commit
from sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sgit_ai.schemas.Schema__Object_Ref        import Schema__Object_Ref
from sgit_ai.schemas.Schema__Transfer_File     import Schema__Transfer_File


class Test_Schema__Vault_Meta__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Vault_Meta.from_json({})
        assert schema.vault_id  is None
        assert schema.name      is None
        assert schema.version   == 0

    def test_round_trip__minimal(self):
        schema   = Schema__Vault_Meta()
        restored = Schema__Vault_Meta.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_from_json__null_fields(self):
        schema = Schema__Vault_Meta.from_json({'vault_id': None, 'name': None})
        assert schema.vault_id is None
        assert schema.name     is None


class Test_Schema__Vault_Config__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Vault_Config.from_json({})
        assert schema.vault_id     is None
        assert schema.endpoint_url is None
        assert schema.access_token is None

    def test_round_trip__minimal(self):
        schema   = Schema__Vault_Config()
        restored = Schema__Vault_Config.from_json(schema.json())
        assert restored.json() == schema.json()


class Test_Schema__Vault_Index__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Vault_Index.from_json({})
        assert schema.vault_id is None
        assert schema.version  == 0
        assert schema.entries  == []

    def test_round_trip__empty_entries(self):
        schema   = Schema__Vault_Index()
        restored = Schema__Vault_Index.from_json(schema.json())
        assert restored.json() == schema.json()


class Test_Schema__Vault_Index_Entry__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Vault_Index_Entry.from_json({})
        assert schema.file_path   is None
        assert schema.local_hash  is None
        assert schema.local_size  == 0

    def test_round_trip__defaults(self):
        schema   = Schema__Vault_Index_Entry()
        restored = Schema__Vault_Index_Entry.from_json(schema.json())
        assert restored.json() == schema.json()


class Test_Schema__Secret_Entry__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Secret_Entry.from_json({})
        assert schema.key        is None
        assert schema.created_at is None

    def test_round_trip__defaults(self):
        schema   = Schema__Secret_Entry()
        restored = Schema__Secret_Entry.from_json(schema.json())
        assert restored.json() == schema.json()


class Test_Schema__Object_Commit__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Object_Commit.from_json({})
        assert schema.tree_id      is None
        assert schema.message_enc  is None
        assert schema.timestamp_ms == 0
        assert schema.parents      == []

    def test_from_json__null_tree_id(self):
        schema = Schema__Object_Commit.from_json({'tree_id': None})
        assert schema.tree_id is None

    def test_round_trip__with_enc_message(self):
        schema   = Schema__Object_Commit(message_enc='ZW5jLW1zZw==')
        restored = Schema__Object_Commit.from_json(schema.json())
        assert restored.json() == schema.json()


class Test_Schema__Object_Tree__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Object_Tree.from_json({})
        assert schema.entries == []

    def test_entry_lookup__empty_tree(self):
        tree  = Schema__Object_Tree()
        entry = next((e for e in tree.entries if str(e.blob_id) == 'missing'), None)
        assert entry is None

    def test_entries__empty_tree(self):
        tree = Schema__Object_Tree()
        assert len(tree.entries) == 0

    def test_round_trip__empty(self):
        schema   = Schema__Object_Tree()
        restored = Schema__Object_Tree.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_round_trip__with_entries(self):
        tree = Schema__Object_Tree()
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-aabbccddeeff',
                                                      name_enc='ZW5jLWZpbGUx'))
        tree.entries.append(Schema__Object_Tree_Entry(tree_id='obj-cas-imm-112233445566',
                                                      name_enc='ZW5jLWRpcg=='))
        restored = Schema__Object_Tree.from_json(tree.json())
        assert restored.json() == tree.json()
        assert len(restored.entries) == 2


class Test_Schema__Object_Ref__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Object_Ref.from_json({})
        assert schema.commit_id is None
        assert schema.version   == 0

    def test_round_trip__defaults(self):
        schema   = Schema__Object_Ref()
        restored = Schema__Object_Ref.from_json(schema.json())
        assert restored.json() == schema.json()


class Test_Schema__Transfer_File__Negative:

    def test_from_json__empty_dict(self):
        schema = Schema__Transfer_File.from_json({})
        assert schema.transfer_id  is None
        assert schema.file_path    is None
        assert schema.file_hash    is None
        assert schema.file_size    == 0
        assert schema.content_type is None

    def test_round_trip__defaults(self):
        schema   = Schema__Transfer_File()
        restored = Schema__Transfer_File.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_round_trip__with_values(self):
        schema   = Schema__Transfer_File(file_path='docs/readme.md',
                                          file_size=1024,
                                          content_type='text/markdown')
        restored = Schema__Transfer_File.from_json(schema.json())
        assert restored.json() == schema.json()
