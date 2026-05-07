import json
import os
import sys

from sgit_ai.safe_types.Safe_Str__Base_URL       import Safe_Str__Base_URL
from sgit_ai.safe_types.Safe_Str__Step_Name      import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Vault_Id       import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                       import Step


class Step__Move__Validate_Local(Step):
    name          = Safe_Str__Step_Name('validate-local')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
        from sgit_ai.storage.Vault__Storage                  import Vault__Storage
        from sgit_ai.network.api.Vault__API                  import DEFAULT_BASE_URL

        directory = str(input.directory)
        storage   = Vault__Storage()
        sg_dir    = storage.sg_vault_dir(directory)
        if not os.path.isdir(sg_dir):
            raise RuntimeError(f'Not a vault: {directory}')

        if not input.dry_run:
            crypto = Vault__Crypto()
            status = Vault__Sync__Status(crypto=crypto).status(directory)
            if not status.get('clean', True):
                raise RuntimeError(
                    'Vault has uncommitted changes — commit or stash before running vault move.'
                )

        local_config_path = storage.local_config_path(directory)
        vault_id       = ''
        key_generation = 1
        api_url        = DEFAULT_BASE_URL
        vault_key_str  = ''
        if os.path.isfile(local_config_path):
            with open(local_config_path) as f:
                cfg = json.load(f)
            vault_id       = cfg.get('vault_id', '') or ''
            key_generation = cfg.get('key_generation', 1) or 1
            api_url        = cfg.get('api_url', '') or DEFAULT_BASE_URL

        if not vault_id:
            vault_key_path = storage.vault_key_path(directory)
            if os.path.isfile(vault_key_path):
                with open(vault_key_path) as f:
                    vault_key_str = f.read().strip()
                try:
                    vault_id = Vault__Crypto().derive_keys_from_vault_key(vault_key_str)['vault_id']
                except Exception as e:
                    print(f'warning: could not derive vault_id from vault_key: {e}', file=sys.stderr)

        if not vault_id:
            raise RuntimeError(
                'Could not determine old vault_id from local config or vault key. '
                'The move would produce an ambiguously-named backup and orphan state. '
                'Aborting before any destructive change.'
            )

        obj_count = 0
        data_dir  = storage.bare_data_dir(directory)
        if os.path.isdir(data_dir):
            obj_count = sum(1 for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-'))

        if not input.dry_run:
            self._verify_commit_graph(directory, sg_dir, storage, vault_key_str, vault_id)

        return Schema__Move__State(
            directory      = input.directory,
            new_vault_key  = input.new_vault_key,
            target_api_url = input.target_api_url,
            reason         = input.reason,
            dry_run        = input.dry_run,
            old_vault_id   = Safe_Str__Vault_Id(vault_id) if vault_id else None,
            old_api_url    = Safe_Str__Base_URL(api_url),
            object_count   = Safe_UInt__Vault_Version(obj_count),
            key_generation = Safe_UInt__Vault_Version(key_generation),
        )

    def _verify_commit_graph(self, directory: str, sg_dir: str,
                              storage, vault_key_str: str, vault_id: str) -> None:
        from sgit_ai.crypto.Vault__Crypto         import Vault__Crypto
        from sgit_ai.crypto.PKI__Crypto           import PKI__Crypto
        from sgit_ai.storage.Vault__Commit        import Vault__Commit
        from sgit_ai.storage.Vault__Object_Store  import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager   import Vault__Ref_Manager

        crypto    = Vault__Crypto()
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        ref_mgr   = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        vc        = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                                  object_store=obj_store, ref_manager=ref_mgr)

        # Resolve read_key
        if vault_key_str:
            try:
                keys     = crypto.derive_keys_from_vault_key(vault_key_str)
                read_key = keys['read_key_bytes']
            except Exception:
                return  # Cannot derive keys; skip graph walk (will fail at push anyway)
        else:
            vault_key_path = storage.vault_key_path(directory)
            if not os.path.isfile(vault_key_path):
                return
            with open(vault_key_path) as f:
                vault_key_str = f.read().strip()
            try:
                keys     = crypto.derive_keys_from_vault_key(vault_key_str)
                read_key = keys['read_key_bytes']
            except Exception:
                return

        # Collect all branch HEAD commit IDs from ref files
        head_commit_ids = self._collect_head_commit_ids(sg_dir, storage, ref_mgr, read_key)
        if not head_commit_ids:
            return  # Empty vault or no refs — nothing to walk

        missing         = []
        visited_commits = set()
        visited_trees   = set()
        visited_blobs   = set()

        for head_commit_id in head_commit_ids:
            queue = [head_commit_id]
            while queue:
                cid = queue.pop()
                if not cid or cid in visited_commits:
                    continue
                visited_commits.add(cid)
                if not obj_store.exists(cid):
                    missing.append(cid)
                    continue
                try:
                    commit = vc.load_commit(cid, read_key)
                except Exception:
                    # Cannot decrypt; treat as present but unreadable — skip subtree
                    continue
                tree_id = str(commit.tree_id) if commit.tree_id else ''
                if tree_id and tree_id not in visited_trees:
                    self._walk_tree(tree_id, vc, obj_store, read_key,
                                    visited_trees, visited_blobs, missing)
                for parent_id in (commit.parents or []):
                    pid = str(parent_id)
                    if pid and pid not in visited_commits:
                        queue.append(pid)

        if missing:
            examples = ', '.join(missing[:3])
            raise RuntimeError(
                f'Local vault is missing {len(missing)} object(s) referenced by the '
                f'commit graph (e.g. {examples}). The move would ship an incomplete '
                f'vault to the server. Run `sgit pull` or `sgit fetch` first to '
                f'complete the local clone before retrying vault move.'
            )

    def _collect_head_commit_ids(self, sg_dir: str, storage,
                                  ref_mgr, read_key: bytes) -> list:
        """Return commit IDs pointed to by all local ref files."""
        head_ids = []
        for ref_id in ref_mgr.list_refs():
            try:
                commit_id = ref_mgr.read_ref(ref_id, read_key)
                if commit_id and commit_id.startswith('obj-cas-imm-'):
                    head_ids.append(commit_id)
            except Exception:
                continue
        return head_ids

    def _walk_tree(self, tree_id: str, vc, obj_store,
                   read_key: bytes, visited_trees: set,
                   visited_blobs: set, missing: list) -> None:
        if tree_id in visited_trees:
            return
        visited_trees.add(tree_id)
        if not obj_store.exists(tree_id):
            missing.append(tree_id)
            return
        try:
            tree = vc.load_tree(tree_id, read_key)
        except Exception:
            return
        for entry in (tree.entries or []):
            blob_id = str(entry.blob_id) if entry.blob_id else ''
            sub_tree_id = str(entry.tree_id) if entry.tree_id else ''
            if blob_id and blob_id not in visited_blobs:
                visited_blobs.add(blob_id)
                if not obj_store.exists(blob_id):
                    missing.append(blob_id)
            if sub_tree_id:
                self._walk_tree(sub_tree_id, vc, obj_store, read_key,
                                visited_trees, visited_blobs, missing)
