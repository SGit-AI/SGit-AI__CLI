import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.api.Vault__API__In_Memory   import Vault__API__In_Memory


class Test_Vault__Sync__Commit:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='my-vault'):
        directory = os.path.join(self.tmp_dir, name)
        return self.sync.init(directory), directory

    def test_commit_after_adding_file(self):
        init_result, directory = self._init_vault()

        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')

        result = self.sync.commit(directory, message='Add hello.txt')
        assert 'commit_id' in result
        assert result['commit_id'].startswith('obj-')
        assert result['message'] == 'Add hello.txt'
        assert result['branch_id'] == init_result['branch_id']

    def test_status_v2_detects_added_file(self):
        init_result, directory = self._init_vault()

        status = self.sync.status(directory)
        assert status['clean'] is True

        with open(os.path.join(directory, 'new.txt'), 'w') as f:
            f.write('new content')

        status = self.sync.status(directory)
        assert 'new.txt' in status['added']
        assert status['clean'] is False

    def test_commit_then_status_is_clean(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')

        self.sync.commit(directory, message='Add file')

        status = self.sync.status(directory)
        assert status['clean'] is True

    def test_commit_detects_modified_file(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('v1')
        self.sync.commit(directory, message='Add file')

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('v2 longer')

        status = self.sync.status(directory)
        assert 'file.txt' in status['modified']

    def test_commit_detects_deleted_file(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'gone.txt'), 'w') as f:
            f.write('temp')
        self.sync.commit(directory, message='Add file')

        os.remove(os.path.join(directory, 'gone.txt'))

        status = self.sync.status(directory)
        assert 'gone.txt' in status['deleted']

    def test_multiple_commits_chain(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'a.txt'), 'w') as f:
            f.write('first')
        r1 = self.sync.commit(directory, message='First')

        with open(os.path.join(directory, 'b.txt'), 'w') as f:
            f.write('second')
        r2 = self.sync.commit(directory, message='Second')

        assert r1['commit_id'] != r2['commit_id']

    def test_content_hash_detects_same_size_edit(self):
        """content_hash fixes the size-only detection bug: same-size edits are now caught."""
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('aaaa')
        self.sync.commit(directory, message='Add file')

        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('bbbb')                                         # same size, different content

        status = self.sync.status(directory)
        assert 'file.txt' in status['modified']
        assert status['clean'] is False

    def test_content_hash_stored_in_tree_entry(self):
        """Committed tree entries include a content_hash field."""
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'doc.txt'), 'w') as f:
            f.write('hello')
        result = self.sync.commit(directory, message='Add doc')

        import hashlib
        expected_hash = hashlib.sha256(b'hello').hexdigest()[:12]

        sg_dir      = os.path.join(directory, '.sg_vault')
        from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
        from sg_send_cli.crypto.PKI__Crypto          import PKI__Crypto
        from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
        from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
        from sg_send_cli.objects.Vault__Commit       import Vault__Commit

        crypto      = Vault__Crypto()
        vault_key   = open(os.path.join(sg_dir, 'local', 'vault_key')).read().strip()
        keys        = crypto.derive_keys_from_vault_key(vault_key)
        read_key    = keys['read_key_bytes']
        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto, use_v2=True)
        vc          = Vault__Commit(crypto=crypto, pki=pki, object_store=obj_store, ref_manager=ref_manager)
        commit_obj  = vc.load_commit(result['commit_id'], read_key)
        tree        = vc.load_tree(str(commit_obj.tree_id), read_key)

        entry = tree.entries[0]
        assert str(entry.content_hash) == expected_hash

    def test_tree_entry_has_encrypted_fields_on_disk(self):
        """Tree entries stored on disk include name_enc, size_enc, content_hash_enc."""
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'secret.txt'), 'w') as f:
            f.write('classified')
        result = self.sync.commit(directory, message='Add secret')

        sg_dir      = os.path.join(directory, '.sg_vault')
        from sg_send_cli.crypto.PKI__Crypto          import PKI__Crypto
        from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
        from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
        from sg_send_cli.objects.Vault__Commit       import Vault__Commit

        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        vc          = Vault__Commit(crypto=self.crypto, pki=pki, object_store=obj_store, ref_manager=ref_manager)

        vault_key = open(os.path.join(sg_dir, 'local', 'vault_key')).read().strip()
        read_key  = self.crypto.derive_keys_from_vault_key(vault_key)['read_key_bytes']

        commit_obj = vc.load_commit(result['commit_id'], read_key)
        tree_id    = str(commit_obj.tree_id)

        # Load raw tree JSON (decrypt blob but don't process entries)
        ciphertext = obj_store.load(tree_id)
        tree_json  = json.loads(self.crypto.decrypt(read_key, ciphertext))
        raw_entry  = tree_json['entries'][0]

        assert 'name_enc'         in raw_entry, 'name_enc missing from stored tree entry'
        assert 'size_enc'         in raw_entry, 'size_enc missing from stored tree entry'
        assert 'content_hash_enc' in raw_entry, 'content_hash_enc missing from stored tree entry'

        # Verify the encrypted values are base64 and non-empty
        import base64
        base64.b64decode(raw_entry['name_enc'])
        base64.b64decode(raw_entry['size_enc'])
        base64.b64decode(raw_entry['content_hash_enc'])

        # Verify load_tree decrypts back to plaintext
        tree = vc.load_tree(tree_id, read_key)
        entry = tree.entries[0]
        assert str(entry.path) == 'secret.txt' or str(entry.name) == 'secret.txt'

    def test_unchanged_file_reuses_blob(self):
        """When content_hash matches, the blob is reused (no re-encryption)."""
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'stable.txt'), 'w') as f:
            f.write('unchanged content')
        r1 = self.sync.commit(directory, message='First')

        with open(os.path.join(directory, 'extra.txt'), 'w') as f:
            f.write('new file')
        r2 = self.sync.commit(directory, message='Second')

        sg_dir      = os.path.join(directory, '.sg_vault')
        from sg_send_cli.crypto.PKI__Crypto          import PKI__Crypto
        from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
        from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
        from sg_send_cli.objects.Vault__Commit       import Vault__Commit

        pki         = PKI__Crypto()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        vc          = Vault__Commit(crypto=self.crypto, pki=pki, object_store=obj_store, ref_manager=ref_manager)

        vault_key = open(os.path.join(sg_dir, 'local', 'vault_key')).read().strip()
        read_key  = self.crypto.derive_keys_from_vault_key(vault_key)['read_key_bytes']

        tree1 = vc.load_tree(str(vc.load_commit(r1['commit_id'], read_key).tree_id), read_key)
        tree2 = vc.load_tree(str(vc.load_commit(r2['commit_id'], read_key).tree_id), read_key)

        blob1 = str([e for e in tree1.entries if str(e.path) == 'stable.txt'][0].blob_id)
        blob2 = str([e for e in tree2.entries if str(e.path) == 'stable.txt'][0].blob_id)
        assert blob1 == blob2
