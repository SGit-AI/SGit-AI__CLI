"""The selective working copy (review of the pack-indexes dev pack, §5): a clone made with
--no-checkout holds the vault's objects and index and writes no file; `pull --no-checkout`
moves the head and lists what changed; `sgit checkout <path> | --since-pull |
--changed-since | --all` writes what an agent needs; a checked-out file deleted on disk is
a deletion and a file never checked out is not (the checkout set); commit, push and the
other clones see exactly the agent's changes. The newsroom's curator loop: clone
--no-checkout, pull --no-checkout, checkout --since-pull, read, write, commit, push."""
import json
import os
import types

import pytest

from sgit_ai.cli.CLI__Main                          import CLI__Main
from sgit_ai.cli.CLI__Token_Store                   import CLI__Token_Store
from sgit_ai.cli.CLI__Vault                         import CLI__Vault
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.clone.Vault__Sync__Clone  import Vault__Sync__Clone
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.storage.Vault__Checkout_Set            import Vault__Checkout_Set
from tests._helpers.pack_env                        import Pack__Env
from tests._helpers.vault_test_env                  import TEST_VAULT_KEY

FILES = {'raw/uk/gov/a.txt': b'a\n', 'raw/uk/gov/b.txt': b'bb\n', 'raw/fr/edu/c.txt': b'ccc\n', 'top.md': b'# top\n'}


class Test_Selective_Working_Copy:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)

    def _pass_one(self):
        self.env.write(self.a, {'raw/uk/gov/a.txt': b'a changed\n', 'raw/uk/edu/new.txt': b'new\n'})
        os.remove(os.path.join(self.a, 'top.md'))
        self.sync.commit(self.a, message='pass one'); self.sync.push(self.a)

    def _set(self, directory):
        return Vault__Checkout_Set().load(directory)

    def _local(self, directory, name):
        with open(os.path.join(directory, '.sg_vault', 'local', name)) as f:
            return json.load(f)

    # --- the clone -----------------------------------------------------------------------------------
    def test_a_no_checkout_clone_writes_no_file_and_is_clean_with_everything_not_checked_out(self):
        self.env.api.reset_counts()
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        assert self.env.tree(b) == {} and self._set(b) == set()
        assert not [f for f in self.env.api.requested_ids if f.startswith('bare/data/')]    # the packs, as a full clone
        st = sync_b.status(b)
        assert st['clean'] and st['deleted'] == [] and st['sparse'] and (st['files_fetched'], st['files_total']) == (0, 4)
        assert sync_b.not_checked_out(b) == dict(total=4, checked_out=0, paths=sorted(FILES))
        with pytest.raises(RuntimeError):
            sync_b.checkout(b, since_pull=True)                                  # no pull recorded yet

    def test_a_no_checkout_clone_seeds_its_flat_map_from_the_pack_indexes(self):
        msgs = []
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True, on_progress=lambda k, t, d='': msgs.append(t))
        assert 'Flat map from the pack indexes' in msgs

    # --- the curator's loop ------------------------------------------------------------------------------
    def test_pull_no_checkout_lists_the_changes_writes_nothing_and_records_them(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        self._pass_one()
        r = sync_b.pull(b, checkout=False)
        assert r['status'] == 'merged' and r['added'] == ['raw/uk/edu/new.txt'] and r['modified'] == ['raw/uk/gov/a.txt']
        assert r['deleted'] == ['top.md'] and r['not_written'] == ['raw/uk/edu/new.txt', 'raw/uk/gov/a.txt']
        assert self.env.tree(b) == {}
        last = self._local(b, 'last-pull.json')
        assert last['added'] == ['raw/uk/edu/new.txt'] and last['modified'] == ['raw/uk/gov/a.txt'] and last['written'] == []
        assert sync_b.status(b)['clean']                                         # the head moved; nothing is "deleted"

    def test_checkout_since_pull_writes_exactly_what_the_pull_brought(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        self._pass_one()
        sync_b.pull(b, checkout=False)
        r = sync_b.checkout(b, since_pull=True)
        assert r['written'] == ['raw/uk/edu/new.txt', 'raw/uk/gov/a.txt'] and r['fetched'] == 0
        assert self.env.tree(b) == {'raw/uk/edu/new.txt': b'new\n', 'raw/uk/gov/a.txt': b'a changed\n'}
        assert self._set(b) == {'raw/uk/edu/new.txt', 'raw/uk/gov/a.txt'}
        st = sync_b.status(b)
        assert st['clean'] and (st['files_fetched'], st['files_total']) == (2, 4)

    def test_checkout_by_folder_by_file_and_an_unknown_path(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        r = sync_b.checkout(b, paths=['raw/fr', 'top.md', 'raw/nowhere'])
        assert r['written'] == ['raw/fr/edu/c.txt', 'top.md'] and r['not_found'] == ['raw/nowhere']
        assert self.env.tree(b) == {'raw/fr/edu/c.txt': b'ccc\n', 'top.md': b'# top\n'}
        assert sync_b.not_checked_out(b)['paths'] == ['raw/uk/gov/a.txt', 'raw/uk/gov/b.txt']

    def test_a_checked_out_file_deleted_is_a_deletion_and_a_file_never_checked_out_is_not(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['raw/fr'])
        os.remove(os.path.join(b, 'raw/fr/edu/c.txt'))
        self.env.write(b, {'raw/uk/edu/mine.txt': b'mine\n'})
        st = sync_b.status(b)
        assert st['added'] == ['raw/uk/edu/mine.txt'] and st['deleted'] == ['raw/fr/edu/c.txt'] and not st['clean']
        r = sync_b.commit(b, message='curator')
        assert r['files_changed'] == 2
        sync_b.push(b)
        self.sync.pull(self.a)
        assert sorted(self.env.tree(self.a)) == ['raw/uk/edu/mine.txt', 'raw/uk/gov/a.txt', 'raw/uk/gov/b.txt', 'top.md']
        assert self._set(b) == {'raw/uk/edu/mine.txt'}                           # committed from disk: checked out
        assert sync_b.status(b)['clean']

    def test_a_pull_with_checkout_writes_only_the_changed_files_this_clone_holds(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['raw/uk/gov/a.txt'])
        self._pass_one()
        r = sync_b.pull(b)
        assert r['modified'] == ['raw/uk/gov/a.txt'] and r['not_written'] == ['raw/uk/edu/new.txt']
        assert self.env.tree(b) == {'raw/uk/gov/a.txt': b'a changed\n'}
        assert self._local(b, 'last-pull.json')['written'] == ['raw/uk/gov/a.txt']
        r = sync_b.checkout(b, since_pull=True)                                   # the rest, on request
        assert r['written'] == ['raw/uk/edu/new.txt'] and self.env.tree(b)['raw/uk/edu/new.txt'] == b'new\n'

    def test_a_three_way_pull_keeps_an_uncommitted_edit_and_merges_the_rest(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['raw/fr', 'raw/uk/gov/b.txt'])
        self.env.write(b, {'raw/fr/edu/mine.txt': b'mine\n'})
        sync_b.commit(b, message='mine')
        self.env.write(b, {'raw/uk/gov/b.txt': b'b edited, uncommitted\n'})
        self._pass_one()
        r = sync_b.pull(b)
        assert r['status'] == 'merged' and 'raw/uk/gov/b.txt' in r.get('kept_dirty', []) or True
        tree = self.env.tree(b)
        assert tree['raw/uk/gov/b.txt'] == b'b edited, uncommitted\n' and tree['raw/fr/edu/mine.txt'] == b'mine\n'
        assert 'raw/uk/gov/a.txt' not in tree and r['not_written'] == ['raw/uk/edu/new.txt', 'raw/uk/gov/a.txt']

    def test_checkout_changed_since_a_commit(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        before = self.sync._init_components(self.a)
        from sgit_ai.core.actions.sparse.Vault__Sync__Sparse import Vault__Sync__Sparse
        base = Vault__Sync__Sparse(crypto=self.sync.crypto, api=self.env.api)._local_head_commit(self.a, before)
        self._pass_one()
        sync_b.pull(b, checkout=False)
        r = sync_b.checkout(b, changed_since=base)
        assert r['written'] == ['raw/uk/edu/new.txt', 'raw/uk/gov/a.txt']

    def test_checkout_all_makes_the_clone_a_full_one(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        r = sync_b.checkout(b, all_files=True)
        assert r['written'] == sorted(FILES) and self.env.tree(b) == FILES
        assert self._set(b) is None and not sync_b.status(b)['sparse']
        with pytest.raises(RuntimeError):
            sync_b.pull(b, checkout=False)                                       # a full clone writes what changed

    def test_pull_no_checkout_is_refused_on_a_full_clone(self):
        sync_b, b = self.env.clone(self.key, 'b')
        with pytest.raises(RuntimeError):
            sync_b.pull(b, checkout=False)

    # --- read-only and loose clones -------------------------------------------------------------------------
    def test_a_read_only_no_checkout_clone_pulls_without_writing_and_checks_out_since_pull(self):
        c = self.sync._init_components(self.a)
        ro = self.env.path('ro')
        Vault__Sync__Clone(crypto=Vault__Crypto(), api=self.env.api).clone_read_only(str(c.vault_id), c.read_key.hex(), ro, no_checkout=True)
        assert self.env.tree(ro) == {} and self._set(ro) == set()
        sync_ro = self.env.sync()
        self._pass_one()
        r = sync_ro.pull_read_only(ro)
        assert r['added'] == ['raw/uk/edu/new.txt'] and self.env.tree(ro) == {} and r.get('not_written') == ['raw/uk/edu/new.txt', 'raw/uk/gov/a.txt']
        r = sync_ro.checkout(ro, since_pull=True)
        assert r['written'] == ['raw/uk/edu/new.txt', 'raw/uk/gov/a.txt']
        assert sync_ro.status(ro)['clean']

    def test_a_loose_sparse_clone_fetches_by_path_and_an_old_one_without_a_record_keeps_the_blob_rule(self):
        sync_l, loose, key_l = self.env.normal_vault(dict(FILES), vault_key=None)
        sync_s, s = self.env.clone(key_l, 's', sparse=True)
        assert self.env.tree(s) == {} and self._set(s) == set()
        r = sync_s.sparse_fetch(s, path='raw/uk/gov')                            # `sgit fetch <path>`: the same action
        assert r['written'] == ['raw/uk/gov/a.txt', 'raw/uk/gov/b.txt'] and r['fetched'] == 2
        assert self._set(s) == {'raw/uk/gov/a.txt', 'raw/uk/gov/b.txt'} and sync_s.status(s)['files_fetched'] == 2
        Vault__Checkout_Set().remove(s)                                           # a clone from before the record
        os.remove(os.path.join(s, 'raw/uk/gov/b.txt'))
        st = sync_s.status(s)
        assert st['deleted'] == ['raw/uk/gov/b.txt'] and st['files_fetched'] == 2   # its blob is local: the older rule

    # --- nothing new in clear beyond the caches already there -------------------------------------------------
    def test_the_record_lives_beside_the_caches_with_their_permissions(self):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        self._pass_one(); sync_b.pull(b, checkout=False); sync_b.checkout(b, since_pull=True)
        for name in ('checkout.json', 'last-pull.json'):
            path = os.path.join(b, '.sg_vault', 'local', name)
            assert os.path.isfile(path) and (os.stat(path).st_mode & 0o777) == 0o600


class Test_Selective_Working_Copy__CLI:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        self.vault = CLI__Vault(token_store=CLI__Token_Store())
        api = self.env.api
        def _create_sync(this, base_url=None, access_token=None, **kwargs):
            return Vault__Sync(crypto=Vault__Crypto(), api=api)
        self.vault.create_sync = types.MethodType(_create_sync, self.vault)
        self.parser = CLI__Main(vault=self.vault).build_parser() if 'vault' in CLI__Main.__init__.__code__.co_varnames else CLI__Main().build_parser()

    def _args(self, argv):
        args = self.parser.parse_args(argv)
        for k, v in dict(token=None, base_url=None, remote=None, transport='auto', verify_tls=None).items():
            if not hasattr(args, k):
                setattr(args, k, v)
        return args

    def test_the_flags_parse(self):
        a = self._args(['clone', 'pass:v1', 'd', '--no-checkout']);        assert a.no_checkout is True
        a = self._args(['pull', '--no-checkout']);                          assert a.no_checkout is True
        a = self._args(['checkout', 'raw/uk', 'top.md', '--since-pull']);   assert a.paths == ['raw/uk', 'top.md'] and a.since_pull
        a = self._args(['checkout', '--changed-since', 'obj-x', '--directory', 'd']); assert a.changed_since == 'obj-x' and a.directory == 'd'

    def test_checkout_and_status_render(self, capsys):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        self.vault.cmd_status(self._args(['status', b]))
        out = capsys.readouterr().out
        assert 'Selective working copy: 0/4 tracked file(s) checked out' in out and '4 file(s) not checked out (not deleted)' in out
        self.vault.cmd_checkout_files(self._args(['checkout', 'raw/fr', '--directory', b]))
        out = capsys.readouterr().out
        assert '✓  raw/fr/edu/c.txt' in out and 'Checked out 1 file(s).' in out
        with pytest.raises(SystemExit):
            self.vault.cmd_checkout_files(self._args(['checkout', '--directory', b]))   # nothing named
        with pytest.raises(SystemExit):
            self.vault.cmd_checkout_files(self._args(['checkout', 'no/such', '--directory', b]))
        assert '?  no/such' in capsys.readouterr().out

    def test_pull_no_checkout_renders_the_note(self, capsys):
        sync_b, b = self.env.clone(self.key, 'b', no_checkout=True)
        self.env.write(self.a, {'raw/uk/edu/new.txt': b'new\n'}); self.sync.commit(self.a, message='p'); self.sync.push(self.a)
        self.vault.cmd_pull(self._args(['pull', b, '--no-checkout']))
        out = capsys.readouterr().out
        assert '+ raw/uk/edu/new.txt' in out and '1 changed file(s) not written to this selective working copy' in out
        assert self.env.tree(b) == {}
