import hashlib
from sg_send_cli.schemas.Schema__Vault_Index_Entry import Schema__Vault_Index_Entry
from sg_send_cli.safe_types.Enum__Sync_State       import Enum__Sync_State


class Test_Schema__Vault_Index_Entry:

    def test_create_with_defaults(self):
        entry = Schema__Vault_Index_Entry()
        assert entry.state == Enum__Sync_State.SYNCED

    def test_create_with_values(self):
        h = hashlib.sha256(b'test content').hexdigest()
        entry = Schema__Vault_Index_Entry(file_path='docs/readme.txt',
                                          local_hash=h,
                                          local_size=1024,
                                          remote_transfer_id='abc123def456',
                                          remote_hash=h,
                                          remote_size=1024,
                                          state=Enum__Sync_State.SYNCED)
        assert entry.file_path  == 'docs/readme.txt'
        assert entry.local_hash == h
        assert entry.local_size == 1024

    def test_round_trip(self):
        h = hashlib.sha256(b'data').hexdigest()
        entry = Schema__Vault_Index_Entry(file_path='test.txt',
                                          local_hash=h,
                                          local_size=42,
                                          remote_transfer_id='abc123def456',
                                          remote_hash=h,
                                          remote_size=42,
                                          state=Enum__Sync_State.MODIFIED_LOCALLY)
        restored = Schema__Vault_Index_Entry.from_json(entry.json())
        assert restored.json() == entry.json()

    def test_state_serializes_as_value(self):
        entry = Schema__Vault_Index_Entry(state=Enum__Sync_State.CONFLICT)
        json_data = entry.json()
        assert json_data['state'] == 'conflict'
