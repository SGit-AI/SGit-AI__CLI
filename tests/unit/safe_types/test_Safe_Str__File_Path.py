import pytest
from sg_send_cli.safe_types.Safe_Str__File_Path import Safe_Str__File_Path, FILE_PATH__MAX_LENGTH


class Test_Safe_Str__File_Path:

    def test_valid_simple_path(self):
        path = Safe_Str__File_Path('documents/readme.txt')
        assert path == 'documents/readme.txt'

    def test_valid_nested_path(self):
        path = Safe_Str__File_Path('a/b/c/d/file.txt')
        assert path == 'a/b/c/d/file.txt'

    def test_valid_with_dashes_underscores(self):
        path = Safe_Str__File_Path('my-folder/my_file.txt')
        assert path == 'my-folder/my_file.txt'

    def test_valid_with_spaces(self):
        path = Safe_Str__File_Path('my folder/my file.txt')
        assert path == 'my folder/my file.txt'

    def test_valid_with_backslash(self):
        path = Safe_Str__File_Path('folder\\file.txt')
        assert '\\' in str(path)

    def test_empty_allowed(self):
        path = Safe_Str__File_Path('')
        assert path == ''

    def test_none_gives_empty(self):
        path = Safe_Str__File_Path(None)
        assert path == ''

    def test_max_length(self):
        assert FILE_PATH__MAX_LENGTH == 4096

    def test_exceeds_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__File_Path('a' * 4097)

    def test_at_max_length_accepted(self):
        path = Safe_Str__File_Path('a' * 4096)
        assert len(path) == 4096

    def test_special_chars_sanitized(self):
        path = Safe_Str__File_Path('file<name>.txt')
        assert '<' not in str(path)
        assert '>' not in str(path)

    def test_shell_injection_chars_sanitized(self):
        path = Safe_Str__File_Path('file;rm -rf /')
        assert ';' not in str(path)

    def test_null_bytes_sanitized(self):
        path = Safe_Str__File_Path('file\x00name.txt')
        assert '\x00' not in str(path)

    def test_type_preserved(self):
        path = Safe_Str__File_Path('test.txt')
        assert type(path).__name__ == 'Safe_Str__File_Path'

    def test_dots_allowed(self):
        path = Safe_Str__File_Path('../parent/file.tar.gz')
        assert '.tar.gz' in str(path)
