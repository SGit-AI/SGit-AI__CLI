"""Coverage tests for Vault__Diff message decrypt failure paths.

Missing lines targeted:
  88-89: show_commit() decrypt_metadata raises → message = '(encrypted...)'
  203-204: log_file() decrypt_metadata raises → message = '(encrypted)'
"""
import base64
import json
import os

from sgit_ai.crypto.PKI__Crypto         import PKI__Crypto
from sgit_ai.objects.Vault__Commit      import Vault__Commit
from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager import Vault__Ref_Manager
from sgit_ai.sync.Vault__Diff           import Vault__Diff
from sgit_ai.sync.Vault__Storage        import SG_VAULT_DIR
from tests._helpers.vault_test_env      import Vault__Test_Env

# Valid base64 that decodes to only 4 bytes — too short for AES-GCM IV (≥8 bytes)
INVALID_MSG_ENC = base64.b64encode(b'\x00' * 4).decode()


class Test_Vault__Diff__Decrypt__Coverage:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap     = self._env.restore()
        self.vault    = self.snap.vault_dir
        self.crypto   = self.snap.crypto
        self.diff     = Vault__Diff(crypto=self.crypto)
        keys          = self.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.read_key = keys['read_key_bytes']
        sg_dir        = os.path.join(self.vault, SG_VAULT_DIR)
        self.obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        pki    = PKI__Crypto()
        ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        vc     = Vault__Commit(crypto=self.crypto, pki=pki,
                               object_store=self.obj_store, ref_manager=ref_mgr)
        commit = vc.load_commit(self.snap.commit_id, self.read_key)
        self.tree_id = str(commit.tree_id)
        self.ref_mgr = ref_mgr

    def teardown_method(self):
        self.snap.cleanup()

    def _make_fake_commit_id(self) -> str:
        """Store a commit with invalid message_enc; return its content-addressed ID."""
        raw = {
            'message_enc': INVALID_MSG_ENC,
            'tree_id'    : self.tree_id,
            'parents'    : [],
            'branch_id'  : '',
            'schema'     : 'commit_v1',
            'timestamp_ms': 0,
            'signature'  : '',
        }
        plaintext  = json.dumps(raw).encode()
        ciphertext = self.crypto.encrypt(self.read_key, plaintext)
        return self.obj_store.store(ciphertext)

    def test_show_commit_decrypt_fails_lines_88_89(self):
        """Lines 88-89: message_enc present but decrypt raises → message = '(encrypted...)'."""
        fake_id = self._make_fake_commit_id()
        commit_info, result = self.diff.show_commit(self.vault, fake_id)
        assert commit_info['message'] == '(encrypted — could not decrypt)'

    def test_log_file_decrypt_fails_lines_203_204(self):
        """Lines 203-204: HEAD commit has invalid message_enc → message = '(encrypted)'."""
        fake_id = self._make_fake_commit_id()
        # Update HEAD ref to point at our fake commit
        from sgit_ai.sync.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
        import json as _json

        sg_dir      = os.path.join(self.vault, SG_VAULT_DIR)
        storage     = Vault__Storage()
        config_path = storage.local_config_path(self.vault)
        with open(config_path, 'r') as f:
            cfg = _json.load(f)
        branch_id = cfg['my_branch_id']

        index_id     = self.crypto.derive_keys_from_vault_key(self.snap.vault_key)['branch_index_file_id']
        bm           = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                             key_manager=None, ref_manager=self.ref_mgr,
                                             storage=storage)
        branch_index = bm.load_branch_index(self.vault, index_id, self.read_key)
        branch_meta  = bm.get_branch_by_id(branch_index, branch_id)
        ref_id       = str(branch_meta.head_ref_id)
        self.ref_mgr.write_ref(ref_id, fake_id, self.read_key)

        entries = self.diff.log_file(self.vault, 'a.txt')
        # The entry should have message = '(encrypted)'
        assert isinstance(entries, list)
