"""Vault__API__Auto — the transport-resolution rule, pinned.

The rule (static-publishing 01 §1): an http(s) host is the live API until its
BATCH endpoint answers 404/405/501; only then is the host remembered as static.

The bug this pins: the resolver used to flip on ANY error carrying 'HTTP 404',
and a fresh vault's first push reads refs that do not exist yet, which is a 404
from /api/vault/read/. The writable vault was silently re-resolved to the
read-only static transport and the push failed with a message about a plain
file server. A 404 on an object is not a missing API."""
from unittest import TestCase

from sgit_ai.network.api.Vault__API__Auto      import Vault__API__Auto, BATCH_PATH, FALLBACK_MARKERS
from sgit_ai.safe_types.Enum__Transport         import Enum__Transport


def _api_error(code: str, reason: str, method: str, url: str) -> RuntimeError:
    return RuntimeError(f'API Error: HTTP {code} {reason}\n  Request:  {method} {url}\n  Headers:  {{}}')


class Test_Vault__API__Auto(TestCase):

    def setUp(self):
        self.api = Vault__API__Auto(base_url='https://vault.example.invalid', access_token='')

    def test_markers_and_batch_path(self):
        assert FALLBACK_MARKERS == ('HTTP 404', 'HTTP 405', 'HTTP 501')
        assert BATCH_PATH       == '/api/vault/batch/'

    def test_object_404_is_not_a_missing_api(self):
        error = _api_error('404', 'Not Found', 'GET',
                           'https://vault.example.invalid/api/vault/read/abcd1234/bare/refs/HEAD')
        assert self.api._resolve_from_error(error) is False
        assert self.api.resolved is None

    def test_batch_404_405_501_resolve_to_static(self):
        for code, reason in (('404', 'Not Found'), ('405', 'Method Not Allowed'), ('501', 'Not Implemented')):
            api   = Vault__API__Auto(base_url='https://vault.example.invalid', access_token='')
            error = _api_error(code, reason, 'POST', 'https://vault.example.invalid/api/vault/batch/abcd1234')
            assert api._resolve_from_error(error) is True, code

    def test_batch_500_is_a_real_error_not_a_resolution(self):
        error = _api_error('500', 'Internal Server Error', 'POST',
                           'https://vault.example.invalid/api/vault/batch/abcd1234')
        assert self.api._resolve_from_error(error) is False

    def test_connection_failure_never_resolves(self):
        assert self.api._resolve_from_error(RuntimeError('URLError: <urlopen error [Errno -2] Name or service not known>')) is False

    def test_once_resolved_it_stays_resolved(self):
        self.api.resolved = Enum__Transport.API
        error = _api_error('404', 'Not Found', 'POST', 'https://vault.example.invalid/api/vault/batch/abcd1234')
        assert self.api._resolve_from_error(error) is False
