import pytest
from sgit_ai.safe_types.Safe_Str__Cache_Id import Safe_Str__Cache_Id


class Test_Safe_Str__Cache_Id:

    def test_accepts_snw(self):
        assert str(Safe_Str__Cache_Id('cch-pid-snw-4aa53f5467b6')) == 'cch-pid-snw-4aa53f5467b6'

    def test_accepts_muw(self):
        assert str(Safe_Str__Cache_Id('cch-pid-muw-4aa53f5467b6')) == 'cch-pid-muw-4aa53f5467b6'

    def test_lowercases(self):
        assert str(Safe_Str__Cache_Id('CCH-PID-SNW-4AA53F5467B6')) == 'cch-pid-snw-4aa53f5467b6'

    def test_rejects_wrong_prefix(self):
        with pytest.raises(Exception):
            Safe_Str__Cache_Id('idx-pid-muw-4aa53f5467b6')

    def test_rejects_bad_mutability(self):
        with pytest.raises(Exception):
            Safe_Str__Cache_Id('cch-pid-xyz-4aa53f5467b6')

    def test_rejects_short_tail(self):
        with pytest.raises(Exception):
            Safe_Str__Cache_Id('cch-pid-snw-4aa53f54')

    def test_rejects_non_hex_tail(self):
        with pytest.raises(Exception):
            Safe_Str__Cache_Id('cch-pid-snw-zzzzzzzzzzzz')

    def test_distinct_from_other_id_families(self):
        for foreign in ('obj-cas-imm-4aa53f5467b6', 'ref-pid-muw-4aa53f5467b6',
                        'idx-pid-muw-4aa53f5467b6', 'key-rnd-imm-4aa53f5467b6'):
            with pytest.raises(Exception):
                Safe_Str__Cache_Id(foreign)
