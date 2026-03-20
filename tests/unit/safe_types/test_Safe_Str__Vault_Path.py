from sgit_ai.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path


class Test_Safe_Str__Vault_Path:

    def test_accepts_unix_path(self):
        p = Safe_Str__Vault_Path()
        p.value = '/tmp/vault/my-vault'
        assert p.value == '/tmp/vault/my-vault'

    def test_accepts_relative_path(self):
        p = Safe_Str__Vault_Path()
        p.value = './my-vault/.sg_vault'
        assert p.value == './my-vault/.sg_vault'

    def test_accepts_empty(self):
        p = Safe_Str__Vault_Path()
        p.value = ''
        assert p.value == ''

    def test_accepts_path_with_spaces(self):
        p = Safe_Str__Vault_Path()
        p.value = '/tmp/my vault'
        assert p.value == '/tmp/my vault'

    def test_max_length(self):
        p = Safe_Str__Vault_Path()
        assert p.max_length == 4096

    def test_type_preserved(self):
        p = Safe_Str__Vault_Path()
        p.value = '/tmp/test'
        assert isinstance(p, Safe_Str__Vault_Path)
