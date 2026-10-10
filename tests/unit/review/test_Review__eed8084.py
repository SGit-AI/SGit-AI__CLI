"""Review of dev at eed8084 (sgit.ai agent, 10 Oct 2026): the release gate.

B1 — tag entries this build cannot read were dropped on read and so erased from the
server by the next index write; a tombstone it could not read stopped hiding its tag."""
import json
import os

import pytest

from sgit_ai.core.Vault__Errors                 import Vault__Tag_Error
from sgit_ai.storage.Vault__Index_Reader        import Vault__Index_Reader
from tests._helpers.vault_test_env              import Vault__Test_Env


def _write(d, rel, content):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full) or d, exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)


NOT_A_NAME    = dict(name='not a name!',   tag_id='obj-cas-imm-aaaaaaaaaaaa', timestamp_ms=1, deleted=False)
BAD_TOMBSTONE = dict(name='bad;tombstone', tag_id='obj-cas-imm-bbbbbbbbbbbb', timestamp_ms=2, deleted=True)


class Test_B1__Entries_This_Build_Cannot_Read_Are_Carried:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.md': 'a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()
        Vault__Index_Reader.WARNED.clear()

    def teardown_method(self):
        self.s.cleanup()

    # the server copy, read raw: what every other client sees
    def _server_key(self):
        c = self.s.sync._init_components(self.s.alice_dir)
        return c, f'{c.vault_id}/bare/indexes/{c.branch_index_file_id}'

    def _server_tags(self) -> list:
        c, key = self._server_key()
        return json.loads(self.s.crypto.decrypt(c.read_key, self.s.api._store[key])).get('tags') or []

    def _plant_on_server(self, entries):
        c, key = self._server_key()
        raw = json.loads(self.s.crypto.decrypt(c.read_key, self.s.api._store[key]))
        raw['tags'] = list(raw.get('tags') or []) + entries
        self.s.api._store[key] = self.s.crypto.encrypt(c.read_key, json.dumps(raw).encode())

    def _entries(self, name):
        return [t for t in self._server_tags() if t.get('name') == name]

    def _tagged_and_pulled(self, *names):
        for name in names:
            self.s.sync.tag_create(self.s.alice_dir, name, self.s.commit_id)
        self.s.sync.pull(self.s.bob_dir)                                    # bob holds them, live
        assert {t['name'] for t in self.s.sync.tag_list(self.s.bob_dir)} >= set(names)

    def _bob_pushes(self):
        _write(self.s.bob_dir, 'b.md', 'b')
        self.s.sync.commit(self.s.bob_dir, 'b')
        self.s.sync.push(self.s.bob_dir)

    def test_after_bobs_push_the_server_still_has_both_raw_entries(self):
        self._tagged_and_pulled('v1.0')
        self._plant_on_server([NOT_A_NAME, BAD_TOMBSTONE])
        self._bob_pushes()
        server = self._server_tags()
        assert NOT_A_NAME    in server                                       # exactly as written
        assert BAD_TOMBSTONE in server
        assert self._entries('v1.0')[0]['deleted'] is False

    def test_a_tombstone_this_build_cannot_read_still_deletes_the_tag(self):
        self._tagged_and_pulled('v0.9', 'v1.0')
        live = self._entries('v0.9')[0]
        tomb = dict(live, deleted=True, timestamp_ms=live['timestamp_ms'] + 1000, reason='superseded')   # a field 0.21 does not know
        c, key = self._server_key()
        raw = json.loads(self.s.crypto.decrypt(c.read_key, self.s.api._store[key]))
        raw['tags'] = [t for t in raw['tags'] if t['name'] != 'v0.9'] + [tomb]      # another client deleted it
        self.s.api._store[key] = self.s.crypto.encrypt(c.read_key, json.dumps(raw).encode())
        self._bob_pushes()                                                   # bob still holds v0.9 live
        assert self._entries('v0.9') == [tomb]                               # not resurrected; carried unchanged
        assert 'v0.9' not in {t['name'] for t in self.s.sync.tag_list(self.s.bob_dir)}
        assert 'v1.0' in     {t['name'] for t in self.s.sync.tag_list(self.s.bob_dir)}

    def test_an_entry_whose_timestamp_cannot_be_read_wins_and_nothing_is_dropped(self):
        self._tagged_and_pulled('v1.0')
        live = self._entries('v1.0')[0]
        tomb = dict(live, deleted=True, timestamp_ms='2026-10-10T12:00:00Z')  # a future encoding of the date
        c, key = self._server_key()
        raw = json.loads(self.s.crypto.decrypt(c.read_key, self.s.api._store[key]))
        raw['tags'] = [t for t in raw['tags'] if t['name'] != 'v1.0'] + [tomb]
        self.s.api._store[key] = self.s.crypto.encrypt(c.read_key, json.dumps(raw).encode())
        self._bob_pushes()
        entries = self._entries('v1.0')
        assert tomb in entries and live in entries                           # both kept, for a client that can judge them
        assert self.s.sync.tag_list(self.s.bob_dir) == []                    # this build: the tombstone hides it

    def test_tag_create_and_delete_keep_them_too(self):
        self._tagged_and_pulled('v1.0')
        self._plant_on_server([NOT_A_NAME, BAD_TOMBSTONE])
        self.s.sync.tag_create(self.s.bob_dir, 'v2', self.s.commit_id)
        self.s.sync.tag_delete(self.s.bob_dir, 'v1.0')
        server = self._server_tags()
        assert NOT_A_NAME in server and BAD_TOMBSTONE in server
        assert {t['name'] for t in self.s.sync.tag_list(self.s.alice_dir)} == {'v2'}

    def test_a_pull_refresh_keeps_them(self):
        self._plant_on_server([NOT_A_NAME, BAD_TOMBSTONE])
        _write(self.s.alice_dir, 'c.md', 'c')
        self.s.sync.commit(self.s.alice_dir, 'c')
        self.s.sync.push(self.s.alice_dir)
        self.s.sync.pull(self.s.bob_dir)                                    # a clone with a write key refreshes the index
        server = self._server_tags()
        assert NOT_A_NAME in server and BAD_TOMBSTONE in server

    def test_a_name_held_by_an_unreadable_entry_is_not_taken_silently(self):
        self._plant_on_server([dict(name='v3', tag_id='obj-cas-imm-cccccccccccc', timestamp_ms=4102444800000 - 1,
                                    deleted=False, kind='annotated')])
        self.s.sync.pull(self.s.bob_dir)
        with pytest.raises(Vault__Tag_Error, match='cannot read'):
            self.s.sync.tag_create(self.s.bob_dir, 'v3', self.s.commit_id)

    def test_the_warning_is_printed_once_per_clone_not_per_command(self, capsys):
        self._plant_on_server([NOT_A_NAME])
        self.s.sync.pull(self.s.bob_dir)
        assert "'not a name!'" in capsys.readouterr().err
        Vault__Index_Reader.WARNED.clear()                                   # a new process
        self.s.sync.pull(self.s.bob_dir)
        self.s.sync.tag_list(self.s.bob_dir)
        assert 'cannot read' not in capsys.readouterr().err


class Test_B1__Reader:

    def test_round_trip_puts_carried_entries_back_in_tags(self):
        reader = Vault__Index_Reader()
        data   = dict(schema='branch_index_v1', branches=[], tags=[NOT_A_NAME, dict(name='v1', tag_id='obj-cas-imm-dddddddddddd',
                                                                                     timestamp_ms=5, deleted=False)])
        index  = reader.parse(data)
        assert [str(t.name) for t in index.tags] == ['v1']
        assert len(index.carried_tags) == 1
        out = reader.to_json(index)
        assert 'carried_tags' not in out
        assert NOT_A_NAME in out['tags']
        assert reader.to_json(reader.parse(out)) == out

    def test_unknown_fields_and_coerced_values_are_not_read(self):
        reader = Vault__Index_Reader()
        base   = dict(name='v1', tag_id='obj-cas-imm-dddddddddddd', timestamp_ms=5, deleted=False)
        assert reader.readable(base)
        assert not reader.readable(dict(base, signature='x'))                # would be dropped on write
        assert not reader.readable(dict(base, timestamp_ms='5'))             # would be coerced on write
        assert not reader.readable(dict(base, name='obj-cas-imm-0123456789ab'))   # commit-shaped (F6)

    def test_a_readable_later_entry_beats_an_older_unreadable_tombstone(self):
        live, tomb = (dict(name='v1', tag_id='obj-cas-imm-dddddddddddd', timestamp_ms=9, deleted=False),
                      dict(name='v1', tag_id='obj-cas-imm-dddddddddddd', timestamp_ms=3, deleted=True, why='x'))
        tags, carried = Vault__Index_Reader().resolve([live, tomb])
        assert tags == [live] and carried == []                              # what a client that reads both decides


class Test_B2__A_File_That_Cannot_Be_Opened_Is_Never_Deleted:
    """`read_regular` returned None for every open error, so a file held open by another
    program, or one without read permission, read as deleted: status listed it and commit
    removed it for everyone."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.md': 'a', 'secret-report.md': 'report'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s     = self._env.restore()
        self.vault = self.s.vault_dir
        self.sync  = self.s.sync

    def teardown_method(self):
        self.s.cleanup()

    def _deny(self, monkeypatch, name, error=PermissionError):
        real = os.open
        def fake_open(path, flags, *args, **kwargs):
            if os.path.basename(str(path)) == name:
                raise error(13, 'Permission denied', str(path))
            return real(path, flags, *args, **kwargs)
        monkeypatch.setattr(os, 'open', fake_open)

    def _committed(self):
        return set(self.sync._get_head_flat_map(self.vault)[0])

    def test_status_lists_it_as_unreadable_not_deleted(self, monkeypatch):
        self._deny(monkeypatch, 'secret-report.md')
        result = self.sync.status(self.vault)
        assert 'secret-report.md' not in result['deleted']
        assert result['unreadable'] == ['secret-report.md']
        assert result['clean'] is False

    def test_commit_refuses_naming_the_file_and_changes_nothing(self, monkeypatch):
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_File_Error
        _write(self.vault, 'b.md', 'b')
        self._deny(monkeypatch, 'secret-report.md')
        with pytest.raises(Vault__Unreadable_File_Error, match='secret-report.md'):
            self.sync.commit(self.vault, 'b')
        monkeypatch.undo()
        assert self._committed() == {'a.md', 'secret-report.md'}

    def test_an_io_error_is_refused_the_same_way(self, monkeypatch):
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_File_Error
        _write(self.vault, 'b.md', 'b')
        self._deny(monkeypatch, 'secret-report.md', error=OSError)          # EIO, a sharing violation
        with pytest.raises(Vault__Unreadable_File_Error):
            self.sync.commit(self.vault, 'b')

    def test_the_cli_prints_the_refusal_without_a_traceback(self, monkeypatch, capsys):
        from types import SimpleNamespace
        from sgit_ai.cli.CLI__Main      import CLI__Main
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_File_Error
        _write(self.vault, 'b.md', 'b')
        self._deny(monkeypatch, 'secret-report.md')
        with pytest.raises(Vault__Unreadable_File_Error) as caught:
            self.sync.commit(self.vault, 'b')
        CLI__Main()._print_friendly_error(caught.value, SimpleNamespace(command='commit', directory=self.vault))
        err = capsys.readouterr().err
        assert 'error: cannot read secret-report.md' in err and 'Traceback' not in err

    def test_a_fifo_at_a_tracked_path_keeps_the_committed_version(self, capsys):
        os.remove(os.path.join(self.vault, 'secret-report.md'))
        os.mkfifo(os.path.join(self.vault, 'secret-report.md'))
        assert 'secret-report.md' not in self.sync.status(self.vault)['deleted']
        _write(self.vault, 'b.md', 'b')
        self.sync.commit(self.vault, 'b')
        assert self._committed() == {'a.md', 'secret-report.md', 'b.md'}
        assert 'not a regular file' in capsys.readouterr().err

    def test_a_deleted_file_is_still_deleted(self):
        os.remove(os.path.join(self.vault, 'secret-report.md'))
        assert self.sync.status(self.vault)['deleted'] == ['secret-report.md']
        self.sync.commit(self.vault, 'rm')
        assert self._committed() == {'a.md'}


class Test_S1__A_Duplicate_Branch_Name_Never_Leaves_A_Clone_Stuck:
    """`refuse_duplicate_names` sat in the shared merge and pull swallowed it: the second
    clone's push reported `pushed` with its ref in no index entry, and from then on that
    clone never refreshed the index and could not tag, with no way out but a re-clone."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.md': 'a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        self.s        = self._env.restore()
        self.branches = Vault__Branch_Switch(crypto=self.s.crypto)
        self.branches.branch_new(self.s.alice_dir, 'feature')
        _write(self.s.alice_dir, 'f.md', 'alice'); self.s.sync.commit(self.s.alice_dir, 'f'); self.s.sync.push(self.s.alice_dir)
        self.branches.branch_new(self.s.bob_dir, 'feature')                 # bob never refreshed: the local check passes
        _write(self.s.bob_dir, 'f.md', 'bob'); self.s.sync.commit(self.s.bob_dir, 'f')

    def teardown_method(self):
        self.s.cleanup()

    def _server_index(self):
        c = self.s.sync._init_components(self.s.alice_dir)
        return json.loads(self.s.crypto.decrypt(c.read_key, self.s.api._store[f'{c.vault_id}/bare/indexes/{c.branch_index_file_id}']))

    def _server_named(self):
        return sorted(b['name'] for b in self._server_index()['branches'] if b.get('branch_type') == 'named')

    def _bobs_feature(self):
        c     = self.s.sync._init_components(self.s.bob_dir)
        index = c.branch_manager.load_branch_index(self.s.bob_dir, c.branch_index_file_id, c.read_key)
        cfg   = self.s.sync._read_local_config(self.s.bob_dir, c.storage)
        return c, c.branch_manager.tracked_named_branch(index, str(cfg.my_branch_id))

    def test_push_refuses_before_writing_anything(self):
        from sgit_ai.core.Vault__Errors import Vault__Push_Conflict_Error
        store_before = dict(self.s.api._store)
        with pytest.raises(Vault__Push_Conflict_Error, match="sgit branch rename feature <new-name>"):
            self.s.sync.push(self.s.bob_dir)
        assert self.s.api._store == store_before                              # no ref, no key, no index write
        c, feature = self._bobs_feature()
        assert f'{c.vault_id}/bare/refs/{feature.head_ref_id}' not in self.s.api._store

    def test_pull_keeps_refreshing_everything_else(self):
        self.s.sync.pull(self.s.bob_dir)                                    # the clash is skipped, not fatal
        self.s.sync.tag_create(self.s.alice_dir, 'v1.0', self.s.commit_id)
        self.branches.branch_new(self.s.alice_dir, 'other'); self.s.sync.push(self.s.alice_dir)
        self.s.sync.pull(self.s.bob_dir)
        c, _  = self._bobs_feature()
        index = c.branch_manager.load_branch_index(self.s.bob_dir, c.branch_index_file_id, c.read_key)
        assert 'other' in {str(b.name) for b in index.branches}
        assert [t['name'] for t in self.s.sync.tag_list(self.s.bob_dir)] == ['v1.0']
        assert self._server_named().count('feature') == 1                     # bob's clashing entry never written

    def test_tag_create_works_on_the_clashing_clone(self):
        self.s.sync.tag_create(self.s.bob_dir, 'v2', self.s.commit_id)
        assert 'v2' in {t['name'] for t in self._server_index()['tags']}
        assert self._server_named().count('feature') == 1

    def test_rename_then_push_registers_the_branch(self):
        self.s.sync.branch_rename(self.s.bob_dir, 'feature', 'feature-bob')
        self.s.sync.push(self.s.bob_dir)
        assert self._server_named() == ['current', 'feature', 'feature-bob']
        _, feature = self._bobs_feature()
        assert str(feature.name) == 'feature-bob'

    def test_rename_refuses_a_pushed_branch_and_a_taken_name(self):
        with pytest.raises(RuntimeError, match='on the server'):
            self.s.sync.branch_rename(self.s.alice_dir, 'feature', 'renamed')
        with pytest.raises(RuntimeError, match='already exists'):
            self.s.sync.branch_rename(self.s.bob_dir, 'feature', 'current')
        with pytest.raises(RuntimeError, match='not a valid branch name'):
            self.s.sync.branch_rename(self.s.bob_dir, 'feature', 'has space')

    def test_rename_is_under_branch_in_the_cli(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        args = CLI__Main().build_parser().parse_args(['branch', 'rename', 'feature', 'feature-bob', self.s.bob_dir])
        assert args.func.__name__ == 'cmd_branch_rename'


class Test_F1__Every_Working_Copy_Read_Is_Safe:
    """`diff`, `revert`, `switch`, `stash` and scope used plain open(): `sgit diff` hung on a FIFO."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.md': 'a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()

    def teardown_method(self):
        self.s.cleanup()

    def _finishes(self, call):
        import threading
        fifo, outcome = os.path.join(self.s.vault_dir, 'pipe'), {}
        os.mkfifo(fifo)
        worker = threading.Thread(target=lambda: outcome.setdefault('r', call()), daemon=True)
        worker.start()
        worker.join(timeout=20)
        if worker.is_alive():
            with open(fifo, 'wb'):                                           # unblock the reader before failing
                pass
            pytest.fail('hung reading a FIFO in the working copy')
        return outcome.get('r')

    def test_diff_does_not_hang_on_a_fifo(self):
        from sgit_ai.core.actions.diff.Vault__Diff import Vault__Diff
        self._finishes(lambda: Vault__Diff(crypto=self.s.crypto).diff_vs_head(self.s.vault_dir))

    def test_stash_status_does_not_hang_on_a_fifo(self):
        from sgit_ai.core.actions.stash.Vault__Stash import Vault__Stash
        _write(self.s.vault_dir, 'a.md', 'changed')
        self._finishes(lambda: Vault__Stash(crypto=self.s.crypto).stash(self.s.vault_dir))

    def test_no_plain_open_of_working_copy_files_is_left(self):
        import re
        root = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'sgit_ai', 'core', 'actions')
        for sub in ('diff/Vault__Diff.py', 'revert/Vault__Revert.py', 'branch/Vault__Branch_Switch.py',
                    'stash/Vault__Stash.py', 'scope/Vault__Sync__Scope.py'):
            with open(os.path.join(root, sub)) as f:
                source = f.read()
            assert not re.search(r"open\((full_path|local_path|local_file), 'rb'\)", source), sub


class Test_F3__A_Server_Ref_That_Does_Not_Decrypt_Is_Reported_Everywhere:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.md': 'a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()
        c      = self.s.sync._init_components(self.s.vault_dir)
        index  = c.branch_manager.load_branch_index(self.s.vault_dir, c.branch_index_file_id, c.read_key)
        cfg    = self.s.sync._read_local_config(self.s.vault_dir, c.storage)
        named  = c.branch_manager.tracked_named_branch(index, str(cfg.my_branch_id))
        self.s.api._store[f'{c.vault_id}/bare/refs/{named.head_ref_id}'] = self.s.crypto.encrypt(b'\x01' * 32, b'{"commit_id": "x"}')

    def teardown_method(self):
        self.s.cleanup()

    def test_status_does_not_say_in_sync(self):
        result = self.s.sync.status(self.s.vault_dir)
        assert result['push_status'] == 'baseline_unreadable'
        assert 'does not decrypt' in result['baseline_error']

    def test_push_refuses(self):
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_Ref_Error
        with pytest.raises(Vault__Unreadable_Ref_Error):
            self.s.sync.push(self.s.vault_dir)

    def test_fetch_refuses_instead_of_falling_back_to_the_local_ref(self):
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_Ref_Error
        with pytest.raises(Vault__Unreadable_Ref_Error):
            self.s.sync.fetch(self.s.vault_dir)
        with pytest.raises(Vault__Unreadable_Ref_Error):
            self.s.sync.sparse_fetch(self.s.vault_dir)                       # what `sgit fetch` runs


class Test_F4__Grep_Guard_Reads_The_Parsed_Pattern:

    @pytest.mark.parametrize('pattern', ['(a+|b)+$', '((a+))+$', '(a+)+$', '(a{2,})*', '(a+){10}', '(?:x*)*', '(A[a-z]+)+$'])
    def test_refused(self, pattern):
        from sgit_ai.core.Vault__Errors                       import Vault__Revision_Error
        from sgit_ai.core.actions.history.Vault__Log_Filter import Vault__Log_Filter
        with pytest.raises(Vault__Revision_Error, match='repeats a repetition'):
            Vault__Log_Filter().setup(grep=pattern)

    @pytest.mark.parametrize('pattern', ['(ab*){2}', 'fix(ed)?', '(feat|fix)+', '[a-z]+(-[a-z]+)*', '(/[^/]+)+', r'(\.\d+)*$'])
    def test_allowed(self, pattern):
        from sgit_ai.core.actions.history.Vault__Log_Filter import Vault__Log_Filter
        assert Vault__Log_Filter().setup(grep=pattern).grep == pattern
