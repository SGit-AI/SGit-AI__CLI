"""Unit tests for Vault__Transfer — setup, upload, collect_head_files, share, receive.

Covers the previously-uncovered lines:
  26-27   setup()
  34-103  collect_head_files()
  46      simple-token vault key branch in collect_head_files
  91      no-commit empty return in collect_head_files
  123     upload()
  134-151 receive()
  205-235 share()

An in-memory drop-in for API__Transfer is wired in so no HTTP calls are made.
"""
import io
import json
import os
import zipfile

import pytest

from sgit_ai.core.actions.transfer.Vault__Transfer    import Vault__Transfer
from sgit_ai.network.api.API__Transfer           import API__Transfer
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from tests.unit.sync.vault_test_env      import Vault__Test_Env


# ---------------------------------------------------------------------------
# In-memory replacement for API__Transfer (no HTTP)
# ---------------------------------------------------------------------------

class API__Transfer__In_Memory(API__Transfer):
    """Stores uploaded blobs in a dict; serves them on download_file."""

    def setup(self):
        self._store = {}
        return self

    def upload_file(self, encrypted_payload: bytes, transfer_id: str = None,
                    content_type: str = 'application/octet-stream') -> str:
        if transfer_id is None:
            import uuid
            transfer_id = uuid.uuid4().hex[:12]
        self._store[transfer_id] = encrypted_payload
        return transfer_id

    def download_file(self, transfer_id: str) -> bytes:
        if transfer_id not in self._store:
            raise RuntimeError(f'Not found: {transfer_id}')
        return self._store[transfer_id]


def _make_transfer(api=None, crypto=None):
    if api is None:
        api = API__Transfer__In_Memory()
        api.setup()
    if crypto is None:
        crypto = Vault__Crypto()
    return Vault__Transfer(api=api, crypto=crypto)


# ---------------------------------------------------------------------------
# setup()
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__Setup:

    def test_setup_returns_self(self):
        api      = API__Transfer__In_Memory()
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=Vault__Crypto())
        result   = transfer.setup()
        assert result is transfer

    def test_setup_calls_api_setup(self):
        called = []

        class TrackingAPI(API__Transfer__In_Memory):
            def setup(self_inner):
                called.append(True)
                return super().setup()

        api      = TrackingAPI()
        transfer = Vault__Transfer(api=api, crypto=Vault__Crypto())
        transfer.setup()
        assert len(called) == 1


# ---------------------------------------------------------------------------
# upload()
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__Upload:

    def setup_method(self):
        self.api      = API__Transfer__In_Memory()
        self.api.setup()
        self.transfer = _make_transfer(api=self.api)

    def test_upload_returns_transfer_id(self):
        tid = self.transfer.upload(b'encrypted data')
        assert isinstance(tid, str)
        assert len(tid) > 0

    def test_upload_with_explicit_transfer_id(self):
        tid = self.transfer.upload(b'data', transfer_id='explicit-id')
        assert tid == 'explicit-id'

    def test_upload_stores_payload(self):
        self.transfer.upload(b'\x01\x02\x03', transfer_id='store-test')
        assert self.api._store['store-test'] == b'\x01\x02\x03'

    def test_upload_multiple_separate_blobs(self):
        t1 = self.transfer.upload(b'blob1', transfer_id='t1')
        t2 = self.transfer.upload(b'blob2', transfer_id='t2')
        assert self.api._store['t1'] == b'blob1'
        assert self.api._store['t2'] == b'blob2'


# ---------------------------------------------------------------------------
# collect_head_files()
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__CollectHeadFiles:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'hello.txt': 'hello world',
            'docs/readme.md': '# Docs',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.transfer = _make_transfer(crypto=self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def test_collect_returns_two_files(self):
        files, _ = self.transfer.collect_head_files(self.vault)
        assert len(files) == 2

    def test_collect_has_hello_txt(self):
        files, _ = self.transfer.collect_head_files(self.vault)
        assert 'hello.txt' in files

    def test_collect_has_nested_readme(self):
        files, _ = self.transfer.collect_head_files(self.vault)
        assert 'docs/readme.md' in files

    def test_collect_content_is_bytes(self):
        files, _ = self.transfer.collect_head_files(self.vault)
        assert isinstance(files['hello.txt'], bytes)

    def test_collect_content_matches_original(self):
        files, _ = self.transfer.collect_head_files(self.vault)
        assert files['hello.txt'] == b'hello world'

    def test_collect_returns_commit_id(self):
        _, commit_id = self.transfer.collect_head_files(self.vault)
        assert commit_id == self.snap.commit_id

    def test_collect_raises_when_no_vault_key(self):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            with pytest.raises(RuntimeError, match='No vault key'):
                self.transfer.collect_head_files(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_collect_raises_when_no_local_config(self):
        """A dir with vault key but missing config.json raises RuntimeError."""
        import tempfile, shutil
        from sgit_ai.storage.Vault__Storage import Vault__Storage, SG_VAULT_DIR
        d       = tempfile.mkdtemp()
        storage = Vault__Storage()
        # Write vault key so first check passes
        local_dir = storage.local_dir(d)
        os.makedirs(local_dir, exist_ok=True)
        with open(storage.vault_key_path(d), 'w') as f:
            f.write(self.snap.vault_key)
        try:
            with pytest.raises(RuntimeError, match='No local config'):
                self.transfer.collect_head_files(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# share()
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__Share:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'file1.txt': 'content one',
            'file2.txt': 'content two',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.api      = API__Transfer__In_Memory()
        self.api.setup()
        self.transfer = _make_transfer(api=self.api, crypto=self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def test_share_returns_dict(self):
        result = self.transfer.share(self.vault)
        assert isinstance(result, dict)

    def test_share_has_required_keys(self):
        result = self.transfer.share(self.vault)
        for key in ('token', 'transfer_id', 'derived_xfer_id', 'folder_hash',
                    'aes_key_hex', 'file_count', 'total_bytes', 'commit_id'):
            assert key in result, f'missing key: {key}'

    def test_share_file_count_correct(self):
        result = self.transfer.share(self.vault)
        assert result['file_count'] == 2

    def test_share_uploads_to_api_store(self):
        result = self.transfer.share(self.vault)
        assert result['transfer_id'] in self.api._store

    def test_share_total_bytes_positive(self):
        result = self.transfer.share(self.vault)
        assert result['total_bytes'] > 0

    def test_share_folder_hash_eight_chars(self):
        result = self.transfer.share(self.vault)
        assert len(result['folder_hash']) == 8

    def test_share_commit_id_matches_head(self):
        result = self.transfer.share(self.vault)
        assert result['commit_id'] == self.snap.commit_id

    def test_share_token_reuse_keeps_same_transfer_id(self):
        r1 = self.transfer.share(self.vault)
        r2 = self.transfer.share(self.vault, token_str=r1['token'])
        assert r1['token']          == r2['token']
        assert r1['derived_xfer_id'] == r2['derived_xfer_id']

    def test_share_folder_hash_is_deterministic(self):
        r1 = self.transfer.share(self.vault)
        r2 = self.transfer.share(self.vault, token_str=r1['token'])
        assert r1['folder_hash'] == r2['folder_hash']

    def test_share_encrypted_payload_decryptable(self):
        """Uploaded blob can be decrypted using the returned AES key."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        result    = self.transfer.share(self.vault)
        tid       = result['transfer_id']
        key_bytes = bytes.fromhex(result['aes_key_hex'])
        blob      = self.api._store[tid]
        iv        = blob[:12]
        ct        = blob[12:]
        plaintext = AESGCM(key_bytes).decrypt(iv, ct, None)
        assert len(plaintext) > 0

    def test_share_zip_contains_manifest(self):
        """Decrypted+unpackaged zip includes a __share__*/manifest.json entry."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from sgit_ai.network.api.Transfer__Envelope import Transfer__Envelope
        result    = self.transfer.share(self.vault)
        tid       = result['transfer_id']
        key_bytes = bytes.fromhex(result['aes_key_hex'])
        blob      = self.api._store[tid]
        iv, ct    = blob[:12], blob[12:]
        plaintext = AESGCM(key_bytes).decrypt(iv, ct, None)
        _, zip_bytes = Transfer__Envelope().unpackage(plaintext)
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, 'r') as zf:
            names = zf.namelist()
        assert any('_manifest.json' in n for n in names)


# ---------------------------------------------------------------------------
# receive() — lines 134-151
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__Receive:
    """Tests for receive() using a round-trip through share() + receive()."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'msg.txt': 'hello receive'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.api      = API__Transfer__In_Memory()
        self.api.setup()
        self.transfer = _make_transfer(api=self.api, crypto=self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def test_receive_returns_files(self):
        result  = self.transfer.share(self.vault)
        token   = result['token']
        r       = self.transfer.receive(token)
        assert 'files' in r
        assert isinstance(r['files'], dict)

    def test_receive_file_count_positive(self):
        result = self.transfer.share(self.vault)
        r      = self.transfer.receive(result['token'])
        # zip contains msg.txt + __share__*/_manifest.json
        assert r['file_count'] >= 1

    def test_receive_contains_original_file(self):
        result = self.transfer.share(self.vault)
        r      = self.transfer.receive(result['token'])
        assert 'msg.txt' in r['files']
        assert r['files']['msg.txt'] == b'hello receive'

    def test_receive_transfer_id_matches_share(self):
        result = self.transfer.share(self.vault)
        r      = self.transfer.receive(result['token'])
        assert r['transfer_id'] == result['derived_xfer_id']


# ---------------------------------------------------------------------------
# collect_head_files — simple-token vault key (line 46)
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__SimpleTokenKey:
    """collect_head_files on a vault initialised with a simple-token vault key."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        # Pass a simple-token-format string as the vault key
        cls._env.setup_single_vault(files={'secret.txt': 'hidden'}, vault_key='cold-idle-7311')

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.transfer = _make_transfer(crypto=self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def test_collect_with_simple_token_key(self):
        """collect_head_files follows the simple-token derive path (line 46)."""
        files, commit_id = self.transfer.collect_head_files(self.vault)
        assert 'secret.txt' in files
        assert files['secret.txt'] == b'hidden'


# ---------------------------------------------------------------------------
# collect_head_files — no commit yet (line 91)
# ---------------------------------------------------------------------------

class Test_Vault__Transfer__NoCommit:
    """collect_head_files on a vault with no committed content returns ({}, '')."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        # setup_single_vault with no files → push bare skeleton, no commit
        cls._env.setup_single_vault(files=None)

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.transfer = _make_transfer(crypto=self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def test_collect_no_files_committed_returns_empty_files(self):
        """A vault without any file commits returns no file entries."""
        files, commit_id = self.transfer.collect_head_files(self.vault)
        # No user files were committed — files dict is empty
        assert files == {}
