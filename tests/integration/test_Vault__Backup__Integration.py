"""Integration tests for Vault__Backup against a real in-memory server.

Requires the Python-3.12 venv with sgraph-ai-app-send:
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
"""
import hashlib
import json
import os
import re

import pytest

from sgit_ai.core.Vault__Sync              import Vault__Sync
from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup
from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto


class Test_Vault__Backup__Integration:

    @pytest.fixture(autouse=True)
    def _dirs(self, temp_dir):
        self.vault_dir = os.path.join(temp_dir, 'vault')

    def _make_sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def test_backup_round_trip_against_real_server(self, vault_api, temp_dir):
        """Init, commit, push, backup — zip exists with correct structure."""
        sync      = self._make_sync(vault_api)
        vault_key = 'backuptest:bkvault01'
        vault_dir = os.path.join(temp_dir, 'bk1')

        sync.init(vault_dir, vault_key=vault_key)
        with open(os.path.join(vault_dir, 'hello.txt'), 'w') as f:
            f.write('hello backup')
        sync.commit(vault_dir, message='backup test commit')
        sync.push(vault_dir)

        # Create backup
        result = Vault__Backup().backup(vault_dir, label='manual')

        zip_path = result['zip_path']
        assert os.path.isfile(zip_path), f'Backup zip not found: {zip_path}'

        # sha256 sidecar matches
        sha256_sidecar = zip_path + '.sha256'
        assert os.path.isfile(sha256_sidecar), 'sha256 sidecar missing'
        with open(sha256_sidecar) as f:
            sidecar_hash = f.read().strip()
        with open(zip_path, 'rb') as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        assert sidecar_hash == actual_hash, 'sha256 sidecar does not match zip content'

        # manifest sidecar parses
        manifest_path = zip_path + '.manifest.json'
        assert os.path.isfile(manifest_path), 'manifest.json sidecar missing'
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest.get('vault_id'), 'manifest missing vault_id'
        assert manifest.get('label') == 'manual'
        assert manifest.get('object_count', 0) > 0, 'manifest should count objects'

    def test_backup_filename_includes_real_vault_id(self, vault_api, temp_dir):
        """Regression test for §2b: backup filename must not start with '__'."""
        sync      = self._make_sync(vault_api)
        vault_key = 'backuptest:bkvault02'
        vault_dir = os.path.join(temp_dir, 'bk2')

        sync.init(vault_dir, vault_key=vault_key)
        with open(os.path.join(vault_dir, 'data.txt'), 'w') as f:
            f.write('regression test for §2b')
        sync.commit(vault_dir, message='pre-backup commit')
        sync.push(vault_dir)

        result   = Vault__Backup().backup(vault_dir, label='pre-move')
        zip_name = os.path.basename(result['zip_path'])

        # Must NOT start with double-underscore (indicates empty vault_id)
        assert not zip_name.startswith('__'), (
            f'Backup filename starts with __ — vault_id was empty: {zip_name}')

        # Must start with the actual vault_id
        crypto    = Vault__Crypto()
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        vault_id  = keys['vault_id']
        assert zip_name.startswith(vault_id), (
            f'Backup filename should start with vault_id={vault_id!r}: {zip_name}')

        # Filename pattern: <vault_id>__<ts>__<label>.zip
        assert re.match(r'^.+__\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z__.+\.zip$', zip_name), (
            f'Backup filename does not match expected pattern: {zip_name}')
