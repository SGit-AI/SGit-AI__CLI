"""Fixed in 0.21.0 — hostile paths in vault data, stashes and backups.

A tree entry name is chosen by whoever wrote the commit (a teammate, a read-key
holder with host access, a hostile vault shared with you). Every loop that writes
or deletes vault-supplied paths must refuse `..`, absolute paths, `.git/**`,
`.sg_vault/**` and planted `.vault__*.zip` backups. Before this release clone,
pull and checkout were guarded but revert, branch switch, stash pop, sparse fetch
and restore were not. Threat model: TM-F03.
"""
import json
import os
import zipfile

import pytest

from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from sgit_ai.core.actions.revert.Vault__Revert        import Vault__Revert
from sgit_ai.core.actions.stash.Vault__Stash          import Vault__Stash
from sgit_ai.core.Vault__Ignore                       import Vault__Ignore
from sgit_ai.storage.Vault__Path_Guard                import Vault__Path_Guard
from tests._helpers.vault_adversary                   import Vault__Adversary
from tests._helpers.vault_test_env                    import Vault__Test_Env

HOSTILE = {'readme.md'                    : b'real content',
           '.git/hooks/post-checkout'     : b'#!/bin/sh\necho PWNED\n',
           '.sg_vault/local/vault_key'    : b'attacker:vaultid',
           '.GIT/config'                  : b'[core]\n\thooksPath = /tmp',
           '.vault__planted.zip'          : b'PK attacker backup',
           '../escape.txt'                : b'outside the clone'}


def _assert_only_real_content_written(clone_dir: str, vault_key_before: bytes):
    assert open(os.path.join(clone_dir, 'readme.md'), 'rb').read() == b'real content'
    assert not os.path.exists(os.path.join(clone_dir, '.git', 'hooks', 'post-checkout'))
    assert not os.path.exists(os.path.join(clone_dir, '.GIT', 'config'))
    assert not os.path.exists(os.path.join(clone_dir, '.vault__planted.zip'))
    assert not os.path.exists(os.path.join(os.path.dirname(clone_dir), 'escape.txt'))
    with open(os.path.join(clone_dir, '.sg_vault', 'local', 'vault_key'), 'rb') as f:
        assert f.read() == vault_key_before


class Test_Fixed__Hostile_Paths__Vault_Data:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'readme.md': 'original'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s   = self._env.restore()
        self.adv = Vault__Adversary(self.s.api, self.s.vault_key)
        named    = self.adv.named_branch()
        self.hostile_commit = self.adv.forge_commit(HOSTILE, parent=self.adv.head_of(named),
                                                    branch_id=str(named.branch_id))
        self.adv.plant_objects(os.path.join(self.s.bob_dir, '.sg_vault'))
        with open(os.path.join(self.s.bob_dir, '.sg_vault', 'local', 'vault_key'), 'rb') as f:
            self.vault_key_before = f.read()

    def teardown_method(self):
        self.adv.cleanup()
        self.s.cleanup()

    def test_revert_to_a_hostile_commit_writes_only_real_content(self):
        Vault__Revert(crypto=self.s.crypto).revert_to_commit(self.s.bob_dir, self.hostile_commit)
        _assert_only_real_content_written(self.s.bob_dir, self.vault_key_before)

    def test_branch_switch_checkout_of_a_hostile_commit_writes_only_real_content(self):
        switch = Vault__Branch_Switch(crypto=self.s.crypto)
        c      = self.s.sync._init_components(self.s.bob_dir)
        switch._checkout_commit(self.s.bob_dir, c, self.hostile_commit)
        _assert_only_real_content_written(self.s.bob_dir, self.vault_key_before)

    def test_pull_of_a_hostile_head_writes_only_real_content(self):
        self.adv.move_branch(self.adv.named_branch(), self.hostile_commit)
        self.s.sync.pull(self.s.bob_dir)
        _assert_only_real_content_written(self.s.bob_dir, self.vault_key_before)


class Test_Fixed__Hostile_Paths__Stash_And_Restore:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'original'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()

    def teardown_method(self):
        self.s.cleanup()

    def test_stash_pop_contains_planted_names(self):
        vault = self.s.vault_dir
        with open(os.path.join(vault, 'readme.md'), 'w') as f:
            f.write('edited')
        stash  = Vault__Stash(crypto=self.s.crypto)
        result = stash.stash(vault)
        assert not result.get('nothing_to_stash')
        zip_path, meta_path, _meta = stash._find_latest_stash(stash._stash_dir(vault))

        with zipfile.ZipFile(zip_path, 'a') as zf:                         # what a tampered stash would carry
            zf.writestr('.git/hooks/post-checkout', b'PWNED')
            zf.writestr('../escape.txt', b'outside')
        with open(meta_path) as f:
            meta = json.load(f)
        outside = os.path.join(os.path.dirname(vault), 'keep-me.txt')
        with open(outside, 'w') as f:
            f.write('must survive')
        meta['files_deleted'] = list(meta.get('files_deleted') or []) + ['../keep-me.txt', '.sg_vault/local/vault_key']
        with open(meta_path, 'w') as f:
            json.dump(meta, f)

        stash.pop(vault)
        assert open(os.path.join(vault, 'readme.md')).read() == 'edited'
        assert not os.path.exists(os.path.join(vault, '.git', 'hooks', 'post-checkout'))
        assert not os.path.exists(os.path.join(os.path.dirname(vault), 'escape.txt'))
        assert os.path.isfile(outside)
        assert os.path.isfile(os.path.join(vault, '.sg_vault', 'local', 'vault_key'))

    def test_restore_from_backup_extracts_only_the_vault_folder(self):
        vault  = self.s.vault_dir
        target = os.path.join(self.s.tmp_dir, 'restored')
        os.makedirs(target)
        planted = os.path.join(target, '.vault__planted.zip')
        with zipfile.ZipFile(planted, 'w') as zf:                          # old-format backup with extra members
            for root, _dirs, files in os.walk(os.path.join(vault, '.sg_vault')):
                for name in files:
                    full = os.path.join(root, name)
                    zf.write(full, os.path.relpath(full, vault))
            zf.writestr('.git/hooks/post-checkout', b'PWNED')
            zf.writestr('notes.txt', b'planted working file')
        self.s.sync.restore_from_backup(planted, target)
        assert os.path.isdir(os.path.join(target, '.sg_vault', 'bare'))
        assert not os.path.exists(os.path.join(target, '.git'))
        assert not os.path.exists(os.path.join(target, 'notes.txt'))


class Test_Fixed__Backup_Zip_Names:

    def test_backup_zip_names_are_structural(self):
        """`sgit vault uninit` leaves .vault__<...>.zip (store + plaintext key) next
        to the files: never committed, never written from vault data."""
        guard = Vault__Path_Guard()
        for name in ('.vault__uninit_20261008.zip', 'docs/.vault__x.zip', '.VAULT__X.ZIP'):
            assert guard.is_protected(name)
            assert Vault__Ignore().should_ignore_file(name)
        for name in ('vault__x.zip', '.vault__notes.txt', 'backup.zip'):
            assert not guard.is_protected(name)


class Test_Fixed__Write_Path_Guard:
    """Review d3b8eef N4: `sgit write` had no path guard. It wrote ../escape.txt,
    .git/hooks/zz and .sg_vault/local/zz.txt, committed those paths into the tree, and
    wrote through an in-tree link into .sg_vault/local."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'hello'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s     = self._env.restore()
        self.vault = self.s.vault_dir

    def teardown_method(self):
        self.s.cleanup()

    def _tree(self):
        return set(self.s.sync._get_head_flat_map(self.vault)[0])

    @pytest.mark.parametrize('path', ['../escape.txt', '.git/hooks/zz', '.sg_vault/local/zz.txt', '/tmp/abs.txt',
                                      'docs/../../escape.txt'])
    def test_unsafe_paths_are_refused_before_anything_is_written(self, path):
        from sgit_ai.storage.Vault__Path_Guard import Vault__Unsafe_Path_Error
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.s.sync.write_file(self.vault, path, b'pwned')
        assert self._tree() == {'readme.md'}
        assert not os.path.exists(os.path.join(os.path.dirname(self.vault), 'escape.txt'))
        assert not os.path.exists(os.path.join(self.vault, '.sg_vault', 'local', 'zz.txt'))

    def test_an_unsafe_also_path_refuses_the_whole_write(self):
        from sgit_ai.storage.Vault__Path_Guard import Vault__Unsafe_Path_Error
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.s.sync.write_file(self.vault, 'ok.md', b'ok', also={'../escape.txt': b'x'})
        assert self._tree() == {'readme.md'}
        assert not os.path.exists(os.path.join(self.vault, 'ok.md'))

    def test_no_write_through_an_in_tree_link(self):
        from sgit_ai.storage.Vault__Path_Guard import Vault__Unsafe_Path_Error
        os.symlink(os.path.join(self.vault, '.sg_vault', 'local'), os.path.join(self.vault, 'notes'))
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.s.sync.write_file(self.vault, 'notes/zz.txt', b'pwned')
        assert not os.path.exists(os.path.join(self.vault, '.sg_vault', 'local', 'zz.txt'))

    def test_ordinary_paths_still_write_and_are_stored_normalised(self):
        self.s.sync.write_file(self.vault, 'docs/./a.md', b'a', also={'b.md': b'b'})
        assert self._tree() == {'readme.md', 'docs/a.md', 'b.md'}
        with open(os.path.join(self.vault, 'docs', 'a.md'), 'rb') as f:
            assert f.read() == b'a'
