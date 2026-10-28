"""Line-level merge on pull (roadmap 2.1, design__01 §5.5-5.8): opt-in, the default unchanged.

Alice pushes, then Bob commits a change to the same file and pulls. With `--merge lines` (or SGIT_MERGE_STYLE, or the clone's config) the
lines are merged as git merges them: clean when they do not collide, markers in the
file when they do; commit refuses while markers remain; resolve takes a side or marks
a hand edit. Without it, today's whole-file `.conflict` merge, byte for byte."""
import json
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Merge_Unresolved_Error, Vault__Dirty_Working_Tree_Error
from sgit_ai.core.Vault__Head_Paths                   import Vault__Head_Paths
from sgit_ai.core.actions.merge.Vault__Merge__Resolve import Vault__Merge__Resolve
from sgit_ai.core.actions.merge.Vault__Merge__State   import Vault__Merge__State
from sgit_ai.crypto.PKI__Crypto                       import PKI__Crypto
from sgit_ai.storage.Vault__Storage                   import Vault__Storage
from tests.unit.sync.vault_test_env                   import Vault__Test_Env

BASE = ''.join(f'line {i}\n' for i in range(1, 11))


def changed(text: str, line: int, new: str) -> str:
    lines = text.splitlines(keepends=True)
    lines[line - 1] = new + '\n'
    return ''.join(lines)


class Test_Vault__Sync__Pull__Line_Merge:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'notes.txt': BASE, 'other.txt': 'x\n'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.crypto, self.pki = self.env.crypto, PKI__Crypto()
        self.sync = self.env.sync
        self.dir  = self.env.bob_dir                                        # this clone
        self.alice = self.env.alice_dir

    def teardown_method(self):
        self.env.cleanup()

    def path(self, rel):
        return os.path.join(self.dir, rel)

    def read(self, rel) -> str:
        with open(self.path(rel)) as f:
            return f.read()

    def diverge(self, ours: str, theirs: str, rel: str = 'notes.txt'):
        with open(os.path.join(self.alice, rel), 'w') as f:                  # theirs: Alice pushes first
            f.write(theirs)
        self.sync.commit(self.alice, message='theirs')
        self.sync.push(self.alice)
        with open(self.path(rel), 'w') as f:                                 # ours: Bob's commit
            f.write(ours)
        self.sync.commit(self.dir, message='ours')

    # --- clean --------------------------------------------------------------------------

    def test_changes_to_different_lines_merge_cleanly(self):
        self.diverge(changed(BASE, 2, 'OURS'), changed(BASE, 8, 'THEIRS'))
        result = self.sync.pull(self.dir, merge_style='lines')
        assert result['status'] == 'merged'
        assert result['line_merged'] == ['notes.txt']
        assert self.read('notes.txt') == changed(changed(BASE, 2, 'OURS'), 8, 'THEIRS')
        assert not os.path.exists(self.path('notes.txt.conflict'))
        assert self.sync.status(self.dir)['clean']

    def test_the_default_is_still_a_whole_file_conflict(self):
        self.diverge(changed(BASE, 2, 'OURS'), changed(BASE, 8, 'THEIRS'))
        result = self.sync.pull(self.dir)
        assert result['status'] == 'conflicts'
        assert os.path.isfile(self.path('notes.txt.conflict'))
        assert self.read('notes.txt') == changed(BASE, 2, 'OURS')

    def test_the_session_environment_and_the_clone_config_choose_lines(self, monkeypatch):
        self.diverge(changed(BASE, 2, 'OURS'), changed(BASE, 8, 'THEIRS'))
        monkeypatch.setenv('SGIT_MERGE_STYLE', 'lines')
        assert self.sync.pull(self.dir)['status'] == 'merged'

    def test_the_clone_config_chooses_lines(self):
        storage = Vault__Storage()
        path    = storage.local_config_path(self.dir)
        with open(path) as f:
            config = json.load(f)
        config['merge_style'] = 'lines'
        with open(path, 'w') as f:
            json.dump(config, f)
        self.diverge(changed(BASE, 2, 'OURS'), changed(BASE, 8, 'THEIRS'))
        assert self.sync.pull(self.dir)['status'] == 'merged'

    # --- conflicts -----------------------------------------------------------------------

    def test_colliding_lines_get_markers_and_commit_waits_for_them(self):
        self.diverge(changed(BASE, 5, 'OURS'), changed(BASE, 5, 'THEIRS'))
        result = self.sync.pull(self.dir, merge_style='lines')
        assert result['status'] == 'conflicts'
        assert result['marker_files'] == ['notes.txt']
        text = self.read('notes.txt')
        assert '<<<<<<< ours (this clone ' in text and '=======\nTHEIRS\n>>>>>>> theirs (current ' in text
        assert not os.path.exists(self.path('notes.txt.conflict'))
        assert [str(p) for p in Vault__Merge__State().read(self.dir).marker_paths] == ['notes.txt']
        with pytest.raises(Vault__Merge_Unresolved_Error) as error:
            self.sync.commit(self.dir, message='would commit markers')
        assert 'notes.txt   (conflict markers in the file)' in str(error.value)
        with open(self.path('notes.txt'), 'w') as f:                         # the agent loop: edit, then commit
            f.write(changed(BASE, 5, 'BOTH'))
        result = self.sync.commit(self.dir, message='merged by hand')
        assert result['merge_commit'] is True
        assert 'notes.txt.conflict' not in Vault__Head_Paths(crypto=self.crypto).paths(self.dir)

    def test_status_names_the_marker_file(self, capsys):
        self.diverge(changed(BASE, 5, 'OURS'), changed(BASE, 5, 'THEIRS'))
        self.sync.pull(self.dir, merge_style='lines')
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        CLI__Vault._print_merge_block(None, self.sync.status(self.dir))
        out = capsys.readouterr().out
        assert 'Merge in progress (lines style): 1 unresolved, 0 resolved' in out
        assert '! notes.txt   conflict markers in the file' in out

    def test_resolve_theirs_replaces_the_markers(self):
        self.diverge(changed(BASE, 5, 'OURS'), changed(BASE, 5, 'THEIRS'))
        self.sync.pull(self.dir, merge_style='lines')
        Vault__Merge__Resolve(crypto=self.crypto).resolve_file(self.dir, 'notes.txt', 'theirs')
        assert self.read('notes.txt') == changed(BASE, 5, 'THEIRS')
        assert self.sync.commit(self.dir, message='took theirs')['merge_commit'] is True

    def test_resolve_ours_and_mark(self):
        self.diverge(changed(BASE, 5, 'OURS'), changed(BASE, 5, 'THEIRS'))
        self.sync.pull(self.dir, merge_style='lines')
        with pytest.raises(RuntimeError):
            Vault__Merge__Resolve(crypto=self.crypto).resolve_file(self.dir, 'notes.txt', 'mark')   # markers remain
        Vault__Merge__Resolve(crypto=self.crypto).resolve_file(self.dir, 'notes.txt', 'ours')
        assert self.read('notes.txt') == changed(BASE, 5, 'OURS')

    def test_diff3_shows_the_base(self):
        self.diverge(changed(BASE, 5, 'OURS'), changed(BASE, 5, 'THEIRS'))
        self.sync.pull(self.dir, merge_style='lines', conflict_style='diff3')
        text = self.read('notes.txt')
        assert '||||||| base (' in text and '\nline 5\n=======\n' in text

    def test_an_uncommitted_edit_where_markers_go_refuses_the_pull(self):
        self.diverge(changed(BASE, 5, 'OURS'), changed(BASE, 5, 'THEIRS'))
        with open(self.path('notes.txt'), 'w') as f:
            f.write('my unsaved work\n')
        head = self.sync.resolve_revision(self.dir, 'HEAD')
        with pytest.raises(Vault__Dirty_Working_Tree_Error) as error:
            self.sync.pull(self.dir, merge_style='lines')
        assert 'replaced by conflict markers' in str(error.value)
        assert self.read('notes.txt') == 'my unsaved work\n'
        assert self.sync.resolve_revision(self.dir, 'HEAD') == head

    def test_a_binary_file_falls_back_to_a_whole_file_conflict(self):
        self.diverge('ours\x00bin', 'theirs\x00bin', rel='data.bin')
        result = self.sync.pull(self.dir, merge_style='lines')
        assert result['status'] == 'conflicts'
        assert result['conflict_notes'] == {'data.bin': 'binary'}
        assert os.path.isfile(self.path('data.bin.conflict'))
