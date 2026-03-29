import os
import tempfile
import shutil
from sgit_ai.crypto.Vault__Crypto    import Vault__Crypto
from sgit_ai.secrets.Secrets__Store  import Secrets__Store


# Pre-derive the master key once for the shared passphrase (saves ~100 ms per test call)
_PASSPHRASE    = 'test-passphrase-123'
_SHARED_CRYPTO = Vault__Crypto()
_MASTER_KEY    = Secrets__Store(crypto=_SHARED_CRYPTO).derive_master_key(_PASSPHRASE)


class Test_Secrets__Store:

    @classmethod
    def setup_class(cls):
        pass

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmp_dir, '.sg-send', 'secrets.enc')
        self.store      = Secrets__Store(store_path=self.store_path, crypto=Vault__Crypto())
        self.passphrase = _PASSPHRASE
        # Patch derive_master_key to return the pre-derived key (same passphrase only)
        _cached = _MASTER_KEY
        self.store.derive_master_key = lambda p: _cached

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_store_and_get(self):
        self.store.store(self.passphrase, 'api-key', 'sk-12345')
        assert self.store.get(self.passphrase, 'api-key') == 'sk-12345'

    def test_get_missing_key_returns_none(self):
        assert self.store.get(self.passphrase, 'nonexistent') is None

    def test_list_keys_empty(self):
        assert self.store.list_keys(self.passphrase) == []

    def test_list_keys_after_store(self):
        self.store.store(self.passphrase, 'beta', 'val-b')
        self.store.store(self.passphrase, 'alpha', 'val-a')
        assert self.store.list_keys(self.passphrase) == ['alpha', 'beta']

    def test_delete_existing_key(self):
        self.store.store(self.passphrase, 'temp', 'value')
        assert self.store.delete(self.passphrase, 'temp') is True
        assert self.store.get(self.passphrase, 'temp') is None

    def test_delete_missing_key(self):
        assert self.store.delete(self.passphrase, 'nope') is False

    def test_overwrite_existing_key(self):
        self.store.store(self.passphrase, 'key', 'old')
        self.store.store(self.passphrase, 'key', 'new')
        assert self.store.get(self.passphrase, 'key') == 'new'

    def test_file_is_encrypted(self):
        self.store.store(self.passphrase, 'secret', 'plaintext-value')
        with open(self.store_path, 'rb') as f:
            raw = f.read()
        assert b'plaintext-value' not in raw
        assert b'secret'          not in raw

    def test_wrong_passphrase_fails(self):
        self.store.store(self.passphrase, 'key', 'value')
        import pytest
        # Create a second store with no key patch to test real wrong-passphrase behaviour
        store2 = Secrets__Store(store_path=self.store_path, crypto=Vault__Crypto())
        with pytest.raises(Exception):
            store2.get('wrong-passphrase', 'key')

    def test_multiple_secrets_round_trip(self):
        self.store.store(self.passphrase, 'db-password', 'postgres123')
        self.store.store(self.passphrase, 'api-token', 'tok-abc')
        self.store.store(self.passphrase, 'ssh-key', 'rsa-key-content')

        assert self.store.get(self.passphrase, 'db-password') == 'postgres123'
        assert self.store.get(self.passphrase, 'api-token')   == 'tok-abc'
        assert self.store.get(self.passphrase, 'ssh-key')     == 'rsa-key-content'

    def test_creates_parent_directory(self):
        nested_path = os.path.join(self.tmp_dir, 'deep', 'nested', 'secrets.enc')
        store = Secrets__Store(store_path=nested_path, crypto=Vault__Crypto())
        _cached = _MASTER_KEY
        store.derive_master_key = lambda p: _cached
        store.store(self.passphrase, 'key', 'value')
        assert os.path.isfile(nested_path)
        assert store.get(self.passphrase, 'key') == 'value'

    def test_derive_master_key_is_deterministic(self):
        # Use a real (unpatched) store for this test
        real_store = Secrets__Store(crypto=Vault__Crypto())
        key1 = real_store.derive_master_key('my-pass')
        key2 = real_store.derive_master_key('my-pass')
        assert key1 == key2

    def test_derive_master_key_differs_per_passphrase(self):
        # Use a real (unpatched) store for this test
        real_store = Secrets__Store(crypto=Vault__Crypto())
        key1 = real_store.derive_master_key('pass-a')
        key2 = real_store.derive_master_key('pass-b')
        assert key1 != key2
