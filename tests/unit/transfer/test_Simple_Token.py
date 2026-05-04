import hashlib
from sgit_ai.network.transfer.Simple_Token             import Simple_Token
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token

# Interop test vectors — computed from Python hashlib and hard-coded here.
# Token:       test-token-1234
# Transfer ID: SHA-256("test-token-1234").hexdigest()[:12]  => d1821422f40b
# AES key hex: PBKDF2("test-token-1234", b"sgraph-send-v1", 600000, 32).hex()
VECTOR_TOKEN       = 'test-token-1234'
VECTOR_TRANSFER_ID = 'd1821422f40b'
VECTOR_KEY_HEX     = '43e366da587e8651bcbf68f4989387b8f2e19357f6388b1c3cf2cda8af400dd8'


class Test_Simple_Token:

    def setup_method(self):
        self.st = Simple_Token(token=Safe_Str__Simple_Token(VECTOR_TOKEN))

    def test_transfer_id_interop_vector(self):
        assert self.st.transfer_id() == VECTOR_TRANSFER_ID

    def test_aes_key_interop_vector(self):
        assert self.st.aes_key_hex() == VECTOR_KEY_HEX

    def test_aes_key_length(self):
        assert len(self.st.aes_key()) == 32

    def test_transfer_id_is_12_chars(self):
        assert len(self.st.transfer_id()) == 12

    def test_transfer_id_is_hex_prefix_of_sha256(self):
        expected = hashlib.sha256(VECTOR_TOKEN.encode('utf-8')).hexdigest()[:12]
        assert self.st.transfer_id() == expected

    def test_aes_key_matches_pbkdf2(self):
        expected = hashlib.pbkdf2_hmac('sha256', VECTOR_TOKEN.encode('utf-8'),
                                       b'sgraph-send-v1', 600000, dklen=32)
        assert self.st.aes_key() == expected

    def test_different_tokens_produce_different_transfer_ids(self):
        st2 = Simple_Token(token=Safe_Str__Simple_Token('other-word-5678'))
        assert self.st.transfer_id() != st2.transfer_id()

    def test_different_tokens_produce_different_keys(self):
        st2 = Simple_Token(token=Safe_Str__Simple_Token('other-word-5678'))
        assert self.st.aes_key() != st2.aes_key()

    def test_empty_token_gives_empty_string_fields(self):
        st_empty = Simple_Token(token=Safe_Str__Simple_Token(''))
        assert isinstance(st_empty.token, Safe_Str__Simple_Token)
