"""Unit tests for CLI__Token_Store.

Covers resolve_token, resolve_base_url, save/load token/base_url/vault_key
and all edge cases (no directory, missing .sg_vault dir, legacy fallback).
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store


class Test_CLI__Token_Store:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        # Create a minimal .sg_vault structure so save_token/save_base_url work
        self.sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(self.sg_dir, exist_ok=True)
        self.store    = CLI__Token_Store()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # resolve_token
    # ------------------------------------------------------------------

    def test_resolve_token_with_token_and_directory_saves_and_returns(self):
        """When token + directory are given, token is saved and returned."""
        result = self.store.resolve_token('mytoken', self.tmp_dir)
        assert result == 'mytoken'
        # Token should be persisted
        assert self.store.load_token(self.tmp_dir) == 'mytoken'

    def test_resolve_token_no_directory_returns_token(self):
        """When directory is None/empty, token is still returned (not saved)."""
        result = self.store.resolve_token('tok', None)
        assert result == 'tok'

    def test_resolve_token_no_token_no_directory_returns_empty(self):
        """When both are missing, returns ''."""
        result = self.store.resolve_token(None, None)
        assert result == ''

    def test_resolve_token_no_token_loads_from_directory(self):
        """When token is None, loads from directory."""
        self.store.save_token('saved-tok', self.tmp_dir)
        result = self.store.resolve_token(None, self.tmp_dir)
        assert result == 'saved-tok'

    # ------------------------------------------------------------------
    # save_token / load_token edge cases
    # ------------------------------------------------------------------

    def test_save_token_no_directory_returns_early(self):
        """save_token with empty directory does nothing without error."""
        self.store.save_token('tok', '')   # should not raise

    def test_save_token_no_sg_vault_dir_returns_early(self):
        """save_token when .sg_vault does not exist does nothing."""
        bare_dir = os.path.join(self.tmp_dir, 'bare-dir')
        os.makedirs(bare_dir)
        self.store.save_token('tok', bare_dir)   # should not raise

    def test_load_token_no_directory_returns_empty(self):
        """load_token with empty directory returns ''."""
        result = self.store.load_token(None)
        assert result == ''

    def test_load_token_legacy_fallback(self):
        """load_token falls back to .sg_vault/token when local/ version absent."""
        legacy_path = os.path.join(self.sg_dir, 'token')
        with open(legacy_path, 'w') as f:
            f.write('legacy-token')
        result = self.store.load_token(self.tmp_dir)
        assert result == 'legacy-token'

    def test_load_token_primary_takes_precedence_over_legacy(self):
        """Primary token path wins over the legacy fallback."""
        # Write legacy
        with open(os.path.join(self.sg_dir, 'token'), 'w') as f:
            f.write('legacy-tok')
        # Write primary (local/)
        self.store.save_token('primary-tok', self.tmp_dir)
        result = self.store.load_token(self.tmp_dir)
        assert result == 'primary-tok'

    def test_load_token_no_file_returns_empty(self):
        """load_token returns '' when no token file exists."""
        result = self.store.load_token(self.tmp_dir)
        assert result == ''

    # ------------------------------------------------------------------
    # save_base_url / load_base_url
    # ------------------------------------------------------------------

    def test_save_base_url_and_load(self):
        """save then load round-trips the base_url."""
        self.store.save_base_url('https://example.com', self.tmp_dir)
        result = self.store.load_base_url(self.tmp_dir)
        assert result == 'https://example.com'

    def test_save_base_url_no_directory_returns_early(self):
        """save_base_url with empty directory does nothing."""
        self.store.save_base_url('https://x.com', '')   # should not raise

    def test_save_base_url_no_base_url_returns_early(self):
        """save_base_url with empty base_url does nothing."""
        self.store.save_base_url('', self.tmp_dir)   # should not raise

    def test_save_base_url_no_sg_vault_dir_returns_early(self):
        """save_base_url when .sg_vault does not exist does nothing."""
        bare_dir = os.path.join(self.tmp_dir, 'bare-dir2')
        os.makedirs(bare_dir)
        self.store.save_base_url('https://x.com', bare_dir)   # should not raise

    def test_load_base_url_no_directory_returns_empty(self):
        """load_base_url with no directory returns ''."""
        result = self.store.load_base_url(None)
        assert result == ''

    def test_load_base_url_primary_path(self):
        """load_base_url reads from local/base_url (primary path)."""
        self.store.save_base_url('https://api.example.com', self.tmp_dir)
        result = self.store.load_base_url(self.tmp_dir)
        assert 'api.example.com' in result

    def test_load_base_url_legacy_fallback(self):
        """load_base_url falls back to .sg_vault/base_url when local/ absent."""
        legacy_path = os.path.join(self.sg_dir, 'base_url')
        with open(legacy_path, 'w') as f:
            f.write('https://legacy.example.com')
        result = self.store.load_base_url(self.tmp_dir)
        assert result == 'https://legacy.example.com'

    def test_load_base_url_no_file_returns_empty(self):
        """load_base_url returns '' when no file exists."""
        result = self.store.load_base_url(self.tmp_dir)
        assert result == ''

    # ------------------------------------------------------------------
    # resolve_base_url
    # ------------------------------------------------------------------

    def test_resolve_base_url_with_url_and_directory_saves_and_returns(self):
        """When base_url + directory are given, it is saved and returned."""
        result = self.store.resolve_base_url('https://x.com', self.tmp_dir)
        assert result == 'https://x.com'
        assert self.store.load_base_url(self.tmp_dir) == 'https://x.com'

    def test_resolve_base_url_no_directory_returns_url(self):
        """When directory is None/empty, url is still returned."""
        result = self.store.resolve_base_url('https://x.com', None)
        assert result == 'https://x.com'

    def test_resolve_base_url_no_url_no_directory_returns_empty(self):
        """When both are missing, returns ''."""
        result = self.store.resolve_base_url(None, None)
        assert result == ''

    # ------------------------------------------------------------------
    # load_vault_key
    # ------------------------------------------------------------------

    def test_load_vault_key_no_directory_returns_empty(self):
        """load_vault_key with no directory returns ''."""
        result = self.store.load_vault_key(None)
        assert result == ''

    def test_load_vault_key_from_local_dir(self, tmp_path):
        """load_vault_key reads from .sg_vault/local/vault_key."""
        local_dir = tmp_path / '.sg_vault' / 'local'
        local_dir.mkdir(parents=True)
        (local_dir / 'vault_key').write_text('my-vault-key:abcd1234')
        result = self.store.load_vault_key(str(tmp_path))
        assert result == 'my-vault-key:abcd1234'

    def test_load_vault_key_no_file_returns_empty(self):
        """load_vault_key returns '' when no vault_key file exists."""
        result = self.store.load_vault_key(self.tmp_dir)
        assert result == ''

    # ------------------------------------------------------------------
    # resolve_read_key
    # ------------------------------------------------------------------

    def test_resolve_read_key_from_vault_key_arg(self, tmp_path):
        """When args.vault_key is set, resolve_read_key returns bytes."""
        import types
        # Use a hardcoded test vault key (passphrase:vault_id format)
        vault_key = 'test-passphrase:testvaultid12345678'
        args      = types.SimpleNamespace(vault_key=vault_key, directory=str(tmp_path))
        result    = self.store.resolve_read_key(args)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_resolve_read_key_no_vault_key_returns_none(self, tmp_path):
        """When no vault_key and no file, returns None."""
        import types
        args   = types.SimpleNamespace(vault_key=None, directory=str(tmp_path))
        result = self.store.resolve_read_key(args)
        assert result is None
