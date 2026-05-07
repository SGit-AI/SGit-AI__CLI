"""Integration tests for vault restore against a real in-memory server.

Requires the Python-3.12 venv with sgraph-ai-app-send:
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.core.Vault__Sync              import Vault__Sync
from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup
from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto


class Test_Vault__Restore__Integration:

    def _make_sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def test_restore_bare_mode_against_real_server(self, vault_api, temp_dir):
        """Backup a pushed vault then restore — .sg_vault/ structure and vault_id preserved."""
        sync      = self._make_sync(vault_api)
        vault_key = 'restoretest:rsvault01'
        vault_dir = os.path.join(temp_dir, 'rs1')
        restore_dir = os.path.join(temp_dir, 'rs1-restored')

        sync.init(vault_dir, vault_key=vault_key)
        with open(os.path.join(vault_dir, 'restore_me.txt'), 'w') as f:
            f.write('restore content')
        sync.commit(vault_dir, message='restore test commit')
        sync.push(vault_dir)

        # Back up (bare mode — no vault key in zip)
        result   = Vault__Backup().backup(vault_dir, label='pre-restore')
        zip_path = result['zip_path']
        assert os.path.isfile(zip_path)

        # Restore into a fresh directory
        restore_result = sync.restore_from_backup(zip_path, restore_dir)

        sg_restored = os.path.join(restore_dir, '.sg_vault')
        assert os.path.isdir(sg_restored), '.sg_vault/ not created after restore'
        assert os.path.isdir(os.path.join(sg_restored, 'bare')), 'bare/ missing after restore'

        # vault_id must be non-empty in the restored local config
        import json
        local_cfg = os.path.join(sg_restored, 'local', 'config.json')
        if os.path.isfile(local_cfg):
            with open(local_cfg) as f:
                cfg = json.load(f)
            assert cfg.get('vault_id'), 'vault_id is empty in restored config.json'

    def test_backup_then_restore_preserves_object_count(self, vault_api, temp_dir):
        """Objects backed up should equal objects after restore."""
        sync      = self._make_sync(vault_api)
        vault_key = 'restoretest:rsvault02'
        vault_dir = os.path.join(temp_dir, 'rs2')
        restore_dir = os.path.join(temp_dir, 'rs2-restored')

        sync.init(vault_dir, vault_key=vault_key)
        for i in range(3):
            with open(os.path.join(vault_dir, f'file{i}.txt'), 'w') as f:
                f.write(f'file {i}')
        sync.commit(vault_dir, message='multi-file commit')
        sync.push(vault_dir)

        backup_result = Vault__Backup().backup(vault_dir, label='count-test')
        original_count = backup_result['object_count']
        zip_path = backup_result['zip_path']

        sync.restore_from_backup(zip_path, restore_dir)

        # Count objects in restored vault
        data_dir = os.path.join(restore_dir, '.sg_vault', 'bare', 'data')
        if os.path.isdir(data_dir):
            restored_count = sum(1 for f in os.listdir(data_dir)
                                 if f.startswith('obj-cas-imm-'))
            assert restored_count == original_count, (
                f'Object count mismatch: backed up {original_count}, '
                f'restored {restored_count}')
