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


class Test_Vault__Sync__Fsck:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_and_push(self, name='vault'):
        directory = os.path.join(self.tmp_dir, name)
        self.sync.init(directory)
        with open(os.path.join(directory, 'file1.txt'), 'w') as f:
            f.write('hello world')
        with open(os.path.join(directory, 'file2.txt'), 'w') as f:
            f.write('second file')
        self.sync.commit(directory, message='initial commit')
        self.sync.push(directory)
        return directory

    def test_fsck_healthy_vault(self):
        """fsck on a clean vault should report ok."""
        directory = self._init_and_push()
        result = self.sync.fsck(directory)
        assert result['ok']       is True
        assert result['missing']  == []
        assert result['corrupt']  == []
        assert result['errors']   == []

    def test_fsck_not_a_vault(self):
        """fsck on a non-vault directory should report error."""
        not_vault = os.path.join(self.tmp_dir, 'not-a-vault')
        os.makedirs(not_vault)
        result = self.sync.fsck(not_vault)
        assert result['ok'] is False
        assert any('Not a vault' in e for e in result['errors'])

    def test_fsck_detects_missing_object(self):
        """fsck should detect when a blob object is missing from the store."""
        directory = self._init_and_push()
        data_dir  = os.path.join(directory, '.sg_vault', 'bare', 'data')

        # Delete a blob object (not a commit or tree — pick the first non-essential one)
        all_objects = sorted(os.listdir(data_dir))
        assert len(all_objects) > 0

        # Remove one object
        victim = all_objects[0]
        os.remove(os.path.join(data_dir, victim))

        result = self.sync.fsck(directory)
        assert result['ok'] is False
        assert victim in result['missing']

    def test_fsck_detects_corrupt_object(self):
        """fsck should detect objects whose hash doesn't match their ID."""
        directory = self._init_and_push()
        data_dir  = os.path.join(directory, '.sg_vault', 'bare', 'data')

        all_objects = sorted(os.listdir(data_dir))
        victim = all_objects[0]
        victim_path = os.path.join(data_dir, victim)

        # Corrupt the file by appending junk
        with open(victim_path, 'ab') as f:
            f.write(b'CORRUPTED')

        result = self.sync.fsck(directory)
        assert result['ok'] is False
        assert victim in result['corrupt']

    def test_fsck_repair_downloads_missing_object(self):
        """fsck --repair should re-download missing objects from remote."""
        directory = self._init_and_push()
        data_dir  = os.path.join(directory, '.sg_vault', 'bare', 'data')

        all_objects = sorted(os.listdir(data_dir))
        victim = all_objects[0]
        os.remove(os.path.join(data_dir, victim))

        result = self.sync.fsck(directory, repair=True)
        assert victim in result['repaired']
        assert os.path.isfile(os.path.join(data_dir, victim)), 'Object should be restored'
        # After repair, vault should be ok (unless there are other issues)
        assert result['ok'] is True or len(result['missing']) == 0

    def test_fsck_empty_vault(self):
        """fsck on an empty vault (no commits) should report ok."""
        directory = os.path.join(self.tmp_dir, 'empty')
        self.sync.init(directory)
        result = self.sync.fsck(directory)
        assert result['ok'] is True
