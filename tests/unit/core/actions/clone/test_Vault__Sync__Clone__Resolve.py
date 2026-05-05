"""Tests for the clone-resolve try/except scope fix (item 1 of v0.14.0 pre-release brief)."""
import pytest

from sgit_ai.core.actions.clone.Vault__Sync__Clone import Vault__Sync__Clone
from sgit_ai.network.api.Vault__API                import Vault__API
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto


class _API__Probe_Fail(Vault__API):
    def batch_read(self, vault_id, file_ids):
        raise ConnectionError('network down')


class _API__Probe_Success(Vault__API):
    def batch_read(self, vault_id, file_ids):
        return {file_ids[0]: b'index-data'}


class _API__Probe_Success__Clone_Fails(Vault__API):
    def __init__(self):
        super().__init__()
        self._calls = 0

    def batch_read(self, vault_id, file_ids):
        self._calls += 1
        if self._calls > 1:
            raise ConnectionError('network blip mid-clone')
        return {file_ids[0]: b'index-data'}


class _API__Probe_Empty(Vault__API):
    def batch_read(self, vault_id, file_ids):
        return {}


class _Crypto__Fixed(Vault__Crypto):
    def derive_keys_from_simple_token(self, token):
        return {'vault_id': 'vault-test', 'branch_index_file_id': 'idx-test'}


def _make_clone(api, crypto=None):
    c        = Vault__Sync__Clone()
    c.api    = api
    c.crypto = crypto or _Crypto__Fixed()
    return c


class Test_Clone__Resolve__Try_Except_Scope:

    def test_probe_failure_does_not_surface(self, tmp_path):
        clone = _make_clone(_API__Probe_Fail())
        with pytest.raises(RuntimeError, match='No vault or transfer found'):
            clone._clone_resolve_simple_token('apple-mango-1234', str(tmp_path))

    def test_mid_clone_failure_surfaces_real_error(self, tmp_path):
        clone = _make_clone(_API__Probe_Success())
        clone._clone_with_keys = lambda *a, **kw: (_ for _ in ()).throw(
            ConnectionError('network blip mid-clone'))

        with pytest.raises(ConnectionError, match='network blip mid-clone'):
            clone._clone_resolve_simple_token('apple-mango-1234', str(tmp_path))

    def test_probe_success_calls_clone_with_keys(self, tmp_path):
        called = []
        clone  = _make_clone(_API__Probe_Success())
        clone._clone_with_keys = lambda *a, **kw: called.append(True) or 'done'

        result = clone._clone_resolve_simple_token('apple-mango-1234', str(tmp_path))
        assert result == 'done'
        assert len(called) == 1

    def test_probe_returns_empty_falls_through(self, tmp_path):
        clone = _make_clone(_API__Probe_Empty())
        with pytest.raises(RuntimeError, match='No vault or transfer found'):
            clone._clone_resolve_simple_token('apple-mango-1234', str(tmp_path))
