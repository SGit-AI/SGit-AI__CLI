"""Step__Push__Upload_Objects on a REAL vault and a real Push__Workspace (the coverage file
next to this one drives the step with a stand-in workspace and never reaches the upload)."""
import os

import pytest

from tests._helpers.vault_test_env                        import Vault__Test_Env
from sgit_ai.core.actions.push.Vault__Sync__Push          import Vault__Sync__Push
from sgit_ai.safe_types.Safe_Str__Branch_Id               import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id               import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Index_Id                import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Read_Key                import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Ref_Id                  import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Write_Key               import Safe_Str__Write_Key
from sgit_ai.schemas.workflow.push.Schema__Push__State    import Schema__Push__State
from sgit_ai.workflow.push.Push__Workspace                import Push__Workspace
from sgit_ai.workflow.push.Step__Push__Upload_Objects     import Step__Push__Upload_Objects


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class Test_Step__Push__Upload_Objects:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_single_vault(files={'a.txt': 'a'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env  = self._env.restore(); self.sync = self.env.sync; self.d = self.env.vault_dir
        self.c    = self.sync._init_components(self.d)
        self.keys = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        config    = self.sync._read_local_config(self.d, self.c.storage)
        index     = self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key)
        self.meta = self.c.branch_manager.get_branch_by_id(index, str(config.my_branch_id))
        self.named = self.c.branch_manager.get_branch_by_name(index, 'current')
        self.events = []
        self.ws   = Push__Workspace(sync_client=Vault__Sync__Push(crypto=self.env.crypto, api=self.env.api),
                                    on_progress=lambda ev, msg, detail='': self.events.append((ev, msg)))

    def teardown_method(self):
        self.env.cleanup()

    def _state(self, clone_commit_id: str, remote_commit_id: str) -> Schema__Push__State:
        return Schema__Push__State(
            vault_id             = Safe_Str__Vault_Id(self.keys['vault_id']),
            read_key_hex         = Safe_Str__Read_Key(self.keys['read_key']),
            write_key_hex        = Safe_Str__Write_Key(self.keys['write_key']),
            branch_index_file_id = Safe_Str__Index_Id(self.keys['branch_index_file_id']),
            sg_dir               = Safe_Str__File_Path(self.c.sg_dir),
            directory            = Safe_Str__File_Path(self.d),
            clone_branch_id      = Safe_Str__Branch_Id(str(self.meta.branch_id)),
            clone_ref_id         = Safe_Str__Ref_Id(str(self.meta.head_ref_id)),
            named_ref_id         = Safe_Str__Ref_Id(str(self.named.head_ref_id)),
            clone_commit_id      = Safe_Str__Commit_Id(clone_commit_id),
            named_commit_id      = Safe_Str__Commit_Id(remote_commit_id),
            remote_commit_id     = Safe_Str__Commit_Id(remote_commit_id),
        )

    def test_nothing_to_upload_builds_the_managers_and_reports_the_step(self):
        out = Step__Push__Upload_Objects().execute(self._state(self.env.commit_id, self.env.commit_id), self.ws)
        assert int(out.n_objects_uploaded) == 0
        assert self.ws.obj_store is not None and self.ws.branch_manager is not None
        assert self.events == [('step', 'Uploading objects to server')]
        assert out.clone_commit_id == self.env.commit_id and out.remote_commit_id == self.env.commit_id

    def test_a_local_only_commit_fails_the_upload_with_the_wrapped_error(self):
        """Pins what the code does today: with something to upload, the step calls
        Vault__Batch.build_push_operations with keyword arguments that method does not take
        (clone_branch_id, and no ref_manager / clone_tree_entries / ...), so every real upload
        raises RuntimeError('Upload failed: ...') naming the TypeError, and nothing reaches
        the host. The live push path (Vault__Sync__Push) does not use this step."""
        _write(self.d, 'b.txt', 'b'); local = self.sync.commit(self.d, message='local only')['commit_id']
        before = dict(self.env.api._store)
        with pytest.raises(RuntimeError) as exc:
            Step__Push__Upload_Objects().execute(self._state(local, self.env.commit_id), self.ws)
        assert str(exc.value).startswith('Upload failed: ')
        assert isinstance(exc.value.__cause__, TypeError)
        assert 'clone_branch_id' in str(exc.value) or 'missing' in str(exc.value)
        assert self.env.api._store == before
