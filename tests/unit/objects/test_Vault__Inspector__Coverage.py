import json
import os
import tempfile
import shutil
from sgit_ai.objects.Vault__Inspector    import Vault__Inspector
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from tests.unit.sync.vault_test_env      import Vault__Test_Env


class Test_Vault__Inspector__Format_Methods:
    """Test inspector formatting using real vaults created via Vault__Sync.

    A single vault snapshot with two committed files (file1.txt, file2.txt,
    readme.md) is created once per class; each test method restores from it.
    Tests that need an empty vault or a non-vault directory create a minimal
    local directory without going through full init.
    """

    _env = None   # Vault__Test_Env — snapshot with two files already committed

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.md':  'file content here',
            'file1.txt':  'content1',
            'file2.txt':  'content2',
        })

    def setup_method(self):
        self.env      = self._env.restore()
        self.crypto   = self.env.crypto
        self.inspector = Vault__Inspector(crypto=self.crypto)
        self.sync      = self.env.sync

        vault_dir          = self.env.vault_dir
        self.vault_key     = self.env.vault_key
        self.keys          = self.crypto.derive_keys_from_vault_key(self.vault_key)
        self.read_key      = self.keys['read_key_bytes']
        self.tmp_dir       = vault_dir   # alias expected by some helpers

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
        # The snapshot vault has files, so we test inspect_tree with the
        # snapshot's read_key; the result will have file_count > 0.
        # For an actually empty vault we rely on a separate small init.
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
        tmp = tempfile.mkdtemp()
        try:
            crypto = Vault__Crypto()
            sync   = Vault__Sync(crypto=crypto, api=Vault__API__In_Memory().setup())
            res    = sync.init(tmp)
            keys   = crypto.derive_keys_from_vault_key(res['vault_key'])
            insp   = Vault__Inspector(crypto=crypto)
            result = insp.inspect_tree(tmp, read_key=keys['read_key_bytes'])
            assert result['commit_id'] is not None
            assert result['file_count'] == 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_inspect_tree__with_file(self):
        result = self.inspector.inspect_tree(self.env.vault_dir, read_key=self.read_key)
        assert result['file_count'] >= 1

    # --- inspect_commit_chain ---

    def test_inspect_commit_chain__single_commit(self):
        # The snapshot has init commit + 1 commit with files = 2 total.
        # We want a chain of exactly 1 — use a bare fresh init.
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
        tmp = tempfile.mkdtemp()
        try:
            crypto = Vault__Crypto()
            sync   = Vault__Sync(crypto=crypto, api=Vault__API__In_Memory().setup())
            res    = sync.init(tmp)
            keys   = crypto.derive_keys_from_vault_key(res['vault_key'])
            insp   = Vault__Inspector(crypto=crypto)
            chain  = insp.inspect_commit_chain(tmp, read_key=keys['read_key_bytes'])
            assert len(chain) == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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
        # Use the commit_id stored in the snapshot (the file-commit id)
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
