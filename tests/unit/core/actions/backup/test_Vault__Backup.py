"""10 tests for Vault__Backup (Brief 04 §5a)."""
import hashlib
import json
import os
import zipfile
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.actions.backup.Vault__Backup   import Vault__Backup
from sgit_ai.schemas.backup.Schema__Backup_Manifest import Schema__Backup_Manifest


class Test_Vault__Backup:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello world\n',
                                           'sub/data.txt': 'data'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_backup_creates_zip_at_default_path(self):
        result = Vault__Backup().backup(self.env.vault_dir)
        assert os.path.isfile(result['zip_path'])
        expected_backups_dir = os.path.join(self.env.vault_dir, '.sg_vault', 'backups')
        assert result['zip_path'].startswith(expected_backups_dir)
        assert result['zip_path'].endswith('.zip')

    def test_backup_zip_contents_match_vault(self):
        result = Vault__Backup().backup(self.env.vault_dir)
        sg_dir = os.path.join(self.env.vault_dir, '.sg_vault')
        bare_dir = os.path.join(sg_dir, 'bare')
        with zipfile.ZipFile(result['zip_path'], 'r') as zf:
            names = set(zf.namelist())
        for root, _, files in os.walk(bare_dir):
            for fname in files:
                full = os.path.join(root, fname)
                arc  = os.path.relpath(full, sg_dir)
                assert arc in names, f'Missing from zip: {arc}'
        assert 'local/config.json' in names

    def test_backup_excludes_vault_key_by_default(self):
        result = Vault__Backup().backup(self.env.vault_dir)
        with zipfile.ZipFile(result['zip_path'], 'r') as zf:
            assert 'VAULT-KEY' not in zf.namelist()
        assert not result['includes_key']

    def test_backup_includes_key_when_opted_in(self):
        result = Vault__Backup().backup(self.env.vault_dir, include_key=True)
        with zipfile.ZipFile(result['zip_path'], 'r') as zf:
            assert 'VAULT-KEY' in zf.namelist()
            key_bytes = zf.read('VAULT-KEY')
        assert key_bytes.decode().strip() == self.env.vault_key
        assert result['includes_key']

    def test_backup_sha256_sidecar_matches_zip(self):
        result  = Vault__Backup().backup(self.env.vault_dir)
        sidecar = result['zip_path'] + '.sha256'
        assert os.path.isfile(sidecar)
        with open(sidecar) as f:
            sidecar_hash = f.read().strip()
        with open(result['zip_path'], 'rb') as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        assert sidecar_hash == actual_hash
        assert sidecar_hash == result['sha256']

    def test_backup_with_label(self):
        result = Vault__Backup().backup(self.env.vault_dir, label='before-move')
        assert '__before-move.zip' in result['zip_path']
        assert result['label'] == 'before-move'

    def test_backup_to_external_dir(self, tmp_path):
        ext_dir = str(tmp_path / 'my-backups')
        result  = Vault__Backup().backup(self.env.vault_dir, output_dir=ext_dir)
        assert result['zip_path'].startswith(ext_dir)
        default_backups_dir = os.path.join(self.env.vault_dir, '.sg_vault', 'backups')
        assert not os.path.isdir(default_backups_dir)

    def test_backup_refuses_dirty_working_copy(self, tmp_path):
        dirty_file = os.path.join(self.env.vault_dir, 'uncommitted.txt')
        with open(dirty_file, 'w') as f:
            f.write('new file not committed')
        with pytest.raises(RuntimeError, match='uncommitted changes'):
            Vault__Backup().backup(self.env.vault_dir)

    def test_backup_manifest_present_and_typed(self):
        result = Vault__Backup().backup(self.env.vault_dir)
        with zipfile.ZipFile(result['zip_path'], 'r') as zf:
            manifest_data = json.loads(zf.read('manifest.json'))
        manifest = Schema__Backup_Manifest.from_json(manifest_data)
        assert Schema__Backup_Manifest.from_json(manifest.json()).json() == manifest.json()
        assert str(manifest.label) == 'manual'
        assert manifest.schema_version is not None

    def test_two_backups_coexist(self):
        r1 = Vault__Backup().backup(self.env.vault_dir, label='first')
        r2 = Vault__Backup().backup(self.env.vault_dir, label='second')
        assert r1['zip_path'] != r2['zip_path']
        assert os.path.isfile(r1['zip_path'])
        assert os.path.isfile(r2['zip_path'])
