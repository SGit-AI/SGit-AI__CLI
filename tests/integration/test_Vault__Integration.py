"""Integration tests for key derivation, API read/write, and crypto round-trips.

Runs against the local SG/Send test server (in-memory mode).
No env vars, no live API, no skips.
"""
import json
import os
import tempfile
import shutil

import pytest

from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
from sgit_ai.network.api.Vault__API       import Vault__API
from sgit_ai.core.Vault__Sync     import Vault__Sync


TEST_PASSPHRASE = 'integrationtestpass01'
TEST_VAULT_ID   = 'inttestvault01'
TEST_VAULT_KEY  = f'{TEST_PASSPHRASE}:{TEST_VAULT_ID}'


class Test_Vault__Integration__Key_Derivation:
    """Test that key derivation produces valid keys."""

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.keys   = self.crypto.derive_keys_from_vault_key(TEST_VAULT_KEY)

    def test_derive_keys__returns_all_fields(self):
        assert 'read_key'              in self.keys
        assert 'write_key'             in self.keys
        assert 'ref_file_id'           in self.keys
        assert 'branch_index_file_id'  in self.keys
        assert 'vault_id'              in self.keys
        assert 'passphrase'            in self.keys

    def test_derive_keys__read_key_is_64_hex(self):
        assert len(self.keys['read_key']) == 64

    def test_derive_keys__write_key_is_64_hex(self):
        assert len(self.keys['write_key']) == 64

    def test_derive_keys__file_ids_have_prefix_and_12_hex(self):
        # ref_file_id:          'ref-pid-muw-' + 12 hex chars  = 24 chars total
        # branch_index_file_id: 'idx-pid-muw-' + 12 hex chars  = 24 chars total
        assert self.keys['ref_file_id'].startswith('ref-pid-muw-')
        assert len(self.keys['ref_file_id']) == 24
        assert self.keys['branch_index_file_id'].startswith('idx-pid-muw-')
        assert len(self.keys['branch_index_file_id']) == 24

    def test_derive_keys__deterministic(self):
        keys2 = self.crypto.derive_keys_from_vault_key(TEST_VAULT_KEY)
        assert self.keys['read_key']             == keys2['read_key']
        assert self.keys['write_key']            == keys2['write_key']
        assert self.keys['ref_file_id']          == keys2['ref_file_id']
        assert self.keys['branch_index_file_id'] == keys2['branch_index_file_id']


class Test_Vault__Integration__Read_API:
    """Test reading/writing vault data via the API against the local server."""

    def _write_encrypted(self, vault_api, crypto, vault_id, file_id, keys, content: bytes):
        """Encrypt content with the read key and write to the API."""
        encrypted = crypto.encrypt(keys['read_key_bytes'], content)
        vault_api.write(vault_id, file_id, keys['write_key'], encrypted)
        return encrypted

    def test_write_and_read_ref(self, vault_api, crypto):
        """Write encrypted data to the ref file ID; read it back and decrypt."""
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'intrefvault01')
        vault_id  = 'intrefvault01'
        file_id   = keys['ref_file_id']
        payload   = json.dumps({'ref': 'obj-cas-imm-aabbcc112233'}).encode()

        self._write_encrypted(vault_api, crypto, vault_id, file_id, keys, payload)

        encrypted = vault_api.read(vault_id, file_id)
        assert len(encrypted) > 0

        decrypted = crypto.decrypt(keys['read_key_bytes'], encrypted)
        data      = json.loads(decrypted)
        assert data['ref'] == 'obj-cas-imm-aabbcc112233'

    def test_write_and_read_branch_index(self, vault_api, crypto):
        """Write encrypted data to the branch index file ID; read and decrypt."""
        keys     = crypto.derive_keys(TEST_PASSPHRASE, 'intidxvault01')
        vault_id = 'intidxvault01'
        file_id  = keys['branch_index_file_id']
        payload  = json.dumps({'branches': ['main', 'feature-x']}).encode()

        self._write_encrypted(vault_api, crypto, vault_id, file_id, keys, payload)

        encrypted = vault_api.read(vault_id, file_id)
        decrypted = crypto.decrypt(keys['read_key_bytes'], encrypted)
        data      = json.loads(decrypted)
        assert 'main' in data['branches']

    def test_write_and_read_arbitrary_object(self, vault_api, crypto):
        """Encrypt a blob object, write it by CAS ID, read and verify content."""
        keys     = crypto.derive_keys(TEST_PASSPHRASE, 'intfilevault01')
        vault_id = 'intfilevault01'

        file_content    = b'# README\nThis is a test vault file.'
        encrypted_file  = crypto.encrypt(keys['read_key_bytes'], file_content)
        content_file_id = 'cf-' + os.urandom(5).hex()

        vault_api.write(vault_id, content_file_id, keys['write_key'], encrypted_file)

        encrypted_back = vault_api.read(vault_id, content_file_id)
        decrypted_back = crypto.decrypt(keys['read_key_bytes'], encrypted_back)
        assert decrypted_back == file_content

    def test_encrypt_decrypt_round_trip(self, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'roundtripvlt01')
        read_key  = keys['read_key_bytes']
        plaintext = b'Round trip test data with special chars: \x00\xff\n'

        ciphertext = crypto.encrypt(read_key, plaintext)
        decrypted  = crypto.decrypt(read_key, ciphertext)
        assert decrypted == plaintext
