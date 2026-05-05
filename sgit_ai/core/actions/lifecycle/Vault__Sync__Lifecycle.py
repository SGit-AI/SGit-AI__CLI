"""Vault__Sync__Lifecycle — key-rotation, backup, and vault lifecycle (Brief 22 — E5-7b)."""
import io
import json
import os
import re
import shutil
import time
import zipfile
from   sgit_ai.storage.Vault__Storage     import Vault__Storage, SG_VAULT_DIR
from   sgit_ai.core.Vault__Sync__Base  import Vault__Sync__Base


class Vault__Sync__Lifecycle(Vault__Sync__Base):

    def delete_on_remote(self, directory: str) -> dict:
        """Delete every server-side file for this vault. Local clone is untouched."""
        c = self._init_components(directory)
        if not c.write_key:
            raise RuntimeError('delete-on-remote requires write access — read-only clones cannot delete a vault')
        result  = self.api.delete_vault(c.vault_id, c.write_key)
        self.crypto.clear_kdf_cache()
        storage = Vault__Storage()
        self._clear_push_state(storage.push_state_path(directory))
        return result

    def rekey_check(self, directory: str) -> dict:
        """Return vault state without making any changes."""
        c        = self._init_components(directory)
        storage  = Vault__Storage()
        sg_dir   = storage.sg_vault_dir(directory)
        bare_dir = storage.bare_dir(directory)

        file_count = 0
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if os.path.join(root, d) != sg_dir]
            file_count += len(files)

        obj_count = 0
        if os.path.isdir(bare_dir):
            for _, _, fs in os.walk(bare_dir):
                obj_count += len(fs)

        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        status = Vault__Sync__Status(crypto=self.crypto, api=self.api).status(directory)
        return dict(vault_id   = c.vault_id,
                    file_count = file_count,
                    obj_count  = obj_count,
                    clean      = status['clean'])

    def rekey_wipe(self, directory: str) -> dict:
        """Wipe the local encrypted store (.sg_vault/). Working files are untouched."""
        storage   = Vault__Storage()
        bare_dir  = storage.bare_dir(directory)
        obj_count = 0
        if os.path.isdir(bare_dir):
            for _, _, fs in os.walk(bare_dir):
                obj_count += len(fs)
        sg_dir = storage.sg_vault_dir(directory)
        if os.path.isdir(sg_dir):
            storage.secure_rmtree(sg_dir)
        self.crypto.clear_kdf_cache()
        return dict(objects_removed=obj_count)

    def rekey_init(self, directory: str, new_vault_key: str = None) -> dict:
        """Re-initialise vault structure with a new key. Run after rekey_wipe."""
        from sgit_ai.core.Vault__Sync import Vault__Sync as _VS
        result = _VS(crypto=self.crypto, api=self.api).init(
            directory, vault_key=new_vault_key, allow_nonempty=True)
        return dict(vault_key=result['vault_key'], vault_id=result['vault_id'])

    def rekey_commit(self, directory: str) -> dict:
        """Commit all working-directory files under the current (new) key."""
        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        try:
            result = Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(
                directory, message='rekey')
            return dict(commit_id=result['commit_id'],
                        file_count=result.get('files_changed', 0))
        except RuntimeError as e:
            if 'nothing to commit' in str(e).lower():
                return dict(commit_id=None, file_count=0)
            raise

    def rekey(self, directory: str, new_vault_key: str = None) -> dict:
        """Replace the vault key and re-encrypt all content with it."""
        self.rekey_wipe(directory)
        init_r   = self.rekey_init(directory, new_vault_key)
        commit_r = self.rekey_commit(directory)
        return dict(vault_key=init_r['vault_key'],
                    vault_id=init_r['vault_id'],
                    commit_id=commit_r['commit_id'])

    def probe_token(self, token_str: str) -> dict:
        """Identify a simple token as vault or share without cloning."""
        from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token as _ST

        token_str = token_str.removeprefix('vault://')
        if not _ST.is_simple_token(token_str):
            raise RuntimeError(
                f"probe only accepts simple tokens (word-word-NNNN format): '{token_str}'"
            )

        keys     = self.crypto.derive_keys_from_simple_token(token_str)
        vault_id = keys['vault_id']
        index_id = keys['branch_index_file_id']

        try:
            idx_data = self.api.batch_read(vault_id, [f'bare/indexes/{index_id}'])
            if idx_data.get(f'bare/indexes/{index_id}'):
                self.crypto.clear_kdf_cache()
                return dict(type='vault', vault_id=vault_id, token=token_str)
        except Exception:
            pass

        from sgit_ai.network.api.API__Transfer import API__Transfer as _AT
        debug_log = getattr(self.api, 'debug_log', None)
        probe_at  = _AT(debug_log=debug_log)
        probe_at.setup()
        try:
            probe_at.info(vault_id)
            self.crypto.clear_kdf_cache()
            return dict(type='share', transfer_id=vault_id, token=token_str)
        except Exception:
            pass

        self.crypto.clear_kdf_cache()
        raise RuntimeError(
            f"Token not found on SGit-AI or SG/Send: '{token_str}'\n"
            f"  (derived vault_id={vault_id})"
        )

    def uninit(self, directory: str) -> dict:
        """Remove .sg_vault/ from a vault directory after creating an auto-backup zip."""
        storage = Vault__Storage()
        sg_dir  = storage.sg_vault_dir(directory)
        if not os.path.isdir(sg_dir):
            raise RuntimeError(f'Not a vault directory: {directory} (no .sg_vault/ found)')

        abs_directory = os.path.abspath(directory)
        folder_name   = os.path.basename(abs_directory)
        safe_name     = re.sub(r'\s+', '', folder_name)
        timestamp_sec = int(time.time())
        backup_name   = f'.vault__{safe_name}__{timestamp_sec}.zip'
        backup_path   = os.path.join(abs_directory, backup_name)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(sg_dir):
                for fname in files:
                    full_path = os.path.join(root, fname)
                    arc_name  = os.path.relpath(full_path, abs_directory)
                    zf.write(full_path, arc_name)
        with open(backup_path, 'wb') as f:
            f.write(buf.getvalue())

        working_files = 0
        for root, dirs, files in os.walk(abs_directory):
            dirs[:] = [d for d in dirs if d != SG_VAULT_DIR]
            for fname in files:
                rel = os.path.relpath(os.path.join(root, fname), abs_directory)
                if not rel.startswith('.vault__'):
                    working_files += 1

        shutil.rmtree(sg_dir)

        return dict(backup_path   = backup_path,
                    backup_size   = os.path.getsize(backup_path),
                    working_files = working_files,
                    sg_vault_dir  = sg_dir)

    def restore_from_backup(self, zip_path: str, directory: str) -> dict:
        """Restore a vault from a .vault__*.zip backup into the given directory."""
        import json as _json

        if not os.path.isfile(zip_path):
            raise RuntimeError(f'Backup zip not found: {zip_path}')

        abs_directory = os.path.abspath(directory)
        sg_dir        = os.path.join(abs_directory, SG_VAULT_DIR)

        if os.path.isdir(sg_dir):
            raise RuntimeError(f'Vault already exists in {directory} — remove .sg_vault/ first')

        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            if not any(n.startswith(SG_VAULT_DIR + '/') or n.startswith(SG_VAULT_DIR + os.sep)
                       for n in names):
                raise RuntimeError(f'Zip does not look like a vault backup: {zip_path}')
            zf.extractall(abs_directory)

        storage           = Vault__Storage()
        local_config_path = storage.local_config_path(abs_directory)
        vault_key_path    = storage.vault_key_path(abs_directory)

        vault_id  = None
        branch_id = None
        if os.path.isfile(local_config_path):
            with open(local_config_path, 'r') as f:
                cfg = _json.load(f)
            branch_id = cfg.get('my_branch_id', '')

        if os.path.isfile(vault_key_path):
            with open(vault_key_path, 'r') as f:
                vault_key = f.read().strip()
            keys     = self.crypto.derive_keys_from_vault_key(vault_key)
            vault_id = keys['vault_id']

        return dict(directory = abs_directory,
                    vault_id  = vault_id or '',
                    branch_id = branch_id or '')
