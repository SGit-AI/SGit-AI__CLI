"""Integration tests for key derivation, API read/write, and crypto round-trips.

Runs against the local SG/Send test server (in-memory mode).
No env vars, no live API, no skips.
"""
import json
import os
import tempfile
import shutil

import pytest

from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
from sg_send_cli.api.Vault__API       import Vault__API
from sg_send_cli.sync.Vault__Sync     import Vault__Sync


TEST_PASSPHRASE = 'integration-test-passphrase'
TEST_VAULT_ID   = 'integration-test-vault'
TEST_VAULT_KEY  = f'{TEST_PASSPHRASE}:{TEST_VAULT_ID}'


class Test_Vault__Integration__Key_Derivation:
    """Test that key derivation produces valid keys."""

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.keys   = self.crypto.derive_keys_from_vault_key(TEST_VAULT_KEY)

    def test_derive_keys__returns_all_fields(self):
        assert 'read_key'         in self.keys
        assert 'write_key'        in self.keys
        assert 'tree_file_id'     in self.keys
        assert 'settings_file_id' in self.keys
        assert 'vault_id'         in self.keys
        assert 'passphrase'       in self.keys

    def test_derive_keys__read_key_is_64_hex(self):
        assert len(self.keys['read_key']) == 64

    def test_derive_keys__write_key_is_64_hex(self):
        assert len(self.keys['write_key']) == 64

    def test_derive_keys__file_ids_are_12_hex(self):
        assert len(self.keys['tree_file_id'])     == 12
        assert len(self.keys['settings_file_id']) == 12

    def test_derive_keys__deterministic(self):
        keys2 = self.crypto.derive_keys_from_vault_key(TEST_VAULT_KEY)
        assert self.keys['read_key']         == keys2['read_key']
        assert self.keys['write_key']        == keys2['write_key']
        assert self.keys['tree_file_id']     == keys2['tree_file_id']
        assert self.keys['settings_file_id'] == keys2['settings_file_id']


class Test_Vault__Integration__Read_API:
    """Test reading/writing vault data via the API against the local server."""

    def _seed_vault(self, vault_api, crypto, vault_id, keys):
        """Seed the server with settings + tree + one file, simulating browser upload."""
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        file_content    = b'# README\nThis is a test vault file.'
        encrypted_file  = crypto.encrypt(read_key, file_content)
        content_file_id = 'cf' + os.urandom(5).hex()

        settings = {'vault_id': vault_id, 'vault_name': 'Test Vault'}
        tree     = {'version': 1,
                    'tree': {'/': {'type': 'folder',
                                   'children': {'README.md': {'type'   : 'file',
                                                               'file_id': content_file_id,
                                                               'size'   : len(file_content)}}}}}

        encrypted_settings = crypto.encrypt(read_key, json.dumps(settings).encode())
        encrypted_tree     = crypto.encrypt(read_key, json.dumps(tree).encode())

        vault_api.write(vault_id, content_file_id,          write_key, encrypted_file)
        vault_api.write(vault_id, keys['settings_file_id'], write_key, encrypted_settings)
        vault_api.write(vault_id, keys['tree_file_id'],     write_key, encrypted_tree)

        return dict(file_content=file_content, content_file_id=content_file_id)

    def test_write_and_read_settings(self, vault_api, crypto):
        keys     = crypto.derive_keys(TEST_PASSPHRASE, 'int-settings-vault')
        self._seed_vault(vault_api, crypto, 'int-settings-vault', keys)

        read_key  = keys['read_key_bytes']
        encrypted = vault_api.read('int-settings-vault', keys['settings_file_id'])
        assert len(encrypted) > 0

        decrypted     = crypto.decrypt(read_key, encrypted)
        settings_data = json.loads(decrypted)
        assert settings_data['vault_name'] == 'Test Vault'

    def test_write_and_read_tree(self, vault_api, crypto):
        keys     = crypto.derive_keys(TEST_PASSPHRASE, 'int-tree-vault')
        self._seed_vault(vault_api, crypto, 'int-tree-vault', keys)

        read_key  = keys['read_key_bytes']
        encrypted = vault_api.read('int-tree-vault', keys['tree_file_id'])
        assert len(encrypted) > 0

        decrypted = crypto.decrypt(read_key, encrypted)
        tree_data = json.loads(decrypted)
        assert 'tree' in tree_data

    def test_write_and_read_file(self, vault_api, crypto):
        keys   = crypto.derive_keys(TEST_PASSPHRASE, 'int-file-vault')
        seeded = self._seed_vault(vault_api, crypto, 'int-file-vault', keys)

        read_key       = keys['read_key_bytes']
        encrypted_file = vault_api.read('int-file-vault', seeded['content_file_id'])
        decrypted_file = crypto.decrypt(read_key, encrypted_file)
        assert decrypted_file == seeded['file_content']

    def test_encrypt_decrypt_round_trip(self, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'roundtrip-vault')
        read_key  = keys['read_key_bytes']
        plaintext = b'Round trip test data with special chars: \x00\xff\n'

        ciphertext = crypto.encrypt(read_key, plaintext)
        decrypted  = crypto.decrypt(read_key, ciphertext)
        assert decrypted == plaintext
