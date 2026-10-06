"""Partial clones: a folder scope (--path) and a history depth (--depth), both
built on the Merkle tree — held folders as files, siblings by id. Two real
clones on the in-memory API: alice (full) and the scoped/shallow clones made
from the same vault."""
import os
import pytest
from tests._helpers.vault_test_env        import Vault__Test_Env
from sgit_ai.core.Vault__Sync             import Vault__Sync
from sgit_ai.core.Vault__Errors           import Vault__Scoped_Clone_Error
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

FILES = {'README.md': 'root', 'mail/crm/a.txt': 'a v1', 'mail/crm/sub/b.txt': 'b v1',
         'mail/inbox/c.txt': 'c v1', 'runs/r1.json': '{}', 'docs/d.md': 'd v1'}


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)

def _read(d, rel):
    with open(os.path.join(d, rel)) as f: return f.read()

def _tree(d):
    return sorted(os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs if '.sg_vault' not in r)

def _store_count(d):
    return len(os.listdir(os.path.join(d, '.sg_vault', 'bare', 'data')))


class _Counting_API(Vault__API__In_Memory):
    def setup(self):
        super().setup(); self.objects_requested = 0; return self
    def batch_read(self, vault_id, file_ids, failures=None):
        self.objects_requested += sum(1 for f in file_ids if '/bare/data/' in f'/{f}')
        return super().batch_read(vault_id, file_ids, failures)


class _Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files=FILES)

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync
        self.alice = self.env.alice_dir                       # full clone, used as "the other agents"
        self.api   = _Counting_API(); self.api.setup(); self.api._store = self.env.api._store
        self.psync = Vault__Sync(crypto=self.env.crypto, api=self.api)    # the partial clone's sync

    def teardown_method(self):
        self.env.cleanup()

    def _alice_pushes(self, files, message='alice'):
        for rel, content in files.items(): _write(self.alice, rel, content)
        self.sync.commit(self.alice, message=message); self.sync.push(self.alice)

    def _clone(self, name, **kw):
        target = os.path.join(self.env.tmp_dir, name)
        result = self.psync.clone(self.env.vault_key, target, **kw)
        return target, result


class Test_Scoped_Clone__Read(_Base):

    def test_holds_only_the_folder_and_its_spine(self):
        d, r = self._clone('scoped', scope_paths=['mail/crm'])
        assert _tree(d) == ['mail/crm/a.txt', 'mail/crm/sub/b.txt']
        assert r['scope_paths'] == ['mail/crm']
        full_objects = sum(1 for k in self.env.api._store if '/bare/data/obj-' in k)
        assert _store_count(d) < full_objects                       # trees and blobs of the held folder + spine only
        assert self.api.objects_requested == _store_count(d)         # nothing fetched that is not held
        assert self.sync.status(d)['clean'] is True

    def test_two_folders(self):
        d, _ = self._clone('two', scope_paths=['mail/crm', 'docs/'])
        assert _tree(d) == ['docs/d.md', 'mail/crm/a.txt', 'mail/crm/sub/b.txt']

    def test_read_only_scoped_clone(self):
        keys   = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        target = os.path.join(self.env.tmp_dir, 'ro')
        self.psync.clone_read_only(keys['vault_id'], keys['read_key'], target, scope_paths=['docs'])
        assert _tree(target) == ['docs/d.md']


class Test_Scoped_Clone__Write(_Base):

    def test_commit_push_changes_only_the_spine_and_others_see_it(self):
        d, _ = self._clone('w', scope_paths=['mail/crm'])
        _write(d, 'mail/crm/a.txt', 'a v2 (scoped)'); _write(d, 'mail/crm/new.txt', 'new')
        assert self.sync.status(d)['modified'] == ['mail/crm/a.txt']
        r = self.psync.commit(d, message='scoped edit'); assert r['files_changed'] >= 1
        self.psync.push(d)
        self.sync.pull(self.alice)
        assert _read(self.alice, 'mail/crm/a.txt') == 'a v2 (scoped)'
        assert _read(self.alice, 'mail/crm/new.txt') == 'new'
        for rel in ('README.md', 'mail/inbox/c.txt', 'runs/r1.json', 'docs/d.md'):
            assert _read(self.alice, rel) == FILES[rel]                 # siblings carried by id, untouched
        assert self.sync.status(self.alice)['clean'] is True

    def test_delete_inside_scope_is_a_real_delete(self):
        d, _ = self._clone('del', scope_paths=['mail/crm'])
        os.remove(os.path.join(d, 'mail/crm/sub/b.txt'))
        self.psync.commit(d, message='rm b'); self.psync.push(d)
        self.sync.pull(self.alice)
        assert not os.path.exists(os.path.join(self.alice, 'mail/crm/sub/b.txt'))
        assert _read(self.alice, 'mail/inbox/c.txt') == 'c v1'

    def test_file_outside_scope_refuses_commit_naming_it(self):
        d, _ = self._clone('out', scope_paths=['mail/crm'])
        _write(d, 'docs/stray.md', 'not held here')
        with pytest.raises(Vault__Scoped_Clone_Error, match='docs/stray.md'):
            self.psync.commit(d, message='x')

    def test_write_file_api_respects_scope(self):
        d, _ = self._clone('wf', scope_paths=['mail/crm'])
        self.psync.write_file(d, 'mail/crm/via-api.txt', b'hello', message='api write')
        with pytest.raises(Vault__Scoped_Clone_Error):
            self.psync.write_file(d, 'docs/x.md', b'nope')
        self.psync.push(d); self.sync.pull(self.alice)
        assert _read(self.alice, 'mail/crm/via-api.txt') == 'hello'


class Test_Scoped_Clone__Pull(_Base):

    def test_fast_forward_pull_fetches_only_what_is_held(self):
        d, _ = self._clone('ff', scope_paths=['mail/crm'])
        before = self.api.objects_requested
        self._alice_pushes({'docs/d.md': 'd v2', 'mail/crm/a.txt': 'a v2 (alice)'})
        r = self.psync.pull(d)
        assert r['status'] == 'merged' and r['modified'] == ['mail/crm/a.txt']
        assert _read(d, 'mail/crm/a.txt') == 'a v2 (alice)'
        assert not os.path.exists(os.path.join(d, 'docs'))            # still not held
        assert self.api.objects_requested - before <= 4                # commit + root + mail + crm (+ the one blob)

    def test_pull_outside_scope_change_is_a_no_op_locally_but_keeps_the_tree_whole(self):
        d, _ = self._clone('noop', scope_paths=['mail/crm'])
        self._alice_pushes({'docs/d.md': 'd v2'})
        r = self.psync.pull(d)
        assert r['status'] == 'merged' and r['modified'] == [] and r['added'] == []
        # and a commit from the scoped clone now carries alice's docs change by id
        _write(d, 'mail/crm/a.txt', 'a v3'); self.psync.commit(d, message='after pull'); self.psync.push(d)
        self.sync.pull(self.alice)
        assert _read(self.alice, 'docs/d.md') == 'd v2' and _read(self.alice, 'mail/crm/a.txt') == 'a v3'

    def test_three_way_merge_with_a_change_outside_scope(self):
        d, _ = self._clone('3way', scope_paths=['mail/crm'])
        _write(d, 'mail/crm/a.txt', 'a (scoped)'); self.psync.commit(d, message='scoped')     # ours
        self._alice_pushes({'docs/d.md': 'd v2', 'mail/inbox/c.txt': 'c v2'})                # theirs, all outside scope
        r = self.psync.pull(d)
        assert r['status'] == 'merged'
        self.psync.push(d); self.sync.pull(self.alice)
        assert _read(self.alice, 'mail/crm/a.txt') == 'a (scoped)'
        assert _read(self.alice, 'docs/d.md') == 'd v2' and _read(self.alice, 'mail/inbox/c.txt') == 'c v2'

    def test_two_scoped_agents_in_different_folders_never_conflict(self):
        a, _ = self._clone('agent-a', scope_paths=['mail/crm'])
        b, _ = self._clone('agent-b', scope_paths=['docs'])
        _write(a, 'mail/crm/a.txt', 'A'); self.psync.commit(a, message='A'); self.psync.push(a)
        _write(b, 'docs/d.md', 'B');      self.psync.commit(b, message='B')
        r = self.psync.pull(b); assert r['status'] == 'merged' and r.get('conflicts', []) == []
        self.psync.push(b)
        self.sync.pull(self.alice)
        assert _read(self.alice, 'mail/crm/a.txt') == 'A' and _read(self.alice, 'docs/d.md') == 'B'

    def test_uncommitted_edit_in_scope_survives_a_pull(self):
        d, _ = self._clone('dirty', scope_paths=['mail/crm'])
        self._alice_pushes({'docs/d.md': 'd v2'})
        _write(d, 'mail/crm/a.txt', 'a UNCOMMITTED')
        r = self.psync.pull(d)
        assert r['status'] == 'merged' and _read(d, 'mail/crm/a.txt') == 'a UNCOMMITTED'


class Test_Shallow_Clone(_Base):

    def _history(self):
        for i in range(3):
            self._alice_pushes({'runs/r1.json': f'{{"v":{i}}}'}, message=f'h{i}')

    def test_depth_1_holds_one_commit_and_works(self):
        self._history()
        d, r = self._clone('shallow', depth=1)
        assert len(r['boundaries']) == 1 and r['boundaries'][0] == r['commit_id']
        assert _tree(d) == sorted(FILES)                                # whole tree, one commit
        commits_local = [o for o in os.listdir(os.path.join(d, '.sg_vault', 'bare', 'data'))]
        assert self.api.objects_requested < sum(1 for k in self.env.api._store if '/bare/data/obj-' in k)
        st = self.sync.status(d); assert (st['clean'], st['ahead'], st['behind']) == (True, 0, 0)

    def test_shallow_commit_push_pull_round_trip(self):
        self._history()
        d, _ = self._clone('sh', depth=1)
        _write(d, 'docs/d.md', 'from shallow'); self.psync.commit(d, message='shallow edit'); self.psync.push(d)
        self.sync.pull(self.alice); assert _read(self.alice, 'docs/d.md') == 'from shallow'
        self._alice_pushes({'README.md': 'root v2'})
        st = self.sync.status(d); assert (st['ahead'], st['behind'], st['push_status']) == (0, 1, 'behind')
        r = self.psync.pull(d); assert r['status'] == 'merged' and _read(d, 'README.md') == 'root v2'

    def test_unshallow_fetches_the_history(self):
        self._history()
        d, r = self._clone('deep', depth=1)
        n_before = _store_count(d)
        out = self.psync.unshallow(d)
        assert out['fetched'] > 0 and _store_count(d) > n_before
        assert self.sync.scope_of(d).is_shallow() is False
        assert self.psync.unshallow(d)['already_full'] is True

    def test_scoped_and_shallow_together(self):
        self._history()
        d, r = self._clone('both', depth=1, scope_paths=['mail/crm'])
        assert _tree(d) == ['mail/crm/a.txt', 'mail/crm/sub/b.txt'] and len(r['boundaries']) == 1
        _write(d, 'mail/crm/a.txt', 'both'); self.psync.commit(d, message='both'); self.psync.push(d)
        self.sync.pull(self.alice); assert _read(self.alice, 'mail/crm/a.txt') == 'both'
        out = self.psync.unshallow(d); assert out['fetched'] > 0          # commits only on a scoped clone
        assert _tree(d) == ['mail/crm/a.txt', 'mail/crm/sub/b.txt']


class Test_Widen_And_Guards(_Base):

    def test_widen_adds_a_folder(self):
        d, _ = self._clone('widen', scope_paths=['mail/crm'])
        out = self.psync.widen(d, 'docs')
        assert out['written'] == 1 and _read(d, 'docs/d.md') == 'd v1'
        assert self.sync.scope_of(d).paths == ['mail/crm', 'docs']
        _write(d, 'docs/d.md', 'widened'); self.psync.commit(d, message='w'); self.psync.push(d)
        self.sync.pull(self.alice); assert _read(self.alice, 'docs/d.md') == 'widened'
        assert self.psync.widen(d, 'docs')['already_held'] is True

    def test_whole_vault_commands_refuse_on_a_partial_clone(self):
        d, _ = self._clone('guard', scope_paths=['mail/crm'])
        with pytest.raises(Vault__Scoped_Clone_Error, match='whole vault'):
            self.psync.require_whole(d, 'sgit check fsck')
        self.sync.require_whole(self.alice, 'sgit check fsck')          # a full clone passes

    def test_branch_switch_config_write_keeps_scope(self):
        d, _ = self._clone('bs', scope_paths=['mail/crm'])
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        cfg_before = self.sync.scope_of(d)
        Vault__Branch_Switch(crypto=self.env.crypto)._write_local_config(d, Vault__Storage(), 'branch-clone-0000000000000000')
        assert self.sync.scope_of(d).paths == cfg_before.paths


class Test_Full_Clone_Unchanged(_Base):

    def test_full_clone_has_no_scope_no_boundary_and_the_same_tree(self):
        d, r = self._clone('full')
        assert r['scope_paths'] == [] and r['boundaries'] == [] and r['depth'] == 0
        assert _tree(d) == sorted(FILES)
        assert self.sync.scope_of(d).is_partial() is False
        assert _store_count(d) == sum(1 for k in self.env.api._store if '/bare/data/obj-' in k)


class Test_Shallow_Clone__CLI_Log(_Base):

    def test_history_log_ends_with_a_shallow_note_not_an_error(self, capsys):
        for i in range(2):
            self._alice_pushes({'runs/r1.json': f'{{"v":{i}}}'}, message=f'h{i}')
        d, _ = self._clone('log', depth=1)
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        import types
        cli  = CLI__Vault(token_store=CLI__Token_Store(), credential_store=CLI__Credential_Store())
        args = types.SimpleNamespace(directory=d, oneline=True, graph=False, limit=None, vault_key=None, read_key=None)
        cli.cmd_inspect_log(args)
        out = capsys.readouterr().out
        assert 'h1' in out
        assert 'not found locally' not in out
        assert 'history stops here: shallow clone' in out and '--unshallow' in out
