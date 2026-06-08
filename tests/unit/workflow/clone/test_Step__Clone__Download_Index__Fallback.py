"""Tests for Step__Clone__Download_Index single-branch fallback.

Reproduces the "web-only vault" case: a vault that has a named ref
(ref-pid-muw-*) and reachable commits on the server but NO branch index
(idx-pid-muw-*) — exactly what the SG/App web UI produces. The fallback must
synthesise a single-branch index and clone successfully, instead of raising
"No branch index found on remote".
"""
import copy
import os
import tempfile
import shutil

import pytest

from sgit_ai.network.api.Vault__API__In_Memory            import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto                         import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Key               import Safe_Str__Vault_Key
from sgit_ai.safe_types.Enum__Fetch_Failure_Class         import Enum__Fetch_Failure_Class
from sgit_ai.schemas.Schema__Fetch_Failure                import Schema__Fetch_Failure
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.core.Vault__Sync                             import Vault__Sync
from sgit_ai.core.actions.clone.Vault__Sync__Clone        import Vault__Sync__Clone
from sgit_ai.workflow.Workflow__Runner                    import Workflow__Runner
from sgit_ai.workflow.clone.Clone__Workspace              import Clone__Workspace
from sgit_ai.workflow.clone.Step__Clone__Download_Index   import Step__Clone__Download_Index
from sgit_ai.workflow.clone.Workflow__Clone               import Workflow__Clone


class Test_Step__Clone__Download_Index__Fallback:

    _snapshot: dict = None
    VAULT_KEY = 'clonetest:webonly01'
    FILES     = {'hello.txt': 'hello from web-only vault', 'docs/readme.md': '# readme'}

    @classmethod
    def _build_snapshot(cls, vault_key, files):
        crypto    = Vault__Crypto()
        api       = Vault__API__In_Memory()
        api.setup()
        sync      = Vault__Sync(crypto=crypto, api=api)
        snap_dir  = tempfile.mkdtemp(prefix='clone_fb_src_')
        vault_dir = os.path.join(snap_dir, 'vault')

        sync.init(vault_dir, vault_key=vault_key)
        for rel_path, content in files.items():
            full = os.path.join(vault_dir, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        sync.commit(vault_dir, message='initial commit')
        sync.push(vault_dir)

        snapshot_store = copy.deepcopy(api._store)
        shutil.rmtree(snap_dir, ignore_errors=True)
        return {'crypto': crypto, 'snapshot_store': snapshot_store, 'vault_key': vault_key}

    @classmethod
    def setup_class(cls):
        cls._snapshot = cls._build_snapshot(cls.VAULT_KEY, cls.FILES)

    def setup_method(self):
        self.tmp        = tempfile.mkdtemp(prefix='clone_fb_dst_')
        self.clone_dir  = os.path.join(self.tmp, 'cloned')
        self.crypto     = self._snapshot['crypto']
        self.api        = Vault__API__In_Memory()
        self.api.setup()
        self.api._store = copy.deepcopy(self._snapshot['snapshot_store'])
        self.sync_clone = Vault__Sync__Clone(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- store-mutation helpers -----------------------------------------------

    def _drop(self, substring):
        for k in [k for k in self.api._store if substring in k]:
            del self.api._store[k]

    def _run_clone(self):
        wf = Workflow__Clone()
        ws = Clone__Workspace.create(wf.workflow_name(), self.tmp)
        ws.sync_client = self.sync_clone
        ws.on_progress = None
        initial = Schema__Clone__State(
            vault_key = Safe_Str__Vault_Key(self.VAULT_KEY),
            directory = Safe_Str__File_Path(self.clone_dir),
        )
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        return runner.run(input=initial)

    # -- tests ----------------------------------------------------------------

    def test_sanity__snapshot_has_index_and_ref(self):
        assert [k for k in self.api._store if 'bare/indexes/' in k] != []
        assert [k for k in self.api._store if 'bare/refs/'    in k] != []

    def test_missing_index__falls_back_and_clones(self):
        self._drop('bare/indexes/')                          # simulate web-only vault
        assert [k for k in self.api._store if 'bare/indexes/' in k] == []

        out = self._run_clone()

        assert os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))
        assert open(os.path.join(self.clone_dir, 'hello.txt')).read() == 'hello from web-only vault'
        assert os.path.isfile(os.path.join(self.clone_dir, 'docs', 'readme.md'))
        assert str(out.get('named_commit_id', '')).startswith('obj-cas-imm-')

    def test_missing_index__synthesises_named_branch_at_deterministic_ref(self):
        self._drop('bare/indexes/')
        out  = self._run_clone()
        keys = self.crypto.derive_keys_from_vault_key(self.VAULT_KEY)
        assert str(out.get('named_ref_id', ''))    == keys['ref_file_id']      # deterministic ref-pid-muw-*
        assert str(out.get('named_branch_id', '')).startswith('branch-named-')

    def test_missing_index_persists_local_index_for_downstream_steps(self):
        self._drop('bare/indexes/')
        self._run_clone()
        keys     = self.crypto.derive_keys_from_vault_key(self.VAULT_KEY)
        idx_path = os.path.join(self.clone_dir, '.sg_vault', 'bare', 'indexes',
                                keys['branch_index_file_id'])
        assert os.path.isfile(idx_path)                                        # synthesised + persisted

    def test_missing_index_and_ref__raises_clear_error(self):
        self._drop('bare/indexes/')
        self._drop('bare/refs/')
        with pytest.raises(RuntimeError) as exc:
            self._run_clone()
        msg = str(exc.value)
        assert 'Nothing to clone' in msg
        assert 'Publish'          in msg

    # -- forbidden guard (direct, real-object) --------------------------------

    def test_forbidden_index__raises_access_denied_not_no_index(self):
        step    = Step__Clone__Download_Index()
        failure = Schema__Fetch_Failure(classification=Enum__Fetch_Failure_Class.FORBIDDEN)
        with pytest.raises(RuntimeError) as exc:
            step._raise_if_forbidden(failure, 'vault index')
        assert '403'           in str(exc.value)
        assert 'Access denied' in str(exc.value)

    def test_absent_or_no_failure__does_not_raise(self):
        step    = Step__Clone__Download_Index()
        absent  = Schema__Fetch_Failure(classification=Enum__Fetch_Failure_Class.ABSENT)
        step._raise_if_forbidden(absent, 'vault index')      # ABSENT → no raise
        step._raise_if_forbidden(None,   'vault index')      # no failure → no raise
