"""Safe types and enums introduced by the static-publishing pack."""
import pytest

from sgit_ai.safe_types.Enum__Api_Docs_Mode           import Enum__Api_Docs_Mode
from sgit_ai.safe_types.Enum__Visibility              import Enum__Visibility
from sgit_ai.safe_types.Safe_Str__Bind_Address        import Safe_Str__Bind_Address
from sgit_ai.safe_types.Safe_Str__Cover_Text          import Safe_Str__Cover_Text
from sgit_ai.safe_types.Safe_Str__Published_File_Id   import Safe_Str__Published_File_Id
from sgit_ai.safe_types.Safe_Str__SHA256              import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_UInt__Port               import Safe_UInt__Port


class Test_Enum__Visibility:

    def test_members(self):
        assert [v.value for v in Enum__Visibility] == ['bare', 'named', 'public']
        assert Enum__Visibility('public') is Enum__Visibility.PUBLIC


class Test_Enum__Api_Docs_Mode:

    def test_members(self):
        assert [v.value for v in Enum__Api_Docs_Mode] == ['cdn', 'bundled']
        assert Enum__Api_Docs_Mode('cdn') is Enum__Api_Docs_Mode.CDN


class Test_Safe_Str__SHA256:

    def test_valid_hash(self):
        assert str(Safe_Str__SHA256('a' * 64)) == 'a' * 64

    def test_uppercase_lowered(self):
        assert str(Safe_Str__SHA256('A' * 64)) == 'a' * 64

    def test_wrong_length_rejected(self):
        with pytest.raises(Exception):
            Safe_Str__SHA256('a' * 63)

    def test_non_hex_rejected(self):
        with pytest.raises(Exception):
            Safe_Str__SHA256('g' * 64)


class Test_Safe_Str__Published_File_Id:

    def test_wire_paths_pass(self):
        value = 'bare/refs/ref-pid-muw-1995ccf51fe8'
        assert str(Safe_Str__Published_File_Id(value)) == value

    def test_hostile_characters_stripped(self):
        assert '\x00' not in str(Safe_Str__Published_File_Id('bare/data/x\x00y'))
        assert ' '    not in str(Safe_Str__Published_File_Id('bare/da ta'))

    def test_traversal_shape_survives_for_the_guard_to_refuse(self):
        # The type constrains the alphabet; Vault__Path_Guard owns topology.
        assert str(Safe_Str__Published_File_Id('../../etc/cron.d/x')) == '../../etc/cron.d/x'


class Test_Safe_Str__Cover_Text:

    def test_email_and_url_shapes_survive(self):
        assert str(Safe_Str__Cover_Text('ir@example.com'))        == 'ir@example.com'
        assert str(Safe_Str__Cover_Text('https://example.com/x')) == 'https://example.com/x'

    def test_markup_is_stripped(self):
        cleaned = str(Safe_Str__Cover_Text('<script>alert("x")</script>'))
        assert '<' not in cleaned and '>' not in cleaned and '"' not in cleaned


class Test_Safe_UInt__Port:

    def test_bounds(self):
        assert int(Safe_UInt__Port(0))     == 0
        assert int(Safe_UInt__Port(65535)) == 65535
        with pytest.raises(Exception):
            Safe_UInt__Port(65536)
        with pytest.raises(Exception):
            Safe_UInt__Port(-1)


class Test_Safe_Str__Bind_Address:

    def test_addresses_pass(self):
        assert str(Safe_Str__Bind_Address('127.0.0.1')) == '127.0.0.1'
        assert str(Safe_Str__Bind_Address('0.0.0.0'))   == '0.0.0.0'
        assert str(Safe_Str__Bind_Address('[::1]'))     == '[::1]'

    def test_hostile_characters_stripped(self):
        assert ';' not in str(Safe_Str__Bind_Address('127.0.0.1;rm'))
