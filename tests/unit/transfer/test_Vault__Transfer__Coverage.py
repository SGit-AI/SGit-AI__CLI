"""Coverage tests for Vault__Transfer missing lines.

Missing lines targeted:
  180-184: receive() binary payload (UnicodeDecodeError path)
  205-227: send_raw() method
"""
from sgit_ai.api.API__Transfer      import API__Transfer
from sgit_ai.crypto.Vault__Crypto   import Vault__Crypto
from sgit_ai.transfer.Vault__Transfer import Vault__Transfer
from sgit_ai.transfer.Simple_Token  import Simple_Token
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token


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
