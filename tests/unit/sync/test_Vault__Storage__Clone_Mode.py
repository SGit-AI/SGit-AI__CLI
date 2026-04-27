"""Tests for Vault__Storage.clone_mode_path()."""
import os
import tempfile
import shutil
from sgit_ai.sync.Vault__Storage import Vault__Storage


class Test_Vault__Storage__Clone_Mode:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_clone_mode_path_returns_string(self):
        path = self.storage.clone_mode_path(self.tmp_dir)
        assert isinstance(path, str)
        assert path.endswith('clone_mode.json')

    def test_clone_mode_path_under_local_dir(self):
        path = self.storage.clone_mode_path(self.tmp_dir)
        local_dir = self.storage.local_dir(self.tmp_dir)
        assert path.startswith(local_dir)

    def test_clone_mode_path_follows_local_dir_pattern(self):
        # push_state_path and clone_mode_path share the same parent
        push_state  = self.storage.push_state_path(self.tmp_dir)
        clone_mode  = self.storage.clone_mode_path(self.tmp_dir)
        assert os.path.dirname(push_state) == os.path.dirname(clone_mode)
