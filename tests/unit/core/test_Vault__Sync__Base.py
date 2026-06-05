"""Tests for Vault__Sync__Base._derive_keys_for_directory (architect contract §4 / §7.1).

The shared key-derivation helper is the single source of truth for the clone-mode
dispatch (§4.2). It returns:
  - the import_read_key() shape       for read-only clones
  - the derive_keys_from_vault_key()  shape for full clones
and raises Vault__Clone_Mode_Corrupt_Error for a corrupt clone_mode.json.
"""
import json
import os

import pytest

from sgit_ai.core.Vault__Errors import Vault__Clone_Mode_Corrupt_Error


class Test_Vault__Sync__Base___derive_keys_for_directory:

    # -- (a) read-only clone returns the import_read_key shape ---------------

    def test_read_only_clone_returns_import_read_key_shape(self, read_only_clone):
        sync = read_only_clone['sync']
        keys = sync._derive_keys_for_directory(read_only_clone['ro_dir'])
        assert keys['vault_id']        == read_only_clone['vault_id']
        assert keys['read_key']        == read_only_clone['read_key_hex']
        assert keys['write_key']       == ''                    # no write key on RO
        assert keys['write_key_bytes'] is None
        assert isinstance(keys['read_key_bytes'], bytes)
        assert keys['ref_file_id']
        assert keys['branch_index_file_id']

    def test_read_only_clone_does_not_read_vault_key(self, read_only_clone):
        """Regression: helper must not require a vault_key file on an RO clone."""
        ro_dir   = read_only_clone['ro_dir']
        vk_path  = os.path.join(ro_dir, '.sg_vault', 'local', 'vault_key')
        assert not os.path.isfile(vk_path)
        keys = read_only_clone['sync']._derive_keys_for_directory(ro_dir)   # must not raise
        assert keys['read_key'] == read_only_clone['read_key_hex']

    # -- (b) full clone returns the derive_keys_from_vault_key shape ---------

    def test_full_clone_returns_vault_key_shape(self, two_clones_workspace):
        sync = two_clones_workspace['sync']
        keys = sync._derive_keys_for_directory(two_clones_workspace['bob_dir'])
        assert keys['vault_id']
        assert keys['read_key']
        assert keys['write_key']                                # full clone has a write key
        assert isinstance(keys['read_key_bytes'], bytes)

    def test_full_clone_matches_direct_derivation(self, two_clones_workspace):
        sync      = two_clones_workspace['sync']
        crypto    = two_clones_workspace['crypto']
        vault_key = two_clones_workspace['vault_key']
        expected  = crypto.derive_keys_from_vault_key(vault_key)
        keys      = sync._derive_keys_for_directory(two_clones_workspace['bob_dir'])
        assert keys['vault_id']             == expected['vault_id']
        assert keys['read_key']             == expected['read_key']
        assert keys['branch_index_file_id'] == expected['branch_index_file_id']

    # -- (c) corrupt clone_mode.json raises ---------------------------------

    def test_corrupt_clone_mode_unparseable_raises(self, read_only_clone):
        cm_path = os.path.join(read_only_clone['ro_dir'], '.sg_vault', 'local', 'clone_mode.json')
        with open(cm_path, 'w') as f:
            f.write('{ this is not valid json ]')
        with pytest.raises(Vault__Clone_Mode_Corrupt_Error):
            read_only_clone['sync']._derive_keys_for_directory(read_only_clone['ro_dir'])

    def test_corrupt_clone_mode_missing_read_key_raises(self, read_only_clone):
        cm_path = os.path.join(read_only_clone['ro_dir'], '.sg_vault', 'local', 'clone_mode.json')
        with open(cm_path, 'w') as f:
            json.dump({'mode': 'read-only', 'vault_id': read_only_clone['vault_id']}, f)
        with pytest.raises(Vault__Clone_Mode_Corrupt_Error):
            read_only_clone['sync']._derive_keys_for_directory(read_only_clone['ro_dir'])

    def test_corrupt_clone_mode_missing_vault_id_raises(self, read_only_clone):
        cm_path = os.path.join(read_only_clone['ro_dir'], '.sg_vault', 'local', 'clone_mode.json')
        with open(cm_path, 'w') as f:
            json.dump({'mode': 'read-only', 'read_key': read_only_clone['read_key_hex']}, f)
        with pytest.raises(Vault__Clone_Mode_Corrupt_Error):
            read_only_clone['sync']._derive_keys_for_directory(read_only_clone['ro_dir'])
