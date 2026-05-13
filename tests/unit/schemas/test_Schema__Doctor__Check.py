from sgit_ai.schemas.Schema__Doctor__Check  import Schema__Doctor__Check
from sgit_ai.schemas.Schema__Doctor__Report import Schema__Doctor__Report
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Schema__Doctor__Check:

    def test_defaults(self):
        c = Schema__Doctor__Check()
        assert c.name        is None
        assert c.status      is None
        assert c.duration_ms is None
        assert c.message     is None
        assert c.hint        is None

    def test_create_with_values(self):
        c = Schema__Doctor__Check(
            name        = 'parse_url',
            status      = Enum__Doctor_Status.PASS,
            duration_ms = 3,
            message     = 'valid (https, send.sgraph.ai, 443)',
        )
        assert c.status == Enum__Doctor_Status.PASS
        assert str(c.name) == 'parse_url'
        assert int(c.duration_ms) == 3

    def test_round_trip(self):
        c = Schema__Doctor__Check(
            name    = 'dns_resolve',
            status  = Enum__Doctor_Status.FAIL,
            message = 'DNS resolution failed',
            hint    = 'Check your URL spelling',
        )
        assert Schema__Doctor__Check.from_json(c.json()).json() == c.json()


class Test_Schema__Doctor__Report:

    def test_defaults(self):
        r = Schema__Doctor__Report()
        assert r.remote_name is None
        assert r.remote_url  is None
        assert r.started_at  is None
        assert r.overall     is None
        assert r.checks      == []

    def test_add_checks(self):
        r = Schema__Doctor__Report(remote_name='origin', remote_url='https://send.sgraph.ai')
        r.checks.append(Schema__Doctor__Check(name='parse_url', status=Enum__Doctor_Status.PASS))
        assert len(r.checks) == 1
        assert r.checks[0].status == Enum__Doctor_Status.PASS

    def test_round_trip(self):
        r = Schema__Doctor__Report(
            remote_name = 'origin',
            remote_url  = 'https://send.sgraph.ai',
            started_at  = 1715603721234,        # milliseconds since epoch
            overall     = Enum__Doctor_Status.PASS,
        )
        r.checks.append(Schema__Doctor__Check(name='parse_url', status=Enum__Doctor_Status.PASS, duration_ms=2))
        assert Schema__Doctor__Report.from_json(r.json()).json() == r.json()
