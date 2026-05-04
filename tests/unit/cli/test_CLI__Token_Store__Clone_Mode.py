"""Tests for CLI__Token_Store.load_clone_mode()."""
import json
import os
import tempfile
import shutil
from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
from sgit_ai.storage.Vault__Storage  import Vault__Storage


class Test_CLI__Token_Store__Clone_Mode:

    def setup_method(self):
        self.tmp_dir     = tempfile.mkdtemp()
        self.token_store = CLI__Token_Store()
        self.storage     = Vault__Storage()
        self.storage.create_bare_structure(self.tmp_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_clone_mode_default_is_full(self):
        result = self.token_store.load_clone_mode(self.tmp_dir)
        assert result == {'mode': 'full'}

    def test_load_clone_mode_reads_json(self):
        clone_mode = {'mode': 'read-only', 'vault_id': 'testvaultid', 'read_key': 'aabbccdd'}
        path = self.storage.clone_mode_path(self.tmp_dir)
        with open(path, 'w') as f:
            json.dump(clone_mode, f)
        result = self.token_store.load_clone_mode(self.tmp_dir)
        assert result['mode'] == 'read-only'
        assert result['vault_id'] == 'testvaultid'
        assert result['read_key'] == 'aabbccdd'

    def test_load_clone_mode_corrupted_file_returns_full(self):
        path = self.storage.clone_mode_path(self.tmp_dir)
        with open(path, 'w') as f:
            f.write('not valid json {{{')
        result = self.token_store.load_clone_mode(self.tmp_dir)
        assert result == {'mode': 'full'}

    def test_load_clone_mode_full_mode_explicit(self):
        clone_mode = {'mode': 'full', 'vault_id': 'fullvault'}
        path = self.storage.clone_mode_path(self.tmp_dir)
        with open(path, 'w') as f:
            json.dump(clone_mode, f)
        result = self.token_store.load_clone_mode(self.tmp_dir)
        assert result['mode'] == 'full'
