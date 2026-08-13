from sgit_ai.cli.doctor.Check__Loopback_Container_Warn import Check__Loopback_Container_Warn
from sgit_ai.cli.doctor.Doctor__Context                import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status            import Enum__Doctor_Status


class Test_Check__Loopback_Container_Warn:

    def _ctx(self, url):
        return Doctor__Context(url=url)

    def test_non_loopback_skipped(self):
        check = Check__Loopback_Container_Warn().execute(self._ctx('https://send.sgraph.ai'))
        assert check.status  == Enum__Doctor_Status.SKIP
        assert check.message == 'n/a'

    def test_loopback_tcp_ok(self):
        check = Check__Loopback_Container_Warn().execute(
            self._ctx('http://localhost:8080'), tcp_failed=False)
        assert check.status == Enum__Doctor_Status.PASS
        assert 'localhost' in str(check.message)

    def test_loopback_tcp_failed(self):
        check = Check__Loopback_Container_Warn().execute(
            self._ctx('http://0.0.0.0:8080'), tcp_failed=True)
        assert check.status == Enum__Doctor_Status.WARN
        assert check.hint is not None

    def test_loopback_127(self):
        check = Check__Loopback_Container_Warn().execute(
            self._ctx('http://127.0.0.1:9000'), tcp_failed=True)
        assert check.status == Enum__Doctor_Status.WARN
