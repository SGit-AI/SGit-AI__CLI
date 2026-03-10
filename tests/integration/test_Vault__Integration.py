import json
import os
import pytest
import tempfile
import shutil
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
from sg_send_cli.api.Vault__API       import Vault__API
from sg_send_cli.sync.Vault__Sync     import Vault__Sync

VAULT_KEY    = os.environ.get('SG_VAULT_KEY', '')
ACCESS_TOKEN = os.environ.get('SG_ACCESS_TOKEN', '')
BASE_URL     = os.environ.get('SG_BASE_URL', 'https://send.sgraph.ai')

SKIP_REASON  = 'SG_VAULT_KEY not set — add it to .env for integration tests'
SKIP         = not VAULT_KEY


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
class Test_Vault__Integration__Key_Derivation:
    """Test that our key derivation produces valid keys that work against the live API."""

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.keys   = self.crypto.derive_keys_from_vault_key(VAULT_KEY)

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
        keys2 = self.crypto.derive_keys_from_vault_key(VAULT_KEY)
        assert self.keys['read_key']         == keys2['read_key']
        assert self.keys['write_key']        == keys2['write_key']
        assert self.keys['tree_file_id']     == keys2['tree_file_id']
        assert self.keys['settings_file_id'] == keys2['settings_file_id']


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
class Test_Vault__Integration__Read_API:
    """Test reading vault data from the live send.sgraph.ai API."""

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.keys   = self.crypto.derive_keys_from_vault_key(VAULT_KEY)
        self.api    = Vault__API(base_url=BASE_URL, access_token=ACCESS_TOKEN)
        self.api.setup()

    def test_read_settings__decrypts_to_valid_json(self):
        vault_id = self.keys['vault_id']
        file_id  = self.keys['settings_file_id']
        read_key = self.keys['read_key_bytes']

        encrypted = self.api.read(vault_id, file_id)
        assert len(encrypted) > 0

        decrypted     = self.crypto.decrypt(read_key, encrypted)
        settings_data = json.loads(decrypted)
        assert 'vault_id' in settings_data or 'vault_name' in settings_data

    def test_read_tree__decrypts_to_valid_json(self):
        vault_id = self.keys['vault_id']
        file_id  = self.keys['tree_file_id']
        read_key = self.keys['read_key_bytes']

        encrypted = self.api.read(vault_id, file_id)
        assert len(encrypted) > 0

        decrypted = self.crypto.decrypt(read_key, encrypted)
        tree_data = json.loads(decrypted)
        assert 'tree' in tree_data or 'version' in tree_data

    def test_read_tree__can_enumerate_files(self):
        vault_id = self.keys['vault_id']
        read_key = self.keys['read_key_bytes']

        encrypted = self.api.read(vault_id, self.keys['tree_file_id'])
        tree_data = json.loads(self.crypto.decrypt(read_key, encrypted))

        sync     = Vault__Sync(crypto=self.crypto, api=self.api)
        file_map = sync._flatten_tree(tree_data.get('tree', {}))
        assert isinstance(file_map, dict)
        # print the files found for debugging
        for path, info in file_map.items():
            assert 'file_id' in info, f'Missing file_id for {path}'

    def test_read_file__first_file_in_tree_decrypts(self):
        vault_id = self.keys['vault_id']
        read_key = self.keys['read_key_bytes']

        encrypted = self.api.read(vault_id, self.keys['tree_file_id'])
        tree_data = json.loads(self.crypto.decrypt(read_key, encrypted))

        sync     = Vault__Sync(crypto=self.crypto, api=self.api)
        file_map = sync._flatten_tree(tree_data.get('tree', {}))
        if not file_map:
            pytest.skip('Vault has no files')

        first_path = next(iter(file_map))
        first_info = file_map[first_path]
        file_id    = first_info['file_id']

        encrypted_file = self.api.read(vault_id, file_id)
        decrypted_file = self.crypto.decrypt(read_key, encrypted_file)
        assert len(decrypted_file) > 0


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
class Test_Vault__Integration__Clone:
    """Test full clone workflow against the live API."""

    def setup_method(self):
        self.crypto   = Vault__Crypto()
        self.api      = Vault__API(base_url=BASE_URL, access_token=ACCESS_TOKEN)
        self.api.setup()
        self.sync     = Vault__Sync(crypto=self.crypto, api=self.api)
        self.temp_dir = tempfile.mkdtemp(prefix='sg_vault_test_')

    def teardown_method(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_clone__creates_sg_vault_directory(self):
        clone_dir = os.path.join(self.temp_dir, 'vault')
        self.sync.clone(VAULT_KEY, clone_dir)

        assert os.path.isdir(os.path.join(clone_dir, '.sg_vault'))
        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'VAULT-KEY'))
        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'tree.json'))
        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'settings.json'))

    def test_clone__vault_key_file_contains_vault_key(self):
        clone_dir = os.path.join(self.temp_dir, 'vault')
        self.sync.clone(VAULT_KEY, clone_dir)

        with open(os.path.join(clone_dir, '.sg_vault', 'VAULT-KEY')) as f:
            head_key = f.read().strip()
        assert head_key == VAULT_KEY

    def test_clone__tree_json_is_valid(self):
        clone_dir = os.path.join(self.temp_dir, 'vault')
        self.sync.clone(VAULT_KEY, clone_dir)

        with open(os.path.join(clone_dir, '.sg_vault', 'tree.json')) as f:
            tree = json.load(f)
        assert 'tree' in tree or 'version' in tree

    def test_clone__downloads_files(self):
        clone_dir = os.path.join(self.temp_dir, 'vault')
        self.sync.clone(VAULT_KEY, clone_dir)

        with open(os.path.join(clone_dir, '.sg_vault', 'tree.json')) as f:
            tree = json.load(f)
        file_map = self.sync._flatten_tree(tree.get('tree', {}))

        for file_path in file_map:
            full_path = os.path.join(clone_dir, file_path)
            assert os.path.isfile(full_path), f'Missing cloned file: {file_path}'

    def test_clone__then_status_is_clean(self):
        clone_dir = os.path.join(self.temp_dir, 'vault')
        self.sync.clone(VAULT_KEY, clone_dir)

        status = self.sync.status(clone_dir)
        assert status['clean'], f'Expected clean status after clone, got: {status}'
