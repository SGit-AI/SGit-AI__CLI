import hashlib
import io
import os
import zipfile
from sgit_ai.transfer.Vault__Transfer          import Vault__Transfer
from sgit_ai.api.API__Transfer                 import API__Transfer
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.transfer.Simple_Token             import Simple_Token
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token

VECTOR_TOKEN   = 'test-token-1234'
VECTOR_KEY_HEX = '43e366da587e8651bcbf68f4989387b8f2e19357f6388b1c3cf2cda8af400dd8'


class Test_Vault__Transfer:

    def setup_method(self):
        self.transfer = Vault__Transfer(api=API__Transfer(), crypto=Vault__Crypto())

    def test_zip_files_produces_valid_zip(self):
        files     = {'hello.txt': b'Hello', 'sub/world.txt': b'World'}
        zip_bytes = self.transfer.zip_files(files)
        buf       = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, 'r') as zf:
            names = zf.namelist()
        assert 'hello.txt' in names
        assert 'sub/world.txt' in names

    def test_zip_files_content_preserved(self):
        files     = {'data.bin': b'\x00\x01\x02\x03'}
        zip_bytes = self.transfer.zip_files(files)
        buf       = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, 'r') as zf:
            assert zf.read('data.bin') == b'\x00\x01\x02\x03'

    def test_zip_files_empty_dict(self):
        zip_bytes = self.transfer.zip_files({})
        buf       = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, 'r') as zf:
            assert zf.namelist() == []

    def test_encrypt_payload_returns_bytes(self):
        key     = bytes.fromhex(VECTOR_KEY_HEX)
        payload = b'hello world'
        result  = self.transfer.encrypt_payload(key, payload)
        assert isinstance(result, bytes)

    def test_encrypt_payload_prepends_12_byte_iv(self):
        key     = bytes.fromhex(VECTOR_KEY_HEX)
        payload = b'hello world'
        result  = self.transfer.encrypt_payload(key, payload)
        # IV is first 12 bytes, remainder is ciphertext + 16-byte GCM tag
        assert len(result) == 12 + len(payload) + 16

    def test_encrypt_payload_different_each_call(self):
        key  = bytes.fromhex(VECTOR_KEY_HEX)
        data = b'same plaintext'
        r1   = self.transfer.encrypt_payload(key, data)
        r2   = self.transfer.encrypt_payload(key, data)
        # IV is random, so ciphertexts must differ
        assert r1 != r2

    def test_encrypt_payload_decryptable_with_aesgcm(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key       = bytes.fromhex(VECTOR_KEY_HEX)
        plaintext = b'secret message'
        blob      = self.transfer.encrypt_payload(key, plaintext)
        iv        = blob[:12]
        ct        = blob[12:]
        aesgcm    = AESGCM(key)
        recovered = aesgcm.decrypt(iv, ct, None)
        assert recovered == plaintext

    def test_simple_token_key_matches_vector(self):
        st = Simple_Token(token=Safe_Str__Simple_Token(VECTOR_TOKEN))
        assert st.aes_key_hex() == VECTOR_KEY_HEX

    def test_vault_transfer_has_api(self):
        assert isinstance(self.transfer.api, API__Transfer)

    def test_vault_transfer_has_crypto(self):
        assert isinstance(self.transfer.crypto, Vault__Crypto)
