"""Step 3 (transfer) — DISABLED pending Simple Token security rework.

Originally: initialise a new local vault from a generated simple token. This
step is reached when a user runs `sgit clone <simple-token>` and the token is
NOT found as a SGit-AI vault but IS found as a SG/Send transfer — at which
point the original code minted a NEW Simple Token via Simple_Token__Wordlist
and called Vault__Sync.init(token=new_token), persisting an insecure construct
to disk.

The four `sgit vault export` / `vault share` / `share send` / `share publish`
CLI commands are disabled at the dispatcher (CLI__Disabled_Command). This
step covers the covert create-path the architect flagged as F2 in
team/explorer/architect/reviews/06/13/v0__architect-review__cli-simple-token-disablement.md:
without it, a user could still mint a Simple Token via the kept `sgit clone`
surface.

The backend implementation (Simple_Token__Wordlist.generate, Vault__Sync.init's
`token=` parameter, Workflow__Clone__Transfer) is preserved so the security
rework can refactor in place; only this step's user-reachable execute() refuses.
"""
from sgit_ai.safe_types.Safe_Str__Step_Name                  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Transfer__State  import Schema__Transfer__State
from sgit_ai.workflow.Step                                   import Step


class Step__Transfer__Init_Vault(Step):
    name          = Safe_Str__Step_Name('transfer-init-vault')
    input_schema  = Schema__Transfer__State
    output_schema = Schema__Transfer__State

    def execute(self, input: Schema__Transfer__State, workspace) -> Schema__Transfer__State:
        raise RuntimeError(
            'sgit clone <simple-token>: transfer-clone is temporarily disabled '
            'pending a security rework of the Simple Token scheme.\n'
            '  This path would mint a new Simple Token at the destination, '
            'which is the construct under rework.\n'
            '  The backend implementation is preserved and will be re-exposed '
            'once the new token scheme lands.\n'
            '  Cloning an existing vault by vault key (passphrase:vault_id) is '
            'unaffected.')
