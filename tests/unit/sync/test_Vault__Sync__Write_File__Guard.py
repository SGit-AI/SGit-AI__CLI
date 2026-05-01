"""Tests for the read-only guard on Vault__Sync.write_file().

Covers:
  1. Read-only clone → write_file raises Vault__Read_Only_Error.
  2. Corrupt clone_mode.json (invalid JSON) → write_file raises Vault__Clone_Mode_Corrupt_Error.
  3. clone_mode.json with missing required fields → raises Vault__Clone_Mode_Corrupt_Error.
  4. Full-mode (normal) vault → write_file still works correctly.
"""
import json
import os

import pytest

from sgit_ai.sync.Vault__Errors import Vault__Read_Only_Error, Vault__Clone_Mode_Corrupt_Error
from sgit_ai.sync.Vault__Storage import Vault__Storage
from tests.unit.sync.vault_test_env import Vault__Test_Env


class Test_Vault__Write_File__Read_Only_Guard:
    """Guard tests for write_file — read-only clone path."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'README.md': 'initial content'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir
        self.storage   = Vault__Storage()

    def teardown_method(self):
        self.env.cleanup()

    # ------------------------------------------------------------------ #
    # Test 1: read-only clone raises Vault__Read_Only_Error
    # ------------------------------------------------------------------ #

    def test_write_file_raises_on_read_only_clone(self):
        """A vault with clone_mode.json mode=read-only must not accept writes."""
        # Simulate a read-only clone by writing clone_mode.json.
        # The read_key value must be valid hex (64 hex chars = 32 bytes).
        read_key_hex = 'aa' * 32   # 64 hex chars
        clone_mode   = {'mode': 'read-only', 'vault_id': 'testvault1', 'read_key': read_key_hex}
        mode_path    = self.storage.clone_mode_path(self.directory)
        with open(mode_path, 'w') as f:
            json.dump(clone_mode, f)

        with pytest.raises(Vault__Read_Only_Error):
            self.sync.write_file(self.directory, 'blocked.md', b'should not write')

    # ------------------------------------------------------------------ #
    # Test 2: corrupt clone_mode.json (invalid JSON) raises before write
    # ------------------------------------------------------------------ #

    def test_write_file_raises_on_corrupt_clone_mode_invalid_json(self):
        """A vault with an unparseable clone_mode.json must fail-closed."""
        mode_path = self.storage.clone_mode_path(self.directory)
        with open(mode_path, 'w') as f:
            f.write('{not valid json !!!}')

        with pytest.raises(Vault__Clone_Mode_Corrupt_Error):
            self.sync.write_file(self.directory, 'blocked.md', b'should not write')

    # ------------------------------------------------------------------ #
    # Test 3: clone_mode.json present but missing required fields
    # ------------------------------------------------------------------ #

    def test_write_file_raises_on_clone_mode_missing_fields(self):
        """clone_mode.json with mode=read-only but no read_key/vault_id must fail-closed."""
        mode_path  = self.storage.clone_mode_path(self.directory)
        clone_mode = {'mode': 'read-only'}   # missing read_key and vault_id
        with open(mode_path, 'w') as f:
            json.dump(clone_mode, f)

        with pytest.raises(Vault__Clone_Mode_Corrupt_Error):
            self.sync.write_file(self.directory, 'blocked.md', b'should not write')

    # ------------------------------------------------------------------ #
    # Test 4: full-mode vault (no clone_mode.json) still writes normally
    # ------------------------------------------------------------------ #

    def test_write_file_succeeds_in_full_mode_vault(self):
        """A normal (full) vault with a write_key must continue to work."""
        # No clone_mode.json → full mode → write_key present → success.
        result = self.sync.write_file(self.directory, 'hello.md', b'hello world')
        assert result['unchanged'] is False
        assert result['blob_id'].startswith('obj-cas-imm-')
        assert 'hello.md' in result['paths']

    # ------------------------------------------------------------------ #
    # Test 5: error class has expected message substring
    # ------------------------------------------------------------------ #

    def test_read_only_error_message_is_descriptive(self):
        """Vault__Read_Only_Error message must mention 'read-only'."""
        err = Vault__Read_Only_Error()
        assert 'read-only' in str(err)

    # ------------------------------------------------------------------ #
    # Test 6: corrupt error class has expected message substring
    # ------------------------------------------------------------------ #

    def test_clone_mode_corrupt_error_message_is_descriptive(self):
        """Vault__Clone_Mode_Corrupt_Error message must mention 'clone_mode.json'."""
        err = Vault__Clone_Mode_Corrupt_Error()
        assert 'clone_mode.json' in str(err)

    # ------------------------------------------------------------------ #
    # Test 7: guard raises before any disk write (no partial side-effect)
    # ------------------------------------------------------------------ #

    def test_write_file_guard_leaves_no_partial_file(self):
        """When the guard fires, no target file must appear on disk."""
        read_key_hex = 'bb' * 32
        clone_mode   = {'mode': 'read-only', 'vault_id': 'testvault2', 'read_key': read_key_hex}
        mode_path    = self.storage.clone_mode_path(self.directory)
        with open(mode_path, 'w') as f:
            json.dump(clone_mode, f)

        target = os.path.join(self.directory, 'never_written.md')
        assert not os.path.exists(target)

        with pytest.raises(Vault__Read_Only_Error):
            self.sync.write_file(self.directory, 'never_written.md', b'secret')

        assert not os.path.exists(target)
