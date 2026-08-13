"""Integration test for read-only clone subcommands (architect contract §7.3).

Runs against the real SG/Send in-memory test server (no mocks). Requires the
Python-3.12 venv with sgraph-ai-app-send:

  python3.12 -m venv /tmp/sgit-ai-venv-312
  /tmp/sgit-ai-venv-312/bin/pip install -e ".[dev]"
  /tmp/sgit-ai-venv-312/bin/pip install sgraph-ai-app-send
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/test_read_only_clone_commands.py -v

Scenario (contract §7.3 steps 1-10):
  1. Provision a vault on the real server.
  2. Push N=5 commits to it.
  3. Clone read-only into directory A → assert config.json exists, mode=READ_ONLY,
     my_branch_id=None.
  4. Push a 6th commit from the original full-clone directory.
  5. A.ls returns N=5 paths.
  6. A.status reports behind=1, ahead=0, push_status='read_only'.
  7. A.pull succeeds; afterwards the working tree matches commit 6.
  8. A.log shows 6 commits.
  9. A.commit exits 1 with a "read-only" message.
 10. A.push   exits 1 with a "read-only" message.
"""
import json
import os

import pytest

from sgit_ai.core.Vault__Sync     import Vault__Sync
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
from sgit_ai.cli.CLI__Vault       import CLI__Vault
from sgit_ai.storage.Vault__Storage import SG_VAULT_DIR


class Test_Read_Only_Clone_Commands__Integration:

    # ------------------------------------------------------------------ helpers

    def _make_sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def _write_file(self, directory, rel_path, content):
        full = os.path.join(directory, rel_path)
        os.makedirs(os.path.dirname(full) or directory, exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)

    def _cli_for(self, vault_api):
        """A CLI__Vault wired so create_sync() reuses the test-server api."""
        cli = CLI__Vault()
        cli.create_sync = lambda *a, **k: self._make_sync(vault_api)        # reuse server api
        return cli

    # ------------------------------------------------------------------ scenario

    def test_read_only_clone_full_command_surface(self, vault_api, temp_dir):
        crypto    = Vault__Crypto()
        sync      = self._make_sync(vault_api)
        vault_key = 'roclone:rocloneint01'

        src_dir = os.path.join(temp_dir, 'src')
        ro_dir  = os.path.join(temp_dir, 'A')

        # ── 1-2. Provision + push N=5 commits ────────────────────────────────
        sync.init(src_dir, vault_key=vault_key)
        for i in range(1, 6):                                               # commits 1..5
            self._write_file(src_dir, 'data.txt', f'version {i}')
            sync.commit(src_dir, message=f'commit {i}')
        sync.push(src_dir)

        keys         = crypto.derive_keys_from_vault_key(vault_key)
        vault_id     = keys['vault_id']
        read_key_hex = keys['read_key']
        read_key     = keys['read_key_bytes']

        # ── 3. Clone read-only into A ────────────────────────────────────────
        sync.clone_read_only(vault_id, read_key_hex, ro_dir)

        config_path = os.path.join(ro_dir, SG_VAULT_DIR, 'local', 'config.json')
        assert os.path.isfile(config_path), 'RO clone must write config.json (§3.3)'
        with open(config_path) as f:
            cfg = json.load(f)
        assert cfg.get('mode')         == 'read_only'                       # Enum__Local_Config_Mode.READ_ONLY
        assert cfg.get('my_branch_id') in (None, '')                        # no clone branch
        # And NO vault_key on disk.
        assert not os.path.isfile(os.path.join(ro_dir, SG_VAULT_DIR, 'local', 'vault_key'))

        # ── 4. Push a 6th commit from the full-clone (source) directory ──────
        self._write_file(src_dir, 'data.txt', 'version 6')
        self._write_file(src_dir, 'new_in_6.txt', 'only in commit 6')
        sync.commit(src_dir, message='commit 6')
        sync.push(src_dir)

        # ── 5. A.ls returns N=5 paths (state before pull = commit 5) ────────
        entries = sync.sparse_ls(ro_dir)
        paths   = sorted(e['path'] for e in entries)
        assert paths == ['data.txt'], f'RO clone should see commit-5 tree, got {paths}'
        # working copy still at commit 5
        with open(os.path.join(ro_dir, 'data.txt')) as f:
            assert f.read() == 'version 5'
        assert not os.path.isfile(os.path.join(ro_dir, 'new_in_6.txt'))

        # ── 6. A.status: behind=1, ahead=0, push_status='read_only' ─────────
        status = sync.status(ro_dir)
        assert status['ahead']       == 0
        assert status['behind']      == 1
        assert status['push_status'] == 'read_only'
        assert status['read_only']   is True
        assert status['clone_branch_id'] == ''

        # ── 7. A.pull succeeds; working tree now matches commit 6 ───────────
        result = sync.pull_read_only(ro_dir)
        assert result['status'] in ('merged', 'up_to_date')
        with open(os.path.join(ro_dir, 'data.txt')) as f:
            assert f.read() == 'version 6'
        assert os.path.isfile(os.path.join(ro_dir, 'new_in_6.txt'))
        with open(os.path.join(ro_dir, 'new_in_6.txt')) as f:
            assert f.read() == 'only in commit 6'

        # ls now shows both files from commit 6
        paths_after = sorted(e['path'] for e in sync.sparse_ls(ro_dir))
        assert paths_after == ['data.txt', 'new_in_6.txt']

        # status now in-sync (behind=0)
        status_after = sync.status(ro_dir)
        assert status_after['behind']      == 0
        assert status_after['push_status'] == 'read_only'

        # ── 8. A.log shows every commit (init + 6 explicit = 7) ─────────────
        # `sync.init()` creates an initial 'init' commit, so the chain is
        # init + commits 1..6 = 7. Assert against the full chain from the source
        # of truth (the source dir) so the count stays correct if init changes.
        from sgit_ai.objects.Vault__Inspector import Vault__Inspector
        src_chain = Vault__Inspector().inspect_commit_chain(src_dir, read_key, limit=50)
        ro_chain  = Vault__Inspector().inspect_commit_chain(ro_dir,  read_key, limit=50)
        assert len(ro_chain) == len(src_chain), (
            f'RO log ({len(ro_chain)}) should match source log ({len(src_chain)}) after pull')
        messages = [c['message'] for c in ro_chain]
        assert 'commit 6' in messages and 'commit 1' in messages       # full history present
        assert len(ro_chain) == 7                                      # init + commits 1..6

        # ── 9. A.commit exits 1 with a read-only message ────────────────────
        cli = self._cli_for(vault_api)

        class _CommitArgs:
            directory    = ro_dir
            message      = 'should fail'
            message_flag = None

        with pytest.raises((SystemExit, RuntimeError)) as exc_commit:
            cli.cmd_commit(_CommitArgs())
        assert 'read-only' in str(exc_commit.value).lower() or self._is_exit_1(exc_commit.value)

        # ── 10. A.push exits 1 with a read-only message ─────────────────────
        class _PushArgs:
            directory = ro_dir
            token     = None
            base_url  = None
            name      = None

        with pytest.raises((SystemExit, RuntimeError)) as exc_push:
            cli.cmd_push(_PushArgs())
        assert 'read-only' in str(exc_push.value).lower() or self._is_exit_1(exc_push.value)

    def _is_exit_1(self, exc):
        return isinstance(exc, SystemExit) and exc.code in (1, '1')
