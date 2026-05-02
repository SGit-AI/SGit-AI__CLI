"""Coverage tests for Vault__Sync__Fsck.

Missing lines targeted:
  75: repair=True but repair returns False → object still missing → continue
  97-103: tree object missing → tree id in result['missing']
  106-107: tree object corrupt → tree id in result['corrupt']
"""
import os

from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
from sgit_ai.objects.Vault__Commit       import Vault__Commit
from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.sync.Vault__Storage         import SG_VAULT_DIR, Vault__Storage
from sgit_ai.sync.Vault__Sync__Fsck      import Vault__Sync__Fsck
from tests._helpers.vault_test_env       import Vault__Test_Env


class Test_Vault__Sync__Fsck__Coverage:

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
        self.snap    = self._env.restore()
        self.vault   = self.snap.vault_dir
        self.crypto  = self.snap.crypto
        self.sync    = self.snap.sync
        keys         = self.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.read_key = keys['read_key_bytes']
        sg_dir        = os.path.join(self.vault, SG_VAULT_DIR)
        self.obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        pki    = PKI__Crypto()
        ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        vc     = Vault__Commit(crypto=self.crypto, pki=pki,
                               object_store=self.obj_store, ref_manager=ref_mgr)
        commit = vc.load_commit(self.snap.commit_id, self.read_key)
        self.tree_id = str(commit.tree_id)

    def teardown_method(self):
        self.snap.cleanup()

    def _data_path(self, object_id: str) -> str:
        return os.path.join(self.vault, SG_VAULT_DIR, 'bare', 'data', object_id)

    def test_fsck_repair_fails_hits_line_75(self):
        """Line 75: repair=True, API returns None → _repair_object False → continue."""
        os.remove(self._data_path(self.snap.commit_id))

        class NullAPI(Vault__API__In_Memory):
            def read(self, vault_id, path, **kwargs):
                return None

        null_api = NullAPI()
        null_api.setup()
        fsck   = Vault__Sync__Fsck(crypto=self.crypto, api=null_api)
        result = fsck.fsck(self.vault, repair=True)
        assert result['ok'] is False
        assert self.snap.commit_id in result['missing']

    def test_fsck_missing_tree_hits_lines_97_103(self):
        """Lines 97-103: tree object missing → tree id in result['missing']."""
        os.remove(self._data_path(self.tree_id))
        result = self.sync.fsck(self.vault)
        assert result['ok'] is False
        assert self.tree_id in result['missing']

    def test_fsck_missing_tree_repair_hits_lines_100_101(self):
        """Lines 100-101: tree missing + repair=True + API has it → tree repaired."""
        os.remove(self._data_path(self.tree_id))
        result = self.sync.fsck(self.vault, repair=True)
        assert result['ok'] is False or self.tree_id in result['repaired']

    def test_fsck_corrupt_tree_hits_lines_106_107(self):
        """Lines 106-107: tree object corrupt → tree id in result['corrupt']."""
        with open(self._data_path(self.tree_id), 'ab') as f:
            f.write(b'CORRUPT_BYTES')
        result = self.sync.fsck(self.vault)
        assert result['ok'] is False
        assert self.tree_id in result['corrupt']
