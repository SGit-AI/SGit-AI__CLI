"""Integration tests for Brief 18 — clone downloads all historical blobs.

Requires the Python-3.12 venv with sgraph-ai-app-send:
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
"""
import os

from sgit_ai.core.Vault__Sync     import Vault__Sync
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


class Test_Clone__Full_History_Blobs__Integration:

    # ------------------------------------------------------------------ helpers

    def _make_sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def _init_and_push_commits(self, sync, directory, vault_key, commits: list[dict]):
        """Init vault, apply a series of commits (each dict is {path: content}), push."""
        sync.init(directory, vault_key=vault_key)
        for i, files in enumerate(commits):
            for rel_path, content in files.items():
                full = os.path.join(directory, rel_path)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, 'w') as f:
                    f.write(content)
            sync.commit(directory, message=f'commit {i}')
        sync.push(directory)

    def _count_blob_objects(self, clone_dir: str) -> int:
        data_dir = os.path.join(clone_dir, '.sg_vault', 'bare', 'data')
        if not os.path.isdir(data_dir):
            return 0
        return sum(1 for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-'))

    # ------------------------------------------------------------------ tests

    def test_clone_downloads_blobs_for_every_historical_commit(self, vault_api, temp_dir):
        """After a full clone, fsck must find 0 missing objects."""
        vault_key = 'histblob:clonehist01'
        src_dir   = os.path.join(temp_dir, 'src')
        sync      = self._make_sync(vault_api)

        # Three commits, each changes file.txt → 3 distinct blob versions
        self._init_and_push_commits(sync, src_dir, vault_key, [
            {'file.txt': 'version one', 'static.txt': 'never changes'},
            {'file.txt': 'version two'},
            {'file.txt': 'version three'},
        ])

        clone_dir = os.path.join(temp_dir, 'clone')
        sync.clone(vault_key, clone_dir)

        result = sync.fsck(clone_dir)
        assert result['missing'] == [], (
            f'fsck found {len(result["missing"])} missing object(s) after full clone: '
            f'{result["missing"][:5]}')
        assert result['ok'] is True, f'fsck reports vault not ok: {result}'

        # Sanity: all 3 file.txt versions must be present as distinct objects
        blob_count = self._count_blob_objects(clone_dir)
        assert blob_count >= 3, (
            f'Expected ≥3 blob objects (one per file.txt version), got {blob_count}')

    def test_clone_then_history_show_works_for_old_commits(self, vault_api, temp_dir):
        """After clone, historical commits are fully readable (trees + blobs present)."""
        vault_key = 'histblob:clonehist02'
        src_dir   = os.path.join(temp_dir, 'src')
        sync      = self._make_sync(vault_api)

        self._init_and_push_commits(sync, src_dir, vault_key, [
            {'story.txt': 'chapter one'},
            {'story.txt': 'chapter two'},
            {'story.txt': 'chapter three'},
        ])

        clone_dir = os.path.join(temp_dir, 'clone')
        sync.clone(vault_key, clone_dir)

        # Every commit's tree must be loadable (no missing blobs); if any were skipped
        # on clone, fsck would report them as missing.
        fsck_result = sync.fsck(clone_dir)
        assert fsck_result['missing'] == [], (
            f'Historical commits not fully readable — missing: {fsck_result["missing"][:5]}')
        assert fsck_result['ok'] is True

        # All three story.txt versions must be present as distinct blobs
        blob_count = self._count_blob_objects(clone_dir)
        assert blob_count >= 3, (
            f'Expected ≥3 blob objects (one per story.txt version), got {blob_count}')

    def test_clone_then_vault_move_passes_validation(self, vault_api, temp_dir):
        """vault move succeeds after a full clone (no missing-objects abort)."""
        vault_key = 'histblob:clonehist03'
        src_dir   = os.path.join(temp_dir, 'src')
        sync      = self._make_sync(vault_api)

        self._init_and_push_commits(sync, src_dir, vault_key, [
            {'data.txt': 'rev 1'},
            {'data.txt': 'rev 2'},
            {'data.txt': 'rev 3'},
        ])

        clone_dir = os.path.join(temp_dir, 'clone')
        sync.clone(vault_key, clone_dir)

        # vault move validates full commit graph before re-encrypting;
        # this must not raise RuntimeError about missing objects
        result = sync.move(clone_dir)
        assert result.get('new_vault_key') or result.get('status') in ('moved', 'complete', 'success'), (
            f'vault move did not succeed after full clone: {result}')

    def test_clone_branch_remains_thin(self, vault_api, temp_dir):
        """clone-branch (sparse=True, head_only=True) downloads only HEAD blobs."""
        vault_key = 'histblob:clonehist04'
        src_dir   = os.path.join(temp_dir, 'src')
        sync      = self._make_sync(vault_api)

        # Three commits each replacing evolving.txt → only the last version needed for HEAD
        self._init_and_push_commits(sync, src_dir, vault_key, [
            {'evolving.txt': 'v1', 'static.txt': 'always here'},
            {'evolving.txt': 'v2'},
            {'evolving.txt': 'v3'},
        ])

        branch_dir = os.path.join(temp_dir, 'branch')
        sync.clone_branch(vault_key, branch_dir)

        # HEAD-only clone: only 1 evolving.txt version + 1 static.txt version = 2 blobs max
        blob_count = self._count_blob_objects(branch_dir)
        assert blob_count <= 2, (
            f'clone-branch should only have HEAD blobs (≤2), got {blob_count} — '
            f'historical blobs were leaked into branch clone')

        # Working copy must still have HEAD files
        assert os.path.isfile(os.path.join(branch_dir, 'evolving.txt'))
        with open(os.path.join(branch_dir, 'evolving.txt')) as f:
            assert f.read() == 'v3', 'HEAD file should contain latest version'
