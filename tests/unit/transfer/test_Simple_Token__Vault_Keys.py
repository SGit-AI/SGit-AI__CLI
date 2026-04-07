from sgit_ai.transfer.Simple_Token             import Simple_Token
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token

TOKEN_CORAL = 'coral-equal-1234'
TOKEN_DAWN  = 'dawn-haven-1234'
TOKEN_AMBER = 'amber-fox-1234'


class Test_Simple_Token__Vault_Keys:

    def setup_method(self):
        self.st = Simple_Token(token=Safe_Str__Simple_Token(TOKEN_CORAL))

    # --- key length tests ---

    def test_read_key_length(self):
        assert len(self.st.read_key()) == 32

    def test_write_key_length(self):
        assert len(self.st.write_key()) == 32

    def test_ec_seed_length(self):
        assert len(self.st.ec_seed()) == 32

    # --- keys must all differ from each other ---

    def test_keys_differ(self):
        rk = self.st.read_key()
        wk = self.st.write_key()
        es = self.st.ec_seed()
        assert rk != wk
        assert rk != es
        assert wk != es

    # --- determinism ---

    def test_deterministic(self):
        st2 = Simple_Token(token=Safe_Str__Simple_Token(TOKEN_CORAL))
        assert self.st.read_key()  == st2.read_key()
        assert self.st.write_key() == st2.write_key()
        assert self.st.ec_seed()   == st2.ec_seed()

    # --- different tokens produce different keys ---

    def test_different_tokens_produce_different_keys(self):
        st2 = Simple_Token(token=Safe_Str__Simple_Token(TOKEN_DAWN))
        assert self.st.read_key()  != st2.read_key()
        assert self.st.write_key() != st2.write_key()
        assert self.st.ec_seed()   != st2.ec_seed()

    # --- is_simple_token validation ---

    def test_is_simple_token_valid(self):
        assert Simple_Token.is_simple_token(TOKEN_CORAL) is True
        assert Simple_Token.is_simple_token(TOKEN_DAWN)  is True
        assert Simple_Token.is_simple_token(TOKEN_AMBER) is True

    def test_is_simple_token_invalid(self):
        assert Simple_Token.is_simple_token('abc123')              is False
        assert Simple_Token.is_simple_token('my-project')          is False
        assert Simple_Token.is_simple_token('vault://foo')         is False
        assert Simple_Token.is_simple_token('coral-equal-12340')   is False  # 5 digits
        assert Simple_Token.is_simple_token('coral-equal-123')     is False  # 3 digits
        assert Simple_Token.is_simple_token('')                    is False

    # --- vault_id ---

    def test_vault_id_is_token(self):
        assert self.st.vault_id() == TOKEN_CORAL

    # --- HKDF output is bytes ---

    def test_read_key_is_bytes(self):
        assert isinstance(self.st.read_key(), bytes)

    def test_write_key_is_bytes(self):
        assert isinstance(self.st.write_key(), bytes)

    def test_ec_seed_is_bytes(self):
        assert isinstance(self.st.ec_seed(), bytes)
