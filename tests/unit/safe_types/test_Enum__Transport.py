from sgit_ai.safe_types.Enum__Transport         import Enum__Transport
from sgit_ai.safe_types.Enum__Published_Layout  import Enum__Published_Layout


class Test_Enum__Transport:

    def test_members(self):
        assert Enum__Transport.AUTO.value   == 'auto'
        assert Enum__Transport.API.value    == 'api'
        assert Enum__Transport.STATIC.value == 'static'
        assert Enum__Transport.LOCAL.value  == 'local'
        assert len(Enum__Transport) == 4

    def test_lookup_by_value(self):
        assert Enum__Transport('static') is Enum__Transport.STATIC


class Test_Enum__Published_Layout:

    def test_members(self):
        assert Enum__Published_Layout.API_PATH.value == 'api-path'
        assert Enum__Published_Layout.FLAT.value     == 'flat'
        assert len(Enum__Published_Layout) == 2

    def test_lookup_by_value(self):
        assert Enum__Published_Layout('api-path') is Enum__Published_Layout.API_PATH
