"""Tests for Vault__Crypto.import_read_key()."""
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


class Test_Vault__Crypto__Import_Read_Key:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    def test_import_read_key_returns_dict(self):
        keys     = self.crypto.derive_keys('passphrase', 'vaultid1')
        read_key = keys['read_key']
        result   = self.crypto.import_read_key(read_key, 'vaultid1')
        assert isinstance(result, dict)

    def test_import_read_key_has_required_fields(self):
        keys     = self.crypto.derive_keys('passphrase', 'vaultid1')
        read_key = keys['read_key']
        result   = self.crypto.import_read_key(read_key, 'vaultid1')
        assert 'read_key_bytes' in result
        assert 'read_key' in result
        assert 'write_key' in result
        assert 'ref_file_id' in result
        assert 'branch_index_file_id' in result
        assert 'vault_id' in result

    def test_import_read_key_derived_ids_match_derive_keys(self):
        """import_read_key must produce the same ref and index IDs as derive_keys."""
        passphrase = 'mytestpassphrase'
        vault_id   = 'myvaultid1'
        keys       = self.crypto.derive_keys(passphrase, vault_id)
        imported   = self.crypto.import_read_key(keys['read_key'], vault_id)
        assert imported['ref_file_id']          == keys['ref_file_id']
        assert imported['branch_index_file_id'] == keys['branch_index_file_id']

    def test_import_read_key_bytes_roundtrip(self):
        passphrase = 'roundtrip'
        vault_id   = 'vtestrt01'
        keys       = self.crypto.derive_keys(passphrase, vault_id)
        imported   = self.crypto.import_read_key(keys['read_key'], vault_id)
        assert imported['read_key_bytes'] == keys['read_key_bytes']
        assert imported['read_key']       == keys['read_key']

    def test_import_read_key_write_key_is_empty(self):
        keys     = self.crypto.derive_keys('passphrase', 'vaultid1')
        imported = self.crypto.import_read_key(keys['read_key'], 'vaultid1')
        assert imported['write_key'] == ''
        assert imported['write_key_bytes'] is None

    def test_import_read_key_vault_id_preserved(self):
        keys     = self.crypto.derive_keys('passphrase', 'vaultid2')
        imported = self.crypto.import_read_key(keys['read_key'], 'vaultid2')
        assert imported['vault_id'] == 'vaultid2'
