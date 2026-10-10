"""Two teammates push at the same moment: the second ref write must FAIL, loudly,
and must never overwrite the first. Before 0.21.0:
  * a conflict reported the way the live server reports it (HTTP 200, the miss on
    the operation itself) was ignored: push said "pushed", wrote nothing, and the
    clone believed its commit was on the server;
  * when the batch call raised for any reason, push fell back to one-by-one writes
    that turned the compare-and-swap ref write into a plain write, silently
    dropping the teammate's commit from the branch."""
import base64
import json
import os
import pytest

from tests._helpers.vault_test_env                 import Vault__Test_Env
from sgit_ai.network.api.Vault__API__In_Memory     import Vault__API__In_Memory
from sgit_ai.core.Vault__Errors                    import Vault__Push_Conflict_Error
from sgit_ai.core.Vault__Sync                      import Vault__Sync
from sgit_ai.schemas.Schema__Branch_Index          import Schema__Branch_Index


def _write(d, rel, content):
    with open(os.path.join(d, rel), 'w') as f: f.write(content)


class _Racing_API(Vault__API__In_Memory):
    """A teammate's push lands between our pull and our ref write. mode:
       'top'   - the in-memory shape (status: conflict)
       'live'  - the live server's shape (HTTP 200, per-operation conflict)
       'raise' - the batch call fails outright (a 5xx, a timeout), forcing the fallback"""
    mode     : str    = 'top'
    racer    : object = None                      # callable that performs the teammate's push once
    raced    : bool   = False

    def batch(self, vault_id, write_key, operations):
        cas = [op for op in operations if op.get('op') == 'write-if-match' and 'bare/refs/' in op.get('file_id', '')]
        if cas and not self.raced:
            self.raced = True
            self.racer()                                              # the teammate wins the race
            if self.mode == 'raise':
                raise RuntimeError('API Error: HTTP 502 Bad Gateway')
            if self.mode == 'live':
                key     = f'{vault_id}/{cas[0]["file_id"]}'
                current = base64.b64encode(self._store[key]).decode()
                if base64.b64decode(cas[0].get('match', '')) != self._store[key]:
                    return {'vault_id': vault_id, 'results': [{'op': 'write-if-match', 'file_id': cas[0]['file_id'],
                                                               'status': 'conflict', 'current': current}]}
        return super().batch(vault_id, write_key, operations)


class Test_Push__Concurrent_CAS:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files={'a.txt': 'v1'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def _race(self, mode):
        e     = self.env
        racer = _Racing_API(mode=mode); racer.setup(); racer._store = e.api._store
        bob   = Vault__Sync(crypto=e.crypto, api=racer)
        _write(e.alice_dir, 'alice.txt', 'alice'); e.sync.commit(e.alice_dir, message='alice')
        racer.racer = lambda: e.sync.push(e.alice_dir)                # alice pushes mid-way through bob's push
        _write(e.bob_dir, 'bob.txt', 'bob'); bob.commit(e.bob_dir, message='bob')
        return bob

    def _server_head(self):
        e = self.env; c = e.sync._init_components(e.alice_dir)
        idx  = Schema__Branch_Index.from_json(json.loads(e.crypto.decrypt(c.read_key, e.api._store[f'{c.vault_id}/bare/indexes/{c.branch_index_file_id}'])))
        meta = next(b for b in idx.branches if str(b.name) == 'current')
        return json.loads(e.crypto.decrypt(c.read_key, e.api._store[f'{c.vault_id}/bare/refs/{meta.head_ref_id}']))['commit_id']

    @pytest.mark.parametrize('mode', ['top', 'live', 'raise'])
    def test_the_losing_push_fails_and_the_winners_commit_stays(self, mode):
        bob = self._race(mode)
        alice_head = None
        with pytest.raises(Vault__Push_Conflict_Error, match='sgit pull'):
            bob.push(self.env.bob_dir)
        alice_head = self.env.sync.resolve_revision(self.env.alice_dir, 'HEAD')
        assert self._server_head() == alice_head                       # alice's push was not overwritten
        assert bob.status(self.env.bob_dir)['push_status'] != 'up_to_date'   # bob knows he has not pushed

    def test_after_a_lost_race_pull_then_push_succeeds(self):
        bob = self._race('live')
        with pytest.raises(Vault__Push_Conflict_Error):
            bob.push(self.env.bob_dir)
        bob.pull(self.env.bob_dir)
        bob.push(self.env.bob_dir)
        assert os.path.isfile(os.path.join(self.env.bob_dir, 'alice.txt'))
        self.env.sync.pull(self.env.alice_dir)
        assert os.path.isfile(os.path.join(self.env.alice_dir, 'bob.txt'))
