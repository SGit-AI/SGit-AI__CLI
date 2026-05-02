from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory    # noqa: F401 — re-export for backwards compat

import pytest
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


@pytest.fixture(scope='session')
def known_test_keys():
    """Pre-derived keys for 5 canonical test vault_keys.

    Returns a dict keyed by vault_key string, value is the dict returned by
    derive_keys_from_vault_key (vault_id, read_key_bytes, write_key_bytes, …).
    Consumers that need to mutate the dict should take a copy; bytes values are
    already immutable.
    """
    crypto = Vault__Crypto()
    # Format: passphrase:vault_id  (24-char passphrase + 8-char vault_id)
    keys = [
        'coralequalpassphrase1234:coralvlt',
        'givefoulpassphrase836100:givefvlt',
        'azurehatpassphrase799120:azurehvlt',
        'plumstackpassphrase55660:plumsvlt',
        'olivefernpassphrase11330:olivefvlt',
    ]
    return {k: crypto.derive_keys_from_vault_key(k) for k in keys}
