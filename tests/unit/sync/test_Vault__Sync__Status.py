import os
import tempfile
import shutil

from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.storage.Vault__Storage               import Vault__Storage
from sgit_ai.storage.Vault__Branch_Manager        import Vault__Branch_Manager
from sgit_ai.storage.Vault__Sub_Tree              import Vault__Sub_Tree
from sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager        import Vault__Ref_Manager
from sgit_ai.storage.Vault__Commit             import Vault__Commit
from sgit_ai.network.api.Vault__API__In_Memory         import Vault__API__In_Memory
from tests.unit.sync.vault_test_env            import Vault__Test_Env


class Test_Vault__Sync__Status:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env    = self._env.restore()
        self.crypto = self.env.crypto
        self.pki    = PKI__Crypto()
        self.api    = self.env.api
        self.sync   = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def _load_branch_components(self, directory: str):
        """Return (read_key, keys, sg_dir, obj_store, ref_manager, key_manager,
                   branch_manager, branch_index, named_meta, clone_meta)."""
        sg_dir      = os.path.join(directory, '.sg_vault')
        vault_key   = open(os.path.join(sg_dir, 'local', 'vault_key')).read().strip()
        keys        = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key    = keys['read_key_bytes']
        storage     = Vault__Storage()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager,
                                               ref_manager=ref_manager,
                                               storage=storage)
        index_id     = keys['branch_index_file_id']
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = branch_manager.get_branch_by_name(branch_index, 'current')

        # Identify clone branch by type
        from sgit_ai.safe_types.Enum__Branch_Type import Enum__Branch_Type
        clone_meta   = next((b for b in branch_index.branches
                             if b.branch_type == Enum__Branch_Type.CLONE), None)

        return (read_key, keys, sg_dir, obj_store, ref_manager, key_manager,
                branch_manager, branch_index, named_meta, clone_meta)

    def _advance_named_branch(self, directory: str, files: dict) -> str:
        """Create a new commit on the named branch (simulates a remote push)."""
        (read_key, keys, sg_dir, obj_store, ref_manager, key_manager,
         branch_manager, branch_index, named_meta, _) = self._load_branch_components(directory)

        named_ref_id = str(named_meta.head_ref_id)
        parent_id    = ref_manager.read_ref(named_ref_id, read_key)

        flat_map = {}
        for path, content in files.items():
            content_bytes = content.encode() if isinstance(content, str) else content
            encrypted     = self.crypto.encrypt(read_key, content_bytes)
            blob_id       = obj_store.store(encrypted)
            flat_map[path] = {'blob_id': blob_id, 'size': len(content_bytes),
                              'content_hash': self.crypto.content_hash(content_bytes)}

        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        root_tree_id = sub_tree.build_from_flat(flat_map, read_key)

        signing_key = key_manager.load_private_key(str(named_meta.private_key_id), read_key)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_id = vault_commit.create_commit(read_key    = read_key,
                                               tree_id     = root_tree_id,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = 'remote advance',
                                               branch_id   = str(named_meta.branch_id),
                                               signing_key = signing_key)
        ref_manager.write_ref(named_ref_id, commit_id, read_key)
        return commit_id

    # ------------------------------------------------------------------
    # Tests: push_status field
    # ------------------------------------------------------------------

    def test_status_up_to_date_after_init(self):
        """Fresh vault: clone and named branch point to the same init commit."""
        directory = self.env.vault_dir
        result = self.sync.status(directory)

        assert result['push_status'] == 'up_to_date'
        assert result['ahead']  == 0
        assert result['behind'] == 0
        assert result['clone_branch_id'].startswith('branch-clone-')
        assert result['named_branch_id'].startswith('branch-named-')
        assert result['clone_head'] is not None
        assert result['named_head'] is not None
        assert result['clone_head'] == result['named_head']

    def test_status_ahead_after_local_commit(self):
        """After a local commit that has not been pushed, clone is ahead by 1."""
        directory = self.env.vault_dir

        with open(os.path.join(directory, 'local.txt'), 'w') as f:
            f.write('local work')
        self.sync.commit(directory, message='local commit')

        result = self.sync.status(directory)
        assert result['push_status'] == 'ahead'
        assert result['ahead']  == 1
        assert result['behind'] == 0

    def test_status_ahead_by_multiple_commits(self):
        """Two local commits ahead of named branch."""
        directory = self.env.vault_dir

        for i in range(2):
            with open(os.path.join(directory, f'f{i}.txt'), 'w') as f:
                f.write(f'content {i}')
            self.sync.commit(directory, message=f'commit {i}')

        result = self.sync.status(directory)
        assert result['push_status'] == 'ahead'
        assert result['ahead']  == 2
        assert result['behind'] == 0

    def test_status_behind_when_named_branch_advances(self):
        """When named branch is ahead of clone, push_status is 'behind'."""
        directory = self.env.vault_dir

        self._advance_named_branch(directory, {'remote.txt': 'remote change'})

        result = self.sync.status(directory)
        assert result['push_status'] == 'behind'
        assert result['behind'] == 1
        assert result['ahead']  == 0

    def test_status_diverged_when_both_advance(self):
        """Local commit + named branch advance => diverged."""
        directory = self.env.vault_dir

        # Local commit (not pushed)
        with open(os.path.join(directory, 'local.txt'), 'w') as f:
            f.write('local')
        self.sync.commit(directory, message='local commit')

        # Remote advance on named branch
        self._advance_named_branch(directory, {'remote.txt': 'remote change'})

        result = self.sync.status(directory)
        assert result['push_status'] == 'diverged'
        assert result['ahead']  >= 1
        assert result['behind'] >= 1

    def test_status_returns_branch_ids(self):
        """clone_branch_id and named_branch_id are populated."""
        directory = self.env.vault_dir

        # Read the branch IDs directly from the vault instead of relying on
        # an init_result that no longer exists at test time (snapshot reuse).
        result = self.sync.status(directory)
        assert result['clone_branch_id'].startswith('branch-clone-')
        assert result['named_branch_id'].startswith('branch-named-')

    def test_status_includes_file_changes_alongside_push_status(self):
        """push_status fields coexist with the file-change fields."""
        directory = self.env.vault_dir

        with open(os.path.join(directory, 'new.txt'), 'w') as f:
            f.write('uncommitted')

        result = self.sync.status(directory)
        assert result['clean']       is False
        assert 'new.txt'             in result['added']
        assert 'push_status'         in result
        assert 'clone_branch_id'     in result
        assert 'named_branch_id'     in result
        assert 'clone_head'          in result
        assert 'named_head'          in result
        assert 'ahead'               in result
        assert 'behind'              in result

    def test_status_up_to_date_after_local_commit_then_advance_named_to_match(self):
        """Advancing named branch to match clone HEAD => up_to_date."""
        directory = self.env.vault_dir

        with open(os.path.join(directory, 'f.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='local')

        # Manually move named branch ref to match clone HEAD
        (read_key, keys, sg_dir, obj_store, ref_manager, key_manager,
         branch_manager, branch_index, named_meta, clone_meta) = self._load_branch_components(directory)

        clone_head   = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_ref_id = str(named_meta.head_ref_id)
        ref_manager.write_ref(named_ref_id, clone_head, read_key)

        result = self.sync.status(directory)
        assert result['push_status'] == 'up_to_date'
        assert result['ahead']  == 0
        assert result['behind'] == 0


class Test_Vault__Sync__Status__ReadOnly:
    """Read-only clone status semantics (architect contract §5.4 / §7.1)."""

    def test_clone_branch_id_empty(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['clone_branch_id'] == ''

    def test_clone_head_none(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['clone_head'] is None

    def test_push_status_read_only(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['push_status'] == 'read_only'

    def test_read_only_marker_true(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['read_only'] is True

    def test_ahead_is_zero(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['ahead'] == 0

    def test_named_head_resolved(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['named_head']
        assert result['named_branch_id']

    def test_clean_when_no_working_tree_changes(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['clean'] is True
        assert result['added'] == [] and result['modified'] == [] and result['deleted'] == []

    def test_behind_zero_when_up_to_date(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['behind'] == 0

    def test_detects_local_modification(self, read_only_clone):
        ro_dir = read_only_clone['ro_dir']
        with open(os.path.join(ro_dir, 'data.txt'), 'w') as f:
            f.write('locally edited')
        result = read_only_clone['sync'].status(ro_dir)
        assert 'data.txt' in result['modified']
        assert result['clean'] is False

    def test_remote_configured_true_never_pushed_false(self, read_only_clone):
        result = read_only_clone['sync'].status(read_only_clone['ro_dir'])
        assert result['remote_configured'] is True
        assert result['never_pushed']      is False


class Test_CLI__Status__ReadOnly_Banner:
    """§5.4 — the CLI status display prints the read-only banner."""

    def _vault_with_status(self, status_dict):
        from sgit_ai.cli.CLI__Vault            import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store      import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store

        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class _FakeSync:
            def status(self_inner, directory):
                return status_dict

        vault.create_sync = lambda *a, **k: _FakeSync()
        vault.token_store.resolve_token  = lambda *a, **k: None
        vault.token_store.resolve_remote = lambda *a, **k: dict(base_url='', tls_verify=True, name='')
        return vault

    def _args(self):
        import types
        return types.SimpleNamespace(directory='.', explain=False, token=None)

    def test_banner_printed_on_read_only(self, capsys):
        status_dict = dict(added=[], modified=[], deleted=[], clean=True,
                           clone_branch_id='', named_branch_id='branch-named-abc',
                           clone_head=None, named_head='commit-1', ahead=0, behind=0,
                           push_status='read_only', remote_configured=True,
                           never_pushed=False, read_only=True, sparse=False,
                           files_total=0, files_fetched=0, merge_in_progress=False)
        vault = self._vault_with_status(status_dict)
        vault.cmd_status(self._args())
        out = capsys.readouterr().out
        assert '(read-only clone — pull to refresh; commits not supported)' in out

    def test_banner_shows_behind_count(self, capsys):
        status_dict = dict(added=[], modified=[], deleted=[], clean=True,
                           clone_branch_id='', named_branch_id='branch-named-abc',
                           clone_head=None, named_head='commit-1', ahead=0, behind=2,
                           push_status='read_only', remote_configured=True,
                           never_pushed=False, read_only=True, sparse=False,
                           files_total=0, files_fetched=0, merge_in_progress=False)
        vault = self._vault_with_status(status_dict)
        vault.cmd_status(self._args())
        out = capsys.readouterr().out
        assert '2 commits behind' in out
        assert 'sgit pull' in out
