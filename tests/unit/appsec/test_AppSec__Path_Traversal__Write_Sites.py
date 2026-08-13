"""Exploit-path regression tests for every working-copy write site that consumes
vault-derived paths.

Threat model: a hostile vault author controls tree entry names, so any path that
reaches the filesystem via decrypted vault data is attacker-influenced. Each test
below drives a real write site with a traversal payload and asserts that nothing
lands outside the working directory.

Companion to test_AppSec__Path_Traversal.py (which covers Vault__Sub_Tree.checkout)
and tests/unit/storage/test_Vault__Path_Guard.py (which unit-tests the guard).
"""
import os
import shutil
import tempfile
import pytest

from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Path_Guard       import Vault__Unsafe_Path_Error
from sgit_ai.core.Vault__Sync__Base          import Vault__Sync__Base
from sgit_ai.core.actions.merge.Vault__Merge import Vault__Merge


class _Base:

    def setup_method(self):
        self.tmp      = tempfile.mkdtemp()
        self.work     = os.path.join(self.tmp, 'work')
        os.makedirs(self.work, exist_ok=True)
        self.sg       = os.path.join(self.work, '.sg_vault')
        os.makedirs(os.path.join(self.sg, 'bare', 'data'), exist_ok=True)
        self.crypto   = Vault__Crypto()
        self.store    = Vault__Object_Store(vault_path=self.sg, crypto=self.crypto)
        self.rk       = self.crypto.derive_read_key('pw', 'abcd1234')
        # the file an attacker would try to clobber, one level above the working copy
        self.outside  = os.path.join(self.tmp, 'VICTIM.txt')
        with open(self.outside, 'w') as f:
            f.write('ORIGINAL')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _blob(self, data: bytes = b'PWNED') -> str:
        return self.store.store(self.crypto.encrypt(self.rk, data))

    def _victim_untouched(self):
        with open(self.outside) as f:
            assert f.read() == 'ORIGINAL', 'traversal payload escaped the working directory'


class Test_AppSec__Checkout_Flat_Map(_Base):
    """Vault__Sync__Base._checkout_flat_map — used by pull fast-forward and merge."""

    def test_traversal_path_does_not_escape(self):
        sync     = Vault__Sync__Base(crypto=self.crypto)
        flat_map = {'../VICTIM.txt': {'blob_id': self._blob()}}
        sync._checkout_flat_map(self.work, flat_map, self.store, self.rk)
        self._victim_untouched()

    def test_absolute_path_does_not_escape(self):
        sync     = Vault__Sync__Base(crypto=self.crypto)
        flat_map = {self.outside: {'blob_id': self._blob()}}
        sync._checkout_flat_map(self.work, flat_map, self.store, self.rk)
        self._victim_untouched()

    def test_benign_path_still_written(self):
        sync     = Vault__Sync__Base(crypto=self.crypto)
        flat_map = {'docs/ok.txt': {'blob_id': self._blob(b'GOOD')}}
        sync._checkout_flat_map(self.work, flat_map, self.store, self.rk)
        with open(os.path.join(self.work, 'docs', 'ok.txt'), 'rb') as f:
            assert f.read() == b'GOOD'


class Test_AppSec__Remove_Deleted_Flat(_Base):
    """Vault__Sync__Base._remove_deleted_flat — a hostile path must not DELETE outside."""

    def test_traversal_path_is_not_deleted(self):
        sync = Vault__Sync__Base(crypto=self.crypto)
        sync._remove_deleted_flat(self.work, {'../VICTIM.txt': {}}, {})
        assert os.path.isfile(self.outside), 'traversal payload deleted a file outside the vault'
        self._victim_untouched()

    def test_benign_deletion_still_happens(self):
        sync   = Vault__Sync__Base(crypto=self.crypto)
        target = os.path.join(self.work, 'gone.txt')
        with open(target, 'w') as f:
            f.write('x')
        sync._remove_deleted_flat(self.work, {'gone.txt': {}}, {})
        assert not os.path.exists(target)


class Test_AppSec__Merge_Conflict_Writes(_Base):
    """Vault__Merge.write_conflict_files — .conflict files derive from vault paths."""

    def test_traversal_conflict_path_does_not_escape(self):
        merge      = Vault__Merge(crypto=self.crypto)
        theirs_map = {'../VICTIM.txt': {'blob_id': self._blob()}}
        merge.write_conflict_files(self.work, ['../VICTIM.txt'], theirs_map, self.store, self.rk)
        self._victim_untouched()
        assert not os.path.exists(self.outside + '.conflict')

    def test_benign_conflict_still_written(self):
        merge      = Vault__Merge(crypto=self.crypto)
        theirs_map = {'a.txt': {'blob_id': self._blob(b'THEIRS')}}
        written    = merge.write_conflict_files(self.work, ['a.txt'], theirs_map, self.store, self.rk)
        assert written == ['a.txt.conflict']
        assert os.path.isfile(os.path.join(self.work, 'a.txt.conflict'))


class Test_AppSec__Guard_Coverage_Invariant:
    """Regression net: every module that writes a vault-derived path to the working
    copy must route through Vault__Path_Guard. Fails if a new unguarded write is added
    or an existing guard is removed."""

    GUARDED_MODULES = [
        'sgit_ai/storage/Vault__Sub_Tree.py',                        # checkout
        'sgit_ai/core/Vault__Sync__Base.py',                         # flat-map checkout + delete
        'sgit_ai/core/actions/sparse/Vault__Sync__Sparse.py',        # sparse fetch
        'sgit_ai/core/actions/merge/Vault__Merge.py',                # conflict writes
        'sgit_ai/core/actions/merge/Vault__Merge__Resolve.py',       # resolve --theirs
        'sgit_ai/core/actions/revert/Vault__Revert.py',              # revert restore
        'sgit_ai/core/actions/backup/Vault__Restore.py',             # restore working copy
    ]

    def test_all_known_write_sites_reference_the_guard(self):
        repo    = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        missing = []
        for rel in self.GUARDED_MODULES:
            with open(os.path.join(repo, rel), encoding='utf-8') as fh:
                src = fh.read()
            if 'Vault__Path_Guard' not in src or 'safe_join' not in src:
                missing.append(rel)
        assert missing == [], (
            'these modules write vault-derived paths but no longer use Vault__Path_Guard:\n'
            + '\n'.join(missing))
