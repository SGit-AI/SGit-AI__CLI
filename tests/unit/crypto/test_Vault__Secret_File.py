"""Tests for Vault__Secret_File — the one way a secret reaches disk: a fresh 0600 temp
file in the same folder, fsync, rename over the target; the temp file never survives a
failure. The bytes written in these tests are placeholders, never key material."""
import os
import shutil
import stat
import sys
import tempfile

import pytest

from sgit_ai.crypto.Vault__Secret_File import Vault__Secret_File


class Test_Vault__Secret_File:

    def setup_method(self):
        self.tmp  = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'secret')
        self.sf   = Vault__Secret_File()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mode(self, path) -> int:
        return stat.S_IMODE(os.stat(path).st_mode)

    def _leftovers(self) -> list:
        return [n for n in os.listdir(self.tmp) if n.startswith('.tmp-secret-')]

    def test_writes_str_as_utf8_and_bytes_as_is(self):
        self.sf.write(self.path, 'placeholder-text')
        with open(self.path, 'rb') as f:
            assert f.read() == b'placeholder-text'
        self.sf.write(self.path, b'\x00\x01placeholder')
        with open(self.path, 'rb') as f:
            assert f.read() == b'\x00\x01placeholder'
        assert self._leftovers() == []

    @pytest.mark.skipif(sys.platform == 'win32', reason='mode bits are not enforced on Windows')
    def test_file_is_owner_only_whatever_the_umask(self):
        old = os.umask(0)
        try:
            self.sf.write(self.path, 'x')
        finally:
            os.umask(old)
        assert self._mode(self.path) == 0o600

    @pytest.mark.skipif(sys.platform == 'win32', reason='mode bits are not enforced on Windows')
    def test_an_existing_world_readable_file_does_not_keep_its_mode(self):
        with open(self.path, 'w') as f:
            f.write('old')
        os.chmod(self.path, 0o644)
        self.sf.write(self.path, 'new')
        assert self._mode(self.path) == 0o600
        with open(self.path) as f:
            assert f.read() == 'new'

    def test_a_symlink_at_the_path_is_replaced_not_written_through(self):
        target = os.path.join(self.tmp, 'elsewhere')
        with open(target, 'w') as f:
            f.write('untouched')
        os.symlink(target, self.path)
        self.sf.write(self.path, 'secret-placeholder')
        assert not os.path.islink(self.path)
        with open(target) as f:
            assert f.read() == 'untouched'
        with open(self.path) as f:
            assert f.read() == 'secret-placeholder'

    def test_missing_parent_folders_are_created(self):
        deep = os.path.join(self.tmp, 'a', 'b', 'secret')
        self.sf.write(deep, 'x')
        assert os.path.isfile(deep)

    def test_a_relative_path_without_a_folder_writes_in_the_cwd(self, monkeypatch):
        monkeypatch.chdir(self.tmp)
        self.sf.write('bare-name', 'x')
        assert os.path.isfile(os.path.join(self.tmp, 'bare-name'))

    def test_failure_to_rename_removes_the_temp_file_and_raises(self):
        """When the target cannot be replaced (here: it is a non-empty directory), the
        error propagates and the 0600 temp file is unlinked, so no half-written secret
        lingers in the folder."""
        os.makedirs(os.path.join(self.path, 'child'))
        with pytest.raises(OSError):
            self.sf.write(self.path, 'x')
        assert self._leftovers() == []
        assert os.path.isdir(self.path)
