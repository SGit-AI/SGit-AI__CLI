import pytest

from sgit_ai.safe_types.Safe_Str__CLI_Command_Label import Safe_Str__CLI_Command_Label


class Test_Safe_Str__CLI_Command_Label:

    def test_accepts_command_label_with_spaces(self):
        # The whole point: CLI command labels like 'sgit vault share' need spaces.
        # The other Safe_Str__* subclasses (Branch_Name, Vault_Id, ...) reject spaces.
        assert str(Safe_Str__CLI_Command_Label('sgit vault share')) == 'sgit vault share'

    def test_accepts_underscores_and_hyphens(self):
        assert str(Safe_Str__CLI_Command_Label('sgit vault show-key')) == 'sgit vault show-key'
        assert str(Safe_Str__CLI_Command_Label('share_command'))       == 'share_command'

    def test_rejects_disallowed_chars(self):
        with pytest.raises(Exception):
            Safe_Str__CLI_Command_Label('sgit vault export; rm -rf /')   # ; not allowed

    def test_rejects_overlength(self):
        with pytest.raises(Exception):
            Safe_Str__CLI_Command_Label('a' * 81)
