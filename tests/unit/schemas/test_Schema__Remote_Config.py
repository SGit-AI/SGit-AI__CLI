from sgit_ai.schemas.Schema__Remote_Config  import Schema__Remote_Config
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Schema__Remote_Config:

    def test_defaults(self):
        r = Schema__Remote_Config()
        assert r.name               is None
        assert r.url                is None
        assert r.vault_id           is None
        assert r.is_default         is False
        assert r.tls_verify         is True
        assert r.created_at         is None
        assert r.last_health_at     is None
        assert r.last_health_status is None

    def test_create_with_values(self):
        r = Schema__Remote_Config(
            name       = 'origin',
            url        = 'https://send.sgraph.ai',
            vault_id   = 'abc123',
            is_default = True,
            tls_verify = False,
        )
        assert str(r.name)  == 'origin'
        assert str(r.url)   == 'https://send.sgraph.ai'
        assert r.is_default is True
        assert r.tls_verify is False

    def test_health_status_field(self):
        r = Schema__Remote_Config()
        r.last_health_status = Enum__Doctor_Status.PASS
        assert r.last_health_status == Enum__Doctor_Status.PASS

    def test_round_trip(self):
        r = Schema__Remote_Config(
            name       = 'origin',
            url        = 'https://send.sgraph.ai',
            vault_id   = 'abc123',
            is_default = True,
            tls_verify = True,
            created_at = '2026-05-13T12:00:00Z',
        )
        assert Schema__Remote_Config.from_json(r.json()).json() == r.json()
