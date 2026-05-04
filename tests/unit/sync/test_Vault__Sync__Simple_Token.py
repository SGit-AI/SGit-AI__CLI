import json
import os
import shutil
import tempfile

from sgit_ai.api.API__Transfer               import API__Transfer
from sgit_ai.api.Vault__API__In_Memory        import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto             import Vault__Crypto
from sgit_ai.sync.Vault__Sync                 import Vault__Sync
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.transfer.Simple_Token            import Simple_Token
from sgit_ai.transfer.Vault__Transfer         import Vault__Transfer


# ---------------------------------------------------------------------------
# Minimal in-memory Transfer API for tests
# ---------------------------------------------------------------------------

class API__Transfer__In_Memory(API__Transfer):
    """In-memory replacement for API__Transfer — no network calls."""

    def setup(self):
        self._store = {}
        return self

    def upload_file(self, encrypted_payload: bytes) -> str:
        # Use first 12 hex chars of SHA256 as fake transfer_id
        import hashlib
        tid = hashlib.sha256(encrypted_payload).hexdigest()[:12]
        self._store[tid] = encrypted_payload
        return tid

    def download_file(self, transfer_id: str) -> bytes:
        if transfer_id not in self._store:
            raise RuntimeError(f'Transfer not found: {transfer_id}')
        return self._store[transfer_id]

    # --- stubs for unused methods ---
    def create(self, *a, **k):    return {}
    def upload(self, *a, **k):    return {}
    def complete(self, *a, **k):  return {}
    def info(self, transfer_id: str) -> dict:
        if transfer_id not in self._store:
            raise RuntimeError(f'Not found: {transfer_id}')
        return {'file_size_bytes': len(self._store[transfer_id])}
    def download(self, transfer_id: str) -> bytes:
        return self.download_file(transfer_id)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

TOKEN_SIMPLE    = 'coral-equal-1234'
TOKEN_VAULT_ID  = 'c4958581e0ab'   # sha256('coral-equal-1234')[:12] — safe public identifier


class Test_Vault__Sync__Simple_Token:

    def setup_method(self):
        self.tmp_dir       = tempfile.mkdtemp()
        self.crypto        = Vault__Crypto()
        self.vault_api     = Vault__API__In_Memory()
        self.vault_api.setup()
        self.transfer_api  = API__Transfer__In_Memory()
        self.transfer_api.setup()
        self.sync          = Vault__Sync(crypto=self.crypto, api=self.vault_api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _vault_dir(self, name='vault'):
        return os.path.join(self.tmp_dir, name)

    # --- Task 3: init with simple token ---

    def test_init_with_simple_token(self):
        directory = self._vault_dir('coral-equal-1234')
        result    = self.sync.init(directory, token=TOKEN_SIMPLE)
        assert result['vault_id'] == TOKEN_VAULT_ID   # hash of token, NOT the raw token

    def test_init_writes_simple_token_config(self):
        directory = self._vault_dir('coral-equal-1234')
        self.sync.init(directory, token=TOKEN_SIMPLE)

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        assert os.path.isfile(config_path)
        with open(config_path) as f:
            config = json.load(f)
        assert config.get('mode')       == 'simple_token'
        assert config.get('edit_token') == TOKEN_SIMPLE

    def test_init_with_simple_token_as_vault_key(self):
        """Passing token via vault_key= also triggers simple token mode."""
        directory = self._vault_dir('coral-equal-1234')
        result    = self.sync.init(directory, vault_key=TOKEN_SIMPLE)
        assert result['vault_id'] == TOKEN_VAULT_ID   # hash of token, NOT the raw token

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        with open(config_path) as f:
            config = json.load(f)
        assert config.get('mode') == 'simple_token'

    def test_init_simple_token_vault_key_file_contains_token(self):
        directory = self._vault_dir('coral-equal-1234')
        self.sync.init(directory, token=TOKEN_SIMPLE)

        storage = Vault__Storage()
        vk_path = storage.vault_key_path(directory)
        with open(vk_path) as f:
            vault_key = f.read().strip()
        assert vault_key == TOKEN_SIMPLE

    def test_init_non_simple_token_is_unchanged(self):
        """Standard vault_key flow still works without changes."""
        directory = self._vault_dir('standard')
        vault_key = 'mypassphrase:myvaultid'
        result    = self.sync.init(directory, vault_key=vault_key)
        assert result['vault_id'] == 'myvaultid'
        assert result['vault_key'] == vault_key

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        with open(config_path) as f:
            config = json.load(f)
        assert config.get('mode') is None

    # --- Task 4 + 5: clone_from_transfer ---

    def _make_transfer(self, files: dict, token_str: str) -> None:
        """Upload files as a SG/Send-style transfer encrypted with token_str."""
        transfer = Vault__Transfer(api=self.transfer_api, crypto=self.crypto)
        # share() uses collect_head_files() which needs a real vault — do it manually
        st        = Simple_Token(token=__import__('sgit_ai.safe_types.Safe_Str__Simple_Token',
                                                   fromlist=['Safe_Str__Simple_Token']).Safe_Str__Simple_Token(token_str))
        key_bytes = st.aes_key()
        zip_bytes = transfer.zip_files(files)
        encrypted = transfer.encrypt_payload(key_bytes, zip_bytes)
        self.transfer_api._store[st.transfer_id()] = encrypted

    def test_clone_from_transfer_creates_vault(self):
        """Scenario A: receive files from SG/Send and create a new local vault."""
        share_token = 'dawn-haven-1234'
        files       = {'hello.txt': b'Hello from SG/Send!\n',
                       'readme.md': b'# README\n'}
        self._make_transfer(files, share_token)

        # Patch Vault__Transfer to use in-memory API
        import sgit_ai.sync.Vault__Sync as _vs_mod
        orig_api_transfer = None
        try:
            import sgit_ai.transfer.Vault__Transfer as _vt_mod
            orig_cls = _vt_mod.Vault__Transfer

            class PatchedTransfer(orig_cls):
                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    self.api = self_ref.transfer_api   # noqa

            self_ref = self
            _vt_mod.Vault__Transfer = PatchedTransfer

            directory = self._vault_dir('new-vault')
            result    = self.sync.clone_from_transfer(share_token, directory)

            assert result['share_token'] == share_token
            assert result['file_count']  == 2
            assert result['directory']   == directory
            # vault_id is the hash of a newly generated edit token — 12 hex chars, safe to log
            assert len(result['vault_id']) == 12
            assert all(c in '0123456789abcdef' for c in result['vault_id'])

            # Check files are on disk
            assert os.path.isfile(os.path.join(directory, 'hello.txt'))
            assert os.path.isfile(os.path.join(directory, 'readme.md'))

            # Check config has share_token
            storage     = Vault__Storage()
            config_path = storage.local_config_path(directory)
            with open(config_path) as f:
                config = json.load(f)
            assert config.get('share_token') == share_token
        finally:
            _vt_mod.Vault__Transfer = orig_cls

    # --- Task 6: clone detects simple token ---

    def test_clone_detects_simple_token_pattern(self):
        """clone() with a simple token that doesn't exist in vault or transfer raises RuntimeError."""
        directory = self._vault_dir('missing-token-vault')
        try:
            self.sync.clone('test-word-0000', directory)
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            assert 'No vault or transfer found' in str(e)

    def test_clone_vault_prefix_detected(self):
        """vault://token prefix is stripped and treated as simple token."""
        directory = self._vault_dir('vault-prefix-test')
        try:
            self.sync.clone('vault://test-word-0000', directory)
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            assert 'No vault or transfer found' in str(e)

    def test_clone_simple_token_vault_found(self, simple_token_origin_pushed):
        """When vault exists for simple token, clone succeeds."""
        # F6: replace local origin (init+commit+push) with shared snapshot.
        # Inject the snapshot's API store into this test's in-memory API
        # so clone() can find the vault.
        import copy
        self.vault_api._store.update(
            copy.deepcopy(simple_token_origin_pushed['snapshot_store'])
        )
        token = simple_token_origin_pushed['token']

        clone_dir = self._vault_dir('cloned')
        result    = self.sync.clone(token, clone_dir)

        assert result['vault_id'] == simple_token_origin_pushed['vault_id']
        assert os.path.isfile(os.path.join(clone_dir, 'data.txt'))

    def test_clone_simple_token_clone_has_simple_token_config(self, simple_token_origin_pushed):
        """Vault cloned via simple token has mode=simple_token in config."""
        import copy
        self.vault_api._store.update(
            copy.deepcopy(simple_token_origin_pushed['snapshot_store'])
        )
        token = simple_token_origin_pushed['token']

        clone_dir = self._vault_dir('cloned')
        self.sync.clone(token, clone_dir)

        storage     = Vault__Storage()
        config_path = storage.local_config_path(clone_dir)
        with open(config_path) as f:
            config = json.load(f)
        assert config.get('mode')       == 'simple_token'
        assert config.get('edit_token') == token
