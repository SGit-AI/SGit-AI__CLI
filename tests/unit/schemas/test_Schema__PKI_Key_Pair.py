import pytest
from sg_send_cli.schemas.Schema__PKI_Key_Pair import Schema__PKI_Key_Pair


class Test_Schema__PKI_Key_Pair:

    def test_create_with_defaults(self):
        schema = Schema__PKI_Key_Pair()
        assert schema.label                  is None
        assert schema.algorithm              is None
        assert schema.key_size               == 0
        assert schema.encryption_fingerprint is None
        assert schema.signing_fingerprint    is None
        assert schema.created_at             is None

    def test_create_with_values(self):
        schema = Schema__PKI_Key_Pair(label                  = 'my-key',
                                      algorithm              = 'RSA-4096',
                                      key_size               = 4096,
                                      encryption_fingerprint = 'sha256:abcdef1234567890',
                                      signing_fingerprint    = 'sha256:1234567890abcdef',
                                      created_at             = '2026-03-12T10:00:00.000Z')
        assert schema.label    == 'my-key'
        assert schema.key_size == 4096

    def test_round_trip(self):
        schema   = Schema__PKI_Key_Pair(label                  = 'test-label',
                                        algorithm              = 'RSA-4096',
                                        key_size               = 4096,
                                        encryption_fingerprint = 'sha256:abcdef1234567890',
                                        signing_fingerprint    = 'sha256:1234567890abcdef',
                                        created_at             = '2026-03-12T10:00:00.000Z')
        restored = Schema__PKI_Key_Pair.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_round_trip_defaults(self):
        schema   = Schema__PKI_Key_Pair()
        restored = Schema__PKI_Key_Pair.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_field_types_preserved(self):
        schema = Schema__PKI_Key_Pair(label='test')
        assert type(schema.label).__name__ == 'Safe_Str__Vault_Name'

    def test_fingerprint_type_preserved(self):
        schema = Schema__PKI_Key_Pair(encryption_fingerprint='sha256:abcdef1234567890')
        assert type(schema.encryption_fingerprint).__name__ == 'Safe_Str__Key_Fingerprint'

    def test_algorithm_stored_as_safe_str(self):
        schema = Schema__PKI_Key_Pair(algorithm='ECDSA-P256')
        assert type(schema.algorithm).__name__ == 'Safe_Str__Vault_Name'
        assert schema.algorithm == 'ECDSA-P256'

    def test_created_at_type_preserved(self):
        schema = Schema__PKI_Key_Pair(created_at='2026-03-12T10:00:00.000Z')
        assert type(schema.created_at).__name__ == 'Safe_Str__ISO_Timestamp'
