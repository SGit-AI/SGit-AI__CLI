from sg_send_cli.schemas.Schema__Remote_Config import Schema__Remote_Config


class Test_Schema__Remote_Config:

    def test_create_with_defaults(self):
        rc = Schema__Remote_Config()
        assert rc.name     is None
        assert rc.url      is None
        assert rc.vault_id is None

    def test_create_with_values(self):
        rc = Schema__Remote_Config(name     = 'origin',
                                   url      = 'https://api.sg-send.com',
                                   vault_id = 'a1b2c3d4')
        assert rc.name     == 'origin'
        assert rc.vault_id == 'a1b2c3d4'

    def test_round_trip(self):
        rc       = Schema__Remote_Config(name     = 'origin',
                                         url      = 'https://api.sg-send.com',
                                         vault_id = 'a1b2c3d4')
        restored = Schema__Remote_Config.from_json(rc.json())
        assert restored.json() == rc.json()
