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


# ---------------------------------------------------------------------------
# Interop contract v0 §9 — present-but-malformed/foreign index degrades to the
# single-branch fallback instead of crashing (e.g. round-1 bug A:
# branch_id:"branch-named-main" fails Safe_Str__Branch_Id, and round-1 bug B:
# name:"main" misses the 'current' lookup).
# ---------------------------------------------------------------------------

class Test_Step__Clone__Download_Index__Graceful_Degrade(Test_Step__Clone__Download_Index__Fallback):

    def _overwrite_index_with(self, plaintext: bytes):
        """Re-encrypt and replace the index file in the in-memory store."""
        keys     = self.crypto.derive_keys_from_vault_key(self.VAULT_KEY)
        vault_id = keys['vault_id']
        read_key = bytes.fromhex(keys['read_key'])
        index_id = keys['branch_index_file_id']
        store_key = f'{vault_id}/bare/indexes/{index_id}'
        assert store_key in self.api._store, 'snapshot must have an index to overwrite'
        self.api._store[store_key] = self.crypto.encrypt(read_key, plaintext)

    def test_malformed_index_parse_failure_degrades_to_fallback(self):
        """An index whose decrypt+parse raises (round-1 'branch-named-main' bug A)
        must fall back to the named-ref single-branch path, not crash the clone."""
        import json as _json
        bad = {'schema'   : 'branch_index_v1',
               'branches' : [{'branch_id'   : 'branch-named-main',          # fails Safe_Str regex
                              'branch_type' : 'named',
                              'head_ref_id' : 'ref-pid-muw-da0dea46b649',
                              'name'        : 'current'}]}
        self._overwrite_index_with(_json.dumps(bad).encode())

        out = self._run_clone()                                              # must not raise
        # Fell back to the deterministic named ref instead of using the malformed index
        keys = self.crypto.derive_keys_from_vault_key(self.VAULT_KEY)
        assert str(out.get('named_ref_id', '')) == keys['ref_file_id']
        assert os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))

    def test_index_without_current_branch_degrades_to_fallback(self):
        """A conformant payload that just lacks name='current' (round-1 bug B
        in isolation) must also fall back, not raise 'Named branch current not found'."""
        import json as _json
        no_current = {'schema'   : 'branch_index_v1',
                      'branches' : [{'branch_id'   : 'branch-named-a1b2c3d4e5f6',
                                     'branch_type' : 'named',
                                     'head_ref_id' : 'ref-pid-muw-da0dea46b649',
                                     'name'        : 'main'}]}    # not 'current'
        self._overwrite_index_with(_json.dumps(no_current).encode())

        out = self._run_clone()
        keys = self.crypto.derive_keys_from_vault_key(self.VAULT_KEY)
        assert str(out.get('named_ref_id', '')) == keys['ref_file_id']
        assert os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))

    def test_malformed_index_with_missing_ref_still_raises_publish_hint(self):
        """Degrade does NOT mask 'nothing published': if the named ref is ALSO
        absent, the absent-index fallback's clear error must still surface."""
        import json as _json
        bad = {'schema': 'branch_index_v1',
               'branches': [{'branch_id': 'branch-named-main', 'name': 'current',
                             'branch_type': 'named',
                             'head_ref_id': 'ref-pid-muw-da0dea46b649'}]}
        self._overwrite_index_with(_json.dumps(bad).encode())
        self._drop('bare/refs/')                                # ref also gone

        with pytest.raises(RuntimeError) as exc:
            self._run_clone()
        msg = str(exc.value)
        assert 'Nothing to clone' in msg
        assert 'Publish'          in msg

    def test_try_use_present_index__direct_parse_failure_returns_reason(self):
        """Direct unit test on the helper: malformed index → (None, reason)."""
        step = Step__Clone__Download_Index()
        class _BadBM:
            def load_branch_index(self, *_a, **_kw):
                raise ValueError('bad regex')
        class _WS:
            branch_manager = _BadBM()
        meta, reason = step._try_use_present_index(_WS(), '.', 'idx-pid-muw-deadbeef', b'k'*32)
        assert meta is None
        assert 'ValueError' in reason

    def test_try_use_present_index__no_current_returns_reason(self):
        """Direct unit test: parsed index with no 'current' branch → (None, reason)."""
        step = Step__Clone__Download_Index()
        class _OkBM:
            def load_branch_index(self, *_a, **_kw):
                return object()                                  # any object will do
            def get_branch_by_name(self, _idx, name):
                return None                                      # 'current' not found
        class _WS:
            branch_manager = _OkBM()
        meta, reason = step._try_use_present_index(_WS(), '.', 'idx-pid-muw-deadbeef', b'k'*32)
        assert meta is None
        assert "'current'" in reason
