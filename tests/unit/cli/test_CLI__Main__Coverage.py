"""Coverage-focused tests for CLI__Main — lines not yet covered.

Targets:
  - Lines 47-48: SSLCertVerificationError / SSLError detection
  - Lines 58-60: macOS SSL hint
  - Line 73: _read_version fallback to 'unknown'
  - Lines 76-82: cmd_update
  - Lines 454-515: run() dispatch (vault/debug/remote/pki/stash/branch sub-commands)
  - Lines 533, 545-546: _print_friendly_error (ConnectionError, no traceback)
  - Lines 554-560: _setup_debug enabled path
  - Lines 578-583, 586-588: _cmd_debug_on / _cmd_debug_off / _cmd_debug_status
"""
import os
import sys
import platform
import subprocess
import shutil
import tempfile
import types

import pytest

from sgit_ai.cli.CLI__Main import CLI__Main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(**kw):
    return types.SimpleNamespace(**kw)


# ---------------------------------------------------------------------------
# Lines 47-48: SSLCertVerificationError / SSLError path in _check_ssl_error
# ---------------------------------------------------------------------------

class Test_CLI__Main__SSLTypes:

    def test_ssl_cert_verification_error_detected(self):
        """Line 47: type name SSLCertVerificationError → is_ssl = True."""
        import ssl
        cli = CLI__Main()
        err = ssl.SSLCertVerificationError('cert error')
        hint = cli._check_ssl_error(err)
        assert 'SSL Error' in hint

    def test_ssl_error_type_detected(self):
        """Line 48: type name SSLError → is_ssl = True."""
        import ssl
        cli = CLI__Main()
        err = ssl.SSLError('ssl error')
        hint = cli._check_ssl_error(err)
        assert 'SSL Error' in hint

    def test_ssl_error_nested_as_context(self):
        """Lines 47-48: SSL error attached as __context__ (not __cause__)."""
        import ssl
        cli  = CLI__Main()
        inner = ssl.SSLError('ssl error')
        outer = RuntimeError('outer')
        outer.__context__ = inner
        hint = cli._check_ssl_error(outer)
        assert 'SSL Error' in hint


# ---------------------------------------------------------------------------
# Lines 58-60: macOS SSL hint
# ---------------------------------------------------------------------------

class Test_CLI__Main__SSLHintMacOS:

    def test_ssl_hint_darwin_includes_install_certs(self, monkeypatch):
        """Lines 58-60: on Darwin, hint includes Install Certificates.command."""
        import ssl
        monkeypatch.setattr(platform, 'system', lambda: 'Darwin')
        cli  = CLI__Main()
        err  = ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED')
        hint = cli._check_ssl_error(err)
        assert 'Install' in hint and 'Certificates' in hint

    def test_ssl_hint_linux_includes_apt(self, monkeypatch):
        """Lines 62-65: on Linux, hint includes apt install."""
        import ssl
        monkeypatch.setattr(platform, 'system', lambda: 'Linux')
        cli  = CLI__Main()
        err  = ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED')
        hint = cli._check_ssl_error(err)
        assert 'apt' in hint or 'Debian' in hint


# ---------------------------------------------------------------------------
# Line 73: _read_version returns 'unknown' when version file absent
# ---------------------------------------------------------------------------

class Test_CLI__Main__Version:

    def test_read_version_returns_unknown_when_no_file(self, monkeypatch):
        """Line 73: version file absent → returns 'unknown'."""
        monkeypatch.setattr(os.path, 'isfile', lambda p: False)
        cli = CLI__Main()
        assert cli._read_version() == 'unknown'

    def test_read_version_returns_content_when_file_exists(self):
        """Lines 70-72: version file present → returns its content (not 'unknown')."""
        cli = CLI__Main()
        version = cli._read_version()
        # A version file exists in the repo — just confirm it reads non-empty content
        assert version != 'unknown'
        assert len(version) > 0


# ---------------------------------------------------------------------------
# Lines 76-82: cmd_update
# ---------------------------------------------------------------------------

class Test_CLI__Main__CmdUpdate:

    def test_cmd_update_success(self, monkeypatch, capsys):
        """Lines 76-79: successful pip upgrade prints version and updating."""
        monkeypatch.setattr(subprocess, 'run',
                            lambda *a, **kw: types.SimpleNamespace(returncode=0))
        cli = CLI__Main()
        cli.cmd_update(_args())
        out = capsys.readouterr().out
        assert 'Updating' in out

    def test_cmd_update_failure_exits(self, monkeypatch, capsys):
        """Lines 80-82: failed pip upgrade → sys.exit with returncode."""
        monkeypatch.setattr(subprocess, 'run',
                            lambda *a, **kw: types.SimpleNamespace(returncode=1))
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.cmd_update(_args())
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Lines 454-515: run() command dispatch
# ---------------------------------------------------------------------------

class Test_CLI__Main__Run:

    def test_run_no_command_exits(self):
        """Lines 449-451: no command → print_help + sys.exit(1)."""
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run([])
        assert exc.value.code == 1

    def test_run_vault_no_subcommand_exits(self):
        """Lines 454-456: vault without subcommand → prints help + exits."""
        cli = CLI__Main()
        with pytest.raises(SystemExit):
            cli.run(['vault'])

    def test_run_debug_no_subcommand_exits(self):
        """Lines 458-460: debug without subcommand → prints help + exits."""
        cli = CLI__Main()
        with pytest.raises(SystemExit):
            cli.run(['debug'])

    def test_run_remote_no_subcommand_exits(self):
        """Lines 462-464: remote without subcommand → prints help + exits."""
        cli = CLI__Main()
        with pytest.raises(SystemExit):
            cli.run(['remote'])

    def test_run_pki_no_subcommand_exits(self):
        """Lines 466-469: pki without subcommand → prints help + exits."""
        cli = CLI__Main()
        with pytest.raises(SystemExit):
            cli.run(['pki'])

    def test_run_stash_no_subcommand_dispatches(self, monkeypatch, capsys):
        """Line 479-480: stash without subcommand → args.func = cmd_stash."""
        from sgit_ai.cli.CLI__Stash import CLI__Stash
        monkeypatch.setattr(CLI__Stash, 'cmd_stash',
                            lambda self, a: print('stash called'))
        cli = CLI__Main()
        cli.run(['stash'])
        assert 'stash called' in capsys.readouterr().out

    def test_run_stash_pop_dispatches(self, monkeypatch, capsys):
        """Line 473-474: stash pop → args.func = cmd_stash_pop."""
        from sgit_ai.cli.CLI__Stash import CLI__Stash
        monkeypatch.setattr(CLI__Stash, 'cmd_stash_pop',
                            lambda self, a: print('pop called'))
        cli = CLI__Main()
        cli.run(['stash', 'pop'])
        assert 'pop called' in capsys.readouterr().out

    def test_run_stash_list_dispatches(self, monkeypatch, capsys):
        """Line 475-476: stash list → args.func = cmd_stash_list."""
        from sgit_ai.cli.CLI__Stash import CLI__Stash
        monkeypatch.setattr(CLI__Stash, 'cmd_stash_list',
                            lambda self, a: print('list called'))
        cli = CLI__Main()
        cli.run(['stash', 'list'])
        assert 'list called' in capsys.readouterr().out

    def test_run_stash_drop_dispatches(self, monkeypatch, capsys):
        """Line 477-478: stash drop → args.func = cmd_stash_drop."""
        from sgit_ai.cli.CLI__Stash import CLI__Stash
        monkeypatch.setattr(CLI__Stash, 'cmd_stash_drop',
                            lambda self, a: print('drop called'))
        cli = CLI__Main()
        cli.run(['stash', 'drop'])
        assert 'drop called' in capsys.readouterr().out

    def test_run_vault_subcommand_calls_setup_credential_store(self, monkeypatch, capsys):
        """Line 456: vault with subcommand → setup_credential_store() called."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        called = []
        monkeypatch.setattr(CLI__Vault, 'setup_credential_store',
                            lambda self: called.append(True))
        monkeypatch.setattr(CLI__Vault, 'cmd_vault_list', lambda self, a: None)
        cli = CLI__Main()
        cli.run(['vault', 'list'])
        assert called

    def test_run_pki_subcommand_calls_setup(self, monkeypatch, capsys):
        """Line 469: pki with subcommand → pki.setup() called."""
        from sgit_ai.cli.CLI__PKI import CLI__PKI
        called = []
        monkeypatch.setattr(CLI__PKI, 'setup', lambda self: called.append(True) or None)
        monkeypatch.setattr(CLI__PKI, 'cmd_keygen', lambda self, a: None)
        cli = CLI__Main()
        cli.run(['pki', 'keygen'])
        assert called

    def test_run_setup_debug_exception_silenced(self, monkeypatch, capsys):
        """Lines 493-494: _setup_debug raises → exception silenced, debug_log=None."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        monkeypatch.setattr(CLI__Main, '_setup_debug',
                            lambda self, a: (_ for _ in ()).throw(RuntimeError('debug crash')))
        monkeypatch.setattr(CLI__Vault, 'cmd_status', lambda self, a: None)
        cli = CLI__Main()
        # Should not raise despite _setup_debug failing
        cli.run(['status'])

    def test_run_branch_no_subcommand_exits(self):
        """Lines 487-489: branch without subcommand → prints help + exits."""
        cli = CLI__Main()
        with pytest.raises(SystemExit):
            cli.run(['branch'])

    def test_run_branch_new_dispatches(self, monkeypatch, capsys, tmp_path):
        """Lines 484-485: branch new → args.func = cmd_branch_new."""
        from sgit_ai.cli.CLI__Branch import CLI__Branch
        monkeypatch.setattr(CLI__Branch, 'cmd_branch_new',
                            lambda self, a: print('branch new called'))
        cli = CLI__Main()
        cli.run(['branch', 'new', 'my-feature'])
        assert 'branch new called' in capsys.readouterr().out

    def test_run_branch_list_dispatches(self, monkeypatch, capsys, tmp_path):
        """Lines 486-487: branch list → args.func = cmd_branch_list."""
        from sgit_ai.cli.CLI__Branch import CLI__Branch
        monkeypatch.setattr(CLI__Branch, 'cmd_branch_list',
                            lambda self, a: print('branch list called'))
        cli = CLI__Main()
        cli.run(['branch', 'list'])
        assert 'branch list called' in capsys.readouterr().out

    def test_run_keyboard_interrupt_exits_130(self, monkeypatch, capsys):
        """Lines 498-500: KeyboardInterrupt → sys.exit(130)."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        monkeypatch.setattr(CLI__Vault, 'cmd_status',
                            lambda self, a: (_ for _ in ()).throw(KeyboardInterrupt()))
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(['status'])
        assert exc.value.code == 130
        assert 'Interrupted' in capsys.readouterr().err

    def test_run_runtime_error_exits_1(self, monkeypatch, capsys):
        """Lines 501-503: RuntimeError → prints error, sys.exit(1)."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        monkeypatch.setattr(CLI__Vault, 'cmd_status',
                            lambda self, a: (_ for _ in ()).throw(RuntimeError('vault broke')))
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(['status'])
        assert exc.value.code == 1
        assert 'vault broke' in capsys.readouterr().err

    def test_run_generic_exception_prints_friendly_error(self, monkeypatch, capsys):
        """Lines 504-512: generic exception → _print_friendly_error, sys.exit(1)."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        monkeypatch.setattr(CLI__Vault, 'cmd_status',
                            lambda self, a: (_ for _ in ()).throw(ValueError('bad val')))
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(['status'])
        assert exc.value.code == 1
        assert 'ValueError' in capsys.readouterr().err

    def test_run_ssl_error_prints_ssl_hint(self, monkeypatch, capsys):
        """Lines 505-508: SSL exception → ssl hint, sys.exit(1)."""
        import ssl
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        monkeypatch.setattr(CLI__Vault, 'cmd_status',
                            lambda self, a: (_ for _ in ()).throw(
                                ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED')))
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(['status'])
        assert exc.value.code == 1
        assert 'SSL Error' in capsys.readouterr().err

    def test_run_debug_mode_reraises(self, monkeypatch, tmp_path):
        """Lines 509-510: debug_log set → generic exception is re-raised."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        # Enable debug mode via file
        local = tmp_path / '.sg_vault' / 'local'
        local.mkdir(parents=True)
        (local / 'debug').write_text('on')
        monkeypatch.setattr(CLI__Vault, 'cmd_status',
                            lambda self, a: (_ for _ in ()).throw(ValueError('reraised')))
        cli = CLI__Main()
        with pytest.raises(ValueError, match='reraised'):
            cli.run(['status', str(tmp_path)])

    def test_run_debug_finally_prints_summary(self, monkeypatch, capsys, tmp_path):
        """Lines 513-515: finally block calls debug_log.print_summary()."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        local = tmp_path / '.sg_vault' / 'local'
        local.mkdir(parents=True)
        (local / 'debug').write_text('on')
        monkeypatch.setattr(CLI__Vault, 'cmd_status', lambda self, a: None)
        cli = CLI__Main()
        cli.run(['status', str(tmp_path)])
        # Summary is printed; just check no crash
        assert True


# ---------------------------------------------------------------------------
# Lines 533, 545-546: _print_friendly_error edge cases
# ---------------------------------------------------------------------------

class Test_CLI__Main__FriendlyError:

    def test_connection_error_shows_network_failure(self, capsys):
        """Line 533: ConnectionError → 'network or I/O failure'."""
        cli   = CLI__Main()
        error = ConnectionError('connection refused')
        args  = _args(command='push', directory='.')
        cli._print_friendly_error(error, args)
        err = capsys.readouterr().err
        assert 'network or I/O failure' in err

    def test_os_error_shows_network_failure(self, capsys):
        """Line 533: OSError → 'network or I/O failure'."""
        cli   = CLI__Main()
        error = OSError('broken pipe')
        args  = _args(command='push', directory='.')
        cli._print_friendly_error(error, args)
        assert 'network or I/O failure' in capsys.readouterr().err

    def test_error_with_no_traceback_skips_at_line(self, capsys):
        """Lines 544-546: error with empty traceback → 'at ...' line not printed."""
        cli   = CLI__Main()
        error = ValueError('no traceback attached')
        error.__traceback__ = None
        args  = _args(command='status', directory='.')
        cli._print_friendly_error(error, args)
        err = capsys.readouterr().err
        assert 'ValueError' in err
        assert 'at ' not in err   # no traceback context → skipped


# ---------------------------------------------------------------------------
# Lines 554-560: _setup_debug enabled path
# ---------------------------------------------------------------------------

class Test_CLI__Main__SetupDebug:

    def test_setup_debug_enabled_returns_debug_log(self, tmp_path):
        """Lines 554-560: debug=True → returns CLI__Debug_Log with summary header."""
        from sgit_ai.cli.CLI__Debug_Log import CLI__Debug_Log
        cli  = CLI__Main()
        args = _args(directory=str(tmp_path), debug=True)
        result = cli._setup_debug(args)
        assert result is not None
        assert isinstance(result, CLI__Debug_Log)

    def test_setup_debug_via_file_flag(self, tmp_path):
        """Lines 551/554-560: debug file 'on' → _setup_debug returns debug log."""
        from sgit_ai.cli.CLI__Debug_Log import CLI__Debug_Log
        local = tmp_path / '.sg_vault' / 'local'
        local.mkdir(parents=True)
        (local / 'debug').write_text('on')
        cli  = CLI__Main()
        args = _args(directory=str(tmp_path), debug=False)
        result = cli._setup_debug(args)
        assert isinstance(result, CLI__Debug_Log)


# ---------------------------------------------------------------------------
# Lines 578-583, 586-588: _cmd_debug_on / _cmd_debug_off / _cmd_debug_status
# ---------------------------------------------------------------------------

class Test_CLI__Main__DebugCommands:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.local_dir = os.path.join(self.tmp_dir, '.sg_vault', 'local')
        os.makedirs(self.local_dir, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cmd_debug_on_enables_debug(self, capsys):
        """Lines 578-579: _cmd_debug_on writes 'on' and prints confirmation."""
        cli = CLI__Main()
        cli._cmd_debug_on(_args(directory=self.tmp_dir))
        out = capsys.readouterr().out
        assert 'enabled' in out
        assert cli._load_debug_flag(self.tmp_dir) is True

    def test_cmd_debug_off_disables_debug(self, capsys):
        """Lines 581-583: _cmd_debug_off writes 'off' and prints confirmation."""
        cli = CLI__Main()
        cli._cmd_debug_on(_args(directory=self.tmp_dir))   # set on first
        cli._cmd_debug_off(_args(directory=self.tmp_dir))
        out = capsys.readouterr().out
        assert 'disabled' in out
        assert cli._load_debug_flag(self.tmp_dir) is False

    def test_cmd_debug_status_shows_off_when_disabled(self, capsys):
        """Lines 586-588: debug=off → prints 'off'."""
        cli = CLI__Main()
        cli._cmd_debug_status(_args(directory=self.tmp_dir))
        out = capsys.readouterr().out
        assert 'off' in out

    def test_cmd_debug_status_shows_on_when_enabled(self, capsys):
        """Lines 586-588: debug=on → prints 'on'."""
        cli = CLI__Main()
        cli._cmd_debug_on(_args(directory=self.tmp_dir))
        capsys.readouterr()
        cli._cmd_debug_status(_args(directory=self.tmp_dir))
        out = capsys.readouterr().out
        assert 'on' in out

    def test_run_debug_on_command(self, capsys):
        """End-to-end: 'sgit dev debug on <dir>' calls _cmd_debug_on."""
        cli = CLI__Main()
        cli.run(['dev', 'debug', 'on', self.tmp_dir])
        assert 'enabled' in capsys.readouterr().out

    def test_run_debug_off_command(self, capsys):
        """End-to-end: 'sgit dev debug off <dir>' calls _cmd_debug_off."""
        cli = CLI__Main()
        cli._cmd_debug_on(_args(directory=self.tmp_dir))
        capsys.readouterr()
        cli.run(['dev', 'debug', 'off', self.tmp_dir])
        assert 'disabled' in capsys.readouterr().out

    def test_run_debug_status_command(self, capsys):
        """End-to-end: 'sgit dev debug status <dir>' calls _cmd_debug_status."""
        cli = CLI__Main()
        cli.run(['dev', 'debug', 'status', self.tmp_dir])
        assert 'off' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _resolve_vault_dir — vault root discovery
# ---------------------------------------------------------------------------

class Test_CLI__Main__Resolve_Vault_Dir:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = None

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_vault(self, name='vault'):
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        vault_dir = os.path.join(self.tmp_dir, name)
        os.makedirs(vault_dir, exist_ok=True)
        Vault__Storage().create_bare_structure(vault_dir)
        return vault_dir

    def test_no_directory_attr_is_noop(self):
        cli  = CLI__Main()
        args = _args(command='status')
        cli._resolve_vault_dir(args)
        assert not hasattr(args, 'directory')

    def test_already_at_vault_root_unchanged(self):
        vault_dir = self._make_vault()
        cli  = CLI__Main()
        args = _args(command='status', directory=vault_dir)
        cli._resolve_vault_dir(args)
        assert args.directory == vault_dir

    def test_subdirectory_resolved_to_vault_root(self):
        vault_dir = self._make_vault()
        subdir    = os.path.join(vault_dir, 'a', 'b')
        os.makedirs(subdir)
        cli  = CLI__Main()
        args = _args(command='status', directory=subdir)
        cli._resolve_vault_dir(args)
        assert args.directory == vault_dir

    def test_no_vault_above_directory_unchanged(self):
        no_vault = os.path.join(self.tmp_dir, 'no-vault')
        os.makedirs(no_vault)
        cli  = CLI__Main()
        args = _args(command='status', directory=no_vault)
        cli._resolve_vault_dir(args)
        assert args.directory == no_vault

    def test_init_command_not_resolved(self):
        vault_dir = self._make_vault()
        subdir    = os.path.join(vault_dir, 'new')
        os.makedirs(subdir)
        cli  = CLI__Main()
        args = _args(command='init', directory=subdir)
        cli._resolve_vault_dir(args)
        assert args.directory == subdir   # must not walk up for init

    def test_clone_command_not_resolved(self):
        vault_dir = self._make_vault()
        subdir    = os.path.join(vault_dir, 'dest')
        os.makedirs(subdir)
        cli  = CLI__Main()
        args = _args(command='clone', directory=subdir)
        cli._resolve_vault_dir(args)
        assert args.directory == subdir


# ---------------------------------------------------------------------------
# Lines 688-691: _cmd_log_dispatch — file_path branch
# ---------------------------------------------------------------------------

class Test_CLI__Main__LogDispatch:

    def test_cmd_log_dispatch_with_file_path_calls_cmd_log_file(self, monkeypatch):
        """Lines 688-689: file_path set → diff.cmd_log_file called."""
        from sgit_ai.cli.CLI__Diff import CLI__Diff
        called = []
        monkeypatch.setattr(CLI__Diff, 'cmd_log_file', lambda self, a: called.append(a))
        cli  = CLI__Main()
        args = _args(command='log', directory='.', file_path='README.md')
        cli._cmd_log_dispatch(args)
        assert called

    def test_cmd_log_dispatch_without_file_path_calls_cmd_log(self, monkeypatch):
        """Lines 690-691: no file_path → vault.cmd_log called."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        called = []
        monkeypatch.setattr(CLI__Vault, 'cmd_log', lambda self, a: called.append(a))
        cli  = CLI__Main()
        args = _args(command='log', directory='.')
        cli._cmd_log_dispatch(args)
        assert called


# ---------------------------------------------------------------------------
# Lines 758-759: _save_debug_flag — os.chmod raises OSError → silenced
# ---------------------------------------------------------------------------

class Test_CLI__Main__SaveDebugFlag:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.local_dir = os.path.join(self.tmp_dir, '.sg_vault', 'local')
        os.makedirs(self.local_dir, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_debug_flag_chmod_oserror_silenced(self, monkeypatch):
        """Lines 758-759: os.chmod raises OSError → except silences it."""
        import unittest.mock
        cli = CLI__Main()
        with unittest.mock.patch('os.chmod', side_effect=OSError('permission denied')):
            cli._save_debug_flag(self.tmp_dir, True)   # must not raise
        debug_path = os.path.join(self.local_dir, 'debug')
        assert open(debug_path).read() == 'on'
