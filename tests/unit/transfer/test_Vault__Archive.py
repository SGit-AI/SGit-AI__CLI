import io
import json
import os
import zipfile
import pytest
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.network.transfer.Vault__Archive    import (Vault__Archive,
                                                 MANIFEST_NAME,
                                                 INNER_ZIP_NAME,
                                                 DECRYPTION_KEY_NAME)
from sgit_ai.schemas.Schema__Vault_Archive_Manifest import (
    Schema__Vault_Archive_Manifest, VAULT_ARCHIVE_SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_archive() -> Vault__Archive:
    return Vault__Archive(crypto=Vault__Crypto())

TOKEN       = 'maple-river-7291'
VAULT_ID    = 'testvault01'
BRANCH_ID   = 'branch-clone-abcdef12'
COMMIT_ID   = 'obj-cas-imm-deadbeef1234'

SIMPLE_FILES = {
    'hello.txt': b'Hello, world!',
    'data.bin':  b'\x00\x01\x02\x03\xff\xfe',
}

MULTI_FILES = {
    'README.md':             b'# Readme\n',
    'src/main.py':           b'print("hello")\n',
    'src/utils/helpers.py':  b'# helpers\n',
    'assets/logo.png':       b'\x89PNG\r\n\x1a\n',
    'empty.txt':             b'',
}


# ---------------------------------------------------------------------------
# build_inner_zip
# ---------------------------------------------------------------------------

class Test_Vault__Archive__build_inner_zip:

    def test_creates_valid_zip(self):
        va  = make_archive()
        data = va.build_inner_zip(SIMPLE_FILES)
        assert zipfile.is_zipfile(io.BytesIO(data))

    def test_paths_preserved(self):
        va   = make_archive()
        data = va.build_inner_zip(SIMPLE_FILES)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
        assert names == set(SIMPLE_FILES)

    def test_content_preserved(self):
        va   = make_archive()
        data = va.build_inner_zip(SIMPLE_FILES)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name, content in SIMPLE_FILES.items():
                assert zf.read(name) == content

    def test_empty_dict(self):
        va   = make_archive()
        data = va.build_inner_zip({})
        assert zipfile.is_zipfile(io.BytesIO(data))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert zf.namelist() == []

    def test_subdirectory_paths(self):
        va   = make_archive()
        data = va.build_inner_zip(MULTI_FILES)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert 'src/main.py' in zf.namelist()
            assert 'src/utils/helpers.py' in zf.namelist()

    def test_str_content_encoded(self):
        va   = make_archive()
        data = va.build_inner_zip({'note.txt': 'unicode: \u00e9'})
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert zf.read('note.txt') == 'unicode: \u00e9'.encode('utf-8')

    def test_binary_content(self):
        binary = bytes(range(256))
        va     = make_archive()
        data   = va.build_inner_zip({'bin.dat': binary})
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert zf.read('bin.dat') == binary


# ---------------------------------------------------------------------------
# encrypt_inner_zip
# ---------------------------------------------------------------------------

class Test_Vault__Archive__encrypt_inner_zip:

    def test_returns_tuple(self):
        va       = make_archive()
        inner_zip = va.build_inner_zip(SIMPLE_FILES)
        result    = va.encrypt_inner_zip(inner_zip)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_key_is_32_bytes(self):
        va       = make_archive()
        inner_zip = va.build_inner_zip(SIMPLE_FILES)
        key, _   = va.encrypt_inner_zip(inner_zip)
        assert len(key) == 32

    def test_ciphertext_differs_each_call(self):
        va       = make_archive()
        inner_zip = va.build_inner_zip(SIMPLE_FILES)
        _, ct1   = va.encrypt_inner_zip(inner_zip)
        _, ct2   = va.encrypt_inner_zip(inner_zip)
        assert ct1 != ct2  # different random IVs

    def test_decryptable(self):
        va        = make_archive()
        inner_zip = va.build_inner_zip(SIMPLE_FILES)
        key, ct   = va.encrypt_inner_zip(inner_zip)
        recovered = va.crypto.decrypt(key, ct)
        assert recovered == inner_zip

    def test_wrong_key_fails(self):
        va        = make_archive()
        inner_zip = va.build_inner_zip(SIMPLE_FILES)
        key, ct   = va.encrypt_inner_zip(inner_zip)
        bad_key   = os.urandom(32)
        with pytest.raises(Exception):
            va.crypto.decrypt(bad_key, ct)


# ---------------------------------------------------------------------------
# encrypt_inner_key
# ---------------------------------------------------------------------------

class Test_Vault__Archive__encrypt_inner_key:

    def test_output_is_bytes(self):
        va            = make_archive()
        vault_read_key = os.urandom(32)
        inner_key     = os.urandom(32)
        result        = va.encrypt_inner_key(inner_key, vault_read_key)
        assert isinstance(result, bytes)

    def test_decryptable_with_vault_read_key(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        inner_key      = os.urandom(32)
        enc            = va.encrypt_inner_key(inner_key, vault_read_key)
        recovered      = va.crypto.decrypt(vault_read_key, enc)
        assert recovered == inner_key

    def test_different_vault_read_key_fails(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        inner_key      = os.urandom(32)
        enc            = va.encrypt_inner_key(inner_key, vault_read_key)
        bad_key        = os.urandom(32)
        with pytest.raises(Exception):
            va.crypto.decrypt(bad_key, enc)

    def test_each_call_produces_different_ciphertext(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        inner_key      = os.urandom(32)
        enc1           = va.encrypt_inner_key(inner_key, vault_read_key)
        enc2           = va.encrypt_inner_key(inner_key, vault_read_key)
        assert enc1 != enc2  # random IVs


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------

class Test_Vault__Archive__build_manifest:

    def test_valid_json(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj  = json.loads(data)
        assert isinstance(obj, dict)

    def test_schema_field_present(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj  = json.loads(data)
        assert obj['schema'] == VAULT_ARCHIVE_SCHEMA_VERSION

    def test_file_count_correct(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj  = json.loads(data)
        assert obj['files'] == len(SIMPLE_FILES)

    def test_inner_key_type_correct(self):
        va   = make_archive()
        for key_type in ('vault_key', 'none'):
            data = va.build_manifest(SIMPLE_FILES, key_type, VAULT_ID, BRANCH_ID, COMMIT_ID)
            obj  = json.loads(data)
            assert obj['inner_key_type'] == key_type

    def test_total_bytes_correct(self):
        va          = make_archive()
        expected    = sum(len(v) for v in SIMPLE_FILES.values())
        data        = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj         = json.loads(data)
        assert obj['total_bytes'] == expected

    def test_created_at_is_int(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj  = json.loads(data)
        assert isinstance(obj['created_at'], int)
        assert obj['created_at'] > 0

    def test_description_field(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID,
                                 description='My archive')
        obj  = json.loads(data)
        assert obj['description'] == 'My archive'

    def test_provenance_branch_commit(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj  = json.loads(data)
        prov = obj.get('provenance', {})
        assert prov.get('branch_id') == BRANCH_ID
        assert prov.get('commit_id') == COMMIT_ID

    def test_round_trip(self):
        va   = make_archive()
        data = va.build_manifest(SIMPLE_FILES, 'vault_key', VAULT_ID, BRANCH_ID, COMMIT_ID)
        obj1     = json.loads(data.decode('utf-8'))
        manifest = Schema__Vault_Archive_Manifest.from_json(obj1)
        obj2     = manifest.json()
        assert obj1 == obj2


# ---------------------------------------------------------------------------
# build_outer_zip
# ---------------------------------------------------------------------------

class Test_Vault__Archive__build_outer_zip:

    def test_valid_zip(self):
        va              = make_archive()
        manifest_bytes  = b'{"schema":"vault_archive_v1"}'
        inner_zip_enc   = b'\xde\xad\xbe\xef'
        data            = va.build_outer_zip(manifest_bytes, inner_zip_enc, None)
        assert zipfile.is_zipfile(io.BytesIO(data))

    def test_contains_manifest_and_inner(self):
        va             = make_archive()
        manifest_bytes = b'{"schema":"vault_archive_v1"}'
        inner_zip_enc  = b'\xde\xad\xbe\xef'
        data           = va.build_outer_zip(manifest_bytes, inner_zip_enc, None)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
        assert MANIFEST_NAME  in names
        assert INNER_ZIP_NAME in names

    def test_contains_decryption_key_when_provided(self):
        va             = make_archive()
        manifest_bytes = b'{"schema":"vault_archive_v1"}'
        inner_zip_enc  = b'\xde\xad\xbe\xef'
        dec_key        = b'\x01\x02\x03'
        data           = va.build_outer_zip(manifest_bytes, inner_zip_enc, dec_key)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert DECRYPTION_KEY_NAME in zf.namelist()
            assert zf.read(DECRYPTION_KEY_NAME) == dec_key

    def test_decryption_key_absent_when_none(self):
        va             = make_archive()
        manifest_bytes = b'{"schema":"vault_archive_v1"}'
        inner_zip_enc  = b'\xde\xad\xbe\xef'
        data           = va.build_outer_zip(manifest_bytes, inner_zip_enc, None)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert DECRYPTION_KEY_NAME not in zf.namelist()

    def test_manifest_content_preserved(self):
        va             = make_archive()
        manifest_bytes = b'{"schema":"vault_archive_v1","files":2}'
        inner_zip_enc  = b'\x00\x01'
        data           = va.build_outer_zip(manifest_bytes, inner_zip_enc, None)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert zf.read(MANIFEST_NAME) == manifest_bytes


# ---------------------------------------------------------------------------
# encrypt_outer_zip
# ---------------------------------------------------------------------------

class Test_Vault__Archive__encrypt_outer_zip:

    def test_output_is_bytes(self):
        va        = make_archive()
        outer_zip = b'fake-zip-bytes'
        result    = va.encrypt_outer_zip(outer_zip, TOKEN)
        assert isinstance(result, bytes)

    def test_decryptable_with_same_token(self):
        va        = make_archive()
        outer_zip = b'fake-zip-bytes'
        enc       = va.encrypt_outer_zip(outer_zip, TOKEN)
        from sgit_ai.network.transfer.Simple_Token           import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        st  = Simple_Token(token=Safe_Str__Simple_Token(TOKEN))
        key = st.aes_key()
        assert va.crypto.decrypt(key, enc) == outer_zip

    def test_different_token_fails(self):
        va        = make_archive()
        outer_zip = b'fake-zip-bytes'
        enc       = va.encrypt_outer_zip(outer_zip, TOKEN)
        with pytest.raises(Exception):
            from sgit_ai.network.transfer.Simple_Token           import Simple_Token
            from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
            st  = Simple_Token(token=Safe_Str__Simple_Token('wrong-token-9999'))
            key = st.aes_key()
            va.crypto.decrypt(key, enc)

    def test_different_output_each_call(self):
        va        = make_archive()
        outer_zip = b'fake-zip-bytes'
        enc1 = va.encrypt_outer_zip(outer_zip, TOKEN)
        enc2 = va.encrypt_outer_zip(outer_zip, TOKEN)
        assert enc1 != enc2


# ---------------------------------------------------------------------------
# decrypt_outer
# ---------------------------------------------------------------------------

class Test_Vault__Archive__decrypt_outer:

    def test_manifest_parseable(self):
        va      = make_archive()
        blob    = va.build_archive(SIMPLE_FILES, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        manifest_bytes, _, _ = va.decrypt_outer(blob, TOKEN)
        obj = json.loads(manifest_bytes)
        assert obj['schema'] == VAULT_ARCHIVE_SCHEMA_VERSION

    def test_inner_zip_enc_present(self):
        va  = make_archive()
        blob = va.build_archive(SIMPLE_FILES, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        _, inner_zip_enc, _ = va.decrypt_outer(blob, TOKEN)
        assert isinstance(inner_zip_enc, bytes)
        assert len(inner_zip_enc) > 0

    def test_decryption_key_present_for_vault_key_type(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        blob           = va.build_archive(SIMPLE_FILES, TOKEN, vault_read_key,
                                          VAULT_ID, BRANCH_ID, COMMIT_ID)
        _, _, dk = va.decrypt_outer(blob, TOKEN)
        assert dk is not None
        assert isinstance(dk, bytes)

    def test_decryption_key_absent_for_none_type(self):
        va   = make_archive()
        blob = va.build_archive(SIMPLE_FILES, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        _, _, dk = va.decrypt_outer(blob, TOKEN)
        assert dk is None

    def test_wrong_token_fails(self):
        va   = make_archive()
        blob = va.build_archive(SIMPLE_FILES, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        with pytest.raises(Exception):
            va.decrypt_outer(blob, 'wrong-token-9999')


# ---------------------------------------------------------------------------
# decrypt_inner
# ---------------------------------------------------------------------------

class Test_Vault__Archive__decrypt_inner:

    def test_recovers_inner_zip_bytes(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        blob           = va.build_archive(SIMPLE_FILES, TOKEN, vault_read_key,
                                          VAULT_ID, BRANCH_ID, COMMIT_ID)
        _, inner_zip_enc, dk = va.decrypt_outer(blob, TOKEN)
        inner_zip = va.decrypt_inner(inner_zip_enc, dk, vault_read_key)
        assert zipfile.is_zipfile(io.BytesIO(inner_zip))

    def test_wrong_vault_read_key_fails(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        blob           = va.build_archive(SIMPLE_FILES, TOKEN, vault_read_key,
                                          VAULT_ID, BRANCH_ID, COMMIT_ID)
        _, inner_zip_enc, dk = va.decrypt_outer(blob, TOKEN)
        with pytest.raises(Exception):
            va.decrypt_inner(inner_zip_enc, dk, os.urandom(32))


# ---------------------------------------------------------------------------
# extract_files
# ---------------------------------------------------------------------------

class Test_Vault__Archive__extract_files:

    def test_recovers_original_dict(self):
        va        = make_archive()
        inner_zip = va.build_inner_zip(SIMPLE_FILES)
        recovered = va.extract_files(inner_zip)
        assert recovered == SIMPLE_FILES

    def test_recovers_subdirectory_paths(self):
        va        = make_archive()
        inner_zip = va.build_inner_zip(MULTI_FILES)
        recovered = va.extract_files(inner_zip)
        assert set(recovered.keys()) == set(MULTI_FILES.keys())

    def test_recovers_binary_content(self):
        binary    = bytes(range(256))
        va        = make_archive()
        inner_zip = va.build_inner_zip({'bin.dat': binary})
        recovered = va.extract_files(inner_zip)
        assert recovered['bin.dat'] == binary

    def test_recovers_empty_file(self):
        va        = make_archive()
        inner_zip = va.build_inner_zip({'empty.txt': b''})
        recovered = va.extract_files(inner_zip)
        assert recovered['empty.txt'] == b''

    def test_empty_zip(self):
        va        = make_archive()
        inner_zip = va.build_inner_zip({})
        recovered = va.extract_files(inner_zip)
        assert recovered == {}


# ---------------------------------------------------------------------------
# Full round-trip: build_archive + decrypt_outer + decrypt_inner + extract_files
# ---------------------------------------------------------------------------

class Test_Vault__Archive__Round_Trip:

    def _round_trip_vault_key(self, files: dict):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        blob           = va.build_archive(files, TOKEN, vault_read_key,
                                          VAULT_ID, BRANCH_ID, COMMIT_ID)
        manifest_bytes, inner_zip_enc, dk = va.decrypt_outer(blob, TOKEN)
        inner_zip  = va.decrypt_inner(inner_zip_enc, dk, vault_read_key)
        recovered  = va.extract_files(inner_zip)
        return manifest_bytes, recovered

    def _round_trip_none(self, files: dict):
        va         = make_archive()
        blob       = va.build_archive(files, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        manifest_bytes, inner_zip_enc, dk = va.decrypt_outer(blob, TOKEN)
        # inner_key_type='none' → inner_zip_enc is a plain zip
        assert dk is None
        recovered  = va.extract_files(inner_zip_enc)
        return manifest_bytes, recovered

    def test_vault_key_simple_files(self):
        _, recovered = self._round_trip_vault_key(SIMPLE_FILES)
        assert recovered == SIMPLE_FILES

    def test_vault_key_manifest_inner_key_type(self):
        manifest_bytes, _ = self._round_trip_vault_key(SIMPLE_FILES)
        obj = json.loads(manifest_bytes)
        assert obj['inner_key_type'] == 'vault_key'

    def test_none_simple_files(self):
        _, recovered = self._round_trip_none(SIMPLE_FILES)
        assert recovered == SIMPLE_FILES

    def test_none_manifest_inner_key_type(self):
        manifest_bytes, _ = self._round_trip_none(SIMPLE_FILES)
        obj = json.loads(manifest_bytes)
        assert obj['inner_key_type'] == 'none'

    def test_vault_key_multi_files(self):
        _, recovered = self._round_trip_vault_key(MULTI_FILES)
        assert set(recovered.keys()) == set(MULTI_FILES.keys())
        for path, content in MULTI_FILES.items():
            assert recovered[path] == content

    def test_none_multi_files(self):
        _, recovered = self._round_trip_none(MULTI_FILES)
        assert set(recovered.keys()) == set(MULTI_FILES.keys())

    def test_binary_files(self):
        binary_files = {
            'data.bin':  bytes(range(256)),
            'zeros.dat': b'\x00' * 1000,
            'random':    os.urandom(512),
        }
        _, recovered = self._round_trip_vault_key(binary_files)
        assert recovered == binary_files

    def test_empty_files(self):
        files = {'empty.txt': b'', 'also_empty': b'', 'real.txt': b'content'}
        _, recovered = self._round_trip_vault_key(files)
        assert recovered == files

    def test_unicode_filenames_and_content(self):
        files = {
            'café.txt':        'café au lait'.encode('utf-8'),
            'données/résumé':  'résumé content'.encode('utf-8'),
        }
        _, recovered = self._round_trip_vault_key(files)
        assert recovered == files

    def test_single_file(self):
        files = {'single.txt': b'just one'}
        _, recovered = self._round_trip_vault_key(files)
        assert recovered == files

    def test_empty_dict(self):
        _, recovered = self._round_trip_vault_key({})
        assert recovered == {}

    def test_large_file(self):
        large = os.urandom(1024 * 1024)   # 1 MB
        files = {'big.dat': large}
        _, recovered = self._round_trip_vault_key(files)
        assert recovered == files

    def test_description_preserved_in_manifest(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        blob           = va.build_archive(SIMPLE_FILES, TOKEN, vault_read_key,
                                          VAULT_ID, BRANCH_ID, COMMIT_ID,
                                          description='Release snapshot')
        manifest_bytes, _, _ = va.decrypt_outer(blob, TOKEN)
        obj = json.loads(manifest_bytes)
        assert obj['description'] == 'Release snapshot'

    def test_file_count_in_manifest(self):
        _, _ = self._round_trip_vault_key(SIMPLE_FILES)
        va   = make_archive()
        vault_read_key = os.urandom(32)
        blob = va.build_archive(SIMPLE_FILES, TOKEN, vault_read_key,
                                VAULT_ID, BRANCH_ID, COMMIT_ID)
        manifest_bytes, _, _ = va.decrypt_outer(blob, TOKEN)
        obj = json.loads(manifest_bytes)
        assert obj['files'] == len(SIMPLE_FILES)

    def test_vault_id_in_manifest(self):
        va             = make_archive()
        vault_read_key = os.urandom(32)
        blob           = va.build_archive(SIMPLE_FILES, TOKEN, vault_read_key,
                                          VAULT_ID, BRANCH_ID, COMMIT_ID)
        manifest_bytes, _, _ = va.decrypt_outer(blob, TOKEN)
        obj = json.loads(manifest_bytes)
        assert obj['vault_id'] == VAULT_ID

    def test_different_tokens_produce_different_blobs(self):
        va  = make_archive()
        b1  = va.build_archive(SIMPLE_FILES, TOKEN,         None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        b2  = va.build_archive(SIMPLE_FILES, 'other-token-1234', None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        assert b1 != b2

    def test_each_build_is_unique(self):
        """Same inputs produce different blobs due to random IVs."""
        va  = make_archive()
        b1  = va.build_archive(SIMPLE_FILES, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        b2  = va.build_archive(SIMPLE_FILES, TOKEN, None, VAULT_ID, BRANCH_ID, COMMIT_ID)
        assert b1 != b2
