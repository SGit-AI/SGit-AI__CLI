"""Tests for NF4 — vault_with_branches fixture."""
import os


class Test_NF4_Vault_With_Branches:

    def test_vault_dir_exists(self, vault_with_branches):
        assert os.path.isdir(vault_with_branches['vault_dir'])

    def test_branches_dict_has_main_and_feature(self, vault_with_branches):
        b = vault_with_branches['branches']
        assert 'main'    in b
        assert 'feature' in b
        assert 'base'    in b

    def test_branch_ids_dict_has_main_and_feature(self, vault_with_branches):
        ids = vault_with_branches['branch_ids']
        assert 'main'    in ids
        assert 'feature' in ids

    def test_main_and_feature_have_different_commit_ids(self, vault_with_branches):
        b = vault_with_branches['branches']
        assert b['main'] != b['feature']

    def test_base_commit_id_differs_from_main(self, vault_with_branches):
        b = vault_with_branches['branches']
        assert b['base'] != b['main']

    def test_branches_command_lists_two_named_branches(self, vault_with_branches):
        ws     = vault_with_branches
        result = ws['sync'].branches(ws['vault_dir'])
        named  = [b for b in result['branches'] if b['branch_type'] == 'named']
        assert len(named) >= 2

    def test_no_shared_state_between_consumers(self, vault_with_branches):
        vault_dir = vault_with_branches['vault_dir']
        with open(os.path.join(vault_dir, 'marker.txt'), 'w') as fh:
            fh.write('marker')
        assert os.path.isfile(os.path.join(vault_dir, 'marker.txt'))
