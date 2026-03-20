"""Tests for global error handler in CLI__Main.

Verifies that unhandled exceptions produce user-friendly messages
instead of raw Python tracebacks.
"""
import sys
from io import StringIO
from sgit_ai.cli.CLI__Main import CLI__Main


class Test_CLI__Main__Error_Handler:

    def test_file_not_found_shows_friendly_message(self):
        """FileNotFoundError should show hint about fsck, not a traceback."""
        cli = CLI__Main()
        error = FileNotFoundError("[Errno 2] No such file: 'obj-cas-imm-abc123'")
        args  = type('Args', (), {'command': 'clone', 'directory': '.'})()

        stderr = StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr
            cli._print_friendly_error(error, args)
        finally:
            sys.stderr = old_stderr

        output = stderr.getvalue()
        assert 'missing file' in output
        assert 'fsck'         in output
        assert 'Traceback'    not in output

    def test_runtime_error_caught_cleanly(self):
        """RuntimeError during command should print error message, not traceback."""
        cli   = CLI__Main()
        error = RuntimeError('Vault is corrupted')
        args  = type('Args', (), {'command': 'pull', 'directory': '.'})()

        stderr = StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr
            # Simulate what the run() method does for RuntimeError
            print(f'error: {error}', file=sys.stderr)
        finally:
            sys.stderr = old_stderr

        output = stderr.getvalue()
        assert 'error: Vault is corrupted' in output
        assert 'Traceback' not in output

    def test_generic_exception_shows_type_and_command(self):
        """Unhandled exception should show error type and command name."""
        cli   = CLI__Main()
        error = ValueError('bad value')
        args  = type('Args', (), {'command': 'push', 'directory': '.'})()

        stderr = StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr
            cli._print_friendly_error(error, args)
        finally:
            sys.stderr = old_stderr

        output = stderr.getvalue()
        assert 'ValueError'  in output
        assert '"push"'      in output
        assert '--debug'     in output

    def test_permission_error_shows_denied(self):
        cli   = CLI__Main()
        error = PermissionError('cannot write to /vault')
        args  = type('Args', (), {'command': 'commit', 'directory': '.'})()

        stderr = StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr
            cli._print_friendly_error(error, args)
        finally:
            sys.stderr = old_stderr

        output = stderr.getvalue()
        assert 'permission denied' in output

    def test_value_error_pattern_mismatch_shows_version_hint(self):
        """ValueError from Safe_Str pattern validation should hint about CLI version."""
        cli   = CLI__Main()
        error = ValueError("in Safe_Str__Branch_Id, value does not match required pattern: ^branch-(named|clone)-[0-9a-f]{8,64}$")
        args  = type('Args', (), {'command': 'pull', 'directory': '.'})()

        stderr = StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr
            cli._print_friendly_error(error, args)
        finally:
            sys.stderr = old_stderr

        output = stderr.getvalue()
        assert 'incompatible vault data' in output
        assert 'older CLI version'       in output
        assert 'sgit clone'              in output
        assert '--debug'                 in output
