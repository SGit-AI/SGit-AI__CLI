"""Tests for NF2 — vault_with_N_commits fixture."""
import os


class Test_NF2_Vault_With_N_Commits:

    def test_n1_vault_dir_exists(self, vault_with_N_commits):
        ws = vault_with_N_commits(1)
        assert os.path.isdir(ws['vault_dir'])

    def test_n1_has_one_file(self, vault_with_N_commits):
        ws    = vault_with_N_commits(1)
        files = [f for f in os.listdir(ws['vault_dir']) if f.startswith('file_')]
        assert len(files) == 1
        assert files[0] == 'file_1.txt'

    def test_n5_has_five_files(self, vault_with_N_commits):
        ws    = vault_with_N_commits(5)
        files = sorted(f for f in os.listdir(ws['vault_dir']) if f.startswith('file_'))
        assert len(files) == 5

    def test_n20_has_twenty_files(self, vault_with_N_commits):
        ws    = vault_with_N_commits(20)
        files = [f for f in os.listdir(ws['vault_dir']) if f.startswith('file_')]
        assert len(files) == 20

    def test_file_content_is_deterministic(self, vault_with_N_commits):
        ws   = vault_with_N_commits(5)
        path = os.path.join(ws['vault_dir'], 'file_3.txt')
        assert open(path).read() == 'commit-3-content'

    def test_invalid_n_raises_key_error(self, vault_with_N_commits):
        try:
            vault_with_N_commits(99)
            assert False, 'Expected KeyError'
        except KeyError:
            pass

    def test_two_calls_return_independent_dirs(self, vault_with_N_commits):
        ws1 = vault_with_N_commits(1)
        ws2 = vault_with_N_commits(1)
        assert ws1['vault_dir'] != ws2['vault_dir']
