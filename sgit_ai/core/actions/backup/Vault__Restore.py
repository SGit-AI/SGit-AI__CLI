import hashlib
import json
import os
import zipfile

from osbot_utils.type_safe.Type_Safe import Type_Safe

MANIFEST_FILE = 'manifest.json'
SG_VAULT_DIR  = '.sg_vault'


class Vault__Restore(Type_Safe):

    def restore(self, zip_source: str, destination: str,
                mode: str = 'expanded', vault_key: str = None,
                on_progress: callable = None) -> dict:
        zip_path    = self._resolve_source(zip_source)
        destination = os.path.abspath(destination)
        self._validate_destination(destination)
        self._verify_integrity(zip_path)
        sg_dir, vault_files = self._extract_bare(zip_path, destination, on_progress)
        vault_id      = ''
        working_files = []
        if mode == 'expanded':
            resolved_key  = self._resolve_vault_key(zip_path, vault_key)
            vault_id      = self._derive_vault_id(resolved_key)
            working_files = self._extract_working_copy(destination, sg_dir,
                                                       resolved_key, on_progress)
        return dict(destination   = destination,
                    sg_dir        = sg_dir,
                    vault_id      = vault_id,
                    mode          = mode,
                    vault_files   = vault_files,
                    working_files = working_files,
                    t_checkout_ms = len(working_files))

    def _resolve_source(self, zip_source: str) -> str:
        if os.path.isfile(zip_source):
            return os.path.abspath(zip_source)
        abs_check = os.path.abspath(zip_source)
        if os.path.isfile(abs_check):
            return abs_check

        colon_pos = zip_source.rfind(':')
        if colon_pos > 0:
            potential_dir = zip_source[:colon_pos]
            backup_id     = zip_source[colon_pos + 1:]
            if os.path.isdir(potential_dir):
                backups_dir = os.path.join(potential_dir, SG_VAULT_DIR, 'backups')
                if os.path.isdir(backups_dir):
                    matches = [f for f in os.listdir(backups_dir)
                               if f.endswith('.zip') and backup_id in f]
                    if len(matches) == 0:
                        raise RuntimeError(f'No backup matches "{backup_id}" in {backups_dir}')
                    if len(matches) > 1:
                        raise RuntimeError(
                            f'Ambiguous backup id "{backup_id}" — matches: '
                            + ', '.join(sorted(matches))
                        )
                    return os.path.abspath(os.path.join(backups_dir, matches[0]))

        raise RuntimeError(f'Backup zip not found: {zip_source}')

    def _validate_destination(self, destination: str) -> None:
        if os.path.exists(destination) and os.listdir(destination):
            raise RuntimeError(f'Destination is not empty: {destination}')
        parent = os.path.dirname(destination)
        while True:
            if os.path.isdir(os.path.join(parent, SG_VAULT_DIR)):
                raise RuntimeError(
                    f'Cannot restore inside an existing vault: {parent}'
                )
            up = os.path.dirname(parent)
            if up == parent:
                break
            parent = up

    def _verify_integrity(self, zip_path: str) -> str:
        with open(zip_path, 'rb') as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        sidecar = zip_path + '.sha256'
        if os.path.isfile(sidecar):
            with open(sidecar) as f:
                expected = f.read().strip()
            if actual != expected:
                raise RuntimeError(
                    f'Integrity check failed: {zip_path}\n'
                    f'  expected: {expected}\n'
                    f'  actual:   {actual}'
                )
        return actual

    def _extract_bare(self, zip_path: str, destination: str,
                      on_progress: callable = None) -> tuple:
        os.makedirs(destination, exist_ok=True)
        sg_dir = os.path.join(destination, SG_VAULT_DIR)
        os.makedirs(sg_dir, exist_ok=True)

        extracted = []
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name in ('VAULT-KEY', MANIFEST_FILE):
                    continue
                zf.extract(name, sg_dir)
                extracted.append(name)
                if on_progress:
                    on_progress('vault', name)

        return sg_dir, extracted

    def _derive_vault_id(self, vault_key: str) -> str:
        try:
            from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
            return Vault__Crypto().derive_keys_from_vault_key(vault_key)['vault_id']
        except Exception:
            return ''

    def _resolve_vault_key(self, zip_path: str, vault_key: str = None) -> str:
        if vault_key:
            return vault_key
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'VAULT-KEY' in zf.namelist():
                return zf.read('VAULT-KEY').decode().strip()
        raise RuntimeError(
            'Vault key required for expanded restore but not provided and not in zip.\n'
            "Re-run with --mode bare, or supply the key with --key <vault-key>."
        )

    def _extract_working_copy(self, destination: str, sg_dir: str, vault_key: str,
                               on_progress: callable = None) -> list:
        from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto
        from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
        from sgit_ai.crypto.Vault__Key_Manager     import Vault__Key_Manager
        from sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager    import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Commit         import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree       import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Storage        import Vault__Storage

        crypto    = Vault__Crypto()
        pki       = PKI__Crypto()
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        read_key  = bytes.fromhex(keys['read_key'])

        obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        ref_manager    = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto)
        storage        = Vault__Storage()
        branch_manager = Vault__Branch_Manager(
            vault_path  = sg_dir,
            crypto      = crypto,
            key_manager = key_manager,
            ref_manager = ref_manager,
            storage     = storage,
        )
        vc       = Vault__Commit(crypto=crypto, pki=pki,
                                  object_store=obj_store, ref_manager=ref_manager)
        sub_tree = Vault__Sub_Tree(crypto=crypto, obj_store=obj_store)

        named_ref_id = self._find_named_ref(destination, keys, branch_manager)
        if not named_ref_id:
            return []

        commit_id = ref_manager.read_ref(named_ref_id, read_key)
        if not commit_id:
            return []

        commit_obj = vc.load_commit(commit_id, read_key)
        flat       = sub_tree.flatten(str(commit_obj.tree_id), read_key)
        written    = []
        for path, entry in flat.items():
            blob_id  = entry.get('blob_id', '')
            if not blob_id:
                continue
            ciphertext = obj_store.load(blob_id)
            content    = crypto.decrypt(read_key, ciphertext)
            dest_path  = os.path.join(destination, path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, 'wb') as f:
                f.write(content)
            written.append(path)
            if on_progress:
                on_progress('working', path)
        return written

    def _find_named_ref(self, directory: str, keys: dict, branch_manager) -> str:
        read_key = bytes.fromhex(keys['read_key'])
        index_id = keys.get('branch_index_file_id', '')
        if not index_id:
            return ''
        try:
            index = branch_manager.load_branch_index(directory, index_id, read_key)
        except Exception:
            return ''
        named_meta = branch_manager.get_branch_by_name(index, 'current')
        if not named_meta:
            return ''
        return str(named_meta.head_ref_id) if named_meta.head_ref_id else ''

    def list_backups(self, directory: str) -> list:
        from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup
        return Vault__Backup().list_backups(directory)
