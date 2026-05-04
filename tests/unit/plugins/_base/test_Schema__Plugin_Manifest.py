from sgit_ai.plugins._base.Schema__Plugin_Manifest import Schema__Plugin_Manifest


class Test_Schema__Plugin_Manifest:

    def test_round_trip(self):
        m          = Schema__Plugin_Manifest()
        m.name     = 'history'
        m.version  = '0.1.0'
        m.commands = ['log', 'diff', 'show']
        assert Schema__Plugin_Manifest.from_json(m.json()).json() == m.json()

    def test_default_enabled(self):
        m = Schema__Plugin_Manifest()
        assert m.enabled   is True
        assert m.stability == 'stable'

    def test_commands_list(self):
        m          = Schema__Plugin_Manifest()
        m.name     = 'check'
        m.version  = '0.1.0'
        m.commands = ['fsck']
        assert m.commands == ['fsck']
