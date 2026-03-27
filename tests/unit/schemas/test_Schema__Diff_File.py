from sgit_ai.schemas.Schema__Diff_File import Schema__Diff_File


class Test_Schema__Diff_File:

    def test_create_with_defaults(self):
        f = Schema__Diff_File()
        assert f.path        is None
        assert f.status      is None
        assert f.is_binary   is False
        assert f.diff_text   is None
        assert f.size_before == 0
        assert f.size_after  == 0
        assert f.hash_before is None
        assert f.hash_after  is None

    def test_create_added_file(self):
        f = Schema__Diff_File(path='new.txt', status='added',
                               size_after=42, hash_after='a' * 64)
        assert f.path       == 'new.txt'
        assert f.status     == 'added'
        assert f.size_after == 42
        assert f.hash_after == 'a' * 64

    def test_create_deleted_file(self):
        f = Schema__Diff_File(path='old.txt', status='deleted',
                               size_before=100, hash_before='b' * 64)
        assert f.status      == 'deleted'
        assert f.size_before == 100
        assert f.hash_before == 'b' * 64

    def test_create_modified_file(self):
        f = Schema__Diff_File(path='file.txt', status='modified',
                               size_before=10, size_after=20,
                               hash_before='a' * 64, hash_after='b' * 64,
                               diff_text='--- a/file.txt\n+++ b/file.txt\n')
        assert f.status     == 'modified'
        assert f.diff_text  == '--- a/file.txt\n+++ b/file.txt\n'

    def test_create_unchanged_file(self):
        f = Schema__Diff_File(path='same.txt', status='unchanged',
                               size_before=5, size_after=5,
                               hash_before='c' * 64, hash_after='c' * 64)
        assert f.status == 'unchanged'

    def test_is_binary_flag(self):
        f = Schema__Diff_File(path='image.png', status='modified', is_binary=True)
        assert f.is_binary is True

    def test_round_trip_empty(self):
        f = Schema__Diff_File()
        assert Schema__Diff_File.from_json(f.json()).json() == f.json()

    def test_round_trip_added(self):
        f = Schema__Diff_File(path='foo.txt', status='added', size_after=99)
        assert Schema__Diff_File.from_json(f.json()).json() == f.json()

    def test_round_trip_modified_text(self):
        f = Schema__Diff_File(path='bar.txt', status='modified',
                               size_before=10, size_after=20,
                               hash_before='a' * 64, hash_after='b' * 64,
                               diff_text='@@ -1 +1,2 @@\n line\n+new\n')
        assert Schema__Diff_File.from_json(f.json()).json() == f.json()

    def test_round_trip_binary(self):
        f = Schema__Diff_File(path='img.bin', status='modified', is_binary=True,
                               size_before=100, size_after=200,
                               hash_before='a' * 64, hash_after='b' * 64)
        assert Schema__Diff_File.from_json(f.json()).json() == f.json()

    def test_round_trip_deleted(self):
        f = Schema__Diff_File(path='gone.txt', status='deleted', size_before=50,
                               hash_before='d' * 64)
        assert Schema__Diff_File.from_json(f.json()).json() == f.json()

    def test_field_types_preserved(self):
        f = Schema__Diff_File(path='test.txt')
        assert type(f.path).__name__ == 'Safe_Str__File_Path'

    def test_size_fields_default_zero(self):
        f = Schema__Diff_File()
        assert int(f.size_before) == 0
        assert int(f.size_after)  == 0
