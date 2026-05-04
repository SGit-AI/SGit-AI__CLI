"""Coverage tests for Vault__Sync__Admin delegation shell.

Each method in Vault__Sync__Admin is a one-liner that constructs a
sub-class and delegates to it.  These tests exercise every delegation
so the file reaches 100% coverage.
"""
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.core.actions.admin.Vault__Sync__Admin   import Vault__Sync__Admin
from tests._helpers.vault_test_env     import Vault__Test_Env


def _make_admin():
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    return Vault__Sync__Admin(crypto=crypto, api=api), crypto, api


class Test_Vault__Sync__Admin__Factory_Methods:
    """_branch_ops, _gc_ops, _lifecycle all return the correct sub-class."""

    def test_branch_ops_returns_branch_ops_instance(self):
        from sgit_ai.core.actions.branch.Vault__Sync__Branch_Ops import Vault__Sync__Branch_Ops
        admin, *_ = _make_admin()
        assert isinstance(admin._branch_ops(), Vault__Sync__Branch_Ops)

    def test_gc_ops_returns_gc_ops_instance(self):
        from sgit_ai.core.actions.gc.Vault__Sync__GC_Ops import Vault__Sync__GC_Ops
        admin, *_ = _make_admin()
        assert isinstance(admin._gc_ops(), Vault__Sync__GC_Ops)

    def test_lifecycle_returns_lifecycle_instance(self):
        from sgit_ai.core.actions.lifecycle.Vault__Sync__Lifecycle import Vault__Sync__Lifecycle
        admin, *_ = _make_admin()
        assert isinstance(admin._lifecycle(), Vault__Sync__Lifecycle)


class Test_Vault__Sync__Admin__Delegation:
    """Each delegation method is called on a real vault so all 43 lines are hit."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        env        = self._env.restore()
        self._snap = env
        crypto     = env.crypto
        admin      = Vault__Sync__Admin(crypto=crypto, api=env.api)
        self.admin    = admin
        self.vault_dir = env.vault_dir

    def teardown_method(self):
        self._snap.cleanup()

    # --- Branch_Ops delegation ---

    def test_branches(self):
        result = self.admin.branches(self.vault_dir)
        assert 'branches' in result

    def test_merge_abort__no_merge_in_progress(self):
        import pytest
        with pytest.raises(RuntimeError, match='No merge in progress'):
            self.admin.merge_abort(self.vault_dir)

    def test_remote_list(self):
        result = self.admin.remote_list(self.vault_dir)
        assert isinstance(result, dict)

    def test_remote_add_and_remove(self):
        add_result = self.admin.remote_add(
            self.vault_dir, 'origin2', 'https://example.com', 'vaultid001'
        )
        assert isinstance(add_result, dict)
        rm_result = self.admin.remote_remove(self.vault_dir, 'origin2')
        assert isinstance(rm_result, dict)

    # --- GC_Ops delegation ---

    def test_gc_drain(self):
        result = self.admin.gc_drain(self.vault_dir)
        assert isinstance(result, dict)

    def test_create_change_pack(self):
        result = self.admin.create_change_pack(self.vault_dir, {'a.txt': b'content'})
        assert isinstance(result, dict)

    # --- Lifecycle delegation ---

    def test_rekey_check(self):
        result = self.admin.rekey_check(self.vault_dir)
        assert isinstance(result, dict)

    def test_probe_token__invalid_format_raises(self):
        import pytest
        with pytest.raises(RuntimeError, match='probe only accepts simple tokens'):
            self.admin.probe_token('not-a-valid-token')

    def test_probe_token__valid_format_not_found_raises(self):
        import pytest
        with pytest.raises(RuntimeError, match='Token not found'):
            self.admin.probe_token('apple-orange-9999')

    def test_rekey_init_and_wipe(self):
        init_result = self.admin.rekey_init(self.vault_dir)
        assert isinstance(init_result, dict)
        wipe_result = self.admin.rekey_wipe(self.vault_dir)
        assert isinstance(wipe_result, dict)

    def test_rekey_init_and_commit(self):
        """Explicitly exercises Admin.rekey_commit delegation (line 59)."""
        init_result = self.admin.rekey_init(self.vault_dir)
        assert isinstance(init_result, dict)
        commit_result = self.admin.rekey_commit(self.vault_dir)
        assert isinstance(commit_result, dict)

    def test_rekey(self):
        result = self.admin.rekey(self.vault_dir)
        assert isinstance(result, dict)

    def test_uninit(self):
        """uninit removes .sg_vault — must run last or on a throw-away dir."""
        tmp = tempfile.mkdtemp()
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            from sgit_ai.sync.Vault__Sync import Vault__Sync
            sync = Vault__Sync(crypto=crypto, api=api)
            sync.init(tmp)
            admin = Vault__Sync__Admin(crypto=crypto, api=api)
            result = admin.uninit(tmp)
            assert isinstance(result, dict)
            assert not os.path.isdir(os.path.join(tmp, '.sg_vault'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_on_remote(self):
        result = self.admin.delete_on_remote(self.vault_dir)
        assert isinstance(result, dict)

    def test_restore_from_backup__missing_zip_raises(self):
        import pytest
        with pytest.raises(RuntimeError, match='Backup zip not found'):
            self.admin.restore_from_backup('/nonexistent/path.zip', self.vault_dir)
