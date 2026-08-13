"""Step 3 — Download (or synthesise) the branch index file.

A branch index (idx-pid-muw-*) is OPTIONAL on the server. Vaults created or
edited only in the SG/App web UI commonly have NO branch index: the web writes
its working state to the clone branch (ref-pid-snw-web-ui) and advances the
named ref (ref-pid-muw-*) only on Publish/Push — and it does not write the
CLI-format branch index at all (it reads from bare/idx/, the CLI from
bare/indexes/; see team/.../04/16 vault-docs-review-part-1, Finding 3).

Per that documented single-branch fallback ("Single-branch vault (no branch
index) — both clients 404 and fall back to the HMAC-derived refFileId"), when
the index is absent we synthesise a single-branch index pointing the 'current'
named branch at the deterministic HMAC-derived named ref, so the remaining
clone steps proceed unchanged.

A 403 (Forbidden) on the index read is NOT treated as "no index" — that is an
access/permission problem (e.g. the vault requires an access key) and is
surfaced honestly rather than masked as a single-branch vault.
"""
from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.safe_types.Enum__Branch_Type                 import Enum__Branch_Type
from sgit_ai.safe_types.Enum__Fetch_Failure_Class         import Enum__Fetch_Failure_Class
from sgit_ai.schemas.Schema__Branch_Meta                  import Schema__Branch_Meta
from sgit_ai.schemas.Schema__Branch_Index                 import Schema__Branch_Index
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Download_Index(Step):
    name          = Safe_Str__Step_Name('download-index')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        vault_id  = str(input.vault_id)
        index_id  = str(input.branch_index_file_id)
        sg_dir    = str(input.sg_dir)
        read_key  = bytes.fromhex(str(input.read_key_hex))
        directory = str(input.directory)

        workspace.ensure_managers(sg_dir)
        workspace.progress('step', 'Downloading vault index')

        index_fid    = f'bare/indexes/{index_id}'
        idx_failures = {}
        idx_data     = workspace.sync_client.api.batch_read(vault_id, [index_fid],
                                                            failures=idx_failures)

        if idx_data.get(index_fid):
            # Multi-branch (v2) vault: an index exists on the server. Try to use it verbatim;
            # if it's malformed or missing 'current' (foreign schema, partial write, future
            # CLI bump, etc.) degrade to the single-branch fallback — interop contract v0 §9.
            # A 403 cannot reach this branch (batch_read returned data), so the only way to
            # land here is a successful read with a non-conformant payload.
            workspace.save_file(sg_dir, index_fid, idx_data[index_fid])
            named_meta, degrade_reason = self._try_use_present_index(
                workspace, directory, index_id, read_key)
            if named_meta is not None:
                named_branch_id = str(named_meta.branch_id)
                named_ref_id    = str(named_meta.head_ref_id)
            else:
                workspace.progress('step',
                    f'Index present but unusable ({degrade_reason}) — '
                    'single-branch fallback (named ref)')
                named_branch_id, named_ref_id = self._fallback_single_branch(
                    workspace, directory, vault_id, index_id, read_key)
        else:
            # No branch index on the server — single-branch fallback (see module docstring).
            self._raise_if_forbidden(idx_failures.get(index_fid), 'vault index')
            named_branch_id, named_ref_id = self._fallback_single_branch(
                workspace, directory, vault_id, index_id, read_key)

        data                    = input.json()
        data['named_branch_id'] = named_branch_id
        data['named_ref_id']    = named_ref_id
        data['index_id']        = index_id
        return Schema__Clone__State.from_json(data)

    def _raise_if_forbidden(self, failure, what: str) -> None:
        """Surface a 403 honestly instead of masking it as "no branch index"."""
        if failure is not None and failure.classification == Enum__Fetch_Failure_Class.FORBIDDEN:
            raise RuntimeError(
                f'Access denied reading the {what} (HTTP 403 Forbidden).\n'
                '  hint: this vault may require an access key, or your credentials lack '
                'permission for it.\n'
                '  hint: set/clear the access key in the web UI (Vault Settings -> Access Key) '
                'and verify your SGIT token.')

    def _try_use_present_index(self, workspace, directory: str, index_id: str,
                               read_key: bytes):
        """Attempt to parse + resolve the present index. Returns (named_meta, None)
        on success, or (None, reason_str) on degradation — interop contract v0 §9.

        Degrades on:
          - decrypt / parse failure (foreign schema, malformed branch_id, etc.)
          - successful parse but no branch matches name='current'
        """
        try:
            branch_index = workspace.branch_manager.load_branch_index(directory, index_id, read_key)
        except Exception as exc:
            return None, f'parse failed: {type(exc).__name__}'
        named_meta = workspace.branch_manager.get_branch_by_name(branch_index, 'current')
        if named_meta is None:
            return None, "no branch named 'current'"
        return named_meta, None

    def _fallback_single_branch(self, workspace, directory: str, vault_id: str,
                                index_id: str, read_key: bytes):
        """Synthesise a single-branch index pointing 'current' at the deterministic
        HMAC-derived named ref, persisting it locally so the remaining clone steps
        (download-branch-meta / create-clone-branch) run unchanged.

        Raises if the named ref is ALSO absent — nothing has been published to clone.
        """
        crypto = workspace.sync_client.crypto
        ref_id = 'ref-pid-muw-' + crypto.derive_ref_file_id(read_key, vault_id)

        # The named branch must actually exist on the server. If neither the index
        # NOR the named ref is present, there is nothing published to clone.
        ref_fid      = f'bare/refs/{ref_id}'
        ref_failures = {}
        ref_data     = workspace.sync_client.api.batch_read(vault_id, [ref_fid],
                                                            failures=ref_failures)
        if not ref_data.get(ref_fid):
            self._raise_if_forbidden(ref_failures.get(ref_fid), 'named branch ref')
            raise RuntimeError(
                'Nothing to clone: this vault has no branch index and no named ref '
                f'({ref_id}) on the server.\n'
                '  Two common causes:\n'
                '    1. The vault key or ID is incorrect — double-check the value you pasted.\n'
                '    2. The vault was created/edited only in the SG/App web UI and never '
                'Published.\n'
                '       Web edits live on the (unpublished) clone branch, not the named branch\n'
                '       the CLI clones. Open the vault in the web UI, click Publish/Push, then\n'
                '       re-run sgit clone.')

        named_branch = Schema__Branch_Meta(
            branch_id   = 'branch-named-' + crypto.derive_file_id(read_key, f'branch:current:{vault_id}'),
            name        = 'current',
            branch_type = Enum__Branch_Type.NAMED,
            head_ref_id = ref_id)
        synth_index = Schema__Branch_Index(schema='branch_index_v1', branches=[named_branch])
        workspace.branch_manager.save_branch_index(directory, synth_index, read_key,
                                                   index_file_id=index_id)
        workspace.progress('step',
                           'No branch index on server — single-branch fallback (named ref)')
        return str(named_branch.branch_id), ref_id
