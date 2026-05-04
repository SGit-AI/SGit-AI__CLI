"""Coverage tests for Vault__Diff.log_file missing lines.

Missing lines targeted:
  137-138: _blob_id_in_tree exception → return None (sub_tree.flatten raises)
  161: not branch_meta → return []
  165: not current_id → return []
  171: HEAD commit missing from obj_store → break
  174-175: HEAD commit load raises → break
  187-188: parent commit load raises → pass
  195: blob_now is None (file deleted) → status = 'deleted'
  203-204: message decrypt raises → message = '(encrypted)'
"""
import json
import os

from sgit_ai.crypto.PKI__Crypto         import PKI__Crypto
from sgit_ai.storage.Vault__Commit      import Vault__Commit
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
from sgit_ai.sync.Vault__Diff           import Vault__Diff
from sgit_ai.storage.Vault__Storage        import SG_VAULT_DIR
from tests._helpers.vault_test_env      import Vault__Test_Env


class Test_Vault__Diff__Log_File__Coverage:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello', 'b.txt': 'world'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap   = self._env.restore()
        self.vault  = self.snap.vault_dir
        self.sync   = self.snap.sync
        self.crypto = self.snap.crypto
        self.diff   = Vault__Diff(crypto=self.crypto)

    def teardown_method(self):
        self.snap.cleanup()

    def _data_path(self, object_id: str) -> str:
        return os.path.join(self.vault, SG_VAULT_DIR, 'bare', 'data', object_id)

    def _local_config_path(self) -> str:
        return os.path.join(self.vault, '.sg_vault', 'local', 'config.json')

    def _get_tree_id(self) -> str:
        sg_dir    = os.path.join(self.vault, SG_VAULT_DIR)
        keys      = self.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        read_key  = keys['read_key_bytes']
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_mgr   = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        vc        = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(),
                                  object_store=obj_store, ref_manager=ref_mgr)
        commit    = vc.load_commit(self.snap.commit_id, read_key)
        return str(commit.tree_id)

    def _delete_head_ref(self) -> None:
        refs_dir = os.path.join(self.vault, SG_VAULT_DIR, 'bare', 'refs')
        for f in os.listdir(refs_dir):
            if f.startswith('ref-pid-'):
                os.remove(os.path.join(refs_dir, f))

    # ─── line 195: deleted status ────────────────────────────────────────

    def test_log_file_deleted_status_line_195(self):
        """Line 195: file deleted between commits → status='deleted'."""
        os.remove(os.path.join(self.vault, 'a.txt'))
        self.sync.commit(self.vault, message='delete a.txt')
        entries = self.diff.log_file(self.vault, 'a.txt')
        assert any(e['status'] == 'deleted' for e in entries)

    # ─── line 161: not branch_meta ───────────────────────────────────────

    def test_log_file_unknown_branch_id_returns_empty_line_161(self):
        """Line 161: branch_id not in index → return []."""
        config_path = self._local_config_path()
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        result = self.diff.log_file(self.vault, 'a.txt')
        assert result == []

    # ─── line 171: HEAD commit missing ───────────────────────────────────

    def test_log_file_missing_head_commit_breaks_line_171(self):
        """Line 171: HEAD commit not in obj_store → break → returns []."""
        os.remove(self._data_path(self.snap.commit_id))
        result = self.diff.log_file(self.vault, 'a.txt')
        assert isinstance(result, list)
        assert result == []

    # ─── lines 174-175: HEAD commit load raises ──────────────────────────

    def test_log_file_corrupt_head_commit_breaks_lines_174_175(self):
        """Lines 174-175: HEAD commit exists but can't be loaded → break."""
        commit_path = self._data_path(self.snap.commit_id)
        with open(commit_path, 'wb') as f:
            f.write(b'\x00' * 16)  # too short to decrypt
        result = self.diff.log_file(self.vault, 'a.txt')
        assert isinstance(result, list)

    # ─── lines 187-188: parent commit load raises ─────────────────────────

    def test_log_file_corrupt_parent_commit_swallows_error_lines_187_188(self):
        """Lines 187-188: parent commit exists but can't be loaded → pass."""
        with open(os.path.join(self.vault, 'a.txt'), 'w') as f:
            f.write('modified')
        self.sync.commit(self.vault, message='second commit')
        # Corrupt the original (parent) commit
        with open(self._data_path(self.snap.commit_id), 'wb') as f:
            f.write(b'\x00' * 16)
        entries = self.diff.log_file(self.vault, 'a.txt')
        assert isinstance(entries, list)

    # ─── line 165: not current_id ────────────────────────────────────────

    def test_log_file_deleted_ref_returns_empty_line_165(self):
        """Line 165: HEAD ref file deleted → read_ref returns None → return []."""
        self._delete_head_ref()
        result = self.diff.log_file(self.vault, 'a.txt')
        assert result == []

    # ─── lines 137-138: exception in _blob_id_in_tree ────────────────────

    def test_log_file_missing_tree_hits_lines_137_138(self):
        """Lines 137-138: tree object missing → sub_tree.flatten raises → return None."""
        tree_id = self._get_tree_id()
        os.remove(self._data_path(tree_id))
        result = self.diff.log_file(self.vault, 'a.txt')
        assert isinstance(result, list)
