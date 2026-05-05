"""Functional tests for B05 per-mode clone workflows: clone-branch, clone-headless, clone-range."""
import os
import tempfile
import shutil

from tests._helpers.vault_test_env          import Vault__Test_Env


class _CloneFunctional:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello world', 'data.txt': 'some data'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()


# ─────────────────────────────────────────────────────────────────────────────
# Workflow registry
# ─────────────────────────────────────────────────────────────────────────────

class Test_B05__Workflow_Registration:

    def test_clone_branch_workflow_registered(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        from sgit_ai.workflow.clone.Workflow__Clone__Branch  import Workflow__Clone__Branch
        assert 'clone-branch' in CLI__Dev__Workflow._known_workflows()

    def test_clone_headless_workflow_registered(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        from sgit_ai.workflow.clone.Workflow__Clone__Headless import Workflow__Clone__Headless
        assert 'clone-headless' in CLI__Dev__Workflow._known_workflows()

    def test_clone_range_workflow_registered(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        from sgit_ai.workflow.clone.Workflow__Clone__Range   import Workflow__Clone__Range
        assert 'clone-range' in CLI__Dev__Workflow._known_workflows()

    def test_all_six_clone_workflows_registered(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        import importlib
        for mod in ('Workflow__Clone', 'Workflow__Clone__Branch',
                    'Workflow__Clone__Headless', 'Workflow__Clone__Range'):
            importlib.import_module(f'sgit_ai.workflow.clone.{mod}')
        known = CLI__Dev__Workflow._known_workflows()
        for name in ('clone', 'clone-branch', 'clone-headless', 'clone-range'):
            assert name in known, f'Workflow {name!r} not in registry'


# ─────────────────────────────────────────────────────────────────────────────
# Workflow__Clone__Branch happy-path tests
# ─────────────────────────────────────────────────────────────────────────────

class Test_B05__Clone_Branch(_CloneFunctional):

    def test_clone_branch_returns_dict(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch')
        result = self.env.sync.clone_branch(self.env.vault_key, dst)
        assert isinstance(result, dict)

    def test_clone_branch_mode_key(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-mode')
        result = self.env.sync.clone_branch(self.env.vault_key, dst)
        assert result.get('mode') == 'clone-branch'

    def test_clone_branch_files_present_in_working_copy(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-files')
        self.env.sync.clone_branch(self.env.vault_key, dst)
        assert os.path.isfile(os.path.join(dst, 'hello.txt'))
        assert os.path.isfile(os.path.join(dst, 'data.txt'))

    def test_clone_branch_file_content_correct(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-content')
        self.env.sync.clone_branch(self.env.vault_key, dst)
        assert open(os.path.join(dst, 'hello.txt')).read() == 'hello world'

    def test_clone_branch_returns_commit_id(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-cid')
        result = self.env.sync.clone_branch(self.env.vault_key, dst)
        assert result.get('commit_id')

    def test_clone_branch_returns_vault_id(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-vid')
        result = self.env.sync.clone_branch(self.env.vault_key, dst)
        assert result.get('vault_id')

    def test_clone_branch_bare_skips_working_copy(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-bare')
        self.env.sync.clone_branch(self.env.vault_key, dst, bare=True)
        assert not os.path.isfile(os.path.join(dst, 'hello.txt'))
        assert not os.path.isfile(os.path.join(dst, 'data.txt'))

    def test_clone_branch_bare_returns_bare_flag(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-branch-bare2')
        result = self.env.sync.clone_branch(self.env.vault_key, dst, bare=True)
        assert result.get('bare') is True

    def test_clone_branch_with_progress_callback(self):
        events = []
        dst    = os.path.join(self.env.tmp_dir, 'dst-branch-prog')
        self.env.sync.clone_branch(self.env.vault_key, dst,
                                   on_progress=lambda *a: events.append(a))
        assert len(events) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Workflow__Clone__Headless happy-path tests
# ─────────────────────────────────────────────────────────────────────────────

class Test_B05__Clone_Headless(_CloneFunctional):

    def test_clone_headless_returns_dict(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-headless')
        result = self.env.sync.clone_headless(self.env.vault_key, dst)
        assert isinstance(result, dict)

    def test_clone_headless_mode_key(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-headless-mode')
        result = self.env.sync.clone_headless(self.env.vault_key, dst)
        assert result.get('mode') == 'headless'

    def test_clone_headless_no_file_data(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-headless-nodata')
        self.env.sync.clone_headless(self.env.vault_key, dst)
        assert not os.path.isfile(os.path.join(dst, 'hello.txt'))

    def test_clone_headless_writes_vault_key_file(self):
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        dst = os.path.join(self.env.tmp_dir, 'dst-headless-vk')
        self.env.sync.clone_headless(self.env.vault_key, dst)
        vk_path = Vault__Storage().vault_key_path(dst)
        assert os.path.isfile(vk_path)

    def test_clone_headless_writes_local_config(self):
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        dst = os.path.join(self.env.tmp_dir, 'dst-headless-cfg')
        self.env.sync.clone_headless(self.env.vault_key, dst)
        cfg_path = Vault__Storage().local_config_path(dst)
        assert os.path.isfile(cfg_path)

    def test_clone_headless_returns_vault_id(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-headless-vid')
        result = self.env.sync.clone_headless(self.env.vault_key, dst)
        assert result.get('vault_id')


# ─────────────────────────────────────────────────────────────────────────────
# Workflow__Clone__Range happy-path tests
# ─────────────────────────────────────────────────────────────────────────────

class Test_B05__Clone_Range(_CloneFunctional):

    def test_clone_range_returns_dict(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-range')
        result = self.env.sync.clone_range(self.env.vault_key, dst)
        assert isinstance(result, dict)

    def test_clone_range_mode_key(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-range-mode')
        result = self.env.sync.clone_range(self.env.vault_key, dst)
        assert result.get('mode') == 'clone-range'

    def test_clone_range_files_present(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-range-files')
        self.env.sync.clone_range(self.env.vault_key, dst)
        assert os.path.isfile(os.path.join(dst, 'hello.txt'))

    def test_clone_range_returns_commit_id(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-range-cid')
        result = self.env.sync.clone_range(self.env.vault_key, dst)
        assert result.get('commit_id')

    def test_clone_range_bare_skips_working_copy(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-range-bare')
        self.env.sync.clone_range(self.env.vault_key, dst, bare=True)
        assert not os.path.isfile(os.path.join(dst, 'hello.txt'))

    def test_clone_range_with_explicit_range_to(self):
        head_commit = self.env.commit_id
        dst = os.path.join(self.env.tmp_dir, 'dst-range-explicit')
        result = self.env.sync.clone_range(self.env.vault_key, dst, range_to=head_commit)
        assert result.get('commit_id') == head_commit

    def test_clone_range_returns_range_from_and_to(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-range-kv')
        result = self.env.sync.clone_range(self.env.vault_key, dst)
        assert 'range_from' in result
        assert 'range_to'   in result


# ─────────────────────────────────────────────────────────────────────────────
# fetch_tree_lazy tests
# ─────────────────────────────────────────────────────────────────────────────

class Test_B05__Fetch_Tree_Lazy(_CloneFunctional):

    def test_fetch_tree_lazy_returns_bool(self):
        dst  = os.path.join(self.env.tmp_dir, 'dst-lazy')
        self.env.sync.clone(self.env.vault_key, dst)
        # The tree is already present after clone — returns False
        from sgit_ai.core.Vault__Sync__Base import Vault__Sync__Base
        sync = self.env.sync
        result = sync.fetch_tree_lazy(dst, 'nonexistent-tree-id-000')
        assert isinstance(result, bool)

    def test_fetch_tree_lazy_false_for_unknown_object(self):
        dst = os.path.join(self.env.tmp_dir, 'dst-lazy2')
        self.env.sync.clone(self.env.vault_key, dst)
        result = self.env.sync.fetch_tree_lazy(dst, 'deadbeef00000000000000000000000000000000000000000000000000000000')
        assert result is False
