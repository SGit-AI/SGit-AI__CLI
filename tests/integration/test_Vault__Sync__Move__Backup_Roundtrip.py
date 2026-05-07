"""Integration test §3d: move creates a backup; restore it under the old key.

The backup zip is the recovery path for "move went wrong" — this test
validates that the pre-move backup is byte-identical to the pre-move vault.

Requires the Python-3.12 venv with sgraph-ai-app-send:
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
"""
import os

import pytest

from sgit_ai.core.Vault__Sync     import Vault__Sync
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


class Test_Vault__Sync__Move__Backup_Roundtrip:

    def _make_sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def test_move_backup_can_be_restored_under_old_key(self, vault_api, temp_dir):
        """Move creates a pre-move backup; restoring it recovers the original vault state."""
        sync      = self._make_sync(vault_api)
        vault_key = 'roundtrip:rtvault01'
        vault_dir = os.path.join(temp_dir, 'rt1')
        restore_dir = os.path.join(temp_dir, 'rt1-restored')

        # Build a vault with multiple commits and files
        sync.init(vault_dir, vault_key=vault_key)
        for name, content in [('alpha.txt', 'aaa'), ('beta.txt', 'bbb'), ('gamma.txt', 'ccc')]:
            with open(os.path.join(vault_dir, name), 'w') as f:
                f.write(content)
        sync.commit(vault_dir, message='first commit')
        sync.push(vault_dir)

        with open(os.path.join(vault_dir, 'delta.txt'), 'w') as f:
            f.write('ddd')
        sync.commit(vault_dir, message='second commit')
        sync.push(vault_dir)

        # Record pre-move object inventory
        data_dir_before = os.path.join(vault_dir, '.sg_vault', 'bare', 'data')
        objects_before  = set(f for f in os.listdir(data_dir_before)
                              if f.startswith('obj-cas-imm-'))
        assert objects_before, 'No objects before move'

        # Execute the move — Step__Move__Backup_Old_Vault creates a pre-move zip
        result = sync.move(vault_dir)

        # Locate the backup zip; after rename it lives in .sg_vault/backups/
        backups_dir = os.path.join(vault_dir, '.sg_vault', 'backups')
        zip_files   = []
        if os.path.isdir(backups_dir):
            zip_files = [os.path.join(backups_dir, f)
                         for f in os.listdir(backups_dir)
                         if f.endswith('.zip') and 'pre-move' in f]

        # Fallback: check backup_zip_path in result (may still point to .sg_vault_new/)
        if not zip_files:
            raw_path = result.get('backup_zip_path') or result.get('backup_zip') or ''
            if isinstance(raw_path, str) and raw_path:
                candidate = raw_path.replace('.sg_vault_new/', '.sg_vault/')
                if os.path.isfile(candidate):
                    zip_files = [candidate]

        assert zip_files, (
            f'Could not find pre-move backup zip in {backups_dir}. '
            f'Move result keys: {list(result.keys())}')

        zip_path = zip_files[0]
        assert os.path.isfile(zip_path), f'Backup zip not found at: {zip_path}'

        # Restore the backup into a fresh directory
        sync.restore_from_backup(zip_path, restore_dir)

        sg_restored = os.path.join(restore_dir, '.sg_vault')
        assert os.path.isdir(sg_restored), '.sg_vault/ not created in restored dir'

        # The restored object set must be byte-identical to the pre-move object set
        data_dir_restored = os.path.join(sg_restored, 'bare', 'data')
        assert os.path.isdir(data_dir_restored), 'bare/data/ missing in restored vault'
        objects_restored = set(f for f in os.listdir(data_dir_restored)
                               if f.startswith('obj-cas-imm-'))

        assert objects_restored == objects_before, (
            f'Restored object set differs from pre-move set.\n'
            f'  Missing: {objects_before - objects_restored}\n'
            f'  Extra:   {objects_restored - objects_before}')
