import os
import tempfile
import shutil
import pytest
from sg_send_cli.crypto.Vault__Crypto    import Vault__Crypto
from sg_send_cli.secrets.Secrets__Store  import Secrets__Store


class Test_Secrets__Store__Edge_Cases:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmp_dir, '.sg-send', 'secrets.enc')
        self.store      = Secrets__Store(store_path=self.store_path, crypto=Vault__Crypto())
        self.passphrase = 'test-passphrase-123'

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_store__unicode_value(self):
        self.store.store(self.passphrase, 'unicode-key', 'café résumé 日本語')
        assert self.store.get(self.passphrase, 'unicode-key') == 'café résumé 日本語'

    def test_store__very_long_value(self):
        long_value = 'A' * 100_000
        self.store.store(self.passphrase, 'long-key', long_value)
        assert self.store.get(self.passphrase, 'long-key') == long_value

    def test_store__empty_value(self):
        self.store.store(self.passphrase, 'empty-key', '')
        assert self.store.get(self.passphrase, 'empty-key') == ''

    def test_store__json_value(self):
        json_value = '{"nested": {"key": "value"}, "list": [1, 2, 3]}'
        self.store.store(self.passphrase, 'json-key', json_value)
        assert self.store.get(self.passphrase, 'json-key') == json_value

    def test_store__special_characters_in_key(self):
        self.store.store(self.passphrase, 'key.with.dots', 'value')
        assert self.store.get(self.passphrase, 'key.with.dots') == 'value'

    def test_get__nonexistent_from_populated_store(self):
        self.store.store(self.passphrase, 'exists', 'yes')
        assert self.store.get(self.passphrase, 'does-not-exist') is None

    def test_delete__then_get_returns_none(self):
        self.store.store(self.passphrase, 'temp', 'value')
        self.store.delete(self.passphrase, 'temp')
        assert self.store.get(self.passphrase, 'temp') is None

    def test_list_keys__sorted_order(self):
        self.store.store(self.passphrase, 'zebra', 'z')
        self.store.store(self.passphrase, 'alpha', 'a')
        self.store.store(self.passphrase, 'middle', 'm')
        keys = self.store.list_keys(self.passphrase)
        assert keys == ['alpha', 'middle', 'zebra']

    def test_list_keys__after_delete(self):
        self.store.store(self.passphrase, 'one', '1')
        self.store.store(self.passphrase, 'two', '2')
        self.store.delete(self.passphrase, 'one')
        assert self.store.list_keys(self.passphrase) == ['two']

    def test_derive_master_key__length(self):
        key = self.store.derive_master_key('test')
        assert len(key) == 32

    def test_store__overwrite_preserves_other_keys(self):
        self.store.store(self.passphrase, 'key1', 'original1')
        self.store.store(self.passphrase, 'key2', 'original2')
        self.store.store(self.passphrase, 'key1', 'updated1')
        assert self.store.get(self.passphrase, 'key1') == 'updated1'
        assert self.store.get(self.passphrase, 'key2') == 'original2'

    def test_store__newline_in_value(self):
        self.store.store(self.passphrase, 'multiline', 'line1\nline2\nline3')
        assert self.store.get(self.passphrase, 'multiline') == 'line1\nline2\nline3'

    def test_no_store_path__load_returns_empty(self):
        store = Secrets__Store(crypto=Vault__Crypto())
        keys  = store.list_keys(self.passphrase)
        assert keys == []
