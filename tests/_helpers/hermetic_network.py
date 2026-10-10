"""The hermetic-network guard shared by tests/unit and tests/security.

  * SGIT_DEFAULT_BASE_URL points the CLI's default server at a closed local
    port, so a command run on a test vault with no remote configured sees an
    unreachable server at once (exactly the offline behaviour) instead of
    calling the live dev server and waiting on it.
  * Guards on http.client, on socket connect/connect_ex and on DNS lookups
    (getaddrinfo): a test that resolves or connects to any host other than
    loopback fails by name, so a new networked test cannot slip in.
    Proxy variables are cleared for the same reason (through a proxy the
    target host would be hidden behind a loopback address).

A conftest calls install() at import time and re-exports `_no_network`.
"""
import http.client
import os
import socket

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


_orig_getaddrinfo = socket.getaddrinfo
_orig_sock_conn   = socket.socket.connect
_orig_sock_conn_x = socket.socket.connect_ex


def _is_loopback(host) -> bool:
    host = str(host or '')
    return host in _LOOPBACK or host.startswith('127.') or host in ('', '0.0.0.0', '::')


def _guarded_getaddrinfo(host, *args, **kwargs):                # DNS: a lookup is already a network request
    if host is not None and not _is_loopback(host if isinstance(host, str) else host.decode()):
        _attempts.append(f'dns:{host}')
        raise socket.gaierror(socket.EAI_NONAME, f'tests are hermetic: refused to resolve {host!r}')
    return _orig_getaddrinfo(host, *args, **kwargs)


def _socket_target(address):
    return address[0] if isinstance(address, tuple) and address else None   # AF_UNIX paths are local


def _guarded_sock_connect(self, address):                       # raw sockets, not only http.client
    target = _socket_target(address)
    if target is not None and not _is_loopback(target):
        _attempts.append(str(target))
        raise OSError(f'tests are hermetic: refused a socket connection to {target!r}')
    return _orig_sock_conn(self, address)


def _guarded_sock_connect_ex(self, address):
    target = _socket_target(address)
    if target is not None and not _is_loopback(target):
        _attempts.append(str(target))
        return 111                                              # ECONNREFUSED
    return _orig_sock_conn_x(self, address)


def install():
    os.environ['SGIT_DEFAULT_BASE_URL'] = 'http://127.0.0.1:9'
    for var in ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy', 'ALL_PROXY', 'all_proxy'):
        os.environ.pop(var, None)
    http.client.HTTPConnection.connect = _guarded_connect
    socket.getaddrinfo                 = _guarded_getaddrinfo   # the review nit: DNS and raw sockets were open
    socket.socket.connect              = _guarded_sock_connect
    socket.socket.connect_ex           = _guarded_sock_connect_ex


@pytest.fixture(autouse=True)
def _no_network():
    _attempts.clear()
    yield
    if _attempts:
        hosts = sorted(set(_attempts))
        _attempts.clear()
        pytest.fail(f'this test tried to reach {hosts}: unit and security tests must be hermetic '
                    f'(use Vault__API__In_Memory or a loopback server; real servers go in tests/integration)')
