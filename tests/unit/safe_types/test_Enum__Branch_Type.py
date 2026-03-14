from sg_send_cli.safe_types.Enum__Branch_Type import Enum__Branch_Type


class Test_Enum__Branch_Type:

    def test_named(self):
        assert Enum__Branch_Type.NAMED.value == 'named'

    def test_clone(self):
        assert Enum__Branch_Type.CLONE.value == 'clone'
