"""Unit tests for CLI__Input — prompt() method.

Covers the non-TTY path (returns None immediately) and mocked TTY paths
(select timeout, successful input).
"""
import select as _select
import sys

import pytest

from sgit_ai.cli.CLI__Input import CLI__Input


class Test_CLI__Input:

    def test_prompt_non_tty_returns_none(self):
        """In a non-TTY context (e.g. CI / Claude Code), prompt returns None."""
        inp = CLI__Input()
        result = inp.prompt('Continue? [y/N]: ')
        # pytest stdin is not a TTY, so this must return None
        assert result is None

    def test_prompt_tty_timeout_returns_none(self, monkeypatch):
        """When stdin is a TTY but no input arrives within timeout, returns None."""
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
        # select.select returns empty ready list → timeout
        monkeypatch.setattr(_select, 'select', lambda rlist, wlist, xlist, timeout: ([], [], []))
        inp = CLI__Input()
        result = inp.prompt('Input: ')
        assert result is None

    def test_prompt_tty_with_input(self, monkeypatch, capsys):
        """When stdin is a TTY and input is ready, returns the line content."""
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
        # select.select returns stdin as ready
        monkeypatch.setattr(_select, 'select',
                            lambda rlist, wlist, xlist, timeout: (rlist, [], []))
        monkeypatch.setattr(sys.stdin, 'readline', lambda: 'yes\n')
        inp = CLI__Input()
        result = inp.prompt('Continue? ')
        assert result == 'yes'

    def test_prompt_tty_empty_input(self, monkeypatch):
        """Empty input (just Enter) returns empty string."""
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
        monkeypatch.setattr(_select, 'select',
                            lambda rlist, wlist, xlist, timeout: (rlist, [], []))
        monkeypatch.setattr(sys.stdin, 'readline', lambda: '\n')
        inp = CLI__Input()
        result = inp.prompt('Enter: ')
        assert result == ''

    def test_prompt_timeout_message_printed(self, monkeypatch, capsys):
        """When timeout occurs, a cancellation message is printed."""
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
        monkeypatch.setattr(_select, 'select', lambda *a, **k: ([], [], []))
        inp = CLI__Input(timeout=5)
        inp.prompt('Confirm: ')
        out = capsys.readouterr().out
        assert 'cancelled' in out.lower() or 'no response' in out.lower()

    def test_prompt_default_timeout(self):
        """Default timeout is 30 seconds."""
        inp = CLI__Input()
        assert int(inp.timeout) == 30
