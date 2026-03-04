import hashlib
from sg_send_cli.schemas.Schema__Vault_Meta import Schema__Vault_Meta


class Test_Schema__Vault_Meta:

    def test_create_with_defaults(self):
        meta = Schema__Vault_Meta()
        assert meta.vault_id is None
        assert meta.name     is None

    def test_create_with_values(self):
        meta = Schema__Vault_Meta(vault_id='abcd1234', name='My Vault',
                                  vault_key='pass:abcd1234')
        assert meta.vault_id  == 'abcd1234'
        assert meta.name      == 'My Vault'
        assert meta.vault_key == 'pass:abcd1234'

    def test_round_trip(self):
        meta = Schema__Vault_Meta(vault_id='abcd1234', name='Test Vault',
                                  vault_key='secret:abcd1234')
        restored = Schema__Vault_Meta.from_json(meta.json())
        assert restored.json() == meta.json()

    def test_round_trip_empty(self):
        meta     = Schema__Vault_Meta()
        restored = Schema__Vault_Meta.from_json(meta.json())
        assert restored.json() == meta.json()

    def test_field_types_preserved(self):
        meta = Schema__Vault_Meta(vault_id='abcd1234')
        assert type(meta.vault_id).__name__ == 'Safe_Str__Vault_Id'

    def test_version_defaults_to_zero(self):
        meta = Schema__Vault_Meta()
        assert meta.version == 0
