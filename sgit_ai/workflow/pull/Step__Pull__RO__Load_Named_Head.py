"""Step 2 (read-only) — Load the named-branch HEAD for a read-only clone.

Replaces Step__Pull__Load_Branch_Info + Step__Pull__Fetch_Remote_Ref for the
read-only pull path. A read-only clone has NO clone branch, so this step does
NO clone-branch lookup (guard rails §8 #3/#4). It:

  1. resolves the tracked named branch via the Phase-1 helper
     (_tracked_branch_name, default 'current') and get_branch_by_name,
  2. records the previously-cached named HEAD (the walk stop-point reused by
     Step__Pull__Fetch_Missing as clone_commit_id),
  3. re-fetches the named-branch HEAD ref from the server (api.read only) and
     overwrites the local ref, then decrypts the new named HEAD.

Server interaction is limited to a single api.read(...) of the named ref —
NO api.write(...) — preserving the read-only / zero-knowledge guarantee.
"""
import os

from osbot_utils.type_safe.primitives.core.Safe_Str      import Safe_Str
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Ref_Id                 import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id
from sgit_ai.schemas.workflow.pull.Schema__Pull__State   import Schema__Pull__State
from sgit_ai.workflow.Step                               import Step


class Step__Pull__RO__Load_Named_Head(Step):
    name          = Safe_Str__Step_Name('ro-load-named-head')
    input_schema  = Schema__Pull__State
    output_schema = Schema__Pull__State

    def execute(self, input: Schema__Pull__State, workspace) -> Schema__Pull__State:
        directory = str(input.directory)
        sg_dir    = str(input.sg_dir)
        read_key  = bytes.fromhex(str(input.read_key_hex))
        vault_id  = str(input.vault_id)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Loading named-branch HEAD')

        branch_index_file_id = str(input.branch_index_file_id)
        if not branch_index_file_id:
            raise RuntimeError('No branch index found — is this a v2 vault?')

        branch_index = workspace.branch_manager.load_branch_index(
            directory, branch_index_file_id, read_key)

        branch_name = workspace.sync_client._tracked_branch_name(directory)
        named_meta  = workspace.branch_manager.get_branch_by_name(branch_index, branch_name)
        if not named_meta:
            raise RuntimeError(f'Named branch "{branch_name}" not found')

        named_ref_id      = str(named_meta.head_ref_id)
        _resolved_name    = getattr(named_meta, 'name', None)
        named_branch_name = str(_resolved_name) if _resolved_name else branch_name

        # Previously-cached named HEAD — the walk stop-point for fetch-missing.
        # The stop-point is only valid if its commit object is actually present
        # locally: a prior read command (e.g. `sgit status`) may have advanced the
        # cached ref pointer to a commit we never downloaded. Trusting that pointer
        # would make fetch-missing/checkout no-op and skip the new HEAD. So we use
        # it as the stop-point only when the object exists; otherwise we fall back
        # to no stop-point (download the full reachable graph — always safe).
        cached_named_commit_id = workspace.ref_manager.read_ref(named_ref_id, read_key) or ''
        if cached_named_commit_id and not workspace.obj_store.exists(cached_named_commit_id):
            cached_named_commit_id = ''

        # Re-fetch the named-branch HEAD ref from the server (read-only: api.read).
        named_ref_file_id = f'bare/refs/{named_ref_id}'
        remote_reachable  = False
        try:
            remote_ref_data = workspace.sync_client.api.read(vault_id, named_ref_file_id)
            if remote_ref_data:
                ref_path = os.path.join(sg_dir, named_ref_file_id)
                os.makedirs(os.path.dirname(ref_path), exist_ok=True)
                with open(ref_path, 'wb') as f:
                    f.write(remote_ref_data)
                remote_reachable = True
        except Exception as exc:
            workspace.progress('warn', f'Could not fetch remote ref: {exc}')

        named_commit_id = workspace.ref_manager.read_ref(named_ref_id, read_key) or ''

        return Schema__Pull__State(
            vault_key             = input.vault_key,
            directory             = input.directory,
            sg_dir                = input.sg_dir,
            vault_id              = input.vault_id,
            branch_index_file_id  = input.branch_index_file_id,
            read_key_hex          = input.read_key_hex,
            clone_branch_id       = None,                         # no clone branch on RO clones
            clone_ref_id          = None,
            named_ref_id          = Safe_Str__Ref_Id(named_ref_id),
            clone_commit_id       = Safe_Str__Commit_Id(cached_named_commit_id) if cached_named_commit_id else None,
            named_branch_name     = Safe_Str(named_branch_name) if named_branch_name else None,
            named_commit_id       = Safe_Str__Commit_Id(named_commit_id) if named_commit_id else None,
            remote_reachable      = remote_reachable,
        )
