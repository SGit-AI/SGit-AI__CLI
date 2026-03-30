"""Unit tests for CLI__Progress — callback and _render_progress_bar methods."""
import pytest
from sgit_ai.cli.CLI__Progress import CLI__Progress


class Test_CLI__Progress:

    def setup_method(self):
        self.progress = CLI__Progress()

    def test_callback_header(self, capsys):
        """Line 11: phase='header' prints message."""
        self.progress.callback('header', 'Starting upload...')
        assert 'Starting upload' in capsys.readouterr().out

    def test_callback_step_with_detail(self, capsys):
        """phase='step' with detail prints message with detail."""
        self.progress.callback('step', 'Uploading', 'file.txt')
        out = capsys.readouterr().out
        assert 'Uploading' in out
        assert 'file.txt' in out

    def test_callback_step_no_detail(self, capsys):
        """phase='step' without detail prints message only."""
        self.progress.callback('step', 'Processing')
        assert 'Processing' in capsys.readouterr().out

    def test_callback_done(self, capsys):
        """Line 18: phase='done' prints message."""
        self.progress.callback('done', 'Upload complete.')
        assert 'Upload complete' in capsys.readouterr().out

    def test_callback_file_add(self, capsys):
        """Line 20: phase='file_add' prints + prefix."""
        self.progress.callback('file_add', 'new_file.txt')
        out = capsys.readouterr().out
        assert '+' in out
        assert 'new_file.txt' in out

    def test_callback_file_mod(self, capsys):
        """Line 22: phase='file_mod' prints ~ prefix."""
        self.progress.callback('file_mod', 'modified.txt')
        out = capsys.readouterr().out
        assert '~' in out
        assert 'modified.txt' in out

    def test_callback_file_del(self, capsys):
        """Line 24: phase='file_del' prints - prefix."""
        self.progress.callback('file_del', 'deleted.txt')
        out = capsys.readouterr().out
        assert '-' in out
        assert 'deleted.txt' in out

    def test_callback_warn(self, capsys):
        """phase='warn' prints warning."""
        self.progress.callback('warn', 'something slow')
        assert 'something slow' in capsys.readouterr().out

    def test_callback_upload_renders_progress(self, capsys):
        """Line 28: phase='upload' calls _render_progress_bar."""
        self.progress.callback('upload', 'Uploading blob', '3/10')
        assert 'Uploading blob' in capsys.readouterr().out

    def test_callback_download_renders_progress(self, capsys):
        """phase='download' calls _render_progress_bar."""
        self.progress.callback('download', 'Downloading', '5/5')
        assert 'Downloading' in capsys.readouterr().out

    def test_render_progress_bar_invalid_fraction(self, capsys):
        """Lines 37-39: invalid fraction_str prints label and returns."""
        self.progress._render_progress_bar('My label', 'not-a-fraction')
        assert 'My label' in capsys.readouterr().out

    def test_render_progress_bar_none_fraction(self, capsys):
        """Lines 37-39: None fraction_str triggers AttributeError path."""
        self.progress._render_progress_bar('Label', None)
        assert 'Label' in capsys.readouterr().out

    def test_render_progress_bar_complete(self, capsys):
        """When current >= total, prints with newline."""
        self.progress._render_progress_bar('Upload', '10/10')
        out = capsys.readouterr().out
        assert 'Upload' in out
        assert '10/10' in out

    def test_render_progress_bar_in_progress(self, capsys):
        """When current < total, prints without newline (end='')."""
        self.progress._render_progress_bar('Upload', '3/10')
        out = capsys.readouterr().out
        assert 'Upload' in out
        assert '3/10' in out
