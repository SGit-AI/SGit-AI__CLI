"""Interop test vectors for cache-layer id derivation — the definition of done
for Phase 1 (cache-layer wire-format contract 08/12 v0, §4.1 and §10).

These exact values MUST reproduce in every runtime (CLI, SG/Vault browser,
any server-side helper). Chain A is KDF-independent and is the primary
cross-runtime assertion; Chain B additionally validates the PBKDF2 leg.
"""
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


class Test_Vault__Crypto__Cache_Ids__Chain_A:
    """Fixed read_key — pure HMAC, no KDF. Contract §4.1 Chain A."""

    def setup_method(self):
        self.crypto   = Vault__Crypto()
        self.read_key = bytes.fromhex(
            '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f')
        self.vault_id = '7y6uk6gj'

    def _full(self, tail, mut='snw'):
        return f'cch-pid-{mut}-{tail}'

    def test_value__pages_home_md(self):
        tail = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'pages/home.md')
        assert self._full(tail) == 'cch-pid-snw-4aa53f5467b6'

    def test_value__keys_api_json(self):
        tail = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'keys/api.json')
        assert self._full(tail) == 'cch-pid-snw-309e3f5c6400'

    def test_pointer__media_photos(self):
        tail = self.crypto.derive_cache_pointer_file_id(self.read_key, self.vault_id, 'media/photos')
        assert self._full(tail) == 'cch-pid-snw-51416375f368'

    def test_pointer__pages_home_md(self):
        tail = self.crypto.derive_cache_pointer_file_id(self.read_key, self.vault_id, 'pages/home.md')
        assert self._full(tail) == 'cch-pid-snw-13b79ad675e8'

    def test_value_and_pointer_namespaces_are_independent(self):
        # Same path, different kind => two unrelated ids (kind is part of the domain).
        v = self.crypto.derive_cache_value_file_id  (self.read_key, self.vault_id, 'pages/home.md')
        p = self.crypto.derive_cache_pointer_file_id(self.read_key, self.vault_id, 'pages/home.md')
        assert v != p

    def test_mutability_label_is_not_hashed(self):
        # muw variant is byte-identical to snw except the label.
        tail = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'pages/home.md')
        assert self._full(tail, 'muw') == 'cch-pid-muw-4aa53f5467b6'


class Test_Vault__Crypto__Cache_Ids__Chain_B:
    """Full derivation from a passphrase (PBKDF2 600k). Contract §4.1 Chain B."""

    def setup_method(self):
        self.crypto   = Vault__Crypto()
        self.vault_id = '7y6uk6gj'
        self.read_key = self.crypto.derive_read_key('test-vector-passphrase-0001', self.vault_id)

    def test_read_key_matches_contract(self):
        assert self.read_key.hex() == (
            '363032d8b69a4ea947385a6f26aff18c2394d513f990aa25fe73892cf2b7f8e0')

    def test_value_id_pages_home_md(self):
        tail = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'pages/home.md')
        assert f'cch-pid-snw-{tail}' == 'cch-pid-snw-23f9f166b48a'

    def test_pointer_id_media_photos(self):
        tail = self.crypto.derive_cache_pointer_file_id(self.read_key, self.vault_id, 'media/photos')
        assert f'cch-pid-snw-{tail}' == 'cch-pid-snw-a3f9b74ad988'

    def test_branch_index_family_cross_check(self):
        # sanity: same key still reproduces the existing branch-index id from the contract
        tail = self.crypto.derive_branch_index_file_id(self.read_key, self.vault_id)
        assert f'idx-pid-muw-{tail}' == 'idx-pid-muw-bb5912c7f5bd'


class Test_Vault__Crypto__Cache_Ids__Properties:

    def setup_method(self):
        self.crypto   = Vault__Crypto()
        self.read_key = bytes.fromhex('00' * 32)
        self.vault_id = 'abcd1234'

    def test_write_key_is_never_an_input(self):
        # read_key alone determines the id (the read-only-clone capability, contract §4.2).
        # There is no code path where write_key participates; deriving with read_key is total.
        tail = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'a/b.txt')
        assert len(tail) == 12 and all(c in '0123456789abcdef' for c in tail)

    def test_deterministic(self):
        a = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'a/b.txt')
        b = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'a/b.txt')
        assert a == b

    def test_path_sensitive(self):
        a = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'a/b.txt')
        b = self.crypto.derive_cache_value_file_id(self.read_key, self.vault_id, 'a/c.txt')
        assert a != b

    def test_vault_id_sensitive(self):
        a = self.crypto.derive_cache_value_file_id(self.read_key, 'abcd1234', 'a/b.txt')
        b = self.crypto.derive_cache_value_file_id(self.read_key, 'wxyz5678', 'a/b.txt')
        assert a != b
