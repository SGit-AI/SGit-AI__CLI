import pytest
import hashlib
from sgit_ai.safe_types.Safe_Str__SHA256 import Safe_Str__SHA256


class Test_Safe_Str__SHA256:

    def test_valid_hash(self):
        h = hashlib.sha256(b'test').hexdigest()
        sha = Safe_Str__SHA256(h)
        assert sha == h

    def test_uppercase_lowered(self):
        h = 'A' * 64
        sha = Safe_Str__SHA256(h)
        assert sha == 'a' * 64

    def test_empty_allowed(self):
        sha = Safe_Str__SHA256('')
        assert sha == ''

    def test_wrong_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__SHA256('abcd1234')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__SHA256('g' * 64)

    def test_real_sha256_round_trip(self):
        data = b'hello encrypted vault'
        h = hashlib.sha256(data).hexdigest()
        sha = Safe_Str__SHA256(h)
        assert sha == h
        assert len(sha) == 64

    def test_type_preserved(self):
        sha = Safe_Str__SHA256('a' * 64)
        assert type(sha).__name__ == 'Safe_Str__SHA256'
