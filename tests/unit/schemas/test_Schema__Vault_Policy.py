from sg_send_cli.schemas.Schema__Vault_Policy   import Schema__Vault_Policy
from sg_send_cli.safe_types.Enum__Provenance_Mode import Enum__Provenance_Mode


class Test_Schema__Vault_Policy:

    def test_create_with_defaults(self):
        policy = Schema__Vault_Policy()
        assert policy.schema                   is None
        assert policy.minimum_provenance       == Enum__Provenance_Mode.MODE_1
        assert policy.require_author_signature is False
        assert policy.require_attestation      is False

    def test_create_mode_3(self):
        policy = Schema__Vault_Policy(schema                   = 'vault_policy_v1',
                                      minimum_provenance       = Enum__Provenance_Mode.MODE_3,
                                      require_author_signature = True,
                                      require_attestation      = True)
        assert policy.minimum_provenance == Enum__Provenance_Mode.MODE_3

    def test_round_trip(self):
        policy   = Schema__Vault_Policy(schema             = 'vault_policy_v1',
                                        minimum_provenance = Enum__Provenance_Mode.MODE_2)
        restored = Schema__Vault_Policy.from_json(policy.json())
        assert restored.json() == policy.json()
