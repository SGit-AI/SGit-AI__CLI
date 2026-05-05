"""Tests for Workflow__Clone__Transfer — 5-step transfer-import pipeline."""
import os
import shutil
import tempfile

from sgit_ai.schemas.workflow.clone.Schema__Transfer__State     import Schema__Transfer__State
from sgit_ai.workflow.clone.Step__Transfer__Receive             import Step__Transfer__Receive
from sgit_ai.workflow.clone.Step__Transfer__Check_Directory     import Step__Transfer__Check_Directory
from sgit_ai.workflow.clone.Step__Transfer__Init_Vault          import Step__Transfer__Init_Vault
from sgit_ai.workflow.clone.Step__Transfer__Write_Files         import Step__Transfer__Write_Files
from sgit_ai.workflow.clone.Step__Transfer__Commit_And_Configure import Step__Transfer__Commit_And_Configure
from sgit_ai.workflow.clone.Workflow__Clone__Transfer           import Workflow__Clone__Transfer
from sgit_ai.workflow.clone.Transfer__Workspace                 import Transfer__Workspace


class Test_Workflow__Clone__Transfer__Structure:

    def test_workflow_name(self):
        assert Workflow__Clone__Transfer().workflow_name() == 'clone-transfer'

    def test_workflow_version(self):
        assert Workflow__Clone__Transfer().workflow_version() == '1.0.0'

    def test_step_count(self):
        assert len(Workflow__Clone__Transfer().step_classes()) == 5

    def test_step_order(self):
        classes = Workflow__Clone__Transfer().step_classes()
        assert classes[0] is Step__Transfer__Receive
        assert classes[1] is Step__Transfer__Check_Directory
        assert classes[2] is Step__Transfer__Init_Vault
        assert classes[3] is Step__Transfer__Write_Files
        assert classes[4] is Step__Transfer__Commit_And_Configure

    def test_step_names(self):
        names = [sc().step_name() for sc in Workflow__Clone__Transfer().step_classes()]
        assert names == [
            'transfer-receive',
            'transfer-check-directory',
            'transfer-init-vault',
            'transfer-write-files',
            'transfer-commit-and-configure',
        ]

    def test_all_steps_use_transfer_state_schema(self):
        for sc in Workflow__Clone__Transfer().step_classes():
            step = sc()
            assert step.input_schema  is Schema__Transfer__State
            assert step.output_schema is Schema__Transfer__State

    def test_workflow_is_registered(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        known = CLI__Dev__Workflow._known_workflows()
        assert 'clone-transfer' in known


class Test_Schema__Transfer__State:

    def test_round_trip_invariant(self):
        assert Schema__Transfer__State.from_json(
            Schema__Transfer__State().json()
        ).json() == Schema__Transfer__State().json()

    def test_initial_fields_are_none(self):
        s = Schema__Transfer__State()
        assert s.token_str  is None
        assert s.directory  is None
        assert s.file_count is None
        assert s.new_token  is None
        assert s.vault_id   is None
        assert s.branch_id  is None
        assert s.share_token is None


class Test_Transfer__Workspace:

    def test_workspace_has_sync_client(self):
        ws = Transfer__Workspace()
        assert ws.sync_client    is None
        assert ws.on_progress    is None
        assert ws.received_files is None

    def test_progress_silent_when_no_callback(self):
        ws = Transfer__Workspace()
        ws.progress('step', 'test')   # must not raise


class Test_Step__Transfer__Check_Directory:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix='xfer_chkdir_')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _workspace(self):
        ws = Transfer__Workspace()
        ws.on_progress = None
        return ws

    def test_creates_new_directory(self):
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        target = os.path.join(self.tmp, 'new_dir')
        state  = Schema__Transfer__State(directory=Safe_Str__File_Path(target))
        step   = Step__Transfer__Check_Directory()
        step.execute(state, self._workspace())
        assert os.path.isdir(target)

    def test_raises_if_directory_not_empty(self):
        import pytest
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        target = os.path.join(self.tmp, 'nonempty')
        os.makedirs(target)
        open(os.path.join(target, 'file.txt'), 'w').close()
        state = Schema__Transfer__State(directory=Safe_Str__File_Path(target))
        step  = Step__Transfer__Check_Directory()
        with pytest.raises(RuntimeError, match='not empty'):
            step.execute(state, self._workspace())


class Test_Step__Transfer__Write_Files:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix='xfer_write_')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _workspace(self, files: dict):
        ws = Transfer__Workspace()
        ws.received_files = files
        return ws

    def test_writes_bytes_file(self):
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        files = {'hello.txt': b'hello world'}
        state = Schema__Transfer__State(directory=Safe_Str__File_Path(self.tmp))
        step  = Step__Transfer__Write_Files()
        step.execute(state, self._workspace(files))
        assert open(os.path.join(self.tmp, 'hello.txt'), 'rb').read() == b'hello world'

    def test_writes_str_file_as_utf8(self):
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        files = {'note.txt': 'text content'}
        state = Schema__Transfer__State(directory=Safe_Str__File_Path(self.tmp))
        step  = Step__Transfer__Write_Files()
        step.execute(state, self._workspace(files))
        assert open(os.path.join(self.tmp, 'note.txt'), 'rb').read() == b'text content'

    def test_skips_share_prefixed_files(self):
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        files = {
            '__share__/meta.json': b'should be skipped',
            'real.txt': b'should be written',
        }
        state = Schema__Transfer__State(directory=Safe_Str__File_Path(self.tmp))
        step  = Step__Transfer__Write_Files()
        step.execute(state, self._workspace(files))
        assert not os.path.exists(os.path.join(self.tmp, '__share__', 'meta.json'))
        assert os.path.isfile(os.path.join(self.tmp, 'real.txt'))

    def test_creates_nested_directories(self):
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        files = {'a/b/c.txt': b'nested'}
        state = Schema__Transfer__State(directory=Safe_Str__File_Path(self.tmp))
        step  = Step__Transfer__Write_Files()
        step.execute(state, self._workspace(files))
        assert os.path.isfile(os.path.join(self.tmp, 'a', 'b', 'c.txt'))
