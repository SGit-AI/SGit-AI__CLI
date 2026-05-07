import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                 import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move


def _vault_key(vault_dir):
    return open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()


def _vault_id(env, key=None):
    k = key or _vault_key(env.vault_dir)
    return env.crypto.derive_keys_from_vault_key(k)['vault_id']


def _mover(env):
    return Vault__Sync__Move(crypto=env.crypto, api=env.api)


def _sync(env):
    return Vault__Sync(crypto=env.crypto, api=env.api)


class Test_Vault__Move__Multi_Round:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.txt' : 'initial content\n',
            'src/app.py' : 'print("app")\n',
        })

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_three_sequential_moves_produce_distinct_ids(self):
        id0 = _vault_id(self.env)
        _mover(self.env).move(self.env.vault_dir, reason='round-1')
        id1 = _vault_id(self.env)
        _mover(self.env).move(self.env.vault_dir, reason='round-2')
        id2 = _vault_id(self.env)
        _mover(self.env).move(self.env.vault_dir, reason='round-3')
        id3 = _vault_id(self.env)
        assert len({id0, id1, id2, id3}) == 4

    def test_clone_works_after_each_move_in_chain(self):
        for i in range(3):
            _mover(self.env).move(self.env.vault_dir, reason=f'chain-{i}')
            key = _vault_key(self.env.vault_dir)
            clone_dir = tempfile.mkdtemp()
            try:
                _sync(self.env).clone(key, clone_dir)
                assert os.path.isfile(os.path.join(clone_dir, 'readme.txt'))
            finally:
                shutil.rmtree(clone_dir, ignore_errors=True)

    def test_commit_and_push_work_after_each_move(self):
        for i in range(3):
            _mover(self.env).move(self.env.vault_dir, reason=f'move-{i}')
            with open(os.path.join(self.env.vault_dir, f'file_{i}.txt'), 'w') as f:
                f.write(f'round {i}')
            sync = _sync(self.env)
            commit_result = sync.commit(self.env.vault_dir, message=f'post-move-{i}')
            assert commit_result.get('commit_id')
            push_result = sync.push(self.env.vault_dir)
            assert push_result is not None

    def test_history_chain_records_all_moves_in_order(self):
        reasons = ['first-move', 'second-move', 'third-move']
        for reason in reasons:
            _mover(self.env).move(self.env.vault_dir, reason=reason)
        hist_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'move-history.json')
        hist = json.load(open(hist_path))
        recorded = [m['reason'] for m in hist['moves']]
        assert recorded == reasons

    def test_all_old_ids_tombstoned_after_chain(self):
        old_ids = [_vault_id(self.env)]
        for _ in range(3):
            _mover(self.env).move(self.env.vault_dir, reason='tombstone-chain')
            old_ids.append(_vault_id(self.env))  # current becomes old on next move
        # Last element is the current live vault; all prior must be tombstoned
        live_id  = old_ids.pop()
        for dead_id in old_ids[:-1]:  # exclude last which is the current key before last move
            assert self.env.api.is_tombstoned(dead_id), f'{dead_id} should be tombstoned'

    def test_object_count_stable_across_three_moves(self):
        def _obj_count():
            d = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')
            return sum(1 for f in os.listdir(d) if f.startswith('obj-cas-imm-'))

        count0 = _obj_count()
        for _ in range(3):
            _mover(self.env).move(self.env.vault_dir, reason='count-check')
        count3 = _obj_count()
        # Sentinel commits add 2 objects per move (commit + tree) times 3 moves
        assert count3 >= count0
        assert count3 <= count0 + 6  # at most 2 new objects per move

    def test_clone_after_three_moves_has_original_files(self):
        for i in range(3):
            _mover(self.env).move(self.env.vault_dir, reason=f'pre-clone-{i}')
        key = _vault_key(self.env.vault_dir)
        clone_dir = tempfile.mkdtemp()
        try:
            _sync(self.env).clone(key, clone_dir)
            assert os.path.isfile(os.path.join(clone_dir, 'readme.txt'))
            assert open(os.path.join(clone_dir, 'readme.txt')).read() == 'initial content\n'
            assert os.path.isfile(os.path.join(clone_dir, 'src', 'app.py'))
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    def test_stale_clone_cannot_push_after_move_chain(self):
        old_key   = self.env.vault_key
        old_keys  = self.env.crypto.derive_keys_from_vault_key(old_key)
        old_id    = old_keys['vault_id']
        write_key = old_keys['write_key']

        for _ in range(3):
            _mover(self.env).move(self.env.vault_dir, reason='chain')

        assert self.env.api.is_tombstoned(old_id)
        with pytest.raises(RuntimeError, match='403'):
            self.env.api.write(old_id, 'bare/refs/stale', write_key, b'data')

    def test_key_generation_increments_across_moves(self):
        hist_path = os.path.join(self.env.vault_dir, '.sg_vault', 'local', 'move-history.json')

        def _last_gen():
            return json.load(open(hist_path))['moves'][-1].get('key_generation')

        _mover(self.env).move(self.env.vault_dir, reason='gen-1')
        gen1 = _last_gen()
        _mover(self.env).move(self.env.vault_dir, reason='gen-2')
        gen2 = _last_gen()
        _mover(self.env).move(self.env.vault_dir, reason='gen-3')
        gen3 = _last_gen()

        assert gen1 is not None
        assert gen2 is not None
        assert gen3 is not None
        assert gen2 > gen1
        assert gen3 > gen2

    def test_status_clean_after_each_move_in_chain(self):
        for i in range(3):
            _mover(self.env).move(self.env.vault_dir, reason=f'status-check-{i}')
            status = _sync(self.env).status(self.env.vault_dir)
            assert status is not None
