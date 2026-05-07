import hashlib
import json
import os
import zipfile

from osbot_utils.type_safe.Type_Safe import Type_Safe

MANIFEST_FILE = 'manifest.json'
SG_VAULT_DIR  = '.sg_vault'


class Vault__Restore(Type_Safe):

    def restore(self, zip_source: str, destination: str,
                mode: str = 'expanded', vault_key: str = None) -> dict:
        zip_path    = self._resolve_source(zip_source)
        destination = os.path.abspath(destination)
        self._validate_destination(destination)
        self._verify_integrity(zip_path)
        sg_dir, vault_id = self._extract_bare(zip_path, destination)
        if mode == 'expanded':
            resolved_key = self._resolve_vault_key(zip_path, vault_key)
            t_ms = self._extract_working_copy(destination, sg_dir, resolved_key)
        else:
            t_ms = 0
        return dict(destination  = destination,
                    sg_dir       = sg_dir,
                    vault_id     = vault_id,
                    mode         = mode,
                    t_checkout_ms = t_ms)

    def _resolve_source(self, zip_source: str) -> str:
        """Resolve zip_source: plain path or vault-dir:backup-id form."""
        if ':' in zip_source and not os.path.isabs(zip_source):
            parts        = zip_source.split(':', 1)
            vault_dir    = parts[0]
            backup_id    = parts[1]
            backups_dir  = os.path.join(vault_dir, SG_VAULT_DIR, 'backups')
            matches      = [f for f in os.listdir(backups_dir)
                            if f.endswith('.zip') and backup_id in f]
            if len(matches) == 0:
                raise RuntimeError(f'No backup matches "{backup_id}" in {backups_dir}')
            if len(matches) > 1:
                raise RuntimeError(
                    f'Ambiguous backup id "{backup_id}" — matches: ' + ', '.join(sorted(matches))
                )
            return os.path.abspath(os.path.join(backups_dir, matches[0]))
        return os.path.abspath(zip_source)

    def _validate_destination(self, destination: str) -> None:
        """Destination must be empty or non-existent, and not inside an existing vault."""
        if os.path.exists(destination):
            entries = [e for e in os.listdir(destination) if not e.startswith('.')]
            if entries or any(os.path.isfile(os.path.join(destination, e))
                              for e in os.listdir(destination)):
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
        """Verify sha256 sidecar if present. Returns hex digest."""
        sidecar = zip_path + '.sha256'
        with open(zip_path, 'rb') as f:
            actual = hashlib.sha256(f.read()).hexdigest()
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

    def _extract_bare(self, zip_path: str, destination: str):
        """Extract bare vault structure. Returns (sg_dir, vault_id)."""
        os.makedirs(destination, exist_ok=True)
        sg_dir = os.path.join(destination, SG_VAULT_DIR)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            for name in names:
                if name == 'VAULT-KEY':
                    continue
                if name == MANIFEST_FILE:
                    continue
                zf.extract(name, destination)

        vault_id = ''
        local_config = os.path.join(sg_dir, 'local', 'config.json')
        if os.path.isfile(local_config):
            with open(local_config) as f:
                cfg = json.load(f)
            vault_id = cfg.get('vault_id', '')

        return sg_dir, vault_id

    def _resolve_vault_key(self, zip_path: str, vault_key: str = None) -> str:
        """Return vault_key: from arg, from zip VAULT-KEY entry, or raise."""
        if vault_key:
            return vault_key
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'VAULT-KEY' in zf.namelist():
                return zf.read('VAULT-KEY').decode().strip()
        raise RuntimeError(
            'Vault key required for expanded restore but not provided and not in zip.\n'
            "Re-run with --mode bare, or supply the key with --key <vault-key>."
        )

    def _extract_working_copy(self, destination: str, sg_dir: str, vault_key: str) -> int:
        """Check out HEAD working copy into destination. Returns checkout time in ms."""
        import time
        from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
        from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
        from sgit_ai.crypto.Vault__Key_Manager   import Vault__Key_Manager
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Commit       import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree

        crypto    = Vault__Crypto()
        pki       = PKI__Crypto()
        keys      = crypto.derive_keys_from_vault_key(vault_key)
        read_key  = bytes.fromhex(keys['read_key'])

        obj_store  = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        vc         = Vault__Commit(crypto=crypto, pki=pki,
                                   object_store=obj_store, ref_manager=ref_manager)
        sub_tree   = Vault__Sub_Tree(crypto=crypto, obj_store=obj_store)

        named_ref_id = self._find_named_ref(sg_dir, keys)
        if not named_ref_id:
            return 0

        ref_data = ref_manager.read_ref(named_ref_id, read_key)
        if not ref_data:
            return 0
        commit_id = ref_data.get('commit_id', '')
        if not commit_id:
            return 0

        t0         = time.monotonic()
        commit_obj = vc.load_commit(commit_id, read_key)
        sub_tree.checkout(destination, str(commit_obj.tree_id), read_key)
        return int((time.monotonic() - t0) * 1000)

    def _find_named_ref(self, sg_dir: str, keys: dict) -> str:
        """Find the named ref id from the branch index."""
        from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store

        index_dir = os.path.join(sg_dir, 'bare', 'indexes')
        if not os.path.isdir(index_dir):
            return ''
        crypto    = Vault__Crypto()
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        read_key  = bytes.fromhex(keys['read_key'])
        index_id  = keys.get('branch_index_file_id', '')
        if not index_id:
            return ''
        index_data = obj_store.load(index_id, read_key)
        if not index_data:
            return ''
        index  = json.loads(index_data)
        branches = index.get('branches', {})
        if not branches:
            return ''
        first_branch = next(iter(branches.values()))
        return first_branch.get('named_ref_id', '')

    def list_backups(self, directory: str) -> list:
        """List backups in directory/.sg_vault/backups/."""
        from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup
        return Vault__Backup().list_backups(directory)
