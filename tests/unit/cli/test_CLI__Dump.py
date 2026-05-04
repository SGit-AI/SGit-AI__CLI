import json
import os
import shutil
import sys
import tempfile
from io import StringIO
from types import SimpleNamespace

import pytest

from sgit_ai.cli.CLI__Dump             import CLI__Dump
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Sync          import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory


class Test_CLI__Dump:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli     = CLI__Dump(crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='cli-dump-test'):
        directory = os.path.join(self.tmp_dir, name)
        result    = self.sync.init(directory)
        return result, directory

    def _add_file(self, directory: str, filename: str, content: str) -> None:
        with open(os.path.join(directory, filename), 'w') as fh:
            fh.write(content)

    def _make_dump_args(self, directory='.', remote=False, structure_key=None, output=None):
        return SimpleNamespace(
            directory     = directory,
            remote        = remote,
            structure_key = structure_key,
            output        = output,
        )

    def _make_diff_args(self, dump_a=None, dump_b=None, local=False, remote=False, directory='.'):
        return SimpleNamespace(
            dump_a    = dump_a,
            dump_b    = dump_b,
            local     = local,
            remote    = remote,
            directory = directory,
        )

    # ------------------------------------------------------------------
    # cmd_dump tests
    # ------------------------------------------------------------------

    def test_cmd_dump_prints_json(self, capsys):
        _, directory = self._init_vault()
        self._add_file(directory, 'hello.txt', 'hello')
        self.sync.commit(directory, message='test commit')
        args = self._make_dump_args(directory=directory)
        self.cli.cmd_dump(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'source' in data
        assert data['source'] == 'local'

    def test_cmd_dump_output_to_file(self, capsys):
        _, directory = self._init_vault()
        self._add_file(directory, 'file.txt', 'content')
        self.sync.commit(directory, message='commit')
        output_file = os.path.join(self.tmp_dir, 'vault-state.json')
        args = self._make_dump_args(directory=directory, output=output_file)
        self.cli.cmd_dump(args)
        assert os.path.isfile(output_file)
        with open(output_file) as fh:
            data = json.load(fh)
        assert data['source'] == 'local'

    def test_cmd_dump_with_structure_key(self, capsys):
        init_result, directory = self._init_vault()
        self._add_file(directory, 'struct.txt', 'structure')
        self.sync.commit(directory, message='struct commit')
        vault_key     = init_result['vault_key']
        keys          = self.crypto.derive_keys_from_vault_key(vault_key)
        structure_key = self.crypto.derive_structure_key(keys['read_key_bytes'])
        args = self._make_dump_args(directory=directory,
                                    structure_key=structure_key.hex())
        self.cli.cmd_dump(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # Safe_Str normalises 'local_structure_key' — check for 'structure' substring
        assert 'structure' in data.get('source', '')

    def test_cmd_dump_invalid_structure_key_exits(self):
        _, directory = self._init_vault()
        args = self._make_dump_args(directory=directory, structure_key='not-valid-hex')
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump(args)
        assert exc_info.value.code == 1

    def test_cmd_dump_remote_produces_json(self, capsys):
        _, directory = self._init_vault()
        # Add a file and commit so the vault has content to push
        self._add_file(directory, 'hello.txt', 'hello')
        self.sync.commit(directory, message='test commit')
        # Push the vault so there is data on the in-memory server
        self.sync.push(directory)
        # Wire the CLI to use the in-memory API
        self.cli.api = self.api
        args = self._make_dump_args(directory=directory, remote=True)
        self.cli.cmd_dump(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['source'] == 'remote'
        assert data['total_refs'] > 0

    def test_cmd_dump_nonexistent_returns_empty(self, capsys):
        # A non-existent directory results in an empty dump (no vault structure)
        # rather than a crash — the dumper is resilient.
        args = self._make_dump_args(directory='/nonexistent/path/xyz')
        self.cli.cmd_dump(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['total_objects'] == 0
        assert data['total_refs']    == 0

    # ------------------------------------------------------------------
    # cmd_dump_diff tests
    # ------------------------------------------------------------------

    def test_cmd_dump_diff_two_identical_files(self, capsys):
        _, directory = self._init_vault()
        self._add_file(directory, 'diff.txt', 'diff data')
        self.sync.commit(directory, message='diff commit')

        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        dumper = Vault__Dump(crypto=self.crypto)
        dump   = dumper.dump_local(directory)

        file_a = os.path.join(self.tmp_dir, 'dump_a.json')
        file_b = os.path.join(self.tmp_dir, 'dump_b.json')
        with open(file_a, 'w') as fh:
            json.dump(dump.json(), fh)
        with open(file_b, 'w') as fh:
            json.dump(dump.json(), fh)

        args = self._make_diff_args(dump_a=file_a, dump_b=file_b)
        self.cli.cmd_dump_diff(args)
        captured = capsys.readouterr()
        assert 'identical' in captured.out.lower() or 'No differences' in captured.out

    def test_cmd_dump_diff_no_args_exits(self):
        args = self._make_diff_args()   # no files, no local/remote
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump_diff(args)
        assert exc_info.value.code == 1

    def test_cmd_dump_diff_remote_not_implemented_exits(self):
        _, directory = self._init_vault()
        args = self._make_diff_args(local=True, remote=True, directory=directory)
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump_diff(args)
        assert exc_info.value.code == 1

    def test_cmd_dump_diff_missing_file_exits(self):
        args = self._make_diff_args(dump_a='/nonexistent/a.json',
                                    dump_b='/nonexistent/b.json')
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump_diff(args)
        assert exc_info.value.code == 1

    # ------------------------------------------------------------------
    # Error handlers — cmd_dump lines 55-60
    # ------------------------------------------------------------------

    def test_cmd_dump_file_not_found_exits(self, monkeypatch, capsys):
        """FileNotFoundError from dump_local → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        monkeypatch.setattr(Vault__Dump, 'dump_local',
                            lambda self, d: (_ for _ in ()).throw(
                                FileNotFoundError('vault key missing')))
        _, directory = self._init_vault('fnf-test')
        args = self._make_dump_args(directory=directory)
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump(args)
        assert exc_info.value.code == 1
        assert 'vault key missing' in capsys.readouterr().err

    def test_cmd_dump_runtime_error_exits(self, monkeypatch, capsys):
        """RuntimeError from dump_local → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        monkeypatch.setattr(Vault__Dump, 'dump_local',
                            lambda self, d: (_ for _ in ()).throw(
                                RuntimeError('corrupt vault')))
        _, directory = self._init_vault('rte-test')
        args = self._make_dump_args(directory=directory)
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump(args)
        assert exc_info.value.code == 1
        assert 'corrupt vault' in capsys.readouterr().err

    # ------------------------------------------------------------------
    # Error handler — cmd_dump_diff lines 103-105
    # ------------------------------------------------------------------

    def test_cmd_dump_diff_runtime_error_exits(self, monkeypatch, capsys):
        """RuntimeError from diff_from_files → prints error, sys.exit(1)."""
        from sgit_ai.core.actions.diff.Vault__Dump_Diff import Vault__Dump_Diff
        monkeypatch.setattr(Vault__Dump_Diff, 'diff_from_files',
                            lambda self, a, b: (_ for _ in ()).throw(
                                RuntimeError('corrupt dump')))
        _, directory = self._init_vault('rte-diff-test')
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        dumper = Vault__Dump(crypto=self.crypto)
        dump   = dumper.dump_local(directory)
        file_a = os.path.join(self.tmp_dir, 'da.json')
        file_b = os.path.join(self.tmp_dir, 'db.json')
        for path in (file_a, file_b):
            with open(path, 'w') as fh:
                json.dump(dump.json(), fh)
        args = self._make_diff_args(dump_a=file_a, dump_b=file_b)
        with pytest.raises(SystemExit) as exc_info:
            self.cli.cmd_dump_diff(args)
        assert exc_info.value.code == 1
        assert 'corrupt dump' in capsys.readouterr().err

    # ------------------------------------------------------------------
    # _print_diff non-identical output — lines 123-160
    # ------------------------------------------------------------------

    def test_cmd_dump_diff_non_identical_shows_differences(self, capsys):
        """Two different vault states produce a non-identical diff with detail lines."""
        init_result, directory = self._init_vault('diff-non-identical')
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        dumper = Vault__Dump(crypto=self.crypto)

        # State A: initial vault (just init commit)
        dump_a_data = dumper.dump_local(directory).json()

        # State B: add a file and commit
        self._add_file(directory, 'extra.txt', 'extra content')
        self.sync.commit(directory, message='extra commit')
        dump_b_data = dumper.dump_local(directory).json()

        file_a = os.path.join(self.tmp_dir, 'snap_a.json')
        file_b = os.path.join(self.tmp_dir, 'snap_b.json')
        with open(file_a, 'w') as fh:
            json.dump(dump_a_data, fh)
        with open(file_b, 'w') as fh:
            json.dump(dump_b_data, fh)

        args = self._make_diff_args(dump_a=file_a, dump_b=file_b)
        self.cli.cmd_dump_diff(args)
        out = capsys.readouterr().out
        # Should show detailed difference output (not 'No differences')
        assert 'Total differences:' in out
        assert 'Comparing:' in out

    def test_cmd_dump_diff_non_identical_shows_object_lines(self, capsys):
        """Objects only in B are printed."""
        init_result, directory = self._init_vault('diff-obj-lines')
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        dumper = Vault__Dump(crypto=self.crypto)

        dump_a_data = dumper.dump_local(directory).json()

        self._add_file(directory, 'new.txt', 'new')
        self.sync.commit(directory, message='second')
        dump_b_data = dumper.dump_local(directory).json()

        file_a = os.path.join(self.tmp_dir, 'obj_a.json')
        file_b = os.path.join(self.tmp_dir, 'obj_b.json')
        with open(file_a, 'w') as fh:
            json.dump(dump_a_data, fh)
        with open(file_b, 'w') as fh:
            json.dump(dump_b_data, fh)

        args = self._make_diff_args(dump_a=file_a, dump_b=file_b)
        self.cli.cmd_dump_diff(args)
        out = capsys.readouterr().out
        # B has more objects than A
        assert 'object only in' in out

    def test_cmd_dump_diff_non_identical_shows_ref_or_commit_lines(self, capsys):
        """Refs or commits that differ are printed."""
        init_result, directory = self._init_vault('diff-ref-lines')
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        dumper = Vault__Dump(crypto=self.crypto)

        dump_a_data = dumper.dump_local(directory).json()

        self._add_file(directory, 'chg.txt', 'change')
        self.sync.commit(directory, message='change commit')
        dump_b_data = dumper.dump_local(directory).json()

        file_a = os.path.join(self.tmp_dir, 'ref_a.json')
        file_b = os.path.join(self.tmp_dir, 'ref_b.json')
        with open(file_a, 'w') as fh:
            json.dump(dump_a_data, fh)
        with open(file_b, 'w') as fh:
            json.dump(dump_b_data, fh)

        args = self._make_diff_args(dump_a=file_a, dump_b=file_b)
        self.cli.cmd_dump_diff(args)
        out = capsys.readouterr().out
        # Should mention diverged refs or commits only in B
        assert ('ref diverged' in out or 'commit only in' in out)

    # ------------------------------------------------------------------
    # Remote dump without self.api (lines 40-41) — creates Vault__API
    # ------------------------------------------------------------------

    def test_cmd_dump_remote_creates_vault_api_when_none(self, monkeypatch, capsys):
        """When self.api is None, a Vault__API is instantiated (lines 40-41)."""
        from sgit_ai.core.actions.dump.Vault__Dump import Vault__Dump
        from sgit_ai.api.Vault__API   import Vault__API

        init_result, directory = self._init_vault('remote-api-test')
        self._add_file(directory, 'r.txt', 'r')
        self.sync.commit(directory, message='r')
        self.sync.push(directory)

        # Use in-memory API but inject it via monkeypatching Vault__API construction
        in_mem_api = self.api
        monkeypatch.setattr(Vault__API, '__init__',
                            lambda self_api, base_url='', access_token='': None)
        monkeypatch.setattr(Vault__API, 'setup', lambda self_api: self_api)
        monkeypatch.setattr(Vault__Dump, 'dump_remote',
                            lambda self_d, api, vault_id, read_key:
                                in_mem_api.dump_remote(vault_id, read_key)
                                if hasattr(in_mem_api, 'dump_remote')
                                else self_d.dump_local(directory))

        # self.cli.api remains None (not set)
        assert self.cli.api is None
        args = self._make_dump_args(directory=directory, remote=True)
        self.cli.cmd_dump(args)
        captured = capsys.readouterr()
        # Just verify it ran without crashing — any JSON output is fine
        assert captured.out.strip() != ''


class Test_CLI__Dump__PrintDiff:
    """Direct unit tests for _print_diff — covers all list-iteration lines (127-155)."""

    def setup_method(self):
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        self.cli = CLI__Dump(crypto=Vault__Crypto())

    def _make_diff(self, **kwargs):
        from sgit_ai.schemas.Schema__Dump_Diff import Schema__Dump_Diff
        d = Schema__Dump_Diff()
        for k, v in kwargs.items():
            setattr(d, k, v)
        return d

    def test_print_diff_refs_only_in_a(self, capsys):
        """Line 127: ref only in A is printed."""
        d = self._make_diff(refs_only_in_a=['refaaa'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'ref only in' in out
        assert 'refaaa' in out

    def test_print_diff_refs_only_in_b(self, capsys):
        """Line 129: ref only in B is printed."""
        d = self._make_diff(refs_only_in_b=['refbbb'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'ref only in' in out
        assert 'refbbb' in out

    def test_print_diff_objects_only_in_a(self, capsys):
        """Line 135: object only in A is printed."""
        d = self._make_diff(objects_only_in_a=['objaaa'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'object only in' in out
        assert 'objaaa' in out

    def test_print_diff_branches_only_in_a(self, capsys):
        """Line 141: branch only in A is printed."""
        d = self._make_diff(branches_only_in_a=['branchaaa'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'branch only in' in out
        assert 'branchaaa' in out

    def test_print_diff_branches_only_in_b(self, capsys):
        """Line 143: branch only in B is printed."""
        d = self._make_diff(branches_only_in_b=['branchbbb'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'branch only in' in out
        assert 'branchbbb' in out

    def test_print_diff_dangling_in_a(self, capsys):
        """Line 149: dangling in A is printed."""
        d = self._make_diff(dangling_in_a=['dangleaaa'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'dangling in' in out
        assert 'dangleaaa' in out

    def test_print_diff_dangling_in_b(self, capsys):
        """Line 151: dangling in B is printed."""
        d = self._make_diff(dangling_in_b=['danglebbb'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'dangling in' in out
        assert 'danglebbb' in out

    def test_print_diff_commits_only_in_a(self, capsys):
        """Line 155: commit only in A is printed."""
        d = self._make_diff(commits_only_in_a=['commitaaa'])
        self.cli._print_diff(d)
        out = capsys.readouterr().out
        assert 'commit only in' in out
        assert 'commitaaa' in out
