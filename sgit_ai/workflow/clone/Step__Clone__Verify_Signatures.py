"""Step — with feature 'signatures-required', refuse a clone whose history does not verify.

Pull has refused unsigned / bad / no-key incoming commits since the feature
existed; clone did not, so a newcomer cloned an unsigned head without a word
(threat model TM-R04). This step runs once every commit is local and before
the clone registers a branch or writes a file, and applies pull's rule to every
commit made since the policy was switched on (the `signed-since-` feature that
`sgit vault format --feature signatures-required` records), down to the shallow
boundary on --depth. A vault whose policy predates that record: the head must
verify (its older, pre-policy history is not held against a new clone).
"""
import os

from sgit_ai.safe_types.Safe_Str__Step_Name               import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Step                                import Step


class Step__Clone__Verify_Signatures(Step):
    name          = Safe_Str__Step_Name('verify-signatures')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        named_commit_id = str(input.named_commit_id) if input.named_commit_id else ''
        index_id        = str(input.branch_index_file_id) if input.branch_index_file_id else ''
        if not named_commit_id or not index_id:
            return input
        from sgit_ai.storage.Vault__Format                 import Vault__Format, FEATURE_SIG_REQUIRED
        sg_dir    = str(input.sg_dir)
        directory = str(input.directory)
        read_key  = bytes.fromhex(str(input.read_key_hex))
        workspace.ensure_managers(sg_dir)
        index_path = workspace.storage.index_path(directory, index_id)
        if not os.path.isfile(index_path):                   # a single-branch vault with no index: no policy to apply
            return input
        index = workspace.branch_manager.load_branch_index(directory, index_id, read_key)   # present but unreadable: fail closed
        if not Vault__Format().has_feature(index, FEATURE_SIG_REQUIRED):
            return input

        from sgit_ai.core.Vault__Components                 import Vault__Components
        from sgit_ai.core.Vault__Errors                     import Vault__Signature_Error
        from sgit_ai.core.actions.verify.Vault__Key_Fetch   import Vault__Key_Fetch
        from sgit_ai.core.actions.verify.Vault__Signatures  import Vault__Signatures
        workspace.progress('step', 'Verifying commit signatures (vault requires signed commits)')
        crypto = workspace.sync_client.crypto
        c      = Vault__Components(vault_id             = str(input.vault_id),
                                   read_key             = read_key,
                                   branch_index_file_id = index_id,
                                   sg_dir               = sg_dir,
                                   storage              = workspace.storage,
                                   pki                  = workspace.pki,
                                   obj_store            = workspace.obj_store,
                                   ref_manager          = workspace.ref_manager,
                                   key_manager          = workspace.key_manager,
                                   branch_manager       = workspace.branch_manager)
        bounds = {str(b) for b in (input.shallow_boundaries or [])}
        range_stop = {str(input.range_from)} if getattr(input, 'range_from', None) else set()   # clone-range: history starts after it
        recorded = Vault__Format().sig_anchor_of(index)
        anchor   = self._anchor_commits(sg_dir, recorded)
        limit    = 0 if (anchor or (recorded and bounds)) else 1    # no recorded start (policy set before 0.21): the head must verify
        report = Vault__Signatures(crypto=crypto, key_fetch=Vault__Key_Fetch(crypto=crypto, api=workspace.sync_client.api)
                                   ).verify_chain(c, read_key, named_commit_id, stop_at=anchor | range_stop, limit=limit,
                                                  index=index, boundaries=bounds)
        if report['first_failure']:
            cid, status = report['first_failure']
            raise Vault__Signature_Error(
                f'this vault requires signed commits and commit {cid} in its history is {status}; '
                f'the clone was refused before any file was written. Ask the vault owner; if the owner '
                f'relaxes the policy (`sgit vault format --remove-feature signatures-required`), clone again.')
        return input

    def _anchor_commits(self, sg_dir: str, anchor_hex: str) -> set:
        """The local commit id(s) the recorded `signed-since-` prefix names; empty when
        none is recorded or that commit is not in this clone."""
        if not anchor_hex:
            return set()
        data_dir = os.path.join(sg_dir, 'bare', 'data')
        prefix   = 'obj-cas-imm-' + anchor_hex
        try:
            return {name for name in os.listdir(data_dir) if name.startswith(prefix)}
        except OSError:
            return set()
