import pytest
from sg_send_cli.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path, VAULT_PATH__MAX_LENGTH


class Test_Safe_Str__Vault_Path__Boundary:

    def test_max_length_value(self):
        assert VAULT_PATH__MAX_LENGTH == 4096

    def test_at_max_length_accepted(self):
        path = Safe_Str__Vault_Path('a' * 4096)
        assert len(path) == 4096

    def test_exceeds_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Path('a' * 4097)

    def test_null_bytes_sanitized(self):
        path = Safe_Str__Vault_Path('/tmp/vault\x00/evil')
        assert '\x00' not in str(path)

    def test_semicolon_sanitized(self):
        path = Safe_Str__Vault_Path('/tmp;rm -rf /')
        assert ';' not in str(path)

    def test_pipe_sanitized(self):
        path = Safe_Str__Vault_Path('/tmp|cat /etc/passwd')
        assert '|' not in str(path)

    def test_backtick_sanitized(self):
        path = Safe_Str__Vault_Path('/tmp/`whoami`')
        assert '`' not in str(path)

    def test_dollar_sign_sanitized(self):
        path = Safe_Str__Vault_Path('/tmp/$HOME')
        assert '$' not in str(path)

    def test_dots_allowed(self):
        path = Safe_Str__Vault_Path('/tmp/.sg_vault')
        assert '.sg_vault' in str(path)

    def test_forward_slash_allowed(self):
        path = Safe_Str__Vault_Path('/tmp/vault/sub')
        assert '/' in str(path)

    def test_backslash_allowed(self):
        path = Safe_Str__Vault_Path('C:\\Users\\vault')
        assert '\\' in str(path)

    def test_spaces_allowed(self):
        path = Safe_Str__Vault_Path('/tmp/my vault')
        assert ' ' in str(path)

    def test_unicode_sanitized(self):
        path = Safe_Str__Vault_Path('/tmp/café')
        assert 'é' not in str(path)
