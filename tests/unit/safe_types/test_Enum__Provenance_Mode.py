from sg_send_cli.safe_types.Enum__Provenance_Mode import Enum__Provenance_Mode


class Test_Enum__Provenance_Mode:

    def test_mode_1(self):
        assert Enum__Provenance_Mode.MODE_1.value == 'mode_1'

    def test_mode_2(self):
        assert Enum__Provenance_Mode.MODE_2.value == 'mode_2'

    def test_mode_3(self):
        assert Enum__Provenance_Mode.MODE_3.value == 'mode_3'
