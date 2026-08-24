"""P0 regression suite (decision 17): a vault that tracks .github/** before the
ignore-set change must keep those files across every command, and a fresh vault
must never add them. This is the maintainer's "no side effects on existing
vaults" condition expressed as tests — see
team/explorer/dev/impl-plans/08/17/static-publishing/12__accepted-risks.md §6.
"""
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto                     import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory        import Vault__API__In_Memory
from sgit_ai.core.Vault__Sync                         import Vault__Sync
from sgit_ai.core.Vault__Head_Paths                   import Vault__Head_Paths
from sgit_ai.core.actions.admin.Vault__Ignore__Apply  import Vault__Ignore__Apply


class Test_Vault__Ignore__Tracked_Wins__Vault_Level:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        self.vault  = os.path.join(self.tmp, 'vault')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _vault_tracking_github(self):
        """A vault whose head tracks .github/workflows/x.yml — the legacy state
        that existed before .github joined ALWAYS_IGNORED_DIRS. write_file
        commits straight to the head (no work-tree scan), which is exactly how
        such vaults came to exist."""
        self.sync.init(self.vault)
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        self.sync.write_file(self.vault, '.github/workflows/x.yml', b'name: ci\n')
        self.sync.push(self.vault)
        return self.vault

    def _head_paths(self):
        return Vault__Head_Paths(crypto=self.crypto).paths(self.vault)

    def test_tracked_github_file_survives_status_and_push(self):
        self._vault_tracking_github()
        status = self.sync.status(self.vault)
        assert status['clean']   is True
        assert status['deleted'] == []
        result = self.sync.push(self.vault)
        assert result['status'] in ('up_to_date',)                    # nothing to push, no deletion
        assert '.github/workflows/x.yml' in self._head_paths()

    def test_tracked_github_file_survives_an_unrelated_commit(self):
        self._vault_tracking_github()
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello v2')
        self.sync.commit(self.vault, 'edit readme')
        heads = self._head_paths()
        assert '.github/workflows/x.yml' in heads
        assert 'readme.md'               in heads

    def test_fresh_vault_never_adds_github(self):
        self.sync.init(self.vault)
        os.makedirs(os.path.join(self.vault, '.github', 'workflows'))
        with open(os.path.join(self.vault, '.github', 'workflows', 'ci.yml'), 'w') as f:
            f.write('name: ci\n')
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        heads = self._head_paths()
        assert 'readme.md' in heads
        assert not any(p.startswith('.github/') for p in heads)

    def test_untracked_new_file_under_grandfathered_dir_not_added(self):
        self._vault_tracking_github()
        with open(os.path.join(self.vault, '.github', 'workflows', 'new.yml'), 'w') as f:
            f.write('name: extra\n')
        status = self.sync.status(self.vault)
        assert status['clean'] is True
        assert status['added'] == []

    def test_deleting_grandfathered_file_still_records_a_deletion(self):
        self._vault_tracking_github()
        os.remove(os.path.join(self.vault, '.github', 'workflows', 'x.yml'))
        status = self.sync.status(self.vault)
        assert status['deleted'] == ['.github/workflows/x.yml']
        self.sync.commit(self.vault, 'drop the workflow deliberately')
        assert '.github/workflows/x.yml' not in self._head_paths()

    def test_ignore_apply_removes_in_one_commit_and_keeps_work_tree(self):
        self._vault_tracking_github()
        on_disk = os.path.join(self.vault, '.github', 'workflows', 'x.yml')
        apply_action = Vault__Ignore__Apply(crypto=self.crypto, api=self.api)
        assert apply_action.tracked_under(self.vault, '.github') == ['.github/workflows/x.yml']
        result = apply_action.apply(self.vault, '.github')
        assert result['status']  == 'removed'
        assert result['removed'] == ['.github/workflows/x.yml']
        assert result['commit_id']
        assert os.path.isfile(on_disk)                                # work tree untouched
        assert '.github/workflows/x.yml' not in self._head_paths()
        status = self.sync.status(self.vault)                         # and the vault is clean:
        assert status['clean'] is True                                # the dir is now plain-ignored

    def test_ignore_apply_noop_when_nothing_tracked(self):
        self.sync.init(self.vault)
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        result = Vault__Ignore__Apply(crypto=self.crypto, api=self.api).apply(self.vault, '.github')
        assert result['status']    == 'up_to_date'
        assert result['commit_id'] is None

    def test_migration_notice_shown_once(self, capsys):
        # The first scan against a head tracking .github/** emits the notice —
        # here that happens inside push's own status check during setup.
        self._vault_tracking_github()
        setup_output = capsys.readouterr().err
        assert 'sgit vault ignore --apply .github' in setup_output
        self.sync.status(self.vault)
        second = capsys.readouterr().err
        assert 'sgit vault ignore --apply .github' not in second      # once, not every command

    def test_no_notice_for_vault_without_github(self, capsys):
        self.sync.init(self.vault)
        with open(os.path.join(self.vault, 'readme.md'), 'w') as f:
            f.write('hello')
        self.sync.commit(self.vault, 'initial')
        capsys.readouterr()
        self.sync.status(self.vault)
        assert 'sgit vault ignore' not in capsys.readouterr().err

    def test_head_paths_empty_outside_a_vault(self):
        assert Vault__Head_Paths(crypto=self.crypto).paths(self.tmp) == set()

    def test_head_paths_lists_the_working_head(self):
        self._vault_tracking_github()
        assert self._head_paths() == {'readme.md', '.github/workflows/x.yml'}


class Test_A2__Structural_Not_Written_On_Checkout:
    """A2 (review finding): a crafted vault tree carrying .git/** or .sg_vault/**
    entries must not have those paths written into the victim's directory —
    Vault__Sub_Tree.checkout is the code path clone/pull materialise trees through,
    and Vault__Path_Guard cannot help because the paths do not ESCAPE the dir."""

    def setup_method(self):
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Storage      import Vault__Storage
        self.crypto = Vault__Crypto()
        self.tmp    = tempfile.mkdtemp()
        self.sg_dir = os.path.join(self.tmp, '.sg_vault')
        Vault__Storage().create_bare_structure(self.sg_dir)
        self.obj_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto)
        self.sub_tree  = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store)
        keys = self.crypto.derive_keys_from_vault_key('checkoutkeypass012345678:chkoutvlt')
        self.read_key = keys['read_key_bytes']

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _blob(self, content: bytes) -> str:
        blob_id, _large, _hash = self.sub_tree.encrypt_or_reuse_blob(content, None, self.read_key)
        return blob_id

    def _tree_with(self, paths: dict) -> str:
        flat = {}
        for path, content in paths.items():
            import mimetypes
            flat[path] = dict(blob_id      = self._blob(content),
                              size         = len(content),
                              content_hash = self.crypto.content_hash(content),
                              content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream',
                              large        = False)
        return self.sub_tree.build_from_flat(flat, self.read_key)

    def test_checkout_writes_real_content_but_refuses_structural(self):
        dest    = os.path.join(self.tmp, 'victim')
        os.makedirs(dest)
        tree_id = self._tree_with({
            'readme.md'              : b'real content',
            'docs/policy.md'         : b'also real',
            '.git/hooks/pre-commit'  : b'#!/bin/sh\necho PWNED\n',
            '.sg_vault/local/ATTACKER': b'attacker bytes',
            'nested/.git/config'     : b'[core]',
        })
        self.sub_tree.checkout(dest, tree_id, self.read_key)
        assert os.path.isfile(os.path.join(dest, 'readme.md'))
        assert os.path.isfile(os.path.join(dest, 'docs', 'policy.md'))
        assert not os.path.exists(os.path.join(dest, '.git', 'hooks', 'pre-commit'))
        assert not os.path.exists(os.path.join(dest, '.sg_vault', 'local', 'ATTACKER'))
        assert not os.path.exists(os.path.join(dest, 'nested', '.git', 'config'))

    def test_checkout_flat_map_refuses_structural(self):
        """The pull / branch-switch materialisation path (_checkout_flat_map)."""
        from sgit_ai.core.Vault__Sync__Base import Vault__Sync__Base
        dest = os.path.join(self.tmp, 'victim2')
        os.makedirs(dest)
        flat = {
            'ok.txt'                 : dict(blob_id=self._blob(b'ok'),      size=2, content_hash='', content_type='text/plain', large=False),
            '.git/hooks/pre-commit'  : dict(blob_id=self._blob(b'PWNED'),   size=5, content_hash='', content_type='text/plain', large=False),
        }
        Vault__Sync__Base(crypto=self.crypto)._checkout_flat_map(dest, flat, self.obj_store, self.read_key)
        assert os.path.isfile(os.path.join(dest, 'ok.txt'))
        assert not os.path.exists(os.path.join(dest, '.git', 'hooks', 'pre-commit'))


class Test_A6__Fail_Open_Coupling:
    """A6 (review note): Vault__Head_Paths fails open (empty set on error), which
    only stays safe because the scan path fails LOUD on the same corrupt head.
    This pins that coupling: if a future change makes status tolerant of an
    unreadable head, this test breaks and flags that tracked-wins is now
    silently disabled (re-exposing the P0 deletion hazard)."""

    def test_head_unreadable_makes_scan_fail_loud(self):
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory().setup()
        sync   = Vault__Sync(crypto=crypto, api=api)
        tmp    = tempfile.mkdtemp()
        try:
            vault = os.path.join(tmp, 'vault')
            sync.init(vault)
            with open(os.path.join(vault, 'a.txt'), 'w') as f:
                f.write('content')
            sync.commit(vault, 'init')
            sync.push(vault)
            # Head_Paths already reads the head fine here
            assert 'a.txt' in Vault__Head_Paths(crypto=crypto).paths(vault)
            # corrupt the store: remove every data object (head commit + tree unreadable)
            data_dir = os.path.join(vault, '.sg_vault', 'bare', 'data')
            for name in os.listdir(data_dir):
                os.remove(os.path.join(data_dir, name))
            # Head_Paths now fails open (empty) ...
            assert Vault__Head_Paths(crypto=crypto).paths(vault) == set()
            # ... but the scan path (status) fails LOUD rather than reporting
            # everything deleted — so the deletion hazard never materialises.
            import pytest
            with pytest.raises(Exception):
                sync.status(vault)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
