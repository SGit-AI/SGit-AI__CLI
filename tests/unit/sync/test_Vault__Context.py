"""Tests for Vault__Context — B04 context detection."""
import json
import os
import sys
import tempfile
import shutil

import pytest

from sgit_ai.core.Vault__Context import Vault__Context, Enum__Vault_Context


def _make_vault_dir(parent, name='myvault', bare=False):
    """Create a minimal vault directory structure."""
    vault_dir = os.path.join(parent, name)
    sg_vault  = os.path.join(vault_dir, '.sg_vault')
    os.makedirs(sg_vault, exist_ok=True)

    if bare:
        # bare vault: refs but no vault_key
        refs_dir = os.path.join(sg_vault, 'bare', 'refs')
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, 'ref-pid-abc123'), 'w') as f:
            f.write('{}')
        # no local/vault_key
        local_dir = os.path.join(sg_vault, 'local')
        os.makedirs(local_dir, exist_ok=True)
        # write config.json with vault_id
        with open(os.path.join(local_dir, 'config.json'), 'w') as f:
            json.dump({'vault_id': 'barevlt1'}, f)
    else:
        # working vault: has vault_key in local/
        local_dir = os.path.join(sg_vault, 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'vault_key'), 'w') as f:
            f.write('passphrase:vault01')
        with open(os.path.join(local_dir, 'config.json'), 'w') as f:
            json.dump({'vault_id': 'workingvl'}, f)
        # Add refs too
        refs_dir = os.path.join(sg_vault, 'bare', 'refs')
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, 'ref-pid-xyz789'), 'w') as f:
            f.write('{}')

    return vault_dir


# ---------------------------------------------------------------------------
# Context detector tests
# ---------------------------------------------------------------------------

class Test_Vault__Context__Detect_Outside:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_directory_is_outside(self):
        ctx = Vault__Context.detect(self.tmp)
        assert ctx.state == Enum__Vault_Context.OUTSIDE

    def test_outside_has_no_vault_path(self):
        ctx = Vault__Context.detect(self.tmp)
        assert ctx.vault_path is None

    def test_outside_has_no_vault_id(self):
        ctx = Vault__Context.detect(self.tmp)
        assert ctx.vault_id is None

    def test_outside_has_no_working_copy(self):
        ctx = Vault__Context.detect(self.tmp)
        assert ctx.has_working_copy is False

    def test_is_outside_helper(self):
        ctx = Vault__Context.detect(self.tmp)
        assert ctx.is_outside() is True
        assert ctx.is_inside() is False


class Test_Vault__Context__Detect_Inside_Working:

    def setup_method(self):
        self.tmp   = tempfile.mkdtemp()
        self.vault = _make_vault_dir(self.tmp, 'working-vault', bare=False)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inside_working_vault_detected(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.state == Enum__Vault_Context.INSIDE_WORKING

    def test_vault_path_populated(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.vault_path is not None
        assert str(ctx.vault_path) == self.vault

    def test_vault_id_populated(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.vault_id is not None
        assert str(ctx.vault_id) == 'workingvl'

    def test_has_working_copy_true(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.has_working_copy is True

    def test_is_inside_working_helper(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.is_inside_working() is True
        assert ctx.is_inside_bare() is False
        assert ctx.is_inside() is True
        assert ctx.is_outside() is False

    def test_subdirectory_walks_up(self):
        subdir = os.path.join(self.vault, 'src', 'components')
        os.makedirs(subdir, exist_ok=True)
        ctx = Vault__Context.detect(subdir)
        assert ctx.state == Enum__Vault_Context.INSIDE_WORKING
        assert str(ctx.vault_path) == self.vault


class Test_Vault__Context__Detect_Inside_Bare:

    def setup_method(self):
        self.tmp   = tempfile.mkdtemp()
        self.vault = _make_vault_dir(self.tmp, 'bare-vault', bare=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bare_vault_detected(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.state == Enum__Vault_Context.INSIDE_BARE

    def test_bare_has_no_working_copy(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.has_working_copy is False

    def test_is_inside_bare_helper(self):
        ctx = Vault__Context.detect(self.vault)
        assert ctx.is_inside_bare() is True
        assert ctx.is_inside_working() is False
        assert ctx.is_inside() is True


class Test_Vault__Context__Override:

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.vault  = _make_vault_dir(self.tmp, 'my-vault')
        self.outside = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_detect_with_override_uses_supplied_path(self):
        ctx = Vault__Context.detect_with_override(cwd=self.outside, vault_path_arg=self.vault)
        assert ctx.state == Enum__Vault_Context.INSIDE_WORKING

    def test_detect_with_override_none_falls_back_to_cwd(self):
        ctx = Vault__Context.detect_with_override(cwd=self.outside, vault_path_arg=None)
        assert ctx.state == Enum__Vault_Context.OUTSIDE


# ---------------------------------------------------------------------------
# Visibility map + wrong-context error tests  (via CLI__Main helpers)
# ---------------------------------------------------------------------------

class Test_CLI__Main__Context_Visibility:

    def setup_method(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        self.cli = CLI__Main()
        self.cli.build_parser()

    def test_outside_only_commands_defined(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        assert 'clone' in CLI__Main._OUTSIDE_ONLY
        assert 'create' in CLI__Main._OUTSIDE_ONLY
        assert 'init' in CLI__Main._OUTSIDE_ONLY

    def test_inside_only_commands_defined(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        assert 'commit' in CLI__Main._INSIDE_ONLY
        assert 'push' in CLI__Main._INSIDE_ONLY
        assert 'status' in CLI__Main._INSIDE_ONLY

    def test_universal_commands_defined(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        assert 'version' in CLI__Main._UNIVERSAL
        assert 'pki' in CLI__Main._UNIVERSAL
        assert 'dev' in CLI__Main._UNIVERSAL


class Test_CLI__Main__Wrong_Context_Errors:

    def setup_method(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        self.cli = CLI__Main()
        self.cli.build_parser()

    def _make_outside_ctx(self):
        return Vault__Context(state=Enum__Vault_Context.OUTSIDE)

    def _make_inside_ctx(self, vault_id='testvlt1'):
        from sgit_ai.safe_types.Safe_Str__Vault_Id  import Safe_Str__Vault_Id
        from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path
        return Vault__Context(state=Enum__Vault_Context.INSIDE_WORKING,
                              vault_path=Safe_Str__File_Path('/tmp/testvault'),
                              vault_id=Safe_Str__Vault_Id(vault_id),
                              has_working_copy=True)

    def test_inside_only_from_outside_exits_1(self, capsys):
        ctx = self._make_outside_ctx()
        with pytest.raises(SystemExit) as exc:
            self.cli._cmd_wrong_context('commit', ctx)
        assert exc.value.code == 1

    def test_inside_only_from_outside_mentions_command(self, capsys):
        ctx = self._make_outside_ctx()
        with pytest.raises(SystemExit):
            self.cli._cmd_wrong_context('commit', ctx)
        err = capsys.readouterr().err
        assert 'commit' in err
        assert 'inside a vault' in err

    def test_outside_only_from_inside_exits_1(self, capsys):
        ctx = self._make_inside_ctx()
        with pytest.raises(SystemExit) as exc:
            self.cli._cmd_wrong_context('clone', ctx)
        assert exc.value.code == 1

    def test_outside_only_from_inside_mentions_vault(self, capsys):
        ctx = self._make_inside_ctx('testvlt1')
        with pytest.raises(SystemExit):
            self.cli._cmd_wrong_context('clone', ctx)
        err = capsys.readouterr().err
        assert 'clone' in err
        assert 'outside a vault' in err

    def test_friendly_error_suggests_alternative(self, capsys):
        ctx = self._make_outside_ctx()
        with pytest.raises(SystemExit):
            self.cli._cmd_wrong_context('push', ctx)
        err = capsys.readouterr().err
        assert 'sgit init' in err or 'sgit clone' in err

    def test_vault_override_flag_exists_in_parser(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli    = CLI__Main()
        parser = cli.build_parser()
        # --vault is a global flag so it must appear before the subcommand
        args   = parser.parse_args(['--vault', '/tmp/myvault', 'version'])
        assert args.vault == '/tmp/myvault'


class Test_CLI__Main__Run_Context_Gate:
    """B04-1: Prove _detect_context() is now wired into run()."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _vault_dir(self):
        """Return a minimal working-vault directory."""
        return _make_vault_dir(self.tmp, name='v1')

    def test_inside_only_command_outside_vault_exits_via_run(self, capsys):
        """run('commit') outside a vault triggers friendly error, not raw commit logic."""
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(['--vault', self.tmp, 'commit'])
        assert exc.value.code == 1
        assert 'inside a vault' in capsys.readouterr().err

    def test_outside_only_command_inside_vault_exits_via_run(self, capsys):
        """run('clone <key>') inside a vault triggers friendly error, not clone logic."""
        from sgit_ai.cli.CLI__Main import CLI__Main
        vault_path = self._vault_dir()
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(['--vault', vault_path, 'clone', 'pass:somekey', vault_path])
        assert exc.value.code == 1
        assert 'outside a vault' in capsys.readouterr().err


class Test_CLI__Main__Help_All:

    def test_help_all_prints_full_surface(self, capsys):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['help', 'all'])
        args.func(args)
        out = capsys.readouterr().out
        assert 'outside' in out.lower()
        assert 'inside' in out.lower()

    def test_help_parser_exists(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['help'])
        assert args.command == 'help'

    def test_help_topic_all_parsed(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['help', 'all'])
        assert args.topic == 'all'
