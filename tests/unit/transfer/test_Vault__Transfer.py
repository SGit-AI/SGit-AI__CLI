import hashlib
import io
import json
import os
import zipfile
from sgit_ai.core.actions.transfer.Vault__Transfer          import Vault__Transfer
from sgit_ai.network.api.API__Transfer                 import API__Transfer
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.crypto.simple_token.Simple_Token             import Simple_Token
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token

VECTOR_TOKEN   = 'test-token-1234'
VECTOR_KEY_HEX = '43e366da587e8651bcbf68f4989387b8f2e19357f6388b1c3cf2cda8af400dd8'

FILES = {'README.md': b'# Hello', 'src/main.py': b'print("hello")', 'data/a.txt': b'abc'}


class Test_Vault__Transfer__Share_Manifest:
    """Unit tests for _share_folder_hash and _share_manifest."""

    def setup_method(self):
        self.transfer = Vault__Transfer(api=API__Transfer(), crypto=Vault__Crypto())

    def test_folder_hash_is_8_hex_chars(self):
        h = self.transfer._share_folder_hash(FILES)
        assert len(h) == 8
        assert all(c in '0123456789abcdef' for c in h)

    def test_folder_hash_is_deterministic(self):
        h1 = self.transfer._share_folder_hash(FILES)
        h2 = self.transfer._share_folder_hash(FILES)
        assert h1 == h2

    def test_folder_hash_changes_with_content(self):
        files2 = dict(FILES)
        files2['README.md'] = b'# Changed'
        assert self.transfer._share_folder_hash(FILES) != self.transfer._share_folder_hash(files2)

    def test_folder_hash_changes_with_new_file(self):
        files2 = dict(FILES)
        files2['extra.txt'] = b'new'
        assert self.transfer._share_folder_hash(FILES) != self.transfer._share_folder_hash(files2)

    def test_manifest_is_valid_json(self):
        h    = self.transfer._share_folder_hash(FILES)
        raw  = self.transfer._share_manifest(FILES, 'cold-idle-7311', 'db90c4cbfad1', h)
        data = json.loads(raw)
        assert data['share_token'] == 'cold-idle-7311'

    def test_manifest_has_required_fields(self):
        h    = self.transfer._share_folder_hash(FILES)
        data = json.loads(self.transfer._share_manifest(FILES, 'tok', 'abc123', h))
        for field in ('version', 'generated_at', 'share_token', 'transfer_id',
                      'folder_hash', 'total_files', 'file_hashes', 'files'):
            assert field in data, f'missing field: {field}'

    def test_manifest_total_files_matches(self):
        h    = self.transfer._share_folder_hash(FILES)
        data = json.loads(self.transfer._share_manifest(FILES, 'tok', 'abc', h))
        assert data['total_files'] == len(FILES)

    def test_manifest_file_hashes_are_sha256(self):
        h    = self.transfer._share_folder_hash(FILES)
        data = json.loads(self.transfer._share_manifest(FILES, 't', 'x', h))
        for fid, digest in data['file_hashes'].items():
            assert len(digest) == 64

    def test_manifest_folder_hash_matches(self):
        h    = self.transfer._share_folder_hash(FILES)
        data = json.loads(self.transfer._share_manifest(FILES, 't', 'x', h))
        assert data['folder_hash'] == h

    def test_zip_contains_manifest(self):
        h       = self.transfer._share_folder_hash(FILES)
        mkey    = f'__share__{h}/_manifest.json'
        mval    = self.transfer._share_manifest(FILES, 'tok', 'abc', h)
        zipped  = self.transfer.zip_files({**FILES, mkey: mval})
        buf     = io.BytesIO(zipped)
        with zipfile.ZipFile(buf, 'r') as zf:
            assert mkey in zf.namelist()
            assert json.loads(zf.read(mkey))['folder_hash'] == h


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
