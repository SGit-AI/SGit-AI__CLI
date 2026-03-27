from sgit_ai.schemas.Schema__Diff_File   import Schema__Diff_File
from sgit_ai.schemas.Schema__Diff_Result import Schema__Diff_Result


class Test_Schema__Diff_Result:

    def test_create_with_defaults(self):
        r = Schema__Diff_Result()
        assert r.directory      is None
        assert r.mode           is None
        assert r.commit_id      is None
        assert r.files          == []
        assert r.added_count    == 0
        assert r.modified_count == 0
        assert r.deleted_count  == 0

    def test_create_with_values(self):
        f = Schema__Diff_File(path='file.txt', status='added', size_after=10)
        r = Schema__Diff_Result(directory='.', mode='head', files=[f],
                                 added_count=1)
        assert r.directory      == '.'
        assert r.mode           == 'head'
        assert r.added_count    == 1
        assert len(r.files)     == 1

    def test_mode_head(self):
        r = Schema__Diff_Result(mode='head')
        assert r.mode == 'head'

    def test_mode_remote(self):
        r = Schema__Diff_Result(mode='remote')
        assert r.mode == 'remote'

    def test_mode_commit(self):
        r = Schema__Diff_Result(mode='commit', commit_id='abc123')
        assert r.mode      == 'commit'
        assert r.commit_id == 'abc123'

    def test_counts_populated(self):
        r = Schema__Diff_Result(added_count=3, modified_count=2, deleted_count=1)
        assert r.added_count    == 3
        assert r.modified_count == 2
        assert r.deleted_count  == 1

    def test_round_trip_empty(self):
        r = Schema__Diff_Result()
        assert Schema__Diff_Result.from_json(r.json()).json() == r.json()

    def test_round_trip_with_files(self):
        f1 = Schema__Diff_File(path='a.txt', status='added',   size_after=10)
        f2 = Schema__Diff_File(path='b.txt', status='deleted', size_before=5)
        r  = Schema__Diff_Result(directory='/tmp/vault', mode='head',
                                  files=[f1, f2], added_count=1, deleted_count=1)
        restored = Schema__Diff_Result.from_json(r.json())
        assert restored.json() == r.json()

    def test_round_trip_commit_mode(self):
        r = Schema__Diff_Result(mode='commit', commit_id='deadbeef1234',
                                 modified_count=5)
        assert Schema__Diff_Result.from_json(r.json()).json() == r.json()

    def test_files_list_preserves_order(self):
        files = [Schema__Diff_File(path=f'file{i}.txt', status='added') for i in range(5)]
        r     = Schema__Diff_Result(files=files, added_count=5)
        paths = [str(f.path) for f in r.files]
        assert paths == [f'file{i}.txt' for i in range(5)]

    def test_directory_field_type(self):
        r = Schema__Diff_Result(directory='/tmp/vault')
        assert type(r.directory).__name__ == 'Safe_Str__File_Path'

    def test_mode_field_type(self):
        r = Schema__Diff_Result(mode='remote')
        assert type(r.mode).__name__ == 'Safe_Str__Diff_Mode'
