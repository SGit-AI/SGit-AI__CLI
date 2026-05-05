"""Tests for shared workflow step library — B15 structural tests."""
from sgit_ai.workflow.shared.Keys__Derivation import Keys__Derivation


class Test_Keys__Derivation:

    def test_instantiates(self):
        kd = Keys__Derivation()
        assert kd is not None

    def test_derive_calls_sync_client(self):
        kd = Keys__Derivation()

        class FakeSyncClient:
            def _derive_keys_from_stored_key(self, vault_key):
                return {
                    'vault_id'             : 'testvlt1',
                    'read_key'             : 'aabbcc',
                    'write_key'            : 'ddeeff',
                    'branch_index_file_id' : 'idx001',
                }

        result = kd.derive('pass:testvlt1', FakeSyncClient())
        assert result['vault_id']              == 'testvlt1'
        assert result['read_key_hex']          == 'aabbcc'
        assert result['write_key_hex']         == 'ddeeff'
        assert result['branch_index_file_id']  == 'idx001'

    def test_derive_returns_all_keys(self):
        kd = Keys__Derivation()

        class FakeSyncClient:
            def _derive_keys_from_stored_key(self, vault_key):
                return {'vault_id': 'v', 'read_key': 'r', 'write_key': 'w',
                        'branch_index_file_id': 'b'}

        result = kd.derive('x', FakeSyncClient())
        assert set(result.keys()) == {'vault_id', 'read_key_hex', 'write_key_hex',
                                      'branch_index_file_id'}
