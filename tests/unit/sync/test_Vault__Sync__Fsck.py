"""Tests for vault fsck (integrity check and repair).

Verifies that fsck detects missing and corrupt objects, and that
--repair mode can re-download them from the remote.
"""
import os
import tempfile
import shutil

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.unit.sync.vault_test_env    import Vault__Test_Env


class Test_Vault__Sync__Fsck:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'file1.txt': 'hello world',
                                           'file2.txt': 'second file'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_fsck_healthy_vault(self):
        """fsck on a clean vault should report ok."""
        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok']       is True
        assert result['missing']  == []
        assert result['corrupt']  == []
        assert result['errors']   == []

    def test_fsck_not_a_vault(self):
        """fsck on a non-vault directory should report error."""
        not_vault = os.path.join(self.env.tmp_dir, 'not-a-vault')
        os.makedirs(not_vault)
        result = self.sync.fsck(not_vault)
        assert result['ok'] is False
        assert any('Not a vault' in e for e in result['errors'])

    def test_fsck_detects_missing_object(self):
        """fsck should detect when a blob object is missing from the store."""
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')

        # Delete a blob object (not a commit or tree — pick the first non-essential one)
        all_objects = sorted(os.listdir(data_dir))
        assert len(all_objects) > 0

        # Remove one object
        victim = all_objects[0]
        os.remove(os.path.join(data_dir, victim))

        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert victim in result['missing']

    def test_fsck_detects_corrupt_object(self):
        """fsck should detect objects whose hash doesn't match their ID."""
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')

        all_objects = sorted(os.listdir(data_dir))
        victim = all_objects[0]
        victim_path = os.path.join(data_dir, victim)

        # Corrupt the file by appending junk
        with open(victim_path, 'ab') as f:
            f.write(b'CORRUPTED')

        result = self.sync.fsck(self.env.vault_dir)
        assert result['ok'] is False
        assert victim in result['corrupt']

    def test_fsck_repair_downloads_missing_object(self):
        """fsck --repair should re-download missing objects from remote."""
        data_dir  = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')

        all_objects = sorted(os.listdir(data_dir))
        victim = all_objects[0]
        os.remove(os.path.join(data_dir, victim))

        result = self.sync.fsck(self.env.vault_dir, repair=True)
        assert victim in result['repaired']
        assert os.path.isfile(os.path.join(data_dir, victim)), 'Object should be restored'
        # After repair, vault should be ok (unless there are other issues)
        assert result['ok'] is True or len(result['missing']) == 0

    def test_fsck_empty_vault(self):
        """fsck on an empty vault (no commits) should report ok."""
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync      = Vault__Sync(crypto=crypto, api=api)
        empty_dir = os.path.join(self.env.tmp_dir, 'empty-vault')
        sync.init(empty_dir)
        result = sync.fsck(empty_dir)
        assert result['ok'] is True
