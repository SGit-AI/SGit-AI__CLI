"""Read-only clone tests for Vault__Sync__Branch_Ops (architect contract §5.1/§5.2 / §7.1).

branches on an RO clone returns the index branch list with is_current=False for
every branch (no clone branch is current) and my_branch_id=''.
"""


class Test_Vault__Sync__Branch_Ops__ReadOnly:

    def test_lists_index_branches(self, read_only_clone):
        result = read_only_clone['sync'].branches(read_only_clone['ro_dir'])
        assert len(result['branches']) >= 1

    def test_no_branch_is_current(self, read_only_clone):
        result = read_only_clone['sync'].branches(read_only_clone['ro_dir'])
        assert all(b['is_current'] is False for b in result['branches'])

    def test_my_branch_id_empty(self, read_only_clone):
        result = read_only_clone['sync'].branches(read_only_clone['ro_dir'])
        assert result['my_branch_id'] == ''

    def test_named_branch_present_in_listing(self, read_only_clone):
        result = read_only_clone['sync'].branches(read_only_clone['ro_dir'])
        names  = [b['name'] for b in result['branches']]
        assert 'current' in names
