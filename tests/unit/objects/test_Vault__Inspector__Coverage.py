import json
import os
import shutil
import tempfile
from unittest.mock import patch
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Inspector    import Vault__Inspector
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.storage.Vault__Storage         import SG_VAULT_DIR
from tests._helpers.vault_test_env       import Vault__Test_Env


class Test_Vault__Inspector__Format_Methods:
    """Test inspector formatting using real vaults created via Vault__Sync."""

    _env       = None   # Vault__Test_Env — snapshot with files committed
    _empty_env = None   # Vault__Test_Env — snapshot with bare init only (no files)

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.md':  'file content here',
            'file1.txt':  'content1',
            'file2.txt':  'content2',
        })
        cls._empty_env = Vault__Test_Env()
        cls._empty_env.setup_single_vault()   # bare init commit only, no files

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()
        if cls._empty_env:
            cls._empty_env.cleanup_snapshot()

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.inspector = Vault__Inspector(crypto=self.crypto)
        self.sync      = self.env.sync

        vault_dir      = self.env.vault_dir
        self.vault_key = self.env.vault_key
        self.keys      = self.crypto.derive_keys_from_vault_key(self.vault_key)
        self.read_key  = self.keys['read_key_bytes']
        self.tmp_dir   = vault_dir   # alias expected by some helpers

    def teardown_method(self):
        self.env.cleanup()

    # --- format_vault_summary ---

    def test_format_vault_summary__no_vault(self):
        empty_dir = tempfile.mkdtemp()
        try:
            summary = self.inspector.format_vault_summary(empty_dir)
            assert 'Vault Summary' in summary
            assert 'none' in summary
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_format_vault_summary__with_objects(self):
        summary = self.inspector.format_vault_summary(self.env.vault_dir)
        assert 'Vault Summary' in summary
        assert 'object-store' in summary

    # --- inspect_tree ---

    def test_inspect_tree__empty_vault(self):
        env = self._empty_env.restore()
        try:
            keys   = env.crypto.derive_keys_from_vault_key(env.vault_key)
            insp   = Vault__Inspector(crypto=env.crypto)
            result = insp.inspect_tree(env.vault_dir, read_key=keys['read_key_bytes'])
            assert result['commit_id'] is not None
            assert result['file_count'] == 0
        finally:
            env.cleanup()

    def test_inspect_tree__with_file(self):
        result = self.inspector.inspect_tree(self.env.vault_dir, read_key=self.read_key)
        assert result['file_count'] >= 1

    # --- inspect_commit_chain ---

    def test_inspect_commit_chain__single_commit(self):
        env = self._empty_env.restore()
        try:
            keys  = env.crypto.derive_keys_from_vault_key(env.vault_key)
            insp  = Vault__Inspector(crypto=env.crypto)
            chain = insp.inspect_commit_chain(env.vault_dir, read_key=keys['read_key_bytes'])
            assert len(chain) == 1
        finally:
            env.cleanup()

    def test_inspect_commit_chain__multiple_commits(self):
        # Snapshot already has init + 1 file commit = 2 commits.
        chain = self.inspector.inspect_commit_chain(self.env.vault_dir,
                                                     read_key=self.read_key)
        assert len(chain) >= 2

    def test_inspect_commit_chain__no_read_key(self):
        chain = self.inspector.inspect_commit_chain(self.env.vault_dir)
        assert chain == [] or (len(chain) == 1 and 'error' in chain[0])

    def test_inspect_commit_chain__limit(self):
        chain = self.inspector.inspect_commit_chain(self.env.vault_dir,
                                                     read_key=self.read_key,
                                                     limit=1)
        assert len(chain) <= 1

    # --- cat_object ---

    def test_cat_object__commit_type(self):
        commit_id = self.env.commit_id
        cat = self.inspector.cat_object(self.env.vault_dir, commit_id,
                                         read_key=self.read_key)
        assert cat is not None
        assert 'tree_id' in cat.get('content', {})

    def test_cat_object__blob_type(self):
        tree_result = self.inspector.inspect_tree(self.env.vault_dir,
                                                   read_key=self.read_key)
        if tree_result.get('entries'):
            blob_id = tree_result['entries'][0]['blob_id']
            cat = self.inspector.cat_object(self.env.vault_dir, blob_id,
                                             read_key=self.read_key)
            assert cat is not None

    # --- object_store_stats ---

    def test_object_store_stats__with_objects(self):
        stats = self.inspector.object_store_stats(self.env.vault_dir)
        assert stats['total_objects'] > 0
        assert stats['total_bytes']   > 0

    def test_object_store_stats__empty(self):
        empty_dir = tempfile.mkdtemp()
        try:
            stats = self.inspector.object_store_stats(empty_dir)
            assert stats['total_objects'] == 0
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    # --- format_cat_object edge cases ---

    def test_format_cat_object__blob_content_not_dict(self):
        """Line 264: blob content is a string, not dict → str() path is taken."""
        sg_dir    = os.path.join(self.env.vault_dir, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        all_ids   = obj_store.all_object_ids()
        blob_id   = None
        for oid in all_ids:
            info = self.inspector.cat_object(self.env.vault_dir, oid, self.read_key)
            if info.get('type') in ('blob', 'blob (binary)'):
                blob_id = oid
                break
        assert blob_id is not None
        result = self.inspector.format_cat_object(self.env.vault_dir, blob_id, self.read_key)
        assert 'blob' in result

    def test_format_cat_object__root_commit_no_parents(self):
        """Line 288: root commit has no parents → '(root commit)' is printed."""
        env = self._empty_env.restore()
        try:
            keys     = env.crypto.derive_keys_from_vault_key(env.vault_key)
            read_key = keys['read_key_bytes']
            insp     = Vault__Inspector(crypto=env.crypto)
            chain    = insp.inspect_commit_chain(env.vault_dir, read_key=read_key)
            assert len(chain) >= 1
            root_id  = chain[-1]['commit_id']
            result   = insp.format_cat_object(env.vault_dir, root_id, read_key)
            assert '(root commit)' in result
        finally:
            env.cleanup()

    def test_format_cat_object__child_commit_shown(self):
        """Lines 282-283: when a child commit exists, 'Child:' line is shown."""
        chain = self.inspector.inspect_commit_chain(self.env.vault_dir,
                                                     read_key=self.read_key)
        assert len(chain) >= 2
        parent_id = chain[-1]['commit_id']
        result    = self.inspector.format_cat_object(self.env.vault_dir,
                                                      parent_id, self.read_key)
        assert 'Child:' in result

    def test_inspect_commit_chain__missing_object(self):
        """Lines 111-112: when a commit object doesn't exist locally, error is recorded."""
        chain_before = self.inspector.inspect_commit_chain(self.env.vault_dir,
                                                            read_key=self.read_key)
        root_id   = chain_before[-1]['commit_id']
        sg_dir    = os.path.join(self.env.vault_dir, SG_VAULT_DIR)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        obj_path  = obj_store.object_path(root_id)
        os.remove(obj_path)
        chain_after = self.inspector.inspect_commit_chain(self.env.vault_dir,
                                                           read_key=self.read_key)
        assert any('object not found locally' in str(e.get('error', '')) for e in chain_after)

    def test_resolve_head_no_config(self):
        """Line 313: when config.json is missing, _resolve_head returns None."""
        tmp = tempfile.mkdtemp()
        try:
            sg_dir = os.path.join(tmp, SG_VAULT_DIR)
            os.makedirs(os.path.join(sg_dir, 'local'), exist_ok=True)
            insp    = Vault__Inspector(crypto=Vault__Crypto())
            ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=Vault__Crypto())
            result  = insp._resolve_head(tmp, ref_mgr, read_key=b'\x00' * 32)
            assert result is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolve_head_no_index(self):
        """Line 337: when no branch index exists, _resolve_head returns None."""
        tmp = tempfile.mkdtemp()
        try:
            sg_dir    = os.path.join(tmp, SG_VAULT_DIR)
            local_dir = os.path.join(sg_dir, 'local')
            os.makedirs(local_dir, exist_ok=True)
            with open(os.path.join(local_dir, 'config.json'), 'w') as f:
                json.dump({'my_branch_id': 'br-test'}, f)
            insp    = Vault__Inspector(crypto=Vault__Crypto())
            ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=Vault__Crypto())
            result  = insp._resolve_head(tmp, ref_mgr, read_key=b'\x00' * 32)
            assert result is None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_format_cat_object__commit_with_entries_and_parents(self):
        """Lines 272-277 and 286-287: commit with tree entries and parents shows them."""
        chain = self.inspector.inspect_commit_chain(self.env.vault_dir,
                                                     read_key=self.read_key)
        non_root_id = chain[0]['commit_id']   # newest commit has parents + entries
        result      = self.inspector.format_cat_object(self.env.vault_dir,
                                                        non_root_id, self.read_key)
        assert 'Parents:' in result
        assert ('Tree' in result or 'blob' in result)

    # ------------------------------------------------------------------
    # Line 73: inspect_tree returns error dict when commit_id exists but no read_key
    # ------------------------------------------------------------------

    def test_inspect_tree_returns_error_when_no_read_key_but_commit_exists(self):
        """Line 73: commit_id resolved but read_key=None → error dict returned."""
        insp = Vault__Inspector(crypto=self.crypto)
        with patch.object(Vault__Inspector, '_resolve_head', return_value='commit-abc000000000'):
            result = insp.inspect_tree(self.env.vault_dir, read_key=None)
        assert result.get('error') == 'read_key required to decrypt tree'
        assert result.get('commit_id') == 'commit-abc000000000'

    # ------------------------------------------------------------------
    # Line 104: inspect_commit_chain returns error list when no read_key but commit exists
    # ------------------------------------------------------------------

    def test_inspect_commit_chain_returns_error_when_no_read_key_but_commit_exists(self):
        """Line 104: commit_id resolved but read_key=None → [error dict] returned."""
        insp = Vault__Inspector(crypto=self.crypto)
        with patch.object(Vault__Inspector, '_resolve_head', return_value='commit-abc000000000'):
            result = insp.inspect_commit_chain(self.env.vault_dir, read_key=None)
        assert len(result) == 1
        assert result[0].get('error') == 'read_key required to decrypt chain'
        assert result[0].get('commit_id') == 'commit-abc000000000'

    # ------------------------------------------------------------------
    # Lines 120-121: inspect_commit_chain silences decrypt_metadata exception
    # ------------------------------------------------------------------

    def test_inspect_commit_chain_silences_decrypt_metadata_exception(self):
        """Lines 120-121: when decrypt_metadata raises, message falls back to '[encrypted]'."""
        insp = Vault__Inspector(crypto=self.crypto)

        def raise_decrypt(self_, read_key, enc):
            raise ValueError('bad ciphertext')

        with patch.object(type(self.crypto), 'decrypt_metadata', raise_decrypt):
            chain = insp.inspect_commit_chain(self.env.vault_dir, read_key=self.read_key)
        assert all(c.get('message') in (None, '[encrypted]') for c in chain)

    # ------------------------------------------------------------------
    # Line 341: _resolve_head returns None when branch_meta not found in index
    # ------------------------------------------------------------------

    def test_resolve_head_returns_none_when_branch_meta_missing(self):
        """Line 341: branch_id in config not found in branch index → returns None."""
        sg_dir      = os.path.join(self.env.vault_dir, SG_VAULT_DIR)
        config_path = os.path.join(sg_dir, 'local', 'config.json')
        with open(config_path, 'w') as fh:
            json.dump({'my_branch_id': 'branch-clone-00000000nonexistent'}, fh)
        ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        result  = Vault__Inspector(crypto=self.crypto)._resolve_head(
            self.env.vault_dir, ref_mgr, self.read_key
        )
        assert result is None
