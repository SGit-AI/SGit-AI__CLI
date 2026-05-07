"""Backup zip integrity and restore tests — Brief 03 §3f."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory


class Test_Vault__Sync__Move__Backup:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'hello.txt'   : 'hello world\n',
            'sub/data.txt': 'nested data',
        })

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    # helpers

    def _move(self, **kwargs):
        mover = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        mover.move(self.env.vault_dir, reason='backup-test', **kwargs)

    def _backups_dir(self):
        return os.path.join(self.env.vault_dir, '.sg_vault', 'backups')

    def _zip_path(self):
        bd   = self._backups_dir()
        zips = [f for f in os.listdir(bd) if f.endswith('.zip')] if os.path.isdir(bd) else []
        assert zips, 'No backup zip found after move'
        return os.path.join(bd, zips[0])

    def _old_sg_dir_snapshot(self):
        """Snapshot all bare/ file content before move."""
        sg_dir   = os.path.join(self.env.vault_dir, '.sg_vault')
        bare_dir = os.path.join(sg_dir, 'bare')
        snapshot = {}
        for root, _, files in os.walk(bare_dir):
            for fname in files:
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, sg_dir)
                with open(full, 'rb') as f:
                    snapshot[rel] = f.read()
        return snapshot

    # 1. Backup zip exists at expected path after move
    def test_backup_zip_exists_at_expected_path(self):
        self._move()
        bd = self._backups_dir()
        assert os.path.isdir(bd)
        zips = [f for f in os.listdir(bd) if f.endswith('.zip')]
        assert len(zips) >= 1

    # 2. Zip contains full bare/ + local/config.json from pre-move vault
    def test_backup_zip_contains_old_vault_structure(self):
        pre_snap = self._old_sg_dir_snapshot()
        self._move()
        zip_path = self._zip_path()
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = set(zf.namelist())
        # Every pre-move bare/ file must be in the zip
        for rel_path in pre_snap:
            assert rel_path in names, f'missing from backup zip: {rel_path}'
        assert 'local/config.json' in names

    # 3. Zip excludes vault key by default
    def test_backup_zip_excludes_vault_key_by_default(self):
        self._move()
        zip_path = self._zip_path()
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
        assert 'VAULT-KEY' not in names
        assert 'local/vault_key' not in names

    # 4. SHA256 sidecar file matches zip content
    def test_backup_zip_sha256_sidecar(self):
        self._move()
        zip_path = self._zip_path()
        sidecar  = zip_path + '.sha256'
        assert os.path.isfile(sidecar), 'SHA256 sidecar file must exist alongside zip'
        with open(sidecar) as f:
            recorded = f.read().strip()
        with open(zip_path, 'rb') as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        assert recorded == actual

    # 5. Old ciphertext in zip is decryptable with the OLD vault key
    def test_backup_zip_restore_round_trip(self):
        old_key      = self.env.vault_key
        old_keys     = self.env.crypto.derive_keys_from_vault_key(old_key)
        old_read_key = old_keys['read_key_bytes']

        # Sample a data object before move
        sg_dir   = os.path.join(self.env.vault_dir, '.sg_vault')
        data_dir = os.path.join(sg_dir, 'bare', 'data')
        sample_files = [f for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-')]
        assert sample_files, 'No data objects to sample'
        sample_id = sorted(sample_files)[0]
        with open(os.path.join(data_dir, sample_id), 'rb') as f:
            original_cipher = f.read()
        original_plain = self.env.crypto.decrypt(old_read_key, original_cipher)

        self._move()
        zip_path = self._zip_path()

        # Extract backup and verify decryptability with old key
        extract_dir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
            restored_path = os.path.join(extract_dir, 'bare', 'data', sample_id)
            assert os.path.isfile(restored_path), f'Sample object not in backup: {sample_id}'
            with open(restored_path, 'rb') as f:
                restored_cipher = f.read()
            restored_plain = self.env.crypto.decrypt(old_read_key, restored_cipher)
            assert restored_plain == original_plain, 'Backup ciphertext does not decrypt to original plaintext'
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    # 6. Post-move clone still works (backup doesn't corrupt anything)
    def test_clone_works_after_move_with_backup(self):
        self._move()
        new_key   = open(os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        clone_dir = tempfile.mkdtemp()
        try:
            from sgit_ai.core.Vault__Sync import Vault__Sync
            Vault__Sync(crypto=self.env.crypto, api=self.env.api).clone(new_key, clone_dir)
            assert os.path.isfile(os.path.join(clone_dir, 'hello.txt'))
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    # 7. Backup zip bytes are consistent: unzipping the zip gives same sha256 as sidecar
    def test_backup_zip_bytes_are_consistent(self):
        self._move()
        zip_path = self._zip_path()
        # Re-hash the zip directly
        with open(zip_path, 'rb') as f:
            content = f.read()
        computed = hashlib.sha256(content).hexdigest()
        sidecar  = zip_path + '.sha256'
        with open(sidecar) as f:
            recorded = f.read().strip()
        assert computed == recorded
        assert len(content) > 0
