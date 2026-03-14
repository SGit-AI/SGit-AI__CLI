from sg_send_cli.schemas.Schema__Local_Config import Schema__Local_Config


class Test_Schema__Local_Config:

    def test_create_with_defaults(self):
        cfg = Schema__Local_Config()
        assert cfg.my_branch_id is None

    def test_create_with_branch(self):
        cfg = Schema__Local_Config(my_branch_id='branch-clone-a1b2c3d4')
        assert cfg.my_branch_id == 'branch-clone-a1b2c3d4'

    def test_round_trip(self):
        cfg      = Schema__Local_Config(my_branch_id='branch-clone-a1b2c3d4')
        restored = Schema__Local_Config.from_json(cfg.json())
        assert restored.json() == cfg.json()
