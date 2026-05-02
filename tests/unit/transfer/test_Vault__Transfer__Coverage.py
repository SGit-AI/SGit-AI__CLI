"""Coverage tests for Vault__Transfer missing lines.

Missing lines targeted:
  86:      collect_head_files() branch not found → RuntimeError
  91:      collect_head_files() no HEAD commit → return {}, ''
  173:     receive() UTF-8 text payload path
  180-184: receive() binary payload (UnicodeDecodeError path)
  205-227: send_raw() method
"""
import json
import os

import pytest

from sgit_ai.api.API__Transfer        import API__Transfer
from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
from sgit_ai.transfer.Simple_Token    import Simple_Token
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
from sgit_ai.sync.Vault__Storage      import SG_VAULT_DIR
from tests._helpers.vault_test_env    import Vault__Test_Env


class API__Transfer__In_Memory(API__Transfer):
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


def _make_transfer():
    api = API__Transfer__In_Memory()
    api.setup()
    return Vault__Transfer(api=api, crypto=Vault__Crypto())


class Test_Vault__Transfer__Coverage:

    def setup_method(self):
        self.transfer = _make_transfer()

    # ─── lines 180-184: binary (non-UTF-8) receive ────────────────────────

    def test_receive_binary_payload_lines_180_184(self):
        """Lines 180-184: payload bytes fail UTF-8 decode → payload_type='binary'."""
        token_str  = 'apple-orange-1234'
        token_val  = Safe_Str__Simple_Token(token_str)
        st         = Simple_Token(token=token_val)
        key_bytes  = st.aes_key()
        xfer_id    = st.transfer_id()

        # Encrypt raw binary content (invalid UTF-8)
        raw_binary = b'\xff\xfe\xfd\xfc' * 32
        encrypted  = self.transfer.encrypt_payload(key_bytes, raw_binary)
        self.transfer.api._store[xfer_id] = encrypted

        result = self.transfer.receive(token_str)
        assert result['payload_type'] == 'binary'
        assert result['raw_bytes'] == raw_binary
        assert result['text'] is None

    # ─── lines 205-227: send_raw ──────────────────────────────────────────

    def test_send_raw_text_content_lines_205_222(self):
        """Lines 205-222: send_raw() with plain text (no filename)."""
        content = b'Hello from send_raw'
        result  = self.transfer.send_raw(content)
        assert 'token' in result
        assert 'transfer_id' in result
        assert 'total_bytes' in result
        assert result['total_bytes'] > 0

    def test_send_raw_with_filename_lines_219_220(self):
        """Lines 219-220: send_raw() with filename → Transfer__Envelope wraps payload."""
        content  = b'file content bytes'
        result   = self.transfer.send_raw(content, filename='test.txt')
        assert 'token' in result
        assert result['total_bytes'] > len(content)

    def test_send_raw_with_explicit_token_line_209_211(self):
        """Lines 209-211: send_raw() with explicit token_str → uses it."""
        content   = b'explicit token test'
        token_str = 'cherry-banana-9999'
        result    = self.transfer.send_raw(content, token_str=token_str)
        assert result['token'] == token_str

    # ─── line 173: receive() text payload ────────────────────────────────────

    def test_receive_text_payload_line_173(self):
        """Line 173: payload decodes as UTF-8 → payload_type='text'."""
        token_str  = 'lemon-grape-5678'
        token_val  = Safe_Str__Simple_Token(token_str)
        st         = Simple_Token(token=token_val)
        key_bytes  = st.aes_key()
        xfer_id    = st.transfer_id()

        text_content = b'Hello, this is plain UTF-8 text!'
        encrypted    = self.transfer.encrypt_payload(key_bytes, text_content)
        self.transfer.api._store[xfer_id] = encrypted

        result = self.transfer.receive(token_str)
        assert result['payload_type'] == 'text'
        assert result['text'] == text_content.decode('utf-8')
        assert result['raw_bytes'] is None


class Test_Vault__Transfer__CollectBranchCoverage:
    """Coverage for collect_head_files lines 86 (branch not found) and 91 (no commit)."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.transfer = Vault__Transfer(api=API__Transfer__In_Memory().setup(),
                                        crypto=self.snap.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def _local_config_path(self) -> str:
        return os.path.join(self.vault, '.sg_vault', 'local', 'config.json')

    def _delete_head_ref(self) -> None:
        refs_dir = os.path.join(self.vault, SG_VAULT_DIR, 'bare', 'refs')
        for fname in os.listdir(refs_dir):
            if fname.startswith('ref-pid-'):
                os.remove(os.path.join(refs_dir, fname))

    def test_collect_unknown_branch_raises_line_86(self):
        """Line 86: my_branch_id not in index → RuntimeError('Branch not found')."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)

        with pytest.raises(RuntimeError, match='Branch not found'):
            self.transfer.collect_head_files(self.vault)

    def test_collect_no_head_ref_returns_empty_line_91(self):
        """Line 91: HEAD ref deleted → read_ref returns None → return ({}, '')."""
        self._delete_head_ref()
        files, commit_id = self.transfer.collect_head_files(self.vault)
        assert files == {}
        assert commit_id == ''
