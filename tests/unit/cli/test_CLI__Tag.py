"""Unit tests for CLI__Tag — `sgit vault tag [list|create|show|delete]`.

The parser is the real one (CLI__Tag.register on an argparse subparser, or CLI__Main's),
so every Namespace is what argparse produces; create_sync on the CLI__Vault is replaced
to hand back a Vault__Sync over the in-memory host of Vault__Test_Env (no HTTP)."""
import argparse
import os
import types as _types

import pytest

from sgit_ai.cli.CLI__Main             import CLI__Main
from sgit_ai.cli.CLI__Tag              import CLI__Tag, STATUS_TEXT
from sgit_ai.cli.CLI__Token_Store      import CLI__Token_Store
from sgit_ai.cli.CLI__Vault            import CLI__Vault
from sgit_ai.core.Vault__Sync          import Vault__Sync
from tests._helpers.vault_test_env     import Vault__Test_Env


def _inject(cli_vault: CLI__Vault, snap) -> CLI__Vault:
    def _create_sync(self, base_url=None, access_token=None, **kwargs):
        return Vault__Sync(crypto=snap.crypto, api=snap.api)
    cli_vault.create_sync = _types.MethodType(_create_sync, cli_vault)
    return cli_vault


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class Test_CLI__Tag:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.txt': 'a v1'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.sync  = self.snap.sync
        self.alice = self.snap.alice_dir
        self.bob   = self.snap.bob_dir
        self.vault = _inject(CLI__Vault(token_store=CLI__Token_Store()), self.snap)
        self.tag   = CLI__Tag(vault=self.vault)
        parser     = argparse.ArgumentParser()
        self.tag.register(parser.add_subparsers(dest='vault_command'))
        self.parse = parser.parse_args

    def teardown_method(self):
        self.snap.cleanup()

    def run(self, argv: list):
        args = self.parse(['tag'] + argv)
        return args.func(args)

    # ── register ────────────────────────────────────────────────────────
    def test_register_without_a_shared_network_parser_builds_its_own(self):
        """network_args None: the tag parsers still accept --token / --base-url."""
        args = self.parse(['tag', 'list', '--token', 'tok', '--base-url', 'http://127.0.0.1:9', self.alice])
        assert args.token == 'tok' and args.base_url == 'http://127.0.0.1:9' and args.directory == self.alice
        assert args.func == self.tag.cmd_list

    def test_bare_tag_lists_with_a_hidden_directory_option(self):
        """`vault tag` alone is `vault tag list`; --directory is accepted though hidden from help."""
        args = self.parse(['tag', '--directory', self.alice])
        assert args.func == self.tag.cmd_list and args.directory == self.alice and args.tag_command is None

    # ── list ────────────────────────────────────────────────────────────
    def test_list_with_no_tags_says_how_to_create_one(self, capsys):
        self.run(['list', self.alice])
        assert capsys.readouterr().out == 'No tags yet. Create one with: sgit vault tag create <name> -m "<message>"\n'

    def test_list_shows_mark_name_short_id_date_and_first_message_line(self, capsys):
        """One line per tag, sorted by name, names padded to the widest; the commit id is
        shown without its obj-cas-imm- prefix; only the message's first line is shown."""
        r = self.sync.tag_create(self.alice, 'v1.0', message='first release\nsecond line never shown')
        self.sync.tag_create(self.alice, 'release/2026-10', message='')
        self.run(['list', self.alice])
        lines = capsys.readouterr().out.splitlines()
        assert len(lines) == 2
        assert lines[0].startswith('  ✓ release/2026-10  ') and lines[0].endswith('UTC  ')
        assert lines[1].startswith('  ✓ v1.0             ' + r['commit_id'][len('obj-cas-imm-'):] + '  ')
        assert lines[1].endswith('UTC  first release') and 'second line' not in lines[1]
        assert '!' not in capsys.readouterr().out

    def test_list_marks_a_bad_tag_and_warns(self, capsys):
        """A tag whose object the host swapped is marked '!' and the warning line follows."""
        r = self.sync.tag_create(self.alice, 'v1.0', message='m')
        c = self.sync._init_components(self.alice)
        os.remove(os.path.join(self.alice, '.sg_vault', 'bare', 'data', r['tag_id']))
        self.snap.api._store[f'{c.vault_id}/bare/data/{r["tag_id"]}'] = self.snap.crypto.encrypt(c.read_key, b'{}')
        self.run(['list', self.alice])
        out = capsys.readouterr().out
        assert out.startswith('  ! v1.0  (unavailable)  ')
        assert out.rstrip().endswith('! = signature does not verify: do not trust that tag; sgit vault tag show <name>')

    def test_list_shows_a_missing_object_as_unavailable_with_a_question_mark(self, capsys):
        r = self.sync.tag_create(self.alice, 'v1.0', message='m')
        c = self.sync._init_components(self.alice)
        os.remove(os.path.join(self.alice, '.sg_vault', 'bare', 'data', r['tag_id']))
        self.snap.api._store.pop(f'{c.vault_id}/bare/data/{r["tag_id"]}')
        self.run(['list', self.alice])
        out = capsys.readouterr().out
        assert out.startswith('  ? v1.0  (unavailable)  ') and '! =' not in out

    # ── create ──────────────────────────────────────────────────────────
    def test_create_tags_the_head_and_reports_the_short_id(self, capsys):
        self.run(['create', 'v1.0', '-m', 'first', '--directory', self.alice])
        t = self.sync.tag_show(self.alice, 'v1.0')
        assert capsys.readouterr().out == f'Tagged {t["commit_id"][len("obj-cas-imm-"):]} as v1.0, signed by this clone.\n'
        assert t['message'] == 'first' and t['status'] == 'verified'

    def test_create_with_force_reports_where_the_tag_moved_from(self, capsys):
        old = self.sync.tag_create(self.alice, 'v1.0', message='m')['commit_id']
        _write(self.alice, 'a.txt', 'a v2'); self.sync.commit(self.alice, message='v2'); self.sync.push(self.alice)
        self.run(['create', 'v1.0', '--force', '-m', 'again', '--directory', self.alice])
        new = self.sync.tag_show(self.alice, 'v1.0')['commit_id']
        assert new != old
        assert capsys.readouterr().out == (f'Tagged {new[len("obj-cas-imm-"):]} as v1.0 '
                                           f'(moved from {old[len("obj-cas-imm-"):]}), signed by this clone.\n')

    def test_create_accepts_an_explicit_revision(self, capsys):
        head = self.sync.tag_create(self.alice, 'seed', message='m')['commit_id']
        self.run(['create', 'v1.0', 'HEAD', '-m', 'x', '--directory', self.alice])
        assert self.sync.tag_show(self.alice, 'v1.0')['commit_id'] == head
        assert 'as v1.0' in capsys.readouterr().out

    def test_create_errors_propagate_as_tag_errors(self):
        from sgit_ai.core.Vault__Errors import Vault__Tag_Error
        self.sync.tag_create(self.alice, 'v1.0', message='m')
        with pytest.raises(Vault__Tag_Error, match='tags do not move'):
            self.run(['create', 'v1.0', '-m', 'dup', '--directory', self.alice])

    # ── show ────────────────────────────────────────────────────────────
    def test_show_prints_the_tag_and_its_message_indented(self, capsys):
        r = self.sync.tag_create(self.alice, 'v1.0', message='line one\nline two')
        t = self.sync.tag_show(self.alice, 'v1.0')
        self.run(['show', 'v1.0', self.alice])
        lines = capsys.readouterr().out.splitlines()
        assert lines[0] == 'tag     v1.0'
        assert lines[1] == f'commit  {r["commit_id"]}'
        assert lines[2].startswith('date    ') and lines[2].endswith(' UTC')
        assert lines[3] == f'tagger  {t["tagger_key_id"]}'
        assert lines[4] == f'status  {STATUS_TEXT["verified"]}'
        assert lines[5:] == ['', '    line one', '    line two']

    def test_show_of_an_unverified_tag_exits_1_after_printing(self, capsys):
        """unsigned / no-key / bad / missing are not good tags: the details are printed, then exit 1."""
        r = self.sync.tag_create(self.alice, 'v1.0', message='')
        c = self.sync._init_components(self.alice)
        os.remove(os.path.join(self.alice, '.sg_vault', 'bare', 'data', r['tag_id']))
        self.snap.api._store.pop(f'{c.vault_id}/bare/data/{r["tag_id"]}')
        with pytest.raises(SystemExit) as exc:
            self.run(['show', 'v1.0', self.alice])
        assert exc.value.code == 1
        lines = capsys.readouterr().out.splitlines()
        assert lines[1] == 'commit  (unavailable)' and lines[3] == 'tagger  (unknown)'
        assert lines[2].startswith('date    20') and lines[2].endswith(' UTC')    # the index entry's own timestamp
        assert lines[4] == f'status  {STATUS_TEXT["missing"]}' and len(lines) == 5

    def test_show_unknown_tag_raises(self):
        from sgit_ai.core.Vault__Errors import Vault__Tag_Error
        with pytest.raises(Vault__Tag_Error, match="no tag named 'nope'"):
            self.run(['show', 'nope', self.alice])

    # ── delete ──────────────────────────────────────────────────────────
    def test_delete_removes_the_tag_and_reports_it(self, capsys):
        self.sync.tag_create(self.alice, 'v1.0', message='m')
        self.run(['delete', 'v1.0', self.alice])
        assert capsys.readouterr().out == 'Deleted tag v1.0.\n'
        assert self.sync.tag_list(self.alice) == []

    # ── through CLI__Main ───────────────────────────────────────────────
    def test_vault_tag_through_the_main_parser(self, capsys, monkeypatch):
        """`sgit vault tag create/list` wired by CLI__Main: the tag CLI shares CLI__Vault's
        token store and create_sync, and the global --token/--base-url parent parser."""
        with open(os.path.join(self.alice, '.sg_vault', 'local', 'base_url'), 'w') as f:
            f.write('http://127.0.0.1:9')
        monkeypatch.chdir(self.alice)                       # `vault` is an inside-only command
        cli = CLI__Main()
        _inject(cli.vault, self.snap)
        cli.run(['vault', 'tag', 'create', 'v1.0', '-m', 'via main'])
        cli.run(['vault', 'tag', 'list'])
        out = capsys.readouterr().out
        assert 'as v1.0, signed by this clone.' in out
        assert '  ✓ v1.0  ' in out and out.rstrip().endswith('via main')
        assert cli.tag.vault is cli.vault
