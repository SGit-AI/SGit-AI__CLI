"""`sgit version` says when the `sgit` first on the PATH is another installation
(newsroom field report, 26 Oct, item 5: /usr/local/bin/sgit stayed at 0.24.0 after
a venv upgrade)."""
import os
import stat
import tempfile

from sgit_ai.cli.CLI__Main import CLI__Main


def _script(directory, name, version_line):
    path = os.path.join(directory, name)
    with open(path, 'w') as f:
        f.write(f'#!/bin/sh\necho "{version_line}"\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class Test_Version__Path_Note:

    def test_another_sgit_first_on_the_path_is_named_with_its_version(self):
        with tempfile.TemporaryDirectory() as d:
            other = _script(d, 'sgit', 'sgit-ai 0.24.0')
            this  = _script(d, 'sgit-this', 'sgit-ai 0.25.0')
            note  = CLI__Main().path_shadow_note(argv0=this, which=lambda name: other)
            assert other in note and 'sgit-ai 0.24.0' in note and this in note

    def test_the_same_program_on_the_path_is_no_note(self):
        with tempfile.TemporaryDirectory() as d:
            this = _script(d, 'sgit', 'sgit-ai 0.25.0')
            assert CLI__Main().path_shadow_note(argv0=this, which=lambda name: this) == ''
            twin = _script(d, 'sgit-twin', 'sgit-ai 0.25.0')                  # the same entry script elsewhere
            assert CLI__Main().path_shadow_note(argv0=this, which=lambda name: twin) == ''

    def test_no_sgit_on_the_path_is_no_note(self):
        assert CLI__Main().path_shadow_note(argv0='/x/sgit', which=lambda name: None) == ''
