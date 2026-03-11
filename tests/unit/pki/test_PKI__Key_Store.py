import os
import tempfile
import shutil
import pytest
from sg_send_cli.crypto.PKI__Crypto    import PKI__Crypto
from sg_send_cli.pki.PKI__Key_Store    import PKI__Key_Store


class Test_PKI__Key_Store:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.keys_dir   = os.path.join(self.tmp_dir, 'keys')
        self.pki        = PKI__Crypto()
        self.store      = PKI__Key_Store(keys_dir=self.keys_dir, crypto=self.pki)
        self.passphrase = 'test-passphrase'

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_generate_and_store_creates_files(self):
        metadata = self.store.generate_and_store('Work Key', self.passphrase)
        assert metadata['label']     == 'Work Key'
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
        assert self.store.list_keys() == []

    def test_list_keys_after_generate(self):
        self.store.generate_and_store('Key 1', self.passphrase)
        self.store.generate_and_store('Key 2', self.passphrase)
        keys = self.store.list_keys()
        assert len(keys) == 2

    def test_load_key_pair(self):
        metadata = self.store.generate_and_store('My Key', self.passphrase)
        fp       = metadata['encryption_fingerprint']
        loaded   = self.store.load_key_pair(fp, self.passphrase)
        assert loaded is not None
        assert loaded['encryption_private'] is not None
        assert loaded['encryption_public']  is not None
        assert loaded['signing_private']    is not None
        assert loaded['signing_public']     is not None
        assert loaded['metadata']['label']  == 'My Key'

    def test_load_key_pair_wrong_passphrase(self):
        metadata = self.store.generate_and_store('Key', self.passphrase)
        fp       = metadata['encryption_fingerprint']
        with pytest.raises(Exception):
            self.store.load_key_pair(fp, 'wrong-pass')

    def test_load_key_pair_missing(self):
        assert self.store.load_key_pair('sha256:0000000000000000', 'pass') is None

    def test_export_public_bundle(self):
        metadata = self.store.generate_and_store('Bundle Key', self.passphrase)
        fp       = metadata['encryption_fingerprint']
        bundle   = self.store.export_public_bundle(fp)
        assert bundle['v']       == 1
        assert '-----BEGIN PUBLIC KEY-----' in bundle['encrypt']
        assert '-----BEGIN PUBLIC KEY-----' in bundle['sign']
        assert bundle['label']       == 'Bundle Key'
        assert bundle['fingerprint'] == fp

    def test_export_public_bundle_missing(self):
        assert self.store.export_public_bundle('sha256:0000000000000000') is None

    def test_delete_key(self):
        metadata = self.store.generate_and_store('Delete Me', self.passphrase)
        fp       = metadata['encryption_fingerprint']
        assert self.store.delete_key(fp) is True
        assert self.store.load_key_pair(fp, self.passphrase) is None

    def test_delete_missing_key(self):
        assert self.store.delete_key('sha256:0000000000000000') is False

    def test_sign_verify_with_stored_keys(self):
        metadata = self.store.generate_and_store('Sign Key', self.passphrase)
        fp       = metadata['encryption_fingerprint']
        loaded   = self.store.load_key_pair(fp, self.passphrase)
        message  = b"test message for signing"
        sig      = self.pki.sign(loaded['signing_private'], message)
        assert self.pki.verify(loaded['signing_public'], sig, message) is True

    def test_encrypt_decrypt_with_stored_keys(self):
        metadata = self.store.generate_and_store('Enc Key', self.passphrase)
        fp       = metadata['encryption_fingerprint']
        loaded   = self.store.load_key_pair(fp, self.passphrase)
        encoded  = self.pki.hybrid_encrypt(loaded['encryption_public'], "secret data")
        result   = self.pki.hybrid_decrypt(loaded['encryption_private'], encoded)
        assert result['plaintext'] == 'secret data'
