"""Tests for the session-scoped known_test_keys fixture."""
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


CANONICAL_KEYS = [
    'coralequalpassphrase1234:coralvlt',
    'givefoulpassphrase836100:givefvlt',
    'azurehatpassphrase799120:azurehvlt',
    'plumstackpassphrase55660:plumsvlt',
    'olivefernpassphrase11330:olivefvlt',
]


class Test_Known_Test_Keys:

    def test_fixture_has_exactly_five_entries(self, known_test_keys):
        assert len(known_test_keys) == 5

    def test_all_canonical_keys_present(self, known_test_keys):
        for k in CANONICAL_KEYS:
            assert k in known_test_keys, f'Missing key: {k}'

    def test_each_entry_has_required_fields(self, known_test_keys):
        for vault_key, derived in known_test_keys.items():
            assert 'vault_id'          in derived, f'{vault_key}: missing vault_id'
            assert 'read_key_bytes'    in derived, f'{vault_key}: missing read_key_bytes'
            assert 'write_key_bytes'   in derived, f'{vault_key}: missing write_key_bytes'

    def test_read_write_keys_are_bytes(self, known_test_keys):
        for vault_key, derived in known_test_keys.items():
            assert isinstance(derived['read_key_bytes'],  bytes), f'{vault_key}: read_key_bytes not bytes'
            assert isinstance(derived['write_key_bytes'], bytes), f'{vault_key}: write_key_bytes not bytes'

    def test_vault_ids_are_deterministic(self, known_test_keys):
        crypto = Vault__Crypto()
        for vault_key, derived in known_test_keys.items():
            fresh = crypto.derive_keys_from_vault_key(vault_key)
            assert derived['vault_id']       == fresh['vault_id']
            assert derived['read_key_bytes'] == fresh['read_key_bytes']

    def test_key_bytes_are_32_bytes(self, known_test_keys):
        for vault_key, derived in known_test_keys.items():
            assert len(derived['read_key_bytes'])  == 32, f'{vault_key}: read key not 32 bytes'
            assert len(derived['write_key_bytes']) == 32, f'{vault_key}: write key not 32 bytes'
