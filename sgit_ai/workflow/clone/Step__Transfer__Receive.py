"""Step 1 (transfer) — Download files from a SG/Send transfer bundle."""
from sgit_ai.safe_types.Safe_Str__Step_Name                              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__File_Count                            import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.clone.Schema__Transfer__State              import Schema__Transfer__State
from sgit_ai.workflow.Step                                               import Step


class Step__Transfer__Receive(Step):
    name          = Safe_Str__Step_Name('transfer-receive')
    input_schema  = Schema__Transfer__State
    output_schema = Schema__Transfer__State

    def execute(self, input: Schema__Transfer__State, workspace) -> Schema__Transfer__State:
        from sgit_ai.network.api.API__Transfer        import API__Transfer
        from sgit_ai.network.transfer.Vault__Transfer import Vault__Transfer

        token_str = str(input.token_str) if input.token_str else ''
        if not token_str:
            raise RuntimeError('token_str is required for transfer clone')

        workspace.progress('step', f'Downloading transfer: {token_str}')

        debug_log      = getattr(workspace.sync_client.api, 'debug_log', None)
        api            = API__Transfer(debug_log=debug_log)
        api.setup()
        transfer       = Vault__Transfer(api=api, crypto=workspace.sync_client.crypto)
        receive_result = transfer.receive(token_str)

        workspace.received_files = receive_result.get('files', {})
        file_count               = len(workspace.received_files)

        data               = input.json()
        data['file_count'] = file_count
        return Schema__Transfer__State.from_json(data)
