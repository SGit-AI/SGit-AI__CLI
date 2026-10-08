"""The hermetic-network guard shared by tests/unit and tests/security.

  * SGIT_DEFAULT_BASE_URL points the CLI's default server at a closed local
    port, so a command run on a test vault with no remote configured sees an
    unreachable server at once (exactly the offline behaviour) instead of
    calling the live dev server and waiting on it.
  * A guard on http.client: a test that opens a connection to any host other
    than loopback fails by name, so a new networked test cannot slip in.
    Proxy variables are cleared for the same reason (through a proxy the
    target host would be hidden behind a loopback address).

A conftest calls install() at import time and re-exports `_no_network`.
"""
import http.client
import os

import pytest

_LOOPBACK     = ('127.0.0.1', 'localhost', '::1')
_attempts     = []
_orig_connect = http.client.HTTPConnection.connect


def _guarded_connect(self):
    target = getattr(self, '_tunnel_host', None) or self.host
    if target not in _LOOPBACK:
        _attempts.append(str(target))
        raise OSError(f'tests are hermetic: refused a connection to {target!r}')
    return _orig_connect(self)


def install():
    os.environ['SGIT_DEFAULT_BASE_URL'] = 'http://127.0.0.1:9'
    for var in ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy', 'ALL_PROXY', 'all_proxy'):
        os.environ.pop(var, None)
    http.client.HTTPConnection.connect = _guarded_connect


@pytest.fixture(autouse=True)
def _no_network():
    _attempts.clear()
    yield
    if _attempts:
        hosts = sorted(set(_attempts))
        _attempts.clear()
        pytest.fail(f'this test tried to reach {hosts}: unit and security tests must be hermetic '
                    f'(use Vault__API__In_Memory or a loopback server; real servers go in tests/integration)')
