import json
import os
import tempfile
import shutil
from sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto, PBKDF2_ITERATIONS, HKDF_INFO_PREFIX, SALT_PREFIX, WRITE_SALT_PREFIX
from sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sg_send_cli.schemas.Schema__Object_Commit     import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.sync.Vault__Sync                  import Vault__Sync, SG_VAULT_DIR, VAULT_KEY_FILE
from sg_send_cli.api.Vault__API                    import Vault__API
from sg_send_cli.secrets.Secrets__Store            import Secrets__Store


class Vault__API__In_Memory(Vault__API):
    def setup(self):
        self._store = {}
        return self

    def write(self, vault_id, file_id, write_key, payload):
        self._store[f'{vault_id}/{file_id}'] = payload
        return {'status': 'ok'}

    def read(self, vault_id, file_id):
        key = f'{vault_id}/{file_id}'
        if key not in self._store:
            raise RuntimeError(f'Not found: {key}')
        return self._store[key]

    def delete(self, vault_id, file_id, write_key):
        self._store.pop(f'{vault_id}/{file_id}', None)
        return {'status': 'ok'}


class Test_AppSec__No_Plaintext_In_Object_Store:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.api      = Vault__API__In_Memory().setup()
        self.sync     = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_object_store__no_plaintext_file_contents(self):
        vault_dir = os.path.join(self.tmp_dir, 'secure-vault')
        self.sync.init(vault_dir)
        secret_content = 'TOP SECRET: nuclear launch codes 12345'
        with open(os.path.join(vault_dir, 'secret.txt'), 'w') as f:
            f.write(secret_content)
        self.sync.commit(vault_dir)

        sg_vault_dir = os.path.join(vault_dir, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        for obj_id in object_store.all_object_ids():
            raw = object_store.load(obj_id)
            assert secret_content.encode() not in raw
            assert b'nuclear launch codes' not in raw


class Test_AppSec__Vault_Key_Not_In_Object_Store:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_vault_key__not_stored_as_object(self):
        vault_dir = os.path.join(self.tmp_dir, 'key-vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        sg_vault_dir = os.path.join(vault_dir, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        for obj_id in object_store.all_object_ids():
            raw = object_store.load(obj_id)
            assert vault_key.encode() not in raw


class Test_AppSec__Secrets_Encrypted_At_Rest:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.store_path = os.path.join(self.tmp_dir, 'secrets.enc')
        self.store      = Secrets__Store(store_path=self.store_path, crypto=Vault__Crypto())

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_secrets__encrypted_at_rest(self):
        passphrase   = 'strong-pass-123'
        secret_value = 'my-super-secret-api-key-never-in-plaintext'
        self.store.store(passphrase, 'api-key', secret_value)

        with open(self.store_path, 'rb') as f:
            raw = f.read()
        assert secret_value.encode() not in raw
        assert b'api-key' not in raw
        assert b'strong-pass-123' not in raw


class Test_AppSec__Key_Derivation_Constants:

    def test_pbkdf2_iterations__600k(self):
        assert PBKDF2_ITERATIONS == 600_000

    def test_salt_prefix__matches_spec(self):
        assert SALT_PREFIX == 'sg-vault-v1'

    def test_write_salt_prefix__matches_spec(self):
        assert WRITE_SALT_PREFIX == 'sg-vault-v1:write'

    def test_hkdf_info_prefix__matches_spec(self):
        assert HKDF_INFO_PREFIX == b'sg-send-file-key'

    def test_read_key__differs_from_write_key(self):
        crypto    = Vault__Crypto()
        read_key  = crypto.derive_read_key('test-pass', 'abcd1234')
        write_key = crypto.derive_write_key('test-pass', 'abcd1234')
        assert read_key != write_key

    def test_read_write_keys__32_bytes_each(self):
        crypto    = Vault__Crypto()
        read_key  = crypto.derive_read_key('test-pass', 'abcd1234')
        write_key = crypto.derive_write_key('test-pass', 'abcd1234')
        assert len(read_key)  == 32
        assert len(write_key) == 32


class Test_AppSec__Commit_Metadata_No_Sensitive_Data:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_commit_objects__no_vault_key_in_commit(self):
        vault_dir = os.path.join(self.tmp_dir, 'metadata-vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        with open(os.path.join(vault_dir, 'doc.txt'), 'w') as f:
            f.write('some document')
        self.sync.commit(vault_dir)

        sg_vault_dir = os.path.join(vault_dir, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)

        keys     = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key = keys['read_key_bytes']

        ref_manager = Vault__Ref_Manager(vault_path=sg_vault_dir)
        commit_id   = ref_manager.read_head()
        raw_commit  = object_store.load(commit_id)
        decrypted   = self.crypto.decrypt(read_key, raw_commit)
        commit_data = json.loads(decrypted)

        assert vault_key not in json.dumps(commit_data)
        assert keys['read_key'] not in json.dumps(commit_data)
        assert keys['write_key'] not in json.dumps(commit_data)


class Test_AppSec__Tree_Structure_Encrypted:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_tree_objects__encrypted_in_object_store(self):
        vault_dir = os.path.join(self.tmp_dir, 'tree-vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'sensitive-name.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(vault_dir)

        sg_vault_dir = os.path.join(vault_dir, SG_VAULT_DIR)
        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)

        for obj_id in object_store.all_object_ids():
            raw = object_store.load(obj_id)
            assert b'sensitive-name.txt' not in raw
