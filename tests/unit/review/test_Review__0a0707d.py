"""Review of dev at 0a0707d (sgit.ai agent, 9 Oct 2026): release conditions and the
items recommended for the same release."""
import json
import os

import pytest

from tests._helpers.vault_test_env import Vault__Test_Env


def _write(d, rel, content):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full) or d, exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)


class Test_R1__One_Unreadable_Tag_Never_Breaks_The_Index:
    """A tag named `7e16` (valid on 0a0707d) made the d3b8eef build fail on the whole index,
    and the tombstone kept the name forever. Entries this version cannot read are skipped
    with a warning; the strict name rule applies only to `tag create`."""

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

    def teardown_method(self):
        self.s.cleanup()

    def _plant_tags(self, entries):
        c   = self.s.sync._init_components(self.s.alice_dir)
        key = f'{c.vault_id}/bare/indexes/{c.branch_index_file_id}'
        raw = json.loads(self.s.crypto.decrypt(c.read_key, self.s.api._store[key]))
        raw['tags'] = list(raw.get('tags') or []) + entries
        data = self.s.crypto.encrypt(c.read_key, json.dumps(raw).encode())
        self.s.api._store[key] = data                                                 # on the server
        with open(c.storage.index_path(self.s.alice_dir, c.branch_index_file_id), 'wb') as f:
            f.write(data)                                                             # and in alice's clone

    def test_an_invalid_tag_and_an_invalid_tombstone_are_skipped(self, capsys):
        self.s.sync.tag_create(self.s.alice_dir, 'v1.0', self.s.commit_id)
        self.s.sync.push(self.s.alice_dir)
        self._plant_tags([dict(name='not a name!', tag_id='obj-cas-imm-aaaaaaaaaaaa', timestamp_ms=1, deleted=False),
                          dict(name='bad;tombstone', tag_id='obj-cas-imm-bbbbbbbbbbbb', timestamp_ms=2, deleted=True)])
        _write(self.s.alice_dir, 'b.md', 'b')
        self.s.sync.commit(self.s.alice_dir, 'b')
        self.s.sync.push(self.s.alice_dir)                                 # alice reads and rewrites the index
        self.s.sync.pull(self.s.bob_dir)                                   # bob reads it
        carol = os.path.join(self.s.tmp_dir, 'carol')
        self.s.sync.clone(self.s.vault_key, carol)                         # a fresh clone reads it
        assert os.path.isfile(os.path.join(carol, 'b.md'))
        assert self.s.sync.resolve_revision(carol, 'v1.0') == self.s.commit_id    # the readable tag survives
        assert 'this sgit cannot read' in capsys.readouterr().err

    def test_names_valid_under_another_rule_are_read(self):
        from sgit_ai.schemas.Schema__Tag_Ref import Schema__Tag_Ref
        for name in ('7e16', 'abcdef0', 'EEA7053550B3', 'HEAD'):                  # refused by `tag create` today or later
            assert str(Schema__Tag_Ref.from_json(dict(name=name, tag_id='obj-cas-imm-aaaaaaaaaaaa', timestamp_ms=1)).name) == name

    def test_create_still_applies_the_rule(self):
        from sgit_ai.core.Vault__Errors import Vault__Tag_Error
        with pytest.raises(Vault__Tag_Error, match='not a valid tag name'):
            self.s.sync.tag_create(self.s.alice_dir, 'abcdef0', self.s.commit_id)


class Test_F2__A_Tag_Is_Never_Silently_Shadowed_By_A_Commit_Prefix:
    """`history show 7e16` showed commit 7e16627c… instead of the tag's target; a writer can
    mine a commit with a given 4-hex prefix in ~65k tries, bypassing the tag's signature."""

    def test_tag_and_commit_prefix_is_ambiguous_and_tag_colon_resolves(self):
        from sgit_ai.core.Vault__Errors import Vault__Revision_Error
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.md': 'a'})
        s = env.restore()
        try:
            _write(s.vault_dir, 'b.md', 'b')
            newer = s.sync.commit(s.vault_dir, 'b')['commit_id']
            s.sync.push(s.vault_dir)
            name  = newer[len('obj-cas-imm-'):][:4]                         # the newer commit's own 4-hex prefix
            s.sync.tag_create(s.vault_dir, name, s.commit_id)               # the tag names the OLDER commit
            with pytest.raises(Vault__Revision_Error, match='ambiguous'):
                s.sync.resolve_revision(s.vault_dir, name)
            assert s.sync.resolve_revision(s.vault_dir, f'tag:{name}') == s.commit_id
            assert s.sync.resolve_revision(s.vault_dir, newer)        == newer
        finally:
            s.cleanup()
            env.cleanup_snapshot()


class Test_0_21_x__Status_Fetch_And_Unreadable_Refs:

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

    def teardown_method(self):
        self.s.cleanup()

    def test_F8__status_reports_the_record_pull_refuses_on(self):
        _write(self.s.alice_dir, 'b.md', 'b'); self.s.sync.commit(self.s.alice_dir, 'b'); self.s.sync.push(self.s.alice_dir)
        self.s.sync.pull(self.s.bob_dir)
        os.remove(os.path.join(self.s.bob_dir, '.sg_vault', 'local', 'remote_heads.json'))
        status = self.s.sync.status(self.s.bob_dir)
        assert status['push_status'] == 'baseline_unreadable'
        assert 'accept-rewind' in status['baseline_error']

    def test_F7__fetch_downloads_but_never_moves_the_local_ref(self):
        c     = self.s.sync._init_components(self.s.bob_dir)
        index = c.branch_manager.load_branch_index(self.s.bob_dir, c.branch_index_file_id, c.read_key)
        ref   = str(c.branch_manager.get_branch_by_name(index, 'current').head_ref_id)
        before = c.ref_manager.read_ref(ref, c.read_key)
        _write(self.s.alice_dir, 'b.md', 'b'); self.s.sync.commit(self.s.alice_dir, 'b'); self.s.sync.push(self.s.alice_dir)
        result = self.s.sync.fetch(self.s.bob_dir)
        assert result['named_commit_id'] != before                       # it saw the new head
        assert c.ref_manager.read_ref(ref, c.read_key) == before          # and wrote no ref
        assert c.obj_store.exists(result['named_commit_id'])              # but has the objects

    def test_F9__an_unreadable_server_ref_fails_the_pull(self):
        from sgit_ai.core.Vault__Errors import Vault__Unreadable_Ref_Error
        c     = self.s.sync._init_components(self.s.bob_dir)
        index = c.branch_manager.load_branch_index(self.s.bob_dir, c.branch_index_file_id, c.read_key)
        key   = f'{c.vault_id}/bare/refs/{c.branch_manager.get_branch_by_name(index, "current").head_ref_id}'
        self.s.api._store[key] = b'not a ref this key opens'
        with pytest.raises(Vault__Unreadable_Ref_Error):
            self.s.sync.pull(self.s.bob_dir)


class Test_0_21_x__Small_Items:

    def test_F10__no_config_json_is_written_in_place(self):
        """Every writer goes through Vault__Storage.write_local_config (temp file, fsync, rename)."""
        import re, pathlib
        root    = pathlib.Path(__file__).resolve().parents[3] / 'sgit_ai'
        pattern = re.compile(r"open\(.*config(?:\.json|_path).*,\s*['\"]w")       # any spelling: missed a join (eed8084 F5)
        offenders = [str(p.relative_to(root)) for p in root.rglob('*.py')
                     if pattern.search(p.read_text()) and p.name != 'Plugin__Loader.py']   # a plugin's own config, not the vault's
        assert offenders == []

    def test_F10__write_local_config_is_atomic_and_private(self, tmp_path):
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        os.makedirs(tmp_path / '.sg_vault' / 'local')
        Vault__Storage().write_local_config(str(tmp_path), {'my_branch_id': 'x'})
        local = tmp_path / '.sg_vault' / 'local'
        assert sorted(os.listdir(local)) == ['config.json']                     # no temp file left behind
        assert json.loads((local / 'config.json').read_text()) == {'my_branch_id': 'x'}
        assert os.stat(local / 'config.json').st_mode & 0o077 == 0

    def test_doctor_names_no_remote_when_there_is_none(self, capsys):
        from sgit_ai.cli.CLI__Doctor         import CLI__Doctor
        from sgit_ai.cli.doctor.Doctor__Context import Doctor__Context
        CLI__Doctor().run(Doctor__Context(url='http://127.0.0.1:9', timeout_seconds=1))
        out = capsys.readouterr().out
        assert "this vault's server (http://127.0.0.1:9)" in out and "remote 'origin'" not in out


class Test_S11__Branch_Names_And_No_Silent_Fallback:

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
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        self.branches = Vault__Branch_Switch(crypto=self.s.crypto)

    def teardown_method(self):
        self.s.cleanup()

    def test_a_clone_whose_branch_is_gone_is_not_pushed_to_current(self):
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.schemas.Schema__Branch_Index  import Schema__Branch_Index
        from sgit_ai.schemas.Schema__Branch_Meta   import Schema__Branch_Meta
        index = Schema__Branch_Index(branches=[Schema__Branch_Meta(branch_id='branch-clone-aaaaaaaaaaaaaaaa', name='c',
                                                                    branch_type='clone',
                                                                    creator_branch='branch-named-bbbbbbbbbbbbbbbb'),
                                               Schema__Branch_Meta(branch_id='branch-named-cccccccccccccccc', name='current')])
        assert Vault__Branch_Manager().tracked_named_branch(index, 'branch-clone-aaaaaaaaaaaaaaaa') is None

    def test_two_clones_cannot_push_two_branches_with_one_name(self):
        self.branches.branch_new(self.s.alice_dir, 'feature')
        _write(self.s.alice_dir, 'f.md', 'alice'); self.s.sync.commit(self.s.alice_dir, 'f'); self.s.sync.push(self.s.alice_dir)
        self.branches.branch_new(self.s.bob_dir, 'feature')                     # bob never refreshed: local check passes
        _write(self.s.bob_dir, 'f.md', 'bob'); self.s.sync.commit(self.s.bob_dir, 'f')
        with pytest.raises(Exception, match="named 'feature' already exists on the server"):
            self.s.sync.push(self.s.bob_dir)


class Test_S12_S14__Messages_And_Reflog:

    def test_S12__the_switch_pull_error_is_printed_in_full(self, capsys):
        from sgit_ai.cli.CLI__Branch import CLI__Branch
        long = 'x' * 150 + ' run sgit pull --accept-rewind'
        CLI__Branch()._report_switch_pull(dict(status='error', error=long))
        assert '--accept-rewind' in capsys.readouterr().out

    def test_S14__the_reflog_never_shows_more_than_the_cap_and_trims_atomically(self, tmp_path):
        from sgit_ai.storage.Vault__Reflog import Vault__Reflog, MAX_ENTRIES
        reflog = Vault__Reflog(vault_path=str(tmp_path))
        for i in range(MAX_ENTRIES + 50):                                      # past the cap, below the batch trim
            reflog.append('ref-pid-muw-aaaaaaaaaaaa', f'obj-cas-imm-{i:012x}', f'obj-cas-imm-{i + 1:012x}')
        assert len(reflog.entries()) == MAX_ENTRIES
        for i in range(100):                                                   # past the batch trim
            reflog.append('ref-pid-muw-aaaaaaaaaaaa', f'obj-cas-imm-{i:012x}', f'obj-cas-imm-{i + 7:012x}')
        assert len(reflog.entries()) == MAX_ENTRIES
        assert [n for n in os.listdir(tmp_path / 'local') if n.startswith('.tmp')] == []


class Test_S15__Lease_Argument:

    def test_a_hex_named_vault_folder_is_the_directory_not_a_commit(self, tmp_path, monkeypatch):
        from types import SimpleNamespace
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        vault = tmp_path / 'cafe1234'
        (vault / '.sg_vault').mkdir(parents=True)
        seen = {}
        cli  = CLI__Vault()
        monkeypatch.setattr(cli, '_check_read_only', lambda d: (_ for _ in ()).throw(SystemExit(seen.update(d=d, lease=args.force_with_lease))))
        monkeypatch.chdir(tmp_path)
        args = SimpleNamespace(directory='.', force_with_lease='cafe1234')        # `push --force-with-lease cafe1234`
        with pytest.raises(SystemExit):
            cli.cmd_push(args)
        assert seen == dict(d='cafe1234', lease='')


class Test_Older_Nits__Revisions_And_Log:

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
        _write(self.s.vault_dir, 'b.md', 'b')
        self.second = self.s.sync.commit(self.s.vault_dir, 'second commit')['commit_id']

    def teardown_method(self):
        self.s.cleanup()

    def test_a_short_id_of_a_blob_is_not_a_revision(self):
        from sgit_ai.core.Vault__Errors import Vault__Revision_Error
        c    = self.s.sync._init_components(self.s.vault_dir)
        flat = self.s.sync._get_head_flat_map(self.s.vault_dir)[0]
        blob = flat['a.md']['blob_id']
        with pytest.raises(Vault__Revision_Error, match='not a commit'):
            self.s.sync.resolve_revision(self.s.vault_dir, blob)

    def test_history_log_with_a_revision(self, capsys, monkeypatch):
        from types import SimpleNamespace
        from sgit_ai.cli.CLI__Main import CLI__Main
        monkeypatch.chdir(self.s.vault_dir)
        with open(os.path.join(self.s.vault_dir, '.sg_vault', 'local', 'base_url'), 'w') as f:
            f.write('http://127.0.0.1:9')
        CLI__Main().run(['history', 'log', 'HEAD~1'])
        out = capsys.readouterr().out
        assert '(no commits)' not in out
        assert 'initial commit' in out and 'second commit' not in out

    def test_log_json_keeps_messages_and_branch_ids(self):
        from sgit_ai.core.actions.diff.Vault__Diff import Vault__Diff
        result = Vault__Diff(crypto=self.s.crypto).log_range_with_details(self.s.vault_dir, include_files=True)
        entry  = [e for e in result.json()['commits'] if e['commit_id'] == self.second][0]
        assert entry['message'] == 'second commit'
        assert entry['branch_id'].startswith('branch-clone-')


class Test_Older_Nits__Log_Filters:

    NOW = 1_800_000_000_000

    def _f(self, **kw):
        from sgit_ai.core.actions.history.Vault__Log_Filter import Vault__Log_Filter
        return Vault__Log_Filter().setup(now_ms=self.NOW, **kw)

    def test_dates_take_z_offsets_months_and_years(self):
        assert self._f(since='2026-10-08T14:30:00Z').since_ms == self._f(since='2026-10-08T14:30').since_ms
        assert self._f(since='2026-10-08T15:30:00+01:00').since_ms == self._f(since='2026-10-08T14:30').since_ms
        assert self._f(since='6mo').since_ms == self.NOW - 6 * 30 * 86400 * 1000
        assert self._f(since='1y').since_ms  == self.NOW - 365 * 86400 * 1000
        assert self._f(since='30m').since_ms == self.NOW - 30 * 60 * 1000                 # m stays minutes

    def test_until_includes_an_exact_match(self):
        when = self._f(until='2026-10-08T14:30').until_ms
        assert self._f(until='2026-10-08T14:30').matches(dict(timestamp_ms=when, message='x'))
        day_end = self._f(until='2026-10-08').until_ms
        assert self._f(until='2026-10-08').matches(dict(timestamp_ms=day_end, message='x'))
        assert not self._f(until='2026-10-08').matches(dict(timestamp_ms=day_end + 1, message='x'))

    def test_author_no_longer_over_matches(self):
        entry = dict(timestamp_ms=1, message='m', author_key_id='key-rnd-imm-12ab34cd56ef7890', branch_id='')
        assert self._f(author='12ab').matches(entry)                                        # start of the hex
        assert self._f(author='7890').matches(entry)                                        # end of the hex
        assert self._f(author='key-rnd-imm-12ab').matches(entry)                            # a prefix into the hex
        assert not self._f(author='key-1').matches(entry)
        assert not self._f(author='b34c').matches(entry)                                    # the middle
        named = dict(timestamp_ms=1, message='m', author_key_id='', branch_id='branch-named-aaaaaaaaaaaaaaaa')
        assert self._f(author='main').matches(named, {'branch-named-aaaaaaaaaaaaaaaa': 'main'})
        assert not self._f(author='mai').matches(named, {'branch-named-aaaaaaaaaaaaaaaa': 'main'})

    def test_grep_refuses_nested_repetition(self):
        from sgit_ai.core.Vault__Errors import Vault__Revision_Error
        for pattern in ('(a+)+$', '(x*)*', '(a|b+)+c'):          # (ab+)+c is allowed since eed8084 F4: every round starts with 'a'
            with pytest.raises(Vault__Revision_Error, match='exponential'):
                self._f(grep=pattern)
        assert self._f(grep='^fix: (api|cli)').grep                                         # ordinary groups are fine


class Test_Older_Nits__Hermetic_Guard:

    def test_dns_and_raw_sockets_are_refused_and_loopback_is_not(self):
        import socket
        from tests._helpers import hermetic_network
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo('example.com', 443)
        s = socket.socket()
        try:
            with pytest.raises(OSError, match='hermetic'):
                s.connect(('93.184.216.34', 443))
            assert s.connect_ex(('93.184.216.34', 443)) == 111
        finally:
            s.close()
        assert socket.getaddrinfo('127.0.0.1', 9)                            # loopback stays open
        hermetic_network._attempts.clear()                                   # this test's refusals were on purpose
