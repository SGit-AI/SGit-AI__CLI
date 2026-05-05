"""Functional tests for Workflow__Pull and Vault__Sync.fetch() — B04."""
import os

from tests._helpers.vault_test_env          import Vault__Test_Env
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
from sgit_ai.crypto.Vault__Crypto           import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto             import PKI__Crypto
from sgit_ai.storage.Vault__Commit          import Vault__Commit
from sgit_ai.storage.Vault__Object_Store    import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager     import Vault__Ref_Manager


class _PullFunctional:
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


class Test_Workflow__Pull__Registration:

    def test_pull_workflow_registered(self):
        from sgit_ai.workflow.pull.Workflow__Pull import Workflow__Pull
        known = CLI__Dev__Workflow._known_workflows()
        assert 'pull' in known

    def test_push_workflow_registered(self):
        from sgit_ai.workflow.push.Workflow__Push import Workflow__Push
        known = CLI__Dev__Workflow._known_workflows()
        assert 'push' in known

    def test_fetch_workflow_registered(self):
        from sgit_ai.workflow.fetch.Workflow__Fetch import Workflow__Fetch
        known = CLI__Dev__Workflow._known_workflows()
        assert 'fetch' in known

    def test_all_three_workflows_in_registry(self):
        known = CLI__Dev__Workflow._known_workflows()
        for name in ('pull', 'push', 'fetch'):
            assert name in known, f'Workflow {name!r} not in registry'


class Test_Workflow__Pull__UpToDate(_PullFunctional):

    def test_pull_up_to_date_returns_status(self):
        result = self.env.sync.pull(self.env.vault_dir)
        assert result.get('status') == 'up_to_date'

    def test_pull_up_to_date_has_message(self):
        result = self.env.sync.pull(self.env.vault_dir)
        assert 'message' in result

    def test_pull_returns_dict(self):
        result = self.env.sync.pull(self.env.vault_dir)
        assert isinstance(result, dict)


class _TwoClonesFunctional:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'shared.txt': 'shared content'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()


class Test_Workflow__Pull__FastForward(_TwoClonesFunctional):

    def test_pull_fast_forward_returns_merged(self):
        sync = self.env.sync
        # Alice adds a file and pushes
        with open(os.path.join(self.env.alice_dir, 'alice.txt'), 'w') as f:
            f.write('alice new file')
        sync.commit(self.env.alice_dir, 'alice adds file')
        sync.push(self.env.alice_dir)
        # Bob pulls — should fast-forward
        result = sync.pull(self.env.bob_dir)
        assert result['status'] == 'merged'

    def test_pull_fast_forward_file_present_in_working_copy(self):
        sync = self.env.sync
        with open(os.path.join(self.env.alice_dir, 'alice2.txt'), 'w') as f:
            f.write('alice file 2')
        sync.commit(self.env.alice_dir, 'alice adds file2')
        sync.push(self.env.alice_dir)
        sync.pull(self.env.bob_dir)
        assert os.path.isfile(os.path.join(self.env.bob_dir, 'alice2.txt'))

    def test_pull_fast_forward_returns_commit_id(self):
        sync = self.env.sync
        with open(os.path.join(self.env.alice_dir, 'alice3.txt'), 'w') as f:
            f.write('alice file 3')
        sync.commit(self.env.alice_dir, 'alice adds file3')
        sync.push(self.env.alice_dir)
        result = sync.pull(self.env.bob_dir)
        assert result.get('commit_id')

    def test_pull_fast_forward_added_list(self):
        sync = self.env.sync
        with open(os.path.join(self.env.alice_dir, 'new.txt'), 'w') as f:
            f.write('new file from alice')
        sync.commit(self.env.alice_dir, 'alice adds new.txt')
        sync.push(self.env.alice_dir)
        result = sync.pull(self.env.bob_dir)
        assert 'new.txt' in result.get('added', [])


class Test_Workflow__Pull__ThreeWayMerge(_TwoClonesFunctional):

    def test_pull_three_way_merge_returns_merged(self):
        sync = self.env.sync
        # Alice adds a file and pushes
        with open(os.path.join(self.env.alice_dir, 'alice_merge.txt'), 'w') as f:
            f.write('alice content')
        sync.commit(self.env.alice_dir, 'alice change')
        sync.push(self.env.alice_dir)
        # Bob adds a different file (creating divergence)
        with open(os.path.join(self.env.bob_dir, 'bob_merge.txt'), 'w') as f:
            f.write('bob content')
        sync.commit(self.env.bob_dir, 'bob change')
        result = sync.pull(self.env.bob_dir)
        assert result['status'] == 'merged'

    def test_pull_three_way_merge_both_files_exist(self):
        sync = self.env.sync
        with open(os.path.join(self.env.alice_dir, 'a_file.txt'), 'w') as f:
            f.write('alice')
        sync.commit(self.env.alice_dir, 'alice change')
        sync.push(self.env.alice_dir)
        with open(os.path.join(self.env.bob_dir, 'b_file.txt'), 'w') as f:
            f.write('bob')
        sync.commit(self.env.bob_dir, 'bob change')
        sync.pull(self.env.bob_dir)
        assert os.path.isfile(os.path.join(self.env.bob_dir, 'a_file.txt'))
        assert os.path.isfile(os.path.join(self.env.bob_dir, 'b_file.txt'))

    def test_pull_three_way_merge_commit_message_uses_branch_names(self):
        sync = self.env.sync
        # Create divergence: Alice pushes, Bob commits independently
        with open(os.path.join(self.env.alice_dir, 'alice_branch_msg.txt'), 'w') as f:
            f.write('alice')
        sync.commit(self.env.alice_dir, 'alice change for branch-name test')
        sync.push(self.env.alice_dir)
        with open(os.path.join(self.env.bob_dir, 'bob_branch_msg.txt'), 'w') as f:
            f.write('bob')
        sync.commit(self.env.bob_dir, 'bob change for branch-name test')
        result = sync.pull(self.env.bob_dir)
        assert result['status'] == 'merged'

        # Load the merge commit and decrypt its message
        sg_dir    = os.path.join(self.env.bob_dir, '.sg_vault')
        crypto    = Vault__Crypto()
        read_key  = sync._init_components(self.env.bob_dir).read_key
        pki       = PKI__Crypto()
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        vc        = Vault__Commit(crypto=crypto, pki=pki,
                                  object_store=obj_store, ref_manager=Vault__Ref_Manager())
        merge_cid = result['commit_id']
        commit    = vc.load_commit(merge_cid, read_key)
        msg       = crypto.decrypt_metadata(read_key, str(commit.message_enc))

        # Before the field-forwarding fix, the message was always 'Merge remote into local'
        # (branch names dropped between Load_Branch_Info and Merge step).
        # With the fix, real branch names from the vault must appear.
        assert msg != 'Merge remote into local', (
            f'Merge message is still the placeholder; field forwarding is broken. got: {msg!r}')
        assert 'into' in msg, f'Expected "Merge X into Y" format; got: {msg!r}'
        # The named branch in this fixture is always 'current'; 'remote' was the broken fallback.
        assert 'remote' not in msg, (
            f'named_branch_name fallback "remote" leaked into commit message; got: {msg!r}')


class Test_Vault__Sync__Fetch(_PullFunctional):

    def test_fetch_returns_dict(self):
        result = self.env.sync.fetch(self.env.vault_dir)
        assert isinstance(result, dict)

    def test_fetch_returns_status_fetched(self):
        result = self.env.sync.fetch(self.env.vault_dir)
        assert result.get('status') == 'fetched'

    def test_fetch_has_n_objects_fetched_key(self):
        result = self.env.sync.fetch(self.env.vault_dir)
        assert 'n_objects_fetched' in result

    def test_fetch_returns_named_commit_id(self):
        result = self.env.sync.fetch(self.env.vault_dir)
        assert 'named_commit_id' in result

    def test_fetch_does_not_modify_working_copy(self):
        before = set(os.listdir(self.env.vault_dir))
        self.env.sync.fetch(self.env.vault_dir)
        after  = set(os.listdir(self.env.vault_dir))
        assert before == after

    def test_fetch_with_progress_callback(self):
        events = []
        self.env.sync.fetch(self.env.vault_dir, on_progress=lambda *a: events.append(a))
        # just verifying no exception with a real callback

    def test_fetch_via_vault_sync_fetch_class(self):
        from sgit_ai.core.actions.fetch.Vault__Sync__Fetch import Vault__Sync__Fetch
        fetcher = Vault__Sync__Fetch(crypto=self.env.crypto, api=self.env.api)
        result  = fetcher.fetch(self.env.vault_dir)
        assert result.get('status') == 'fetched'
