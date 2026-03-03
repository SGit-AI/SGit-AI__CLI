from sg_send_cli.schemas.Schema__Vault_Config import Schema__Vault_Config


class Test_Schema__Vault_Config:

    def test_create_with_defaults(self):
        config = Schema__Vault_Config()
        assert config.vault_id     is None
        assert config.endpoint_url is None
        assert config.access_token is None
        assert config.local_path   is None

    def test_create_with_values(self):
        config = Schema__Vault_Config(vault_id='abcd1234',
                                      endpoint_url='/api/transfers',
                                      local_path='/home/user/vaults/alpha')
        assert config.vault_id   == 'abcd1234'
        assert config.local_path == '/home/user/vaults/alpha'

    def test_round_trip(self):
        config   = Schema__Vault_Config(vault_id='abcd1234',
                                        endpoint_url='/api/transfers',
                                        access_token='tok.en.123',
                                        local_path='/home/user/vaults')
        restored = Schema__Vault_Config.from_json(config.json())
        assert restored.json() == config.json()
