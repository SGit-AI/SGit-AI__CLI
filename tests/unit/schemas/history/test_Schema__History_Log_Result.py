"""Round-trip and structural tests for history log schemas (Brief 13)."""
from sgit_ai.schemas.history.Schema__History_Log_Commit_Entry import Schema__History_Log_Commit_Entry
from sgit_ai.schemas.history.Schema__History_Log_Result       import Schema__History_Log_Result
from sgit_ai.schemas.history.Schema__History_Diff_File        import Schema__History_Diff_File
from sgit_ai.schemas.history.Schema__History_Diff_Result      import Schema__History_Diff_Result


class Test_Schema__History_Log_Result:

    def test_round_trip_empty(self):
        r = Schema__History_Log_Result()
        assert Schema__History_Log_Result.from_json(r.json()).json() == r.json()

    def test_round_trip_with_entry(self):
        entry = Schema__History_Log_Commit_Entry(
            commit_id     = 'obj-cas-imm-aabbccddeeff',
            parent_ids    = ['obj-cas-imm-000000000000'],
            timestamp_ms  = 1747088400000,
            timestamp_iso = '2026-05-12T10:00:00Z',
            message       = 'Add foo.py',
            branch_id     = 'obj-cas-imm-bbbbbbbbbbbb',
        )
        r = Schema__History_Log_Result(
            schema       = 'history_log_v1',
            from_commit  = 'obj-cas-imm-000000000000',
            to_commit    = 'obj-cas-imm-aabbccddeeff',
            commit_count = 1,
            commits      = [entry],
        )
        assert Schema__History_Log_Result.from_json(r.json()).json() == r.json()

    def test_round_trip_with_optional_patch(self):
        entry = Schema__History_Log_Commit_Entry(
            commit_id      = 'obj-cas-imm-aabbccddeeff',
            files_added    = ['src/foo.py'],
            files_modified = ['README.md'],
            files_deleted  = [],
            patch          = '--- a/README.md\n+++ b/README.md\n@@ -1 +1,2 @@\n+extra line\n',
        )
        r = Schema__History_Log_Result(
            schema       = 'history_log_v1',
            commit_count = 1,
            commits      = [entry],
        )
        assert Schema__History_Log_Result.from_json(r.json()).json() == r.json()

    def test_commit_count_default_is_zero(self):
        r = Schema__History_Log_Result()
        assert int(r.commit_count) == 0

    def test_commits_list_default_is_empty(self):
        r = Schema__History_Log_Result()
        assert r.commits == []

    def test_entry_defaults(self):
        e = Schema__History_Log_Commit_Entry()
        assert e.commit_id is None
        assert e.parent_ids == []
        assert int(e.timestamp_ms) == 0
        assert e.files_added == []
        assert e.files_modified == []
        assert e.files_deleted == []
        assert e.patch is None


class Test_Schema__History_Diff_Result:

    def test_round_trip_empty(self):
        r = Schema__History_Diff_Result()
        assert Schema__History_Diff_Result.from_json(r.json()).json() == r.json()

    def test_round_trip_with_files(self):
        mod = Schema__History_Diff_File(path='src/foo.py', lines_added=10, lines_removed=4)
        r = Schema__History_Diff_Result(
            schema         = 'history_diff_v1',
            from_commit    = 'obj-cas-imm-aaa000000000',
            to_commit      = 'obj-cas-imm-zzz000000000',
            files_added    = ['src/new.py'],
            files_modified = [mod],
            files_deleted  = ['old.py'],
        )
        assert Schema__History_Diff_Result.from_json(r.json()).json() == r.json()

    def test_diff_file_defaults(self):
        f = Schema__History_Diff_File()
        assert f.path is None
        assert int(f.lines_added)   == 0
        assert int(f.lines_removed) == 0
