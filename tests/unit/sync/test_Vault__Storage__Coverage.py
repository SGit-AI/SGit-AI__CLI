"""Coverage tests for Vault__Storage missing lines.

Missing lines targeted:
  85: tracking_path()
  109-110: chmod_local_file() OSError → pass
  138-139: secure_rmtree() inner os.rmdir fails → pass
  142-143: secure_rmtree() final os.rmdir fails → pass
"""
import os
import stat
import tempfile
import shutil
import unittest.mock

from sgit_ai.sync.Vault__Storage import Vault__Storage


class Test_Vault__Storage__Coverage:

    def setup_method(self):
        self.storage = Vault__Storage()
        self.tmp     = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tracking_path_line_85(self):
        """Line 85: tracking_path() returns correct path."""
        result = self.storage.tracking_path(self.tmp)
        assert result.endswith('tracking.json')
        assert '.sg_vault' in result

    def test_chmod_local_file_oserror_passes_lines_109_110(self):
        """Lines 109-110: os.chmod raises → except OSError: pass."""
        path = os.path.join(self.tmp, 'file.txt')
        with open(path, 'w') as f:
            f.write('x')
        with unittest.mock.patch('os.chmod', side_effect=OSError('no perm')):
            self.storage.chmod_local_file(path)  # should not raise

    def test_secure_rmtree_inner_rmdir_fails_lines_138_139(self):
        """Lines 138-139: os.rmdir raises for a subdir → except OSError: pass."""
        sub = os.path.join(self.tmp, 'subdir')
        os.makedirs(sub)
        with open(os.path.join(sub, 'f.txt'), 'w') as f:
            f.write('x')

        call_count = [0]
        real_rmdir = os.rmdir

        def patched_rmdir(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError('busy')
            real_rmdir(path)

        with unittest.mock.patch('os.rmdir', side_effect=patched_rmdir):
            count = self.storage.secure_rmtree(self.tmp)
        assert isinstance(count, int)

    def test_secure_rmtree_final_rmdir_fails_lines_142_143(self):
        """Lines 142-143: final os.rmdir on root directory fails → except OSError: pass."""
        with open(os.path.join(self.tmp, 'f.txt'), 'w') as f:
            f.write('x')

        real_rmdir = os.rmdir

        def patched_rmdir(path):
            if os.path.basename(path) == os.path.basename(self.tmp):
                raise OSError('busy')
            real_rmdir(path)

        with unittest.mock.patch('os.rmdir', side_effect=patched_rmdir):
            count = self.storage.secure_rmtree(self.tmp)
        assert isinstance(count, int)
