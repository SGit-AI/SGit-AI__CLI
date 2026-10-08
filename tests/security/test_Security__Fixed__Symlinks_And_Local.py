"""Fixed in 0.21.0 — symlinks in the working copy, key-file permissions, `sgit update`.

Threat model: TM-F04 (symlinks), TM-F05 (key-bearing files), TM-F06 (update).
"""
import os
import stat
import subprocess
import sys

import pytest

from sgit_ai.cli.CLI__Main                         import CLI__Main
from sgit_ai.core.actions.revert.Vault__Revert      import Vault__Revert
from sgit_ai.storage.Vault__Path_Guard             import Vault__Path_Guard, Vault__Unsafe_Path_Error
from sgit_ai.storage.Vault__Storage                import Vault__Storage
from tests._helpers.vault_test_env                 import Vault__Test_Env


class Test_Fixed__Symlinks:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'hello', 'docs/a.md': 'doc a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s       = self._env.restore()
        self.vault   = self.s.vault_dir
        self.outside = os.path.join(self.s.tmp_dir, 'outside')
        os.makedirs(self.outside)
        self.secret  = os.path.join(self.outside, 'id_rsa')
        with open(self.secret, 'w') as f:
            f.write('-----BEGIN OPENSSH PRIVATE KEY-----')

    def teardown_method(self):
        self.s.cleanup()

    def test_a_link_out_of_the_tree_is_never_committed(self):
        """Before: the scan followed the link and committed (then pushed) the
        target's bytes — a link to ~/.ssh/id_rsa leaked the key to every reader."""
        os.symlink(self.secret, os.path.join(self.vault, 'notes.txt'))
        os.symlink(self.outside, os.path.join(self.vault, 'linked_dir'))
        status = self.s.sync.status(self.vault)
        assert 'notes.txt' not in status['added']
        assert not any(p.startswith('linked_dir') for p in status['added'])

    def test_a_link_inside_the_tree_is_still_followed(self):
        os.symlink(os.path.join(self.vault, 'readme.md'), os.path.join(self.vault, 'readme-link.md'))
        assert 'readme-link.md' in self.s.sync.status(self.vault)['added']

    def test_a_write_through_a_symlinked_folder_is_refused(self):
        """A checked-in folder replaced by a link to elsewhere must not carry vault
        writes out of the tree (revert, checkout, pull all write through safe_join)."""
        import shutil
        shutil.rmtree(os.path.join(self.vault, 'docs'))
        os.symlink(self.outside, os.path.join(self.vault, 'docs'))
        guard = Vault__Path_Guard()
        with pytest.raises(Vault__Unsafe_Path_Error):
            guard.safe_join(self.vault, 'docs/a.md')
        assert guard.is_writable(self.vault, 'readme.md')

        Vault__Revert(crypto=self.s.crypto).revert_to_head(self.vault)
        assert not os.path.exists(os.path.join(self.outside, 'a.md'))

    def test_secure_unlink_of_a_link_never_zeroes_its_target(self):
        link = os.path.join(self.vault, 'secret-link')
        os.symlink(self.secret, link)
        Vault__Storage().secure_unlink(link)
        assert not os.path.lexists(link)
        with open(self.secret) as f:
            assert f.read().startswith('-----BEGIN')


class Test_Fixed__Local_Execution:

    def test_sgit_update_runs_pip_isolated(self, monkeypatch, capsys):
        """`python -m pip` puts the current directory first on sys.path, so a pip.py
        (or pip/ package) in the folder where `sgit update` runs was imported and
        executed. -I (isolated mode) leaves the cwd off sys.path."""
        seen = []
        monkeypatch.setattr(subprocess, 'run', lambda cmd, **kw: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0))
        CLI__Main().cmd_update(None)
        assert seen and seen[0][:4] == [sys.executable, '-I', '-m', 'pip']

    def test_vault_writes_key_bearing_files_owner_only(self, tmp_path):
        old = os.umask(0o022)
        try:
            path = str(tmp_path / 'vault_key')
            Vault__Storage().write_private(path, 'passphrase:vaultid')
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        finally:
            os.umask(old)
