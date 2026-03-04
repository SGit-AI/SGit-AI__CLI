import pytest
from sg_send_cli.safe_types.Safe_Str__Write_Key import Safe_Str__Write_Key


class Test_Safe_Str__Write_Key:

    def test_valid_write_key(self):
        key = Safe_Str__Write_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e')
        assert key == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'

    def test_empty_allowed(self):
        key = Safe_Str__Write_Key('')
        assert key == ''

    def test_uppercase_converted_to_lower(self):
        key = Safe_Str__Write_Key('3181D6650958B51FD00F913F6290ECA22E6B09DA661C8E831FC89FE659DF378E')
        assert key == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'

    def test_too_short_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Write_Key('3181d665')

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Write_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e00')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Write_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378z')

    def test_type_preserved(self):
        key = Safe_Str__Write_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e')
        assert type(key).__name__ == 'Safe_Str__Write_Key'
