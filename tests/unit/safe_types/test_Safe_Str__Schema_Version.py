import pytest
from sg_send_cli.safe_types.Safe_Str__Schema_Version import Safe_Str__Schema_Version


class Test_Safe_Str__Schema_Version:

    def test_valid_commit_v1(self):
        sv = Safe_Str__Schema_Version('commit_v1')
        assert sv == 'commit_v1'

    def test_valid_tree_v1(self):
        sv = Safe_Str__Schema_Version('tree_v1')
        assert sv == 'tree_v1'

    def test_valid_blob_v1(self):
        sv = Safe_Str__Schema_Version('blob_v1')
        assert sv == 'blob_v1'

    def test_valid_branch_index_v1(self):
        sv = Safe_Str__Schema_Version('branch_index_v1')
        assert sv == 'branch_index_v1'

    def test_valid_change_pack_v1(self):
        sv = Safe_Str__Schema_Version('change_pack_v1')
        assert sv == 'change_pack_v1'

    def test_empty_allowed(self):
        sv = Safe_Str__Schema_Version('')
        assert sv == ''

    def test_uppercase_lowered(self):
        sv = Safe_Str__Schema_Version('COMMIT_V1')
        assert sv == 'commit_v1'

    def test_invalid_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Schema_Version('commit-v1')

    def test_missing_version_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Schema_Version('commit')

    def test_type_preserved(self):
        sv = Safe_Str__Schema_Version('tree_v1')
        assert type(sv).__name__ == 'Safe_Str__Schema_Version'
