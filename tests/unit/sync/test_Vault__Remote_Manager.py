import os
import tempfile
import shutil
import pytest

from sg_send_cli.sync.Vault__Remote_Manager import Vault__Remote_Manager
from sg_send_cli.sync.Vault__Storage        import Vault__Storage


class Test_Vault__Remote_Manager:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = Vault__Storage()
        self.manager = Vault__Remote_Manager(storage=self.storage)
        os.makedirs(self.storage.local_dir(self.tmp_dir), exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_add_remote(self):
        result = self.manager.add_remote(self.tmp_dir, 'origin',
                                          'https://send.sgraph.ai', 'a1b2c3d4')
        assert str(result.name)     == 'origin'
        assert str(result.url)      == 'https://send.sgraph.ai'
        assert str(result.vault_id) == 'a1b2c3d4'

    def test_list_remotes_empty(self):
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert remotes == []

    def test_list_remotes_after_add(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://backup.example.com', 'cc33dd44')
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert len(remotes) == 2
        names = [r['name'] for r in remotes]
        assert 'origin' in names
        assert 'backup' in names

    def test_remove_remote(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        assert self.manager.remove_remote(self.tmp_dir, 'origin')
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert remotes == []

    def test_remove_nonexistent_returns_false(self):
        assert not self.manager.remove_remote(self.tmp_dir, 'nonexistent')

    def test_get_remote(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        remote = self.manager.get_remote(self.tmp_dir, 'origin')
        assert remote is not None
        assert str(remote.name) == 'origin'

    def test_get_remote_nonexistent(self):
        remote = self.manager.get_remote(self.tmp_dir, 'missing')
        assert remote is None

    def test_add_duplicate_raises(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        with pytest.raises(RuntimeError, match='Remote already exists'):
            self.manager.add_remote(self.tmp_dir, 'origin', 'https://other.example.com', 'cc33dd44')

    def test_remotes_persist_to_disk(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')

        manager2 = Vault__Remote_Manager(storage=self.storage)
        remotes  = manager2.list_remotes(self.tmp_dir)
        assert len(remotes) == 1
        assert remotes[0]['name'] == 'origin'
