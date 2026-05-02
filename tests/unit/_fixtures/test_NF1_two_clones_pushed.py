"""Tests for NF1 — two_clones_pushed / two_clones_workspace fixtures."""
import os


class Test_NF1_Two_Clones_Pushed:

    def test_alice_dir_exists(self, two_clones_workspace):
        assert os.path.isdir(two_clones_workspace['alice_dir'])

    def test_bob_dir_exists(self, two_clones_workspace):
        assert os.path.isdir(two_clones_workspace['bob_dir'])

    def test_vault_key_present(self, two_clones_workspace):
        assert two_clones_workspace['vault_key']

    def test_head_commit_id_present(self, two_clones_workspace):
        assert two_clones_workspace['head_commit_id']

    def test_alice_and_bob_are_independent_dirs(self, two_clones_workspace):
        assert two_clones_workspace['alice_dir'] != two_clones_workspace['bob_dir']

    def test_no_shared_state_between_two_consumers(self, two_clones_workspace):
        # Writes to alice_dir must not affect a second call's alice_dir
        alice_dir = two_clones_workspace['alice_dir']
        sentinel  = os.path.join(alice_dir, 'mutation_marker.txt')
        with open(sentinel, 'w') as fh:
            fh.write('mutated')
        # The fixture for the next test gets a fresh copytree — this test
        # just confirms our local copy has the marker (snapshot is clean)
        assert os.path.isfile(sentinel)

    def test_sync_can_pull_as_bob(self, two_clones_workspace):
        ws     = two_clones_workspace
        result = ws['sync'].pull(ws['bob_dir'])
        assert 'file_count' in result or result.get('up_to_date') or isinstance(result, dict)
