import json
import os
import tempfile
from sg_send_cli.objects.Vault__Inspector    import Vault__Inspector
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.schemas.Schema__Object_Commit import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Test_Vault__Inspector:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.crypto     = Vault__Crypto()
        self.inspector  = Vault__Inspector(crypto=self.crypto)

    def _vault_path(self):
        return os.path.join(self.tmp_dir, '.sg_vault')

    def _setup_empty_vault(self):
        vault_path = self._vault_path()
        os.makedirs(vault_path, exist_ok=True)
        return vault_path

    def _setup_object_store_vault(self):
        vault_path   = self._setup_empty_vault()
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=vault_path, crypto=self.crypto)
        return vault_path, object_store, ref_manager

    def test_inspect_vault_no_sg_vault(self):
        result = self.inspector.inspect_vault(self.tmp_dir)
        assert result['vault_format'] == 'none'
        assert result['commit_id'] is None
        assert result['object_count'] == 0

    def test_inspect_vault_empty_sg_vault(self):
        self._setup_empty_vault()
        result = self.inspector.inspect_vault(self.tmp_dir)
        assert result['vault_format'] == 'uninitialized'

    def test_inspect_vault_legacy_format(self):
        vault_path = self._setup_empty_vault()
        with open(os.path.join(vault_path, 'tree.json'), 'w') as f:
            json.dump({'version': 3}, f)
        result = self.inspector.inspect_vault(self.tmp_dir)
        assert result['vault_format'] == 'legacy'

    def test_inspect_vault_object_store_format(self):
        vault_path, object_store, ref_manager = self._setup_object_store_vault()
        ref_manager.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-a1b2c3d4e5f6')
        object_store.store(b'test data')
        result = self.inspector.inspect_vault(self.tmp_dir)
        assert result['vault_format'] == 'object-store'
        assert result['commit_id'] is None  # requires read_key to decrypt
        assert result['object_count'] == 1

    def test_inspect_object_exists(self):
        vault_path, object_store, _ = self._setup_object_store_vault()
        data      = b'test object data'
        object_id = object_store.store(data)
        result    = self.inspector.inspect_object(self.tmp_dir, object_id)
        assert result['exists'] is True
        assert result['size_bytes'] == len(data)
        assert result['integrity_ok'] is True
        assert len(result['sha256']) == 64

    def test_inspect_object_missing(self):
        self._setup_empty_vault()
        result = self.inspector.inspect_object(self.tmp_dir, 'aabbccddeeff')
        assert result['exists'] is False

    def test_object_store_stats_empty(self):
        self._setup_empty_vault()
        stats = self.inspector.object_store_stats(self.tmp_dir)
        assert stats['total_objects'] == 0
        assert stats['total_bytes'] == 0
        assert stats['buckets'] == {}

    def test_object_store_stats_with_objects(self):
        vault_path, object_store, _ = self._setup_object_store_vault()
        object_store.store(b'data one')
        object_store.store(b'data two')
        object_store.store(b'data three')
        stats = self.inspector.object_store_stats(self.tmp_dir)
        assert stats['total_objects'] == 3
        assert stats['total_bytes'] > 0

    def test_format_vault_summary(self):
        self._setup_empty_vault()
        summary = self.inspector.format_vault_summary(self.tmp_dir)
        assert 'Vault Summary' in summary
        assert 'Format:' in summary
        assert 'Objects:' in summary

    def test_format_object_detail(self):
        vault_path, object_store, _ = self._setup_object_store_vault()
        object_id = object_store.store(b'detail test')
        detail    = self.inspector.format_object_detail(self.tmp_dir, object_id)
        assert object_id in detail
        assert 'Integrity:' in detail
        assert 'OK' in detail

    def test_format_commit_log_empty(self):
        result = self.inspector.format_commit_log([])
        assert result == '(no commits)'

    def test_inspect_tree_no_head(self):
        self._setup_empty_vault()
        result = self.inspector.inspect_tree(self.tmp_dir)
        assert result['commit_id'] is None
        assert result['entries'] == []

    def test_inspect_tree_no_read_key(self):
        vault_path, _, ref_manager = self._setup_object_store_vault()
        ref_manager.write_ref('ref-pid-muw-aabbccddeeff', 'obj-cas-imm-a1b2c3d4e5f6')
        result = self.inspector.inspect_tree(self.tmp_dir)
        # Without read_key, _resolve_head returns None
        assert result['commit_id'] is None

    def test_inspect_commit_chain_no_head(self):
        self._setup_empty_vault()
        chain = self.inspector.inspect_commit_chain(self.tmp_dir)
        assert chain == []

    def test_full_inspect_with_real_objects(self):
        """Full round-trip using Vault__Sync.init() for proper vault setup."""
        from sg_send_cli.sync.Vault__Sync import Vault__Sync
        sync = Vault__Sync(crypto=self.crypto)
        result = sync.init(self.tmp_dir)
        vault_key = result['vault_key']
        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']

        tree_result = self.inspector.inspect_tree(self.tmp_dir, read_key=read_key)
        assert tree_result['commit_id'] is not None
        assert tree_result['file_count'] == 0  # empty vault

        chain = self.inspector.inspect_commit_chain(self.tmp_dir, read_key=read_key)
        assert len(chain) == 1
        assert chain[0]['commit_id'] == result['commit_id']
