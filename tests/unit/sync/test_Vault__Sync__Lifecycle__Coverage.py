"""Coverage tests for Vault__Sync__Lifecycle missing lines.

Missing lines:
  82: rekey_commit → 'nothing to commit' RuntimeError path
  112-113: probe_token → api.batch_read raises → except pass
  188: restore_from_backup → zip has no .sg_vault/ entries → RuntimeError
"""
import os
import tempfile
import shutil
import zipfile

import pytest

from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.core.Vault__Sync           import Vault__Sync
from sgit_ai.core.actions.lifecycle.Vault__Sync__Lifecycle import Vault__Sync__Lifecycle
from tests._helpers.vault_test_env      import Vault__Test_Env


class Test_Vault__Sync__Lifecycle__Coverage:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap      = self._env.restore()
        self.vault     = self.snap.vault_dir
        self.lifecycle = Vault__Sync__Lifecycle(crypto=self.snap.crypto, api=self.snap.api)

    def teardown_method(self):
        self.snap.cleanup()

    def test_rekey_commit_nothing_to_commit_returns_empty(self):
        """Line 82: rekey_commit when working tree is clean → (commit_id=None)."""
        self.lifecycle.rekey_init(self.vault)
        self.lifecycle.rekey_commit(self.vault)   # first commit: success
        result = self.lifecycle.rekey_commit(self.vault)   # second: nothing to commit
        assert result['commit_id'] is None

    def test_probe_token_batch_read_exception_falls_through(self):
        """Lines 112-113: probe_token when batch_read raises → except pass → no vault found."""
        class BrokenAPI(Vault__API__In_Memory):
            def batch_read(self, vault_id, paths, **kw):
                raise RuntimeError('simulated network failure')

        broken_api = BrokenAPI()
        broken_api.setup()
        lc = Vault__Sync__Lifecycle(crypto=Vault__Crypto(), api=broken_api)

        with pytest.raises(RuntimeError, match='Token not found'):
            lc.probe_token('apple-orange-9999')

    def test_rekey_commit_non_nothing_to_commit_reraises_line_82(self):
        """Line 82: rekey_commit raises RuntimeError not about 'nothing to commit' → re-raise."""
        import json
        self.lifecycle.rekey_init(self.vault)
        # Corrupt the local config so commit raises 'Branch not found'
        config_path = os.path.join(self.vault, '.sg_vault', 'local', 'config.json')
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        cfg['my_branch_id'] = 'branch-clone-0000000000000000'
        with open(config_path, 'w') as f:
            json.dump(cfg, f)
        with pytest.raises(RuntimeError, match='Branch not found'):
            self.lifecycle.rekey_commit(self.vault)

    def test_probe_token_share_path_lines_121_122(self):
        """Lines 121-122: batch_read returns empty (unknown vault); Transfer.info succeeds → type='share'."""
        import unittest.mock
        from sgit_ai.network.api.API__Transfer import API__Transfer
        # 'blue-mist-9999' derives a vault_id not in the in-memory API,
        # so batch_read returns {key: None} (vault path skipped).
        # Patching API__Transfer.info to return {} makes the share path fire.
        with unittest.mock.patch.object(API__Transfer, 'info', return_value={}):
            result = self.lifecycle.probe_token('blue-mist-9999')
        assert result['type'] == 'share'
        assert result['token'] == 'blue-mist-9999'

    def test_restore_from_backup_bad_zip_raises(self):
        """Line 188: zip without .sg_vault/ entries raises RuntimeError."""
        tmp = tempfile.mkdtemp()
        try:
            zip_path = os.path.join(tmp, 'bad.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('readme.txt', 'not a vault backup')

            restore_dir = os.path.join(tmp, 'restore-target')
            with pytest.raises(RuntimeError, match='does not look like a vault backup'):
                self.lifecycle.restore_from_backup(zip_path, restore_dir)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
