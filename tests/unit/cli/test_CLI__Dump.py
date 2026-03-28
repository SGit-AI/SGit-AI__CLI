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

        from sgit_ai.sync.Vault__Dump import Vault__Dump
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
