"""Coverage tests for Vault__Commit — bad branch_id handler (lines 63-75),
other-exception re-raise (lines 76-78), and no-signature shortcut (line 92).
"""
import json
import os

import pytest

from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
from sgit_ai.storage.Vault__Commit         import Vault__Commit
from sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager    import Vault__Ref_Manager
from sgit_ai.schemas.Schema__Object_Commit import Schema__Object_Commit
from sgit_ai.storage.Vault__Storage           import SG_VAULT_DIR
from tests._helpers.vault_test_env         import Vault__Test_Env


def _make_vault_commit(snap):
    sg_dir = os.path.join(snap.vault_dir, SG_VAULT_DIR)
    pki         = PKI__Crypto()
    obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=snap.crypto)
    ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=snap.crypto)
    return Vault__Commit(crypto=snap.crypto, pki=pki,
                         object_store=obj_store, ref_manager=ref_manager), obj_store


class Test_Vault__Commit__Coverage:

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
        self.snap        = self._env.restore()
        self.crypto      = self.snap.crypto
        keys             = self.crypto.derive_keys_from_vault_key(self.snap.vault_key)
        self.read_key    = keys['read_key_bytes']
        self.vault_commit, self.obj_store = _make_vault_commit(self.snap)

    def teardown_method(self):
        self.snap.cleanup()

    def _store_encrypted_raw(self, fake_id: str, raw: dict):
        plaintext  = json.dumps(raw).encode()
        ciphertext = self.crypto.encrypt(self.read_key, plaintext)
        self.obj_store.store_raw(fake_id, ciphertext)

    def test_load_commit_bad_branch_id_is_stripped(self, capsys):
        """Lines 63-75: branch_id failing Safe_Str__Branch_Id pattern is stripped and warns."""
        fake_id = 'a' * 64
        self._store_encrypted_raw(fake_id, {
            'branch_id':   'INVALID_BRANCH_ID_NOT_MATCHING_PATTERN',
            'tree_id':     '',
            'parents':     [],
            'timestamp_ms': 0,
            'message_enc': '',
            'signature':   '',
        })
        result = self.vault_commit.load_commit(fake_id, self.read_key)
        assert str(result.branch_id) == ''
        err = capsys.readouterr().err
        assert 'warning' in err.lower() or 'unrecognised branch_id' in err

    def test_load_commit_bad_branch_id_dedup_warning(self, capsys):
        """Lines 63-75: second load of same commit_id does NOT print duplicate warning."""
        fake_id = 'c' * 64
        self._store_encrypted_raw(fake_id, {
            'branch_id':   'INVALID_BRANCH_DEDUP',
            'tree_id':     '',
            'parents':     [],
            'timestamp_ms': 0,
        })
        self.vault_commit.load_commit(fake_id, self.read_key)
        capsys.readouterr()   # discard first warning
        self.vault_commit.load_commit(fake_id, self.read_key)   # second call: no new warning
        err = capsys.readouterr().err
        assert 'warning' not in err.lower()

    def test_load_commit_other_parse_error_reraises(self):
        """Lines 76-78: non-branch_id validation error re-raises ValueError with context."""
        fake_id = 'b' * 64
        self._store_encrypted_raw(fake_id, {
            'branch_id':   '',
            'tree_id':     '',
            'parents':     [],
            'timestamp_ms': 'not-a-number',
        })
        with pytest.raises(ValueError) as exc_info:
            self.vault_commit.load_commit(fake_id, self.read_key)
        assert fake_id in str(exc_info.value)

    def test_verify_commit_signature_returns_false_when_no_signature(self):
        """Line 92: verify returns False when commit.signature is empty/None."""
        commit     = Schema__Object_Commit()   # default: signature = None
        public_key = None
        result     = self.vault_commit.verify_commit_signature(commit, public_key)
        assert result is False
