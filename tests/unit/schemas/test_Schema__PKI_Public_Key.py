import pytest
from sg_send_cli.schemas.Schema__PKI_Public_Key import Schema__PKI_Public_Key


class Test_Schema__PKI_Public_Key:

    def test_create_with_defaults(self):
        schema = Schema__PKI_Public_Key()
        assert schema.label               is None
        assert schema.fingerprint         is None
        assert schema.signing_fingerprint is None
        assert schema.public_key_pem      == ''
        assert schema.signing_key_pem     == ''

    def test_create_with_values(self):
        schema = Schema__PKI_Public_Key(label               = 'alice',
                                        fingerprint         = 'sha256:abcdef1234567890',
                                        signing_fingerprint = 'sha256:1234567890abcdef',
                                        public_key_pem      = '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
                                        signing_key_pem     = '-----BEGIN PUBLIC KEY-----\ntest2\n-----END PUBLIC KEY-----')
        assert schema.label          == 'alice'
        assert schema.public_key_pem == '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----'

    def test_round_trip(self):
        schema   = Schema__PKI_Public_Key(label               = 'bob',
                                          fingerprint         = 'sha256:abcdef1234567890',
                                          signing_fingerprint = 'sha256:1234567890abcdef',
                                          public_key_pem      = 'pem-data-1',
                                          signing_key_pem     = 'pem-data-2')
        restored = Schema__PKI_Public_Key.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_round_trip_defaults(self):
        schema   = Schema__PKI_Public_Key()
        restored = Schema__PKI_Public_Key.from_json(schema.json())
        assert restored.json() == schema.json()

    def test_field_types_preserved(self):
        schema = Schema__PKI_Public_Key(label='test')
        assert type(schema.label).__name__ == 'Safe_Str__Vault_Name'

    def test_fingerprint_type_preserved(self):
        schema = Schema__PKI_Public_Key(fingerprint='sha256:abcdef1234567890')
        assert type(schema.fingerprint).__name__ == 'Safe_Str__Key_Fingerprint'

    def test_pem_fields_type_preserved(self):
        schema = Schema__PKI_Public_Key(public_key_pem='test-pem')
        assert type(schema.public_key_pem).__name__ == 'Safe_Str__PEM_Key'
