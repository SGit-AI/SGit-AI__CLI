import json
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.core.actions.dump.Vault__Dump            import Vault__Dump
from sgit_ai.core.actions.diff.Vault__Dump_Diff       import Vault__Dump_Diff
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.schemas.Schema__Dump_Result import Schema__Dump_Result
from sgit_ai.schemas.Schema__Dump_Ref    import Schema__Dump_Ref
from sgit_ai.schemas.Schema__Dump_Branch import Schema__Dump_Branch
from sgit_ai.schemas.Schema__Dump_Commit import Schema__Dump_Commit
from sgit_ai.schemas.Schema__Dump_Object import Schema__Dump_Object
from sgit_ai.schemas.Schema__Dump_Diff   import Schema__Dump_Diff


class Test_Vault__Dump_Diff:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.crypto     = Vault__Crypto()
        self.api        = Vault__API__In_Memory()
        self.api.setup()
        self.sync       = Vault__Sync(crypto=self.crypto, api=self.api)
        self.dumper     = Vault__Dump(crypto=self.crypto)
        self.diff_engine = Vault__Dump_Diff()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='diff-test'):
        directory = os.path.join(self.tmp_dir, name)
        result    = self.sync.init(directory)
        return result, directory

    def _add_file(self, directory: str, filename: str, content: str) -> None:
        with open(os.path.join(directory, filename), 'w') as fh:
            fh.write(content)

    def _make_empty_dump(self, source='test') -> Schema__Dump_Result:
        return Schema__Dump_Result(source=source)

    # ------------------------------------------------------------------
    # Tests using synthetic dumps (no real vault I/O)
    # ------------------------------------------------------------------

    def test_diff_identical_empty_dumps(self):
        a = self._make_empty_dump('A')
        b = self._make_empty_dump('B')
        result = self.diff_engine.diff(a, b)
        assert isinstance(result, Schema__Dump_Diff)
        assert result.identical is True
        assert int(result.total_diffs) == 0

    def test_diff_refs_only_in_a(self):
        a = Schema__Dump_Result(
            source='a',
            refs=[Schema__Dump_Ref(ref_id='ref-pid-muw-aabb1122',
                                   commit_id='obj-cas-imm-111111111111')],
        )
        b = self._make_empty_dump('b')
        result = self.diff_engine.diff(a, b)
        assert result.identical is False
        assert 'ref-pid-muw-aabb1122' in result.refs_only_in_a
        assert result.refs_only_in_b == []

    def test_diff_refs_only_in_b(self):
        a = self._make_empty_dump('a')
        b = Schema__Dump_Result(
            source='b',
            refs=[Schema__Dump_Ref(ref_id='ref-pid-muw-ccdd3344',
                                   commit_id='obj-cas-imm-222222222222')],
        )
        result = self.diff_engine.diff(a, b)
        assert result.identical is False
        assert 'ref-pid-muw-ccdd3344' in result.refs_only_in_b

    def test_diff_refs_diverged(self):
        ref_id = 'ref-pid-muw-aabb1122'
        a = Schema__Dump_Result(
            source='a',
            refs=[Schema__Dump_Ref(ref_id=ref_id, commit_id='obj-cas-imm-111111111111')],
        )
        b = Schema__Dump_Result(
            source='b',
            refs=[Schema__Dump_Ref(ref_id=ref_id, commit_id='obj-cas-imm-222222222222')],
        )
        result = self.diff_engine.diff(a, b)
        assert result.identical is False
        assert ref_id in result.refs_diverged

    def test_diff_objects_only_in_a(self):
        a = Schema__Dump_Result(
            source='a',
            objects=[Schema__Dump_Object(object_id='obj-cas-imm-aaaaaaaaaaaa', size_bytes=100)],
        )
        b = self._make_empty_dump('b')
        result = self.diff_engine.diff(a, b)
        assert 'obj-cas-imm-aaaaaaaaaaaa' in result.objects_only_in_a

    def test_diff_branches_head_differ(self):
        branch_id = 'branch-named-aabb1122'
        a = Schema__Dump_Result(
            source='a',
            branches=[Schema__Dump_Branch(branch_id=branch_id,
                                          head_commit='obj-cas-imm-111111111111',
                                          created_at=1000)],
        )
        b = Schema__Dump_Result(
            source='b',
            branches=[Schema__Dump_Branch(branch_id=branch_id,
                                          head_commit='obj-cas-imm-222222222222',
                                          created_at=1000)],
        )
        result = self.diff_engine.diff(a, b)
        assert branch_id in result.branches_head_differ
        assert result.identical is False

    def test_diff_branches_only_in_a(self):
        a = Schema__Dump_Result(
            source='a',
            branches=[Schema__Dump_Branch(branch_id='branch-named-unique-a',
                                          created_at=1000)],
        )
        b = self._make_empty_dump('b')
        result = self.diff_engine.diff(a, b)
        assert 'branch-named-unique-a' in result.branches_only_in_a

    def test_diff_commits_only_in_a(self):
        a = Schema__Dump_Result(
            source='a',
            commits=[Schema__Dump_Commit(commit_id='obj-cas-imm-commitaaaaaa',
                                         timestamp_ms=1000)],
        )
        b = self._make_empty_dump('b')
        result = self.diff_engine.diff(a, b)
        assert 'obj-cas-imm-commitaaaaaa' in result.commits_only_in_a

    def test_diff_counts(self):
        ref_id = 'ref-pid-muw-zzzzzzzz'
        a = Schema__Dump_Result(
            source='a',
            refs=[Schema__Dump_Ref(ref_id=ref_id, commit_id='obj-cas-imm-111111111111')],
            objects=[Schema__Dump_Object(object_id='obj-cas-imm-aaaaaaaaaaaa', size_bytes=50)],
        )
        b = self._make_empty_dump('b')
        result = self.diff_engine.diff(a, b)
        assert int(result.refs_diff_count)    >= 1
        assert int(result.objects_diff_count) >= 1
        assert int(result.total_diffs)        >= 2

    def test_diff_labels(self):
        # Note: Safe_Str normalises hyphens to underscores.
        a = self._make_empty_dump('local')
        b = self._make_empty_dump('remote')
        result = self.diff_engine.diff(a, b, label_a='vaultlocal', label_b='vaultremote')
        assert str(result.label_a) == 'vaultlocal'
        assert str(result.label_b) == 'vaultremote'

    def test_diff_result_round_trip(self):
        a = Schema__Dump_Result(
            source='a',
            refs=[Schema__Dump_Ref(ref_id='ref-pid-muw-aabb1122',
                                   commit_id='obj-cas-imm-111111111111')],
        )
        b = self._make_empty_dump('b')
        diff_result = self.diff_engine.diff(a, b)
        restored    = Schema__Dump_Diff.from_json(diff_result.json())
        assert restored.json() == diff_result.json()

    # ------------------------------------------------------------------
    # Tests using a real vault
    # ------------------------------------------------------------------

    def test_diff_same_dump_is_identical(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'file.txt', 'data')
        self.sync.commit(directory, message='commit')
        dump   = self.dumper.dump_local(directory)
        result = self.diff_engine.diff(dump, dump)
        assert result.identical is True

    def test_diff_two_dumps_of_same_vault_state_are_identical(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'file.txt', 'data')
        self.sync.commit(directory, message='commit')
        dump_a = self.dumper.dump_local(directory)
        dump_b = self.dumper.dump_local(directory)
        result = self.diff_engine.diff(dump_a, dump_b)
        assert result.identical is True

    def test_diff_from_files(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'a.txt', 'alpha')
        self.sync.commit(directory, message='first')

        dump_a    = self.dumper.dump_local(directory)
        file_a    = os.path.join(self.tmp_dir, 'dump_a.json')
        file_b    = os.path.join(self.tmp_dir, 'dump_b.json')
        with open(file_a, 'w') as fh:
            json.dump(dump_a.json(), fh)
        with open(file_b, 'w') as fh:
            json.dump(dump_a.json(), fh)

        result = self.diff_engine.diff_from_files(file_a, file_b)
        assert result.identical is True
