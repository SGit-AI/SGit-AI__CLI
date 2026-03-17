import json
import os
import tempfile
from sg_send_cli.objects.Vault__Inspector    import Vault__Inspector
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Sync            import Vault__Sync


class Test_Vault__Inspector__Format_Methods:
    """Test inspector formatting using real vaults created via Vault__Sync."""

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.crypto     = Vault__Crypto()
        self.inspector  = Vault__Inspector(crypto=self.crypto)
        self.sync       = Vault__Sync(crypto=self.crypto)

    def _init_vault(self):
        result    = self.sync.init(self.tmp_dir)
        self.vault_key = result['vault_key']
        self.keys      = self.crypto.derive_keys_from_vault_key(self.vault_key)
        self.read_key  = self.keys['read_key_bytes']
        return result

    def _add_file_and_commit(self, filename='readme.md', content='file content here', message='added file'):
        filepath = os.path.join(self.tmp_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(content)
        return self.sync.commit(self.tmp_dir, message)

    # --- format_vault_summary ---

    def test_format_vault_summary__no_vault(self):
        empty_dir = tempfile.mkdtemp()
        summary   = self.inspector.format_vault_summary(empty_dir)
        assert 'Vault Summary' in summary
        assert 'none' in summary

    def test_format_vault_summary__with_objects(self):
        result  = self._init_vault()
        self._add_file_and_commit()
        summary = self.inspector.format_vault_summary(self.tmp_dir)
        assert 'Vault Summary' in summary
        assert 'object-store' in summary

    # --- inspect_tree ---

    def test_inspect_tree__empty_vault(self):
        self._init_vault()
        result = self.inspector.inspect_tree(self.tmp_dir, read_key=self.read_key)
        assert result['commit_id'] is not None
        assert result['file_count'] == 0

    def test_inspect_tree__with_file(self):
        self._init_vault()
        self._add_file_and_commit()
        result = self.inspector.inspect_tree(self.tmp_dir, read_key=self.read_key)
        assert result['file_count'] == 1

    # --- inspect_commit_chain ---

    def test_inspect_commit_chain__single_commit(self):
        self._init_vault()
        chain = self.inspector.inspect_commit_chain(self.tmp_dir, read_key=self.read_key)
        assert len(chain) == 1

    def test_inspect_commit_chain__multiple_commits(self):
        self._init_vault()
        self._add_file_and_commit('file1.txt', 'content1', 'first')
        self._add_file_and_commit('file2.txt', 'content2', 'second')
        chain = self.inspector.inspect_commit_chain(self.tmp_dir, read_key=self.read_key)
        assert len(chain) == 3  # init + 2 commits

    def test_inspect_commit_chain__no_read_key(self):
        self._init_vault()
        chain = self.inspector.inspect_commit_chain(self.tmp_dir)
        assert chain == [] or (len(chain) == 1 and 'error' in chain[0])

    def test_inspect_commit_chain__limit(self):
        self._init_vault()
        self._add_file_and_commit('file1.txt', 'c1', 'first')
        self._add_file_and_commit('file2.txt', 'c2', 'second')
        chain = self.inspector.inspect_commit_chain(self.tmp_dir, read_key=self.read_key, limit=2)
        assert len(chain) <= 2

    # --- cat_object ---

    def test_cat_object__commit_type(self):
        result = self._init_vault()
        commit_id = result['commit_id']
        cat = self.inspector.cat_object(self.tmp_dir, commit_id, read_key=self.read_key)
        assert cat is not None
        data = json.loads(cat)
        assert 'tree_id' in data

    def test_cat_object__blob_type(self):
        self._init_vault()
        commit_result = self._add_file_and_commit()
        tree_result = self.inspector.inspect_tree(self.tmp_dir, read_key=self.read_key)
        if tree_result.get('entries'):
            blob_id = tree_result['entries'][0]['blob_id']
            cat = self.inspector.cat_object(self.tmp_dir, blob_id, read_key=self.read_key)
            assert cat is not None

    # --- object_store_stats ---

    def test_object_store_stats__with_objects(self):
        self._init_vault()
        self._add_file_and_commit()
        stats = self.inspector.object_store_stats(self.tmp_dir)
        assert stats['object_count'] > 0
        assert stats['total_size']   > 0

    def test_object_store_stats__empty(self):
        empty_dir = tempfile.mkdtemp()
        stats = self.inspector.object_store_stats(empty_dir)
        assert stats['object_count'] == 0
