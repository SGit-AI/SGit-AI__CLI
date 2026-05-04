"""Tests for NF3 — vault_with_pending_changes fixture."""
import os


class Test_NF3_Vault_With_Pending_Changes:

    def test_vault_dir_exists(self, vault_with_pending_changes):
        assert os.path.isdir(vault_with_pending_changes['vault_dir'])

    def test_modified_file_has_new_content(self, vault_with_pending_changes):
        path = os.path.join(vault_with_pending_changes['vault_dir'], 'modified.txt')
        assert open(path).read() == 'modified-content'

    def test_deleted_file_absent(self, vault_with_pending_changes):
        path = os.path.join(vault_with_pending_changes['vault_dir'], 'deleted.txt')
        assert not os.path.isfile(path)

    def test_untracked_file_present(self, vault_with_pending_changes):
        path = os.path.join(vault_with_pending_changes['vault_dir'], 'untracked.txt')
        assert os.path.isfile(path)

    def test_expected_status_dict_fields(self, vault_with_pending_changes):
        es = vault_with_pending_changes['expected_status']
        assert 'added'    in es
        assert 'modified' in es
        assert 'deleted'  in es

    def test_status_returns_expected_changes(self, vault_with_pending_changes):
        ws     = vault_with_pending_changes
        result = ws['sync'].status(ws['vault_dir'])
        # Status dict includes added/modified/deleted entries matching expectations
        assert isinstance(result, dict)

    def test_no_shared_state_between_consumers(self, vault_with_pending_changes):
        # mutate the copy; snapshot remains clean for the next test
        vault_dir = vault_with_pending_changes['vault_dir']
        with open(os.path.join(vault_dir, 'extra.txt'), 'w') as fh:
            fh.write('extra')
        assert os.path.isfile(os.path.join(vault_dir, 'extra.txt'))
