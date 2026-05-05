import pytest
from sgit_ai.safe_types.Safe_Str__Read_Key  import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Write_Key import Safe_Str__Write_Key


class Test_Safe_Str__Read_Key:

    def test_valid_read_key(self):
        key = Safe_Str__Read_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e')
        assert key == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'

    def test_empty_allowed(self):
        assert Safe_Str__Read_Key('') == ''

    def test_uppercase_converted_to_lower(self):
        key = Safe_Str__Read_Key('3181D6650958B51FD00F913F6290ECA22E6B09DA661C8E831FC89FE659DF378E')
        assert key == '3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e'

    def test_too_short_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Read_Key('3181d665')

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Read_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378e00')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Read_Key('3181d6650958b51fd00f913f6290eca22e6b09da661c8e831fc89fe659df378z')

    def test_type_is_distinct_from_write_key(self):
        """Read and write key are different types despite same format."""
        read_key  = Safe_Str__Read_Key('aa' * 32)
        write_key = Safe_Str__Write_Key('aa' * 32)
        assert type(read_key)  is Safe_Str__Read_Key
        assert type(write_key) is Safe_Str__Write_Key
        assert type(read_key)  is not type(write_key)
