"""Tests for vault fsck (integrity check and repair).

Verifies that fsck detects missing and corrupt objects, and that
--repair mode can re-download them from the remote.
"""
import os
import tempfile
import shutil

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env    import Vault__Test_Env


class Test_Vault__Sync__Fsck:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'file1.txt': 'hello world',
                                           'file2.txt': 'second file'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_fsck_healthy_vault(self):
        """fsck on a clean vault should report ok."""
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok']       is True
        assert result['missing']  == []
        assert result['corrupt']  == []
        assert result['errors']   == []

    def test_fsck_not_a_vault(self):
        """fsck on a non-vault directory should report error."""
        not_vault = os.path.join(self.env.tmp_dir, 'not-a-vault')
        os.makedirs(not_vault)
        result = self.sync.fsck(not_vault)
        assert result['ok'] is False
        assert any('Not a vault' in e for e in result['errors'])

    def test_fsck_detects_missing_object(self):
        """fsck should detect when a blob object is missing from the store."""
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')

        # Delete a blob object (not a commit or tree — pick the first non-essential one)
        all_objects = sorted(os.listdir(data_dir))
        assert len(all_objects) > 0

        # Remove one object
        victim = all_objects[0]
        os.remove(os.path.join(data_dir, victim))

        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert victim in result['missing']

    def test_fsck_detects_corrupt_object(self):
        """fsck should detect objects whose hash doesn't match their ID."""
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')

        all_objects = sorted(os.listdir(data_dir))
        victim = all_objects[0]
        victim_path = os.path.join(data_dir, victim)

        # Corrupt the file by appending junk
        with open(victim_path, 'ab') as f:
            f.write(b'CORRUPTED')

        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert victim in result['corrupt']

    def test_fsck_repair_downloads_missing_object(self):
        """fsck --repair should re-download missing objects from remote."""
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')

        all_objects = sorted(os.listdir(data_dir))
        victim = all_objects[0]
        os.remove(os.path.join(data_dir, victim))

        result = self.sync.fsck(self.env.vault_dir, repair=True)
        assert victim in result['repaired']
        assert os.path.isfile(os.path.join(data_dir, victim)), 'Object should be restored'
        # After repair, vault should be ok (unless there are other issues)
        assert result['ok'] is True or len(result['missing']) == 0

    def test_fsck_empty_vault(self):
        """fsck on an empty vault (no commits) should report ok."""
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync      = Vault__Sync(crypto=crypto, api=api)
        empty_dir = os.path.join(self.env.tmp_dir, 'empty-vault')
        sync.init(empty_dir)
        result = sync.fsck(empty_dir)
        assert result['ok'] is True


class Test_Vault__Sync__Fsck__Error_Paths:
    """Additional tests for rarely-hit error branches in fsck / _repair_object."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'docs/readme.txt': 'readme',
            'file.txt':        'content',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def _get_head_commit_id(self):
        """Return the HEAD commit ID for the snapshot vault."""
        import json as _json
        from sgit_ai.storage.Vault__Storage          import SG_VAULT_DIR
        from sgit_ai.storage.Vault__Branch_Manager   import Vault__Branch_Manager
        from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
        from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
        from sgit_ai.storage.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager   import Vault__Ref_Manager
        from sgit_ai.crypto.Vault__Key_Manager    import Vault__Key_Manager
        from sgit_ai.storage.Vault__Storage          import Vault__Storage

        vault_dir = self.env.vault_dir
        sg_dir    = os.path.join(vault_dir, SG_VAULT_DIR)
        crypto    = self.env.crypto
        storage   = Vault__Storage()
        pki       = PKI__Crypto()

        ref_manager    = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=crypto,
                                                key_manager=key_manager,
                                                ref_manager=ref_manager,
                                                storage=storage)
        vault_key = self.env.vault_key
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']
        index_id  = keys['branch_index_file_id']

        config_path = storage.local_config_path(vault_dir)
        with open(config_path) as f:
            config_data = _json.load(f)
        local_config = Schema__Local_Config.from_json(config_data)
        branch_id    = str(local_config.my_branch_id)

        branch_index = branch_manager.load_branch_index(vault_dir, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        return ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

    def test_fsck_bad_vault_config__init_components_fails(self):
        """Lines 25-28: _init_components raises when vault_key file is invalid."""
        vk_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')
        with open(vk_path, 'w') as f:
            f.write('INVALID_KEY_NO_COLON')
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert any('Cannot read vault config' in e for e in result['errors'])

    def test_fsck_corrupt_branch_index__branch_info_fails(self):
        """Lines 42-45: branch index unreadable → error captured and early return."""
        import json as _json
        # Corrupt the branch index file so load_branch_index raises
        from sgit_ai.storage.Vault__Storage import Vault__Storage, SG_VAULT_DIR
        vault_dir   = self.env.vault_dir
        sg_dir      = os.path.join(vault_dir, SG_VAULT_DIR)
        crypto      = self.env.crypto
        vault_key   = self.env.vault_key
        keys        = crypto.derive_keys_from_vault_key(vault_key)
        index_id    = keys['branch_index_file_id']
        index_path  = os.path.join(sg_dir, 'bare', 'indexes', index_id)

        if os.path.isfile(index_path):
            with open(index_path, 'wb') as f:
                f.write(b'\x00' * 64)   # corrupt the encrypted index

        result = self.sync.fsck(vault_dir)
        assert result['ok'] is False
        assert any('Cannot read branch info' in e for e in result['errors'])

    def test_fsck_no_commit_id__returns_ok_early(self):
        """Lines 48-49: branch_id not in index → clone_meta is None → commit_id is None → early ok."""
        import json as _json
        config_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'config.json')
        with open(config_path, 'w') as f:
            _json.dump({
                'my_branch_id': 'branch-clone-0000000000000000',
                'mode': None, 'edit_token': None, 'sparse': False
            }, f)
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is True
        assert result['missing'] == []

    def test_fsck_missing_head_commit(self):
        """Lines 66-72: HEAD commit object missing → commit reported as missing."""
        commit_id = self._get_head_commit_id()
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')
        obj_path  = os.path.join(data_dir, commit_id)
        if os.path.isfile(obj_path):
            os.remove(obj_path)
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert commit_id in result['missing']

    def test_fsck_corrupt_head_commit(self):
        """Lines 77-79: HEAD commit object corrupt → commit reported as corrupt."""
        commit_id = self._get_head_commit_id()
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')
        obj_path  = os.path.join(data_dir, commit_id)
        if os.path.isfile(obj_path):
            with open(obj_path, 'ab') as f:
                f.write(b'CORRUPT')
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert commit_id in result['corrupt']

    def test_fsck_unreadable_commit_object(self):
        """Lines 83-86: object exists but decrypt fails → error captured."""
        commit_id = self._get_head_commit_id()
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')
        obj_path  = os.path.join(data_dir, commit_id)
        if os.path.isfile(obj_path):
            # Overwrite with random bytes so size matches but content is garbage
            with open(obj_path, 'wb') as f:
                f.write(b'\x00' * 48)   # 48 bytes is less than a valid ciphertext
        result = self.sync.fsck(self.env.vault_dir)
        # Either corrupt or errors depending on verification order
        assert result['ok'] is False

    def test_fsck_missing_blob_in_tree(self):
        """Lines 120-124: blob object missing from tree → blob in missing."""
        from sgit_ai.storage.Vault__Storage     import SG_VAULT_DIR
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector

        vault_dir = self.env.vault_dir
        sg_dir    = os.path.join(vault_dir, SG_VAULT_DIR)
        crypto    = self.env.crypto
        inspector = Vault__Inspector(crypto=crypto)
        vault_key = self.env.vault_key
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']

        tree_result = inspector.inspect_tree(vault_dir, read_key=read_key)
        assert tree_result.get('entries'), 'vault must have blob entries'
        blob_id  = tree_result['entries'][0]['blob_id']
        data_dir = os.path.join(sg_dir, 'bare', 'data')
        os.remove(os.path.join(data_dir, blob_id))

        result = self.sync.fsck(vault_dir)
        assert result['ok'] is False
        assert blob_id in result['missing']

    def test_fsck_corrupt_blob_in_tree(self):
        """Lines 126-127: blob object corrupt → blob in corrupt."""
        from sgit_ai.storage.Vault__Storage     import SG_VAULT_DIR
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector

        vault_dir = self.env.vault_dir
        sg_dir    = os.path.join(vault_dir, SG_VAULT_DIR)
        crypto    = self.env.crypto
        inspector = Vault__Inspector(crypto=crypto)
        vault_key = self.env.vault_key
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']

        tree_result = inspector.inspect_tree(vault_dir, read_key=read_key)
        assert tree_result.get('entries'), 'vault must have blob entries'
        blob_id  = tree_result['entries'][0]['blob_id']
        blob_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
        with open(blob_path, 'ab') as f:
            f.write(b'CORRUPT')

        result = self.sync.fsck(vault_dir)
        assert result['ok'] is False
        assert blob_id in result['corrupt']

    def test_fsck_vault_with_subdirectory_hits_sub_tree(self):
        """Line 130: vault with subdirectory creates a sub_tree entry in the tree."""
        # The class-level snapshot has docs/readme.txt which creates a sub-tree.
        # A clean fsck should succeed and traverse the sub-tree (line 130 executed).
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is True

    def test_fsck_repair_object_fails_silently(self):
        """Lines 157-159: _repair_object API error falls back to return False."""
        from sgit_ai.core.actions.fsck.Vault__Sync__Fsck import Vault__Sync__Fsck

        crypto = self.env.crypto
        # Use an API that will fail to read the object
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory

        class BrokenAPI(Vault__API__In_Memory):
            def read(self, vault_id, path, **kwargs):
                raise RuntimeError('simulated network failure')

        broken_api = BrokenAPI()
        broken_api.setup()
        fsck = Vault__Sync__Fsck(crypto=crypto, api=broken_api)
        result = fsck._repair_object('nonexistent-object-id', 'vault-id-dummy', '/tmp')
        assert result is False
