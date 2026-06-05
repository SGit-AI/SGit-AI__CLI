"""Tests for Step__Fetch__Derive_Keys on a read-only clone (architect contract §4.2 / §7.1).

Same shape as the pull derive-keys step: routes through
sync_client._derive_keys_for_directory so it works on an RO clone with no vault_key.
"""
from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State import Schema__Fetch__State
from sgit_ai.safe_types.Safe_Str__File_Path             import Safe_Str__File_Path
from sgit_ai.workflow.fetch.Step__Fetch__Derive_Keys     import Step__Fetch__Derive_Keys


class _Workspace:
    """Minimal workspace exposing only what Step__Fetch__Derive_Keys touches."""

    def __init__(self, sync_client):
        self.sync_client = sync_client

    def progress(self, tag, msg):
        pass


class Test_Step__Fetch__Derive_Keys__ReadOnly:

    def test_step_succeeds_against_ro_clone(self, read_only_clone):
        ws    = _Workspace(read_only_clone['sync'])
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(read_only_clone['ro_dir']))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)        # must not raise
        assert out is not None

    def test_output_carries_vault_id(self, read_only_clone):
        ws    = _Workspace(read_only_clone['sync'])
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(read_only_clone['ro_dir']))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)
        assert str(out.vault_id) == read_only_clone['vault_id']

    def test_output_carries_branch_index_file_id(self, read_only_clone):
        ws    = _Workspace(read_only_clone['sync'])
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(read_only_clone['ro_dir']))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)
        assert str(out.branch_index_file_id).startswith('idx-pid-muw-')

    def test_output_carries_read_key_hex(self, read_only_clone):
        ws    = _Workspace(read_only_clone['sync'])
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(read_only_clone['ro_dir']))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)
        assert str(out.read_key_hex) == read_only_clone['read_key_hex']
