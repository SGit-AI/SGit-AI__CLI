"""Integration tests for sgit vault move against a real in-memory server.

Requires the Python-3.12 venv with sgraph-ai-app-send:
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.core.Vault__Sync     import Vault__Sync
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


class Test_Vault__Sync__Move__Integration:

    @pytest.fixture(autouse=True)
    def _dirs(self, temp_dir):
        self.vault_dir = os.path.join(temp_dir, 'vault')
        self.clone_dir = os.path.join(temp_dir, 'clone')

    # ------------------------------------------------------------------ helpers

    def _make_sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def _init_push_commit(self, sync, directory, vault_key, files: dict):
        """Init a vault, write files, commit, and push."""
        sync.init(directory, vault_key=vault_key)
        for path, content in files.items():
            full = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        sync.commit(directory, message='initial commit')
        sync.push(directory)

    # ------------------------------------------------------------------ tests

    def test_move_in_place_rotation_then_clone_succeeds(self, vault_api, temp_dir):
        """Move vault to a new key then clone with the new key — all commits readable."""
        sync      = self._make_sync(vault_api)
        vault_key = 'movetest:mvvault01'
        vault_dir = os.path.join(temp_dir, 'mv1')

        self._init_push_commit(sync, vault_dir,
                               vault_key=vault_key,
                               files={'first.txt': 'first', 'second.txt': 'second'})

        # Second commit
        with open(os.path.join(vault_dir, 'third.txt'), 'w') as f:
            f.write('third')
        sync.commit(vault_dir, message='second commit')
        sync.push(vault_dir)

        # Move
        result = sync.move(vault_dir)
        assert result.get('status') in ('moved', 'complete', 'success') or result.get('new_vault_key')
        new_vault_key = result.get('new_vault_key') or result.get('vault_key')
        assert new_vault_key, f'move result missing new_vault_key: {result}'

        # Clone with new key into a fresh dir
        clone_dir = os.path.join(temp_dir, 'mv1-clone')
        clone_result = sync.clone(new_vault_key, clone_dir)
        assert os.path.isdir(clone_dir)

        # Working copy should have all three files
        for fname in ('first.txt', 'second.txt', 'third.txt'):
            assert os.path.isfile(os.path.join(clone_dir, fname)), f'{fname} missing after clone'

    def test_move_validates_full_commit_graph_before_proceeding(self, vault_api, temp_dir):
        """Move aborts with a clear error when a local object is missing."""
        sync      = self._make_sync(vault_api)
        vault_key = 'movetest:mvvault02'
        vault_dir = os.path.join(temp_dir, 'mv2')

        self._init_push_commit(sync, vault_dir,
                               vault_key=vault_key,
                               files={'a.txt': 'aaa', 'b.txt': 'bbb'})

        # Add more commits to generate more objects
        for i in range(3):
            fname = os.path.join(vault_dir, f'c{i}.txt')
            with open(fname, 'w') as f:
                f.write(f'content-{i}')
            sync.commit(vault_dir, message=f'commit {i}')

        # Manually delete one object from bare/data/
        data_dir = os.path.join(vault_dir, '.sg_vault', 'bare', 'data')
        objects  = [f for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-')]
        assert objects, 'No objects to delete'
        os.remove(os.path.join(data_dir, objects[0]))

        # Move must abort before creating .sg_vault_new or touching the server
        with pytest.raises(RuntimeError) as exc_info:
            sync.move(vault_dir)

        err = str(exc_info.value)
        assert 'missing' in err.lower() or 'object' in err.lower(), (
            f'Expected missing-object error, got: {err}')
        assert not os.path.isdir(os.path.join(vault_dir, '.sg_vault_new')), (
            '.sg_vault_new/ was created even though validation should have aborted')

    def test_move_then_old_vault_id_is_tombstoned(self, vault_api, temp_dir):
        """After a move, pushing to the old vault key should fail (403/tombstoned)."""
        sync       = self._make_sync(vault_api)
        vault_key  = 'movetest:mvvault03'
        vault_dir  = os.path.join(temp_dir, 'mv3')

        self._init_push_commit(sync, vault_dir,
                               vault_key=vault_key,
                               files={'file.txt': 'hello'})

        # Capture old vault_id before move
        crypto      = Vault__Crypto()
        old_keys    = crypto.derive_keys_from_vault_key(vault_key)
        old_vault_id = old_keys['vault_id']

        # Move
        sync.move(vault_dir)

        # Try to read/write to old vault — server should reject
        with pytest.raises(Exception) as exc_info:
            vault_api.read(old_vault_id, old_keys['ref_file_id'])
        err = str(exc_info.value)
        # 403, 404, tombstoned, or "deleted" are all acceptable rejection signals
        assert any(code in err for code in ('403', '404', 'tombstone', 'deleted', 'moved')), (
            f'Expected rejection accessing old vault, got: {err}')

    def test_move_with_dirty_local_clone_fails_validation_clearly(self, vault_api, temp_dir):
        """Move must abort before doing anything when there are uncommitted changes."""
        sync      = self._make_sync(vault_api)
        vault_key = 'movetest:mvvault04'
        vault_dir = os.path.join(temp_dir, 'mv4')

        self._init_push_commit(sync, vault_dir,
                               vault_key=vault_key,
                               files={'clean.txt': 'clean'})

        # Write an uncommitted file
        with open(os.path.join(vault_dir, 'dirty.txt'), 'w') as f:
            f.write('dirty')

        with pytest.raises(RuntimeError) as exc_info:
            sync.move(vault_dir)

        err = str(exc_info.value)
        assert 'uncommitted' in err.lower() or 'dirty' in err.lower() or 'stash' in err.lower(), (
            f'Expected uncommitted-changes error, got: {err}')
        assert not os.path.isdir(os.path.join(vault_dir, '.sg_vault_new')), (
            '.sg_vault_new/ was created despite dirty working copy')
