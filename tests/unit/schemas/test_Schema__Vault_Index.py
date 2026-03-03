import hashlib
from sg_send_cli.schemas.Schema__Vault_Index       import Schema__Vault_Index
from sg_send_cli.schemas.Schema__Vault_Index_Entry import Schema__Vault_Index_Entry
from sg_send_cli.safe_types.Enum__Sync_State       import Enum__Sync_State


class Test_Schema__Vault_Index:

    def test_create_empty(self):
        index = Schema__Vault_Index(vault_id='abcd1234')
        assert index.vault_id == 'abcd1234'
        assert len(index.entries) == 0

    def test_add_entry(self):
        h = hashlib.sha256(b'content').hexdigest()
        index = Schema__Vault_Index(vault_id='abcd1234')
        entry = Schema__Vault_Index_Entry(file_path='test.txt',
                                          local_hash=h,
                                          local_size=100,
                                          remote_transfer_id='abc123def456',
                                          remote_hash=h,
                                          remote_size=100)
        index.entries.append(entry)
        assert len(index.entries) == 1

    def test_round_trip(self):
        index    = Schema__Vault_Index(vault_id='abcd1234')
        restored = Schema__Vault_Index.from_json(index.json())
        assert restored.json() == index.json()

    def test_round_trip_with_entries(self):
        h = hashlib.sha256(b'file data').hexdigest()
        index = Schema__Vault_Index(vault_id='abcd1234')
        entry = Schema__Vault_Index_Entry(file_path='notes.txt',
                                          local_hash=h,
                                          local_size=512,
                                          remote_transfer_id='abc123def456',
                                          remote_hash=h,
                                          remote_size=512,
                                          state=Enum__Sync_State.SYNCED)
        index.entries.append(entry)
        restored = Schema__Vault_Index.from_json(index.json())
        assert restored.json() == index.json()
        assert len(restored.entries) == 1
