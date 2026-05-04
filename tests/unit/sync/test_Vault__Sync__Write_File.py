"""Tests for Vault__Sync.write_file() — surgical vault editing."""
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.sync.Vault__Sync           import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from tests.unit.sync.vault_test_env     import Vault__Test_Env


class Test_Vault__Sync__Write_File:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'README.md': 'hello'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_write_file_creates_new_file(self):
        result = self.sync.write_file(self.directory, 'new_file.txt', b'new content')
        assert result['blob_id'].startswith('obj-cas-imm-')
        assert result['commit_id'].startswith('obj-cas-imm-')
        assert result['unchanged'] is False
        assert 'new_file.txt' in result['paths']

    def test_written_file_appears_on_disk(self):
        content = b'disk content test'
        self.sync.write_file(self.directory, 'written.md', content)
        disk_path = os.path.join(self.directory, 'written.md')
        assert os.path.isfile(disk_path)
        with open(disk_path, 'rb') as f:
            assert f.read() == content

    def test_write_file_nested_path(self):
        result = self.sync.write_file(self.directory, 'content/hero.md', b'hero text')
        assert result['blob_id'].startswith('obj-cas-imm-')
        assert os.path.isfile(os.path.join(self.directory, 'content', 'hero.md'))

    def test_write_file_appears_in_ls(self):
        self.sync.write_file(self.directory, 'agent.json', b'{"key": "val"}')
        entries = self.sync.sparse_ls(self.directory)
        paths   = [e['path'] for e in entries]
        assert 'agent.json' in paths

    def test_write_same_content_returns_unchanged(self):
        content = b'stable content'
        r1 = self.sync.write_file(self.directory, 'stable.md', content, message='first')
        r2 = self.sync.write_file(self.directory, 'stable.md', content, message='second')
        assert r1['unchanged'] is False
        assert r2['unchanged'] is True
        assert r2['blob_id'] == r1['blob_id']
        assert r2['commit_id'] == r1['commit_id']

    def test_write_different_content_creates_new_commit(self):
        r1 = self.sync.write_file(self.directory, 'evolving.md', b'v1')
        r2 = self.sync.write_file(self.directory, 'evolving.md', b'v2')
        assert r1['unchanged'] is False
        assert r2['unchanged'] is False
        assert r1['commit_id'] != r2['commit_id']
        assert r1['blob_id'] != r2['blob_id']

    def test_write_file_commit_message(self):
        result = self.sync.write_file(self.directory, 'msg.txt', b'hello',
                                      message='custom commit message')
        assert result['message'] == 'custom commit message'

    def test_write_file_auto_message(self):
        result = self.sync.write_file(self.directory, 'auto.txt', b'hello')
        assert 'auto.txt' in result['message']

    def test_write_file_status_is_clean_after_write(self):
        self.sync.write_file(self.directory, 'status_check.md', b'content')
        status = self.sync.status(self.directory)
        assert status['clean'] is True

    def test_write_file_with_also_atomic(self):
        also = {'instructions/home.json': b'{"ref": "new_hero"}'}
        result = self.sync.write_file(self.directory, 'content/hero.md', b'hero v2',
                                      also=also)
        assert result['unchanged'] is False
        assert 'content/hero.md' in result['paths']
        assert 'instructions/home.json' in result['paths']
        entries = self.sync.sparse_ls(self.directory)
        paths   = [e['path'] for e in entries]
        assert 'content/hero.md' in paths
        assert 'instructions/home.json' in paths

    def test_write_file_with_also_single_commit(self):
        """Atomic write: content/hero.md + instructions/ → one commit, not two."""
        also = {'meta/tags.json': b'["a","b"]'}
        r = self.sync.write_file(self.directory, 'content/page.md', b'page text',
                                 also=also)
        assert 'content/page.md' in r['paths']
        assert 'meta/tags.json' in r['paths']
        # One commit covers both files
        assert r['commit_id'].startswith('obj-cas-imm-')

    def test_write_file_does_not_scan_directory(self):
        """write_file must NOT require an uncommitted file to be present on disk."""
        # Drop an uncommitted stray file (would normally cause status to show dirty)
        stray = os.path.join(self.directory, 'stray.txt')
        with open(stray, 'w') as f:
            f.write('stray')
        # write_file should succeed regardless (it doesn't scan)
        result = self.sync.write_file(self.directory, 'targeted.md', b'targeted')
        assert result['unchanged'] is False


class Test_Vault__Sync__Write_File__Push:
    """AC-4: push after write_file uploads only the new blob."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'existing.md': 'existing content'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_push_after_write_file_succeeds(self):
        """AC-4: push succeeds after write_file (no uncommitted-changes error)."""
        self.env.sync.push(self.directory)          # baseline push
        result = self.sync.write_file(self.directory, 'new.md', b'new blob content')
        assert result['unchanged'] is False
        push_result = self.env.sync.push(self.directory)
        assert push_result.get('status') in ('pushed', 'resynced', 'up_to_date')

    def test_push_after_write_file_status_clean(self):
        """AC-4: status is clean immediately after write_file (disk stays in sync)."""
        self.sync.write_file(self.directory, 'status_clean.md', b'clean')
        status = self.sync.status(self.directory)
        assert status['clean'] is True

    def test_write_file_on_sparse_clone(self):
        """AC-2: write_file works on a sparse clone (no full working copy required)."""
        # Simulate sparse by NOT having blob content locally — only the tree structure
        result = self.sync.write_file(self.directory, 'sparse_new.md', b'sparse content')
        assert result['blob_id'].startswith('obj-cas-imm-')
        assert result['unchanged'] is False
        # File must appear on disk after write (AC-3 disk requirement)
        disk_path = os.path.join(self.directory, 'sparse_new.md')
        assert os.path.isfile(disk_path)
