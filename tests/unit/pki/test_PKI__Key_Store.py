"""Tests for PKI__Key_Store.

Module-level RSA-4096 key pairs are generated once and stored into a
golden key-store directory.  Each test class restores a shutil.copytree
copy (~1 ms) instead of generating new RSA keys (~1-2 s per call).
"""
import copy
import json
import os
import shutil
import tempfile
import pytest
from sgit_ai.crypto.PKI__Crypto    import PKI__Crypto
from sgit_ai.crypto.pki.PKI__Key_Store    import PKI__Key_Store


# ---------------------------------------------------------------------------
# Module-level: generate RSA key pairs once, store into a golden directory
# ---------------------------------------------------------------------------

_pki = PKI__Crypto()
_PASSPHRASE = 'test-passphrase'

# Build a golden key-store with two pre-generated keys
_GOLDEN_DIR = tempfile.mkdtemp()
_golden_store = PKI__Key_Store(keys_dir=_GOLDEN_DIR, crypto=_pki)

_META_1 = _golden_store.generate_and_store('Key 1', _PASSPHRASE)
_META_2 = _golden_store.generate_and_store('Key 2', _PASSPHRASE)

_FP_1 = _META_1['encryption_fingerprint']
_FP_2 = _META_2['encryption_fingerprint']

# Pre-load the key pairs from the golden store for tests that need live objects
_LOADED_1 = _golden_store.load_key_pair(_FP_1, _PASSPHRASE)
_LOADED_2 = _golden_store.load_key_pair(_FP_2, _PASSPHRASE)


def _restore_store():
    """Return a fresh (tmp_dir, PKI__Key_Store) copied from the golden snapshot."""
    tmp = tempfile.mkdtemp()
    keys_dir = os.path.join(tmp, 'keys')
    shutil.copytree(_GOLDEN_DIR, keys_dir)
    store = PKI__Key_Store(keys_dir=keys_dir, crypto=_pki)
    return tmp, store


class Test_PKI__Key_Store:

    def setup_method(self):
        self.tmp_dir, self.store = _restore_store()
        self.keys_dir  = os.path.join(self.tmp_dir, 'keys')
        self.pki       = _pki
        self.passphrase = _PASSPHRASE

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # generate_and_store — only one test that needs the full round-trip;
    # others reuse the pre-generated data.
    # ------------------------------------------------------------------

    def test_generate_and_store_creates_files(self):
        # Verify the golden pre-generated entry for Key 1 has all expected files.
        metadata = _META_1
        assert metadata['label']     == 'Key 1'
        assert metadata['algorithm'] == 'RSA-OAEP'
        assert metadata['key_size']  == 4096
        assert metadata['encryption_fingerprint'].startswith('sha256:')
        assert metadata['signing_fingerprint'].startswith('sha256:')

        fp      = metadata['encryption_fingerprint']
        key_dir = self.store._key_dir(fp)
        assert os.path.isfile(os.path.join(key_dir, 'private_key.pem'))
        assert os.path.isfile(os.path.join(key_dir, 'public_key.pem'))
        assert os.path.isfile(os.path.join(key_dir, 'signing_private.pem'))
        assert os.path.isfile(os.path.join(key_dir, 'signing_public.pem'))
        assert os.path.isfile(os.path.join(key_dir, 'metadata.json'))

    def test_list_keys_empty(self):
        # Use a fresh empty store (not the golden one)
        empty_tmp = tempfile.mkdtemp()
        try:
            empty_keys_dir = os.path.join(empty_tmp, 'keys')
            empty_store    = PKI__Key_Store(keys_dir=empty_keys_dir, crypto=_pki)
            assert empty_store.list_keys() == []
        finally:
            shutil.rmtree(empty_tmp, ignore_errors=True)

    def test_list_keys_after_generate(self):
        # Golden store already has two keys — just list them.
        keys = self.store.list_keys()
        assert len(keys) == 2

    def test_load_key_pair(self):
        loaded = self.store.load_key_pair(_FP_1, self.passphrase)
        assert loaded is not None
        assert loaded['encryption_private'] is not None
        assert loaded['encryption_public']  is not None
        assert loaded['signing_private']    is not None
        assert loaded['signing_public']     is not None
        assert loaded['metadata']['label']  == 'Key 1'

    def test_load_key_pair_wrong_passphrase(self):
        with pytest.raises(Exception):
            self.store.load_key_pair(_FP_1, 'wrong-pass')

    def test_load_key_pair_missing(self):
        assert self.store.load_key_pair('sha256:0000000000000000', 'pass') is None

    def test_export_public_bundle(self):
        bundle = self.store.export_public_bundle(_FP_1)
        assert bundle['v']       == 1
        assert '-----BEGIN PUBLIC KEY-----' in bundle['encrypt']
        assert '-----BEGIN PUBLIC KEY-----' in bundle['sign']
        assert bundle['label']       == 'Key 1'
        assert bundle['fingerprint'] == _FP_1

    def test_export_public_bundle_missing(self):
        assert self.store.export_public_bundle('sha256:0000000000000000') is None

    def test_delete_key(self):
        assert self.store.delete_key(_FP_1) is True
        assert self.store.load_key_pair(_FP_1, self.passphrase) is None

    def test_delete_missing_key(self):
        assert self.store.delete_key('sha256:0000000000000000') is False

    def test_sign_verify_with_stored_keys(self):
        loaded  = _LOADED_1
        message = b"test message for signing"
        sig     = self.pki.sign(loaded['signing_private'], message)
        assert self.pki.verify(loaded['signing_public'], sig, message) is True

    def test_encrypt_decrypt_with_stored_keys(self):
        loaded  = _LOADED_1
        encoded = self.pki.hybrid_encrypt(loaded['encryption_public'], "secret data")
        result  = self.pki.hybrid_decrypt(loaded['encryption_private'], encoded)
        assert result['plaintext'] == 'secret data'
