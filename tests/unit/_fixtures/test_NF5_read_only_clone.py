"""Tests for NF5 — read_only_clone fixture."""
import json
import os


class Test_NF5_Read_Only_Clone:

    def test_ro_dir_exists(self, read_only_clone):
        assert os.path.isdir(read_only_clone['ro_dir'])

    def test_vault_id_present(self, read_only_clone):
        assert read_only_clone['vault_id']

    def test_read_key_hex_present(self, read_only_clone):
        assert read_only_clone['read_key_hex']

    def test_clone_mode_is_read_only(self, read_only_clone):
        sg_dir = os.path.join(read_only_clone['ro_dir'], '.sg_vault')
        clone_mode_path = os.path.join(sg_dir, 'local', 'clone_mode.json')
        assert os.path.isfile(clone_mode_path), f'clone_mode.json missing at {clone_mode_path}'
        data = json.loads(open(clone_mode_path).read())
        assert data.get('mode') == 'read-only'

    def test_no_write_key_in_clone_mode(self, read_only_clone):
        sg_dir = os.path.join(read_only_clone['ro_dir'], '.sg_vault')
        clone_mode_path = os.path.join(sg_dir, 'local', 'clone_mode.json')
        data = json.loads(open(clone_mode_path).read())
        assert 'write_key' not in data

    def test_data_file_checked_out(self, read_only_clone):
        data_path = os.path.join(read_only_clone['ro_dir'], 'data.txt')
        assert os.path.isfile(data_path)
        assert open(data_path).read() == 'read-only data'

    def test_no_shared_state_between_consumers(self, read_only_clone):
        ro_dir = read_only_clone['ro_dir']
        with open(os.path.join(ro_dir, 'marker.txt'), 'w') as fh:
            fh.write('marker')
        assert os.path.isfile(os.path.join(ro_dir, 'marker.txt'))
