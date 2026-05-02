"""Coverage tests for Vault__Inspector — inspect_commit_dag (lines 188-228),
_format_graph (lines 333, 352-353, 385, 393, 398-399, 413-416, 419-424),
format_commit_log obj_parts branch (line 309), and _dir_set subdirectory (line 171).
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.objects.Vault__Inspector  import Vault__Inspector
from sgit_ai.sync.Vault__Storage       import SG_VAULT_DIR
from tests._helpers.vault_test_env     import Vault__Test_Env


def _make_inspector(snap):
    return Vault__Inspector(crypto=snap.crypto)


def _read_key(snap):
    keys = snap.crypto.derive_keys_from_vault_key(snap.vault_key)
    return keys['read_key_bytes']


class Test_Vault__Inspector__Dag:
    """Tests for inspect_commit_dag (lines 188-228)."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'f.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap      = self._env.restore()
        self.inspector = _make_inspector(self.snap)
        self.read_key  = _read_key(self.snap)

    def teardown_method(self):
        self.snap.cleanup()

    def test_inspect_commit_dag_no_read_key_returns_empty(self):
        """Lines 191-192: no read_key → return []."""
        result = self.inspector.inspect_commit_dag(self.snap.vault_dir)
        assert result == []

    def test_inspect_commit_dag_returns_commits(self):
        """Lines 193-228: walks commits from HEAD via BFS."""
        result = self.inspector.inspect_commit_dag(
            self.snap.vault_dir, read_key=self.read_key
        )
        assert len(result) >= 1
        assert 'commit_id' in result[0]
        assert 'parents' in result[0]
        assert 'tree_id' in result[0]

    def test_inspect_commit_dag_includes_message(self):
        """Lines 214-218: message is decrypted and included."""
        result = self.inspector.inspect_commit_dag(
            self.snap.vault_dir, read_key=self.read_key
        )
        # HEAD commit has 'initial commit' message
        head = result[0]
        assert 'message' in head

    def test_inspect_commit_dag_missing_commit_shows_error(self):
        """Lines 203-207: commit not cached locally → error entry returned."""
        # Delete one object from the data store so it appears 'not cached locally'
        data_dir = os.path.join(self.snap.vault_dir, SG_VAULT_DIR, 'bare', 'data')
        objects  = sorted(os.listdir(data_dir))
        # Remove the head commit so the HEAD object is missing
        commit_id = self.snap.commit_id
        obj_path  = os.path.join(data_dir, commit_id)
        if os.path.isfile(obj_path):
            os.remove(obj_path)

        result = self.inspector.inspect_commit_dag(
            self.snap.vault_dir, read_key=self.read_key
        )
        # There should be an entry with error='not cached locally'
        errors = [c for c in result if c.get('error') == 'not cached locally']
        assert len(errors) >= 1

    def test_inspect_commit_dag_respects_limit(self):
        """Lines 197 (limit check): limit=1 returns at most 1 commit."""
        result = self.inspector.inspect_commit_dag(
            self.snap.vault_dir, read_key=self.read_key, limit=1
        )
        assert len(result) <= 1

    def test_inspect_commit_dag_with_multiple_commits(self):
        """Lines 223-226: parent commits enqueued and processed."""
        # Make a second commit so there are 2 reachable commits in the DAG
        snap = self._env.restore()
        try:
            import json as _json
            from sgit_ai.sync.Vault__Storage           import Vault__Storage
            from sgit_ai.schemas.Schema__Local_Config  import Schema__Local_Config
            vault_dir = snap.vault_dir
            with open(os.path.join(vault_dir, 'f.txt'), 'w') as f:
                f.write('modified')
            snap.sync.commit(vault_dir, message='second commit')
            inspector = Vault__Inspector(crypto=snap.crypto)
            keys      = snap.crypto.derive_keys_from_vault_key(snap.vault_key)
            result    = inspector.inspect_commit_dag(
                vault_dir, read_key=keys['read_key_bytes']
            )
            assert len(result) >= 2
        finally:
            snap.cleanup()


class Test_Vault__Inspector__Format_Graph:
    """Tests for _format_graph (lines 333, 352-353, 385, 393, 398-399, 413-416, 419-424)
    and format_commit_log with graph=True / obj_parts (lines 309, 333).
    """

    def setup_method(self):
        self.inspector = Vault__Inspector(crypto=Vault__Crypto())

    def test_format_commit_log_graph_empty(self):
        """Line 333: _format_graph with empty list → '(no commits)'."""
        result = self.inspector.format_commit_log([], graph=True)
        assert result == '(no commits)'

    def test_format_commit_log_obj_parts_only(self):
        """Line 309: commit with new_trees>0 but no added/modified/deleted → 'Objects:' line."""
        chain = [dict(
            commit_id    = 'abc' * 21 + 'a',   # 64 chars
            timestamp_ms = 1_000_000,
            message      = '',
            tree_id      = 'tree' + 'a' * 60,
            parents      = [],
            new_blobs    = 0,
            new_trees    = 1,
            added        = 0,
            modified     = 0,
            deleted      = 0,
            total_files  = 1,
        )]
        result = self.inspector.format_commit_log(chain, oneline=False)
        assert 'Objects:' in result

    def test_format_graph_single_commit(self):
        """Basic graph rendering: single commit produces marker line."""
        commits = [dict(commit_id='commit-a', parents=[], timestamp_ms=0,
                        message='first', tree_id='tree-a')]
        result = self.inspector._format_graph(commits)
        assert 'commit-a' in result
        assert '*' in result

    def test_format_graph_fan_out_merge_commit(self):
        """Lines 398-399, 413-416: merge commit with two parents adds extra column (fan-out)."""
        # commit-a is a merge with parents [commit-b, commit-c].
        # After processing: columns = [commit-b, commit-c]. new_n=2 > old_n=1 → fan-out.
        commits = [
            dict(commit_id='commit-a', parents=['commit-b', 'commit-c'],
                 timestamp_ms=0, message='merge', tree_id='t1'),
            dict(commit_id='commit-b', parents=[], timestamp_ms=0, message='b', tree_id='t2'),
            dict(commit_id='commit-c', parents=[], timestamp_ms=0, message='c', tree_id='t3'),
        ]
        result = self.inspector._format_graph(commits)
        assert 'commit-a' in result
        assert 'commit-b' in result
        assert '\\' in result   # fan-out transition marker

    def test_format_graph_fan_in_single_lane(self):
        """Lines 419-420: lane ends → new_n==1 → simple '|' transition."""
        # merge commit-a has 2 parents. After processing: columns=[commit-b, commit-c].
        # processing commit-b: pop → columns=[commit-c]. new_n=1 < old_n=2 → '|'.
        commits = [
            dict(commit_id='commit-a', parents=['commit-b', 'commit-c'],
                 timestamp_ms=0, message='merge', tree_id='t1'),
            dict(commit_id='commit-b', parents=[], timestamp_ms=0, message='b', tree_id='t2'),
            dict(commit_id='commit-c', parents=[], timestamp_ms=0, message='c', tree_id='t3'),
        ]
        result = self.inspector._format_graph(commits)
        assert '|' in result

    def test_format_graph_fan_in_multi_lane(self):
        """Lines 422-424: lane ends with new_n>1 → '/' transition."""
        # commit-a has 3 parents: [b, c, d]. After processing: columns=[b, c, d] (3 lanes).
        # processing commit-b: pop → columns=[c, d]. new_n=2 < old_n=3 → '/' transition.
        commits = [
            dict(commit_id='commit-a', parents=['commit-b', 'commit-c', 'commit-d'],
                 timestamp_ms=0, message='mega-merge', tree_id='t1'),
            dict(commit_id='commit-b', parents=[], timestamp_ms=0, message='b', tree_id='t2'),
            dict(commit_id='commit-c', parents=[], timestamp_ms=0, message='c', tree_id='t3'),
            dict(commit_id='commit-d', parents=[], timestamp_ms=0, message='d', tree_id='t4'),
        ]
        result = self.inspector._format_graph(commits)
        assert '/' in result

    def test_format_graph_oneline_mode(self):
        """Lines 352-353 + oneline path: _format_graph with oneline=True."""
        commits = [
            dict(commit_id='commit-a', parents=['commit-b'], timestamp_ms=1_000_000,
                 message='first', tree_id='tree-a'),
            dict(commit_id='commit-b', parents=[], timestamp_ms=0,
                 message='init', tree_id='tree-b'),
        ]
        result = self.inspector._format_graph(commits, oneline=True)
        assert 'commit-a' in result
        # oneline mode suppresses Date/Tree lines
        assert 'Date:' not in result


class Test_Vault__Inspector__Subdir_Coverage:
    """Test line 171: _dir_set inner loop in inspect_commit_chain."""

    _env = None

    @classmethod
    def setup_class(cls):
        # Create vault with files in subdirectory so inspect_commit_chain
        # enters the _dir_set inner for loop (line 171)
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'docs/readme.txt': 'guide content',
            'src/main.py':     'print("hello")',
            'top.txt':         'top level',
        })

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap      = self._env.restore()
        self.inspector = _make_inspector(self.snap)
        self.read_key  = _read_key(self.snap)

    def teardown_method(self):
        self.snap.cleanup()

    def test_inspect_commit_chain_with_subdirectories_hits_dir_set(self):
        """Line 171: vault with subdirectories causes _dir_set inner loop to execute."""
        chain = self.inspector.inspect_commit_chain(
            self.snap.vault_dir, read_key=self.read_key
        )
        assert len(chain) >= 1
        # The HEAD commit should show new_trees > 0 (docs/ and src/ are new directories)
        head = chain[0]
        assert head.get('new_trees', 0) > 0
