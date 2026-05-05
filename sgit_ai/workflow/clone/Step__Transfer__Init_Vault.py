"""Step 3 (transfer) — Initialise a new local vault from a generated simple token."""
from sgit_ai.safe_types.Safe_Str__Step_Name                  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.clone.Schema__Transfer__State  import Schema__Transfer__State
from sgit_ai.workflow.Step                                   import Step


class Step__Transfer__Init_Vault(Step):
    name          = Safe_Str__Step_Name('transfer-init-vault')
    input_schema  = Schema__Transfer__State
    output_schema = Schema__Transfer__State

    def execute(self, input: Schema__Transfer__State, workspace) -> Schema__Transfer__State:
        from sgit_ai.crypto.simple_token.Simple_Token__Wordlist import Simple_Token__Wordlist
        from sgit_ai.crypto.simple_token.Simple_Token          import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token      import Safe_Str__Simple_Token
        from sgit_ai.core.Vault__Sync                       import Vault__Sync

        directory = str(input.directory) if input.directory else ''
        workspace.progress('step', 'Initialising new vault')

        new_token = str(Simple_Token__Wordlist().setup().generate())
        Vault__Sync(crypto=workspace.sync_client.crypto,
                    api=workspace.sync_client.api).init(directory,
                                                        token=new_token,
                                                        allow_nonempty=True)

        st       = Simple_Token(token=Safe_Str__Simple_Token(new_token))
        vault_id = st.transfer_id()

        data               = input.json()
        data['new_token']  = new_token
        data['vault_id']   = vault_id
        return Schema__Transfer__State.from_json(data)
