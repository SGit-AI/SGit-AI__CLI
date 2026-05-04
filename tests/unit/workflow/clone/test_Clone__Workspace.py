"""Tests for Clone__Workspace."""
import os
import tempfile
import shutil

import pytest

from sgit_ai.api.Vault__API__In_Memory       import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.core.actions.clone.Vault__Sync__Clone         import Vault__Sync__Clone
from sgit_ai.workflow.clone.Clone__Workspace import Clone__Workspace
from sgit_ai.workflow.clone.Workflow__Clone  import Workflow__Clone


class Test_Clone__Workspace:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix='ws_test_')
        self.wf  = Workflow__Clone()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_ws(self):
        ws = Clone__Workspace.create(self.wf.workflow_name(), self.tmp)
        crypto         = Vault__Crypto()
        api            = Vault__API__In_Memory()
        api.setup()
        ws.sync_client = Vault__Sync__Clone(crypto=crypto, api=api)
        ws.on_progress = None
        return ws

    def test_all_managers_start_none(self):
        ws = self._make_ws()
        assert ws.storage        is None
        assert ws.obj_store      is None
        assert ws.vc             is None
        assert ws.sub_tree       is None
        assert ws.ref_manager    is None
        assert ws.branch_manager is None

    def test_ensure_managers_builds_storage(self):
        ws     = self._make_ws()
        sg_dir = tempfile.mkdtemp(dir=self.tmp, prefix='sg_')
        ws.ensure_managers(sg_dir)
        assert ws.storage is not None

    def test_ensure_managers_builds_obj_store(self):
        ws     = self._make_ws()
        sg_dir = tempfile.mkdtemp(dir=self.tmp, prefix='sg_')
        ws.ensure_managers(sg_dir)
        assert ws.obj_store is not None

    def test_ensure_managers_builds_vc(self):
        ws     = self._make_ws()
        sg_dir = tempfile.mkdtemp(dir=self.tmp, prefix='sg_')
        ws.ensure_managers(sg_dir)
        assert ws.vc is not None

    def test_ensure_managers_is_idempotent(self):
        ws     = self._make_ws()
        sg_dir = tempfile.mkdtemp(dir=self.tmp, prefix='sg_')
        ws.ensure_managers(sg_dir)
        first_obj_store = ws.obj_store
        ws.ensure_managers(sg_dir)   # second call — must not rebuild
        assert ws.obj_store is first_obj_store

    def test_save_file_writes_to_disk(self):
        ws     = self._make_ws()
        sg_dir = tempfile.mkdtemp(dir=self.tmp, prefix='sg_')
        ws.save_file(sg_dir, 'bare/data/obj-cas-imm-aabb11223344', b'ciphertext')
        path = os.path.join(sg_dir, 'bare', 'data', 'obj-cas-imm-aabb11223344')
        assert os.path.isfile(path)
        assert open(path, 'rb').read() == b'ciphertext'

    def test_save_file_creates_parent_dirs(self):
        ws     = self._make_ws()
        sg_dir = tempfile.mkdtemp(dir=self.tmp, prefix='sg_')
        ws.save_file(sg_dir, 'bare/refs/ref-pid-muw-aabb11223344', b'refdata')
        path = os.path.join(sg_dir, 'bare', 'refs', 'ref-pid-muw-aabb11223344')
        assert os.path.isfile(path)

    def test_progress_calls_callback(self):
        ws     = self._make_ws()
        events = []
        ws.on_progress = lambda e, m, d='': events.append((e, m, d))
        ws.progress('step', 'Starting', 'detail here')
        assert events == [('step', 'Starting', 'detail here')]

    def test_progress_silent_when_callback_none(self):
        ws = self._make_ws()
        ws.on_progress = None
        ws.progress('step', 'msg')   # must not raise
