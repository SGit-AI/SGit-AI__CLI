import pytest
from sg_send_cli.safe_types.Safe_Str__PEM_Key import Safe_Str__PEM_Key


class Test_Safe_Str__PEM_Key:

    def test_valid_pem(self):
        pem = '-----BEGIN PUBLIC KEY-----\nMIIBIjANBg==\n-----END PUBLIC KEY-----'
        key = Safe_Str__PEM_Key(pem)
        assert key == pem

    def test_empty_allowed(self):
        key = Safe_Str__PEM_Key('')
        assert key == ''

    def test_simple_string(self):
        key = Safe_Str__PEM_Key('pem-data-1')
        assert key == 'pem-data-1'

    def test_multiline_pem(self):
        pem = '-----BEGIN PUBLIC KEY-----\nline1\nline2\nline3\n-----END PUBLIC KEY-----'
        key = Safe_Str__PEM_Key(pem)
        assert key == pem

    def test_type_preserved(self):
        key = Safe_Str__PEM_Key('test-pem')
        assert type(key).__name__ == 'Safe_Str__PEM_Key'
