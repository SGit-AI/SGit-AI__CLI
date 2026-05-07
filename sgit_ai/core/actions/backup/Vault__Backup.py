import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone

from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.crypto.Vault__Crypto                         import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__App_Version             import Safe_Str__App_Version
from sgit_ai.safe_types.Safe_Str__Backup_Label            import Safe_Str__Backup_Label
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp           import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Byte_Size              import Safe_UInt__Byte_Size
from sgit_ai.safe_types.Safe_UInt__File_Count             import Safe_UInt__File_Count
from sgit_ai.safe_types.Safe_UInt__Vault_Version          import Safe_UInt__Vault_Version
from sgit_ai.schemas.backup.Schema__Backup_Manifest       import Schema__Backup_Manifest
from sgit_ai.storage.Vault__Storage                       import Vault__Storage

BACKUPS_DIR    = 'backups'
MANIFEST_FILE  = 'manifest.json'
SCHEMA_VERSION = 1


class Vault__Backup(Type_Safe):
    crypto  : Vault__Crypto

    def backup(self, directory: str, output_dir: str = None,
               label: str = 'manual', include_key: bool = False,
               allow_dirty: bool = False) -> dict:
        storage  = Vault__Storage()
        sg_dir   = storage.sg_vault_dir(directory)
        if not os.path.isdir(sg_dir):
            raise RuntimeError(f'Not a vault: {directory}')

        if not allow_dirty:
            from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
            status = Vault__Sync__Status(crypto=self.crypto).status(directory)
            if not status.get('clean', True):
                raise RuntimeError(
                    'Vault has uncommitted changes — commit or stash before backing up.'
                )

        local_config_path = storage.local_config_path(directory)
        if not os.path.isfile(local_config_path):
            raise RuntimeError(f'Missing local config: {local_config_path}')
        with open(local_config_path) as f:
            local_config = json.load(f)
        vault_id       = local_config.get('vault_id', '')
        key_generation = local_config.get('key_generation', 1)

        # Schema__Local_Config stores branch state, not vault identity.
        # Derive vault_id from the vault key when config.json doesn't have it.
        if not vault_id:
            vault_key_path = storage.vault_key_path(directory)
            if os.path.isfile(vault_key_path):
                import sys
                with open(vault_key_path) as f:
                    vault_key_str = f.read().strip()
                try:
                    vault_id = self.crypto.derive_keys_from_vault_key(vault_key_str)['vault_id']
                except Exception as e:
                    print(f'warning: could not derive vault_id from vault_key: {e}', file=sys.stderr)

        if output_dir is None:
            output_dir = os.path.join(sg_dir, BACKUPS_DIR)
        os.makedirs(output_dir, exist_ok=True)

        ts       = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
        zip_name = f'{vault_id}__{ts}__{label}.zip'
        zip_path = os.path.join(output_dir, zip_name)

        zip_bytes, manifest = self._build_zip(sg_dir, directory, vault_id,
                                              key_generation, label, include_key)

        with open(zip_path, 'wb') as f:
            f.write(zip_bytes)

        sha256_hex = hashlib.sha256(zip_bytes).hexdigest()
        sidecar    = zip_path + '.sha256'
        with open(sidecar, 'w') as f:
            f.write(sha256_hex + '\n')

        manifest.byte_size = Safe_UInt__Byte_Size(len(zip_bytes))
        manifest_path = zip_path + '.manifest.json'
        with open(manifest_path, 'w') as f:
            json.dump(manifest.json(), f, indent=2)

        return dict(zip_path    = zip_path,
                    sha256      = sha256_hex,
                    byte_size   = len(zip_bytes),
                    object_count = int(manifest.object_count),
                    includes_key = include_key,
                    vault_id    = vault_id,
                    label       = label)

    def _build_zip(self, sg_dir: str, directory: str, vault_id: str,
                   key_generation: int, label: str, include_key: bool):
        try:
            from importlib.metadata import version as _pkg_version
            _VERSION = _pkg_version('sgit-ai')
        except Exception:
            _VERSION = '0.0.0'

        bare_dir  = os.path.join(sg_dir, 'bare')
        local_dir = os.path.join(sg_dir, 'local')

        object_count = 0
        data_dir = os.path.join(bare_dir, 'data')
        if os.path.isdir(data_dir):
            object_count = sum(1 for f in os.listdir(data_dir)
                               if f.startswith('obj-cas-imm-'))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_STORED) as zf:
            for sub in ('bare',):
                sub_path = os.path.join(sg_dir, sub)
                if os.path.isdir(sub_path):
                    for root, _, files in os.walk(sub_path):
                        for fname in sorted(files):
                            full = os.path.join(root, fname)
                            arc  = os.path.relpath(full, sg_dir)
                            zf.write(full, arc)
            for fname in ('config.json', 'move-history.json', 'migrations.json'):
                full = os.path.join(local_dir, fname)
                if os.path.isfile(full):
                    zf.write(full, os.path.join('local', fname))
            if include_key:
                key_path = os.path.join(local_dir, 'vault_key')
                if os.path.isfile(key_path):
                    zf.write(key_path, 'VAULT-KEY')

            now_iso  = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            app_ver  = _VERSION.lstrip('v').replace('.', '').replace('-', '') if _VERSION else '0'
            manifest = Schema__Backup_Manifest(
                schema_version = Safe_UInt__Vault_Version(SCHEMA_VERSION),
                vault_id       = Safe_Str__Vault_Id(vault_id) if vault_id else None,
                key_generation = Safe_UInt__Vault_Version(key_generation),
                created_at     = Safe_Str__ISO_Timestamp(now_iso),
                created_by     = Safe_Str__App_Version(f'sgit v{_VERSION.lstrip("v")}' if _VERSION else 'sgit'),
                label          = Safe_Str__Backup_Label(label),
                includes_key   = include_key,
                object_count   = Safe_UInt__File_Count(object_count),
                byte_size      = Safe_UInt__Byte_Size(0),
            )
            zf.writestr(MANIFEST_FILE, json.dumps(manifest.json(), indent=2))

        return buf.getvalue(), manifest

    def list_backups(self, directory: str) -> list:
        storage     = Vault__Storage()
        sg_dir      = storage.sg_vault_dir(directory)
        backups_dir = os.path.join(sg_dir, BACKUPS_DIR)
        if not os.path.isdir(backups_dir):
            return []
        results = []
        for fname in sorted(os.listdir(backups_dir)):
            if not fname.endswith('.zip'):
                continue
            zip_path    = os.path.join(backups_dir, fname)
            sha256      = self._read_sidecar(zip_path + '.sha256')
            manifest    = self._read_manifest_sidecar(zip_path + '.manifest.json')
            results.append(dict(
                zip_path     = zip_path,
                filename     = fname,
                byte_size    = os.path.getsize(zip_path),
                sha256       = sha256,
                includes_key = manifest.get('includes_key', False) if manifest else False,
                label        = manifest.get('label', '') if manifest else '',
                created_at   = manifest.get('created_at', '') if manifest else '',
            ))
        return results

    def _read_sidecar(self, path: str) -> str:
        if os.path.isfile(path):
            with open(path) as f:
                return f.read().strip()
        return ''

    def _read_manifest_sidecar(self, path: str) -> dict:
        if os.path.isfile(path):
            with open(path) as f:
                return json.load(f)
        return {}
