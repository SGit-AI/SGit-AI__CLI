import pytest

from sgit_ai.crypto.signing.SSH__Wire import SSH__Wire, Vault__SSH_Format_Error


class Test_SSH__Wire:

    def test_round_trips(self):
        w    = SSH__Wire()
        data = w.uint32(7) + w.string(b'abc') + w.mpint(0) + w.mpint(0x80) + w.mpint(2 ** 300 + 5)
        r    = SSH__Wire(data=data)
        assert (r.read_uint32(), r.read_string(), r.read_mpint(), r.read_mpint(), r.read_mpint()) == \
               (7, b'abc', 0, 0x80, 2 ** 300 + 5)
        assert r.at_end()
        assert w.mpint(0x80) == b'\x00\x00\x00\x02\x00\x80'                          # sign byte added

    def test_a_length_past_the_end_raises(self):
        with pytest.raises(Vault__SSH_Format_Error, match='truncated'):
            SSH__Wire(data=b'\x00\x00\x00\x09abc').read_string()
        with pytest.raises(Vault__SSH_Format_Error):
            SSH__Wire(data=b'\xff\xff\xff\xff').read_string()

    def test_a_negative_mpint_is_refused(self):
        with pytest.raises(Vault__SSH_Format_Error, match='negative'):
            SSH__Wire(data=b'\x00\x00\x00\x01\x80').read_mpint()

    def test_trailing_bytes_are_detected(self):
        wire = SSH__Wire(data=SSH__Wire().string(b'x') + b'!')
        wire.read_string()
        with pytest.raises(Vault__SSH_Format_Error, match='1 trailing byte'):
            wire.expect_end('thing')
