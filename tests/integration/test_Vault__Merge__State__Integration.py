import os
import pytest

from sgit_ai.core.Vault__Sync                         import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                     import Vault__Crypto
from sgit_ai.core.Vault__Errors                       import Vault__Merge_In_Progress_Error
from sgit_ai.core.actions.merge.Vault__Merge__State   import Vault__Merge__State
from sgit_ai.core.actions.merge.Vault__Merge__Resolve import Vault__Merge__Resolve


class Test_Vault__Merge__State__Integration:

    def _sync(self, vault_api):
        return Vault__Sync(crypto=Vault__Crypto(), api=vault_api)

    def _write(self, directory, path, content):
        full = os.path.join(directory, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)

    def _setup_conflict(self, vault_api, temp_dir, vault_key, dir_a, dir_b,
                        shared_file='shared.txt', ours='user b content', theirs='user a updated'):
        sync = self._sync(vault_api)

        sync.init(dir_a, vault_key=vault_key)
        self._write(dir_a, shared_file, 'initial content')
        sync.commit(dir_a, message='add shared file')
        sync.push(dir_a)

        sync.clone(vault_key, dir_b)
        self._write(dir_b, shared_file, ours)
        sync.commit(dir_b, message='user b changes')

        self._write(dir_a, shared_file, theirs)
        sync.commit(dir_a, message='user a update')
        sync.push(dir_a)

        return sync

    def test_conflict_loop_can_be_aborted(self, vault_api, temp_dir):
        vault_key = 'conflict:looptest1'
        dir_a     = os.path.join(temp_dir, 'user_a')
        dir_b     = os.path.join(temp_dir, 'user_b')
        sync      = self._setup_conflict(vault_api, temp_dir, vault_key, dir_a, dir_b)

        result = sync.pull(dir_b)
        assert result['status'] == 'conflicts'
        assert 'shared.txt' in result['conflicts']
        assert os.path.isfile(os.path.join(dir_b, 'shared.txt.conflict'))
        assert Vault__Merge__State().exists(dir_b)

        with pytest.raises(Vault__Merge_In_Progress_Error):
            sync.pull(dir_b)

        abort_result = sync.merge_abort(dir_b)
        assert abort_result['status'] == 'aborted'
        assert not os.path.isfile(os.path.join(dir_b, 'shared.txt.conflict'))
        assert not Vault__Merge__State().exists(dir_b)

        with open(os.path.join(dir_b, 'shared.txt')) as f:
            assert f.read() == 'user b content'

    def test_flow_a_capture_then_resolve_end_to_end(self, vault_api, temp_dir):
        vault_key = 'flowa:restest01'
        dir_a     = os.path.join(temp_dir, 'user_a')
        dir_b     = os.path.join(temp_dir, 'user_b')
        sync      = self._setup_conflict(vault_api, temp_dir, vault_key, dir_a, dir_b,
                                         ours='user b version', theirs='user a version')

        pull_result = sync.pull(dir_b)
        assert pull_result['status'] == 'conflicts'
        assert Vault__Merge__State().exists(dir_b)

        self._write(dir_b, 'shared.txt', 'manually resolved content')
        os.remove(os.path.join(dir_b, 'shared.txt.conflict'))

        commit_result = sync.commit(dir_b, message='resolve merge')
        assert commit_result['merge_commit'] is True
        assert not Vault__Merge__State().exists(dir_b)

        push_result = sync.push(dir_b)
        assert push_result['status'] == 'pushed'

        dir_c = os.path.join(temp_dir, 'verify')
        sync.clone(vault_key, dir_c)
        with open(os.path.join(dir_c, 'shared.txt')) as f:
            assert f.read() == 'manually resolved content'

    def test_flow_b_resolve_then_merge_commit_end_to_end(self, vault_api, temp_dir):
        vault_key = 'flowb:mergetest1'
        dir_a     = os.path.join(temp_dir, 'user_a')
        dir_b     = os.path.join(temp_dir, 'user_b')
        sync      = self._setup_conflict(vault_api, temp_dir, vault_key, dir_a, dir_b,
                                         shared_file='note.txt',
                                         ours='b note', theirs='a updated note')

        pull_result = sync.pull(dir_b)
        assert pull_result['status'] == 'conflicts'
        assert 'note.txt' in pull_result['conflicts']
        assert Vault__Merge__State().exists(dir_b)

        resolver       = Vault__Merge__Resolve()
        resolve_result = resolver.resolve_all(dir_b, 'theirs')
        assert resolve_result['status']   == 'all_resolved'
        assert resolve_result['resolved'] == 1
        assert not os.path.isfile(os.path.join(dir_b, 'note.txt.conflict'))

        commit_result = sync.commit(dir_b, message='merge: take theirs')
        assert commit_result['merge_commit'] is True
        assert not Vault__Merge__State().exists(dir_b)

        with open(os.path.join(dir_b, 'note.txt')) as f:
            assert f.read() == 'a updated note'

        push_result = sync.push(dir_b)
        assert push_result['status'] == 'pushed'

    def test_push_refuses_non_ff_auto_pull(self, vault_api, temp_dir):
        vault_key = 'nonff:pushtest1'
        dir_a     = os.path.join(temp_dir, 'user_a')
        dir_b     = os.path.join(temp_dir, 'user_b')
        sync      = self._setup_conflict(vault_api, temp_dir, vault_key, dir_a, dir_b,
                                         shared_file='doc.txt',
                                         ours='user b edit', theirs='user a edit')

        with pytest.raises(RuntimeError, match='merge conflicts'):
            sync.push(dir_b)

        assert Vault__Merge__State().exists(dir_b)

        resolver = Vault__Merge__Resolve()
        resolver.resolve_all(dir_b, 'ours')

        commit_result = sync.commit(dir_b, message='resolve and push')
        assert commit_result['merge_commit'] is True

        push_result = sync.push(dir_b)
        assert push_result['status'] == 'pushed'

    def test_history_reset_fetch_for_stuck_agent(self, vault_api, temp_dir):
        vault_key = 'reset:agenttest'
        dir_a     = os.path.join(temp_dir, 'agent')
        sync      = self._sync(vault_api)

        sync.init(dir_a, vault_key=vault_key)
        self._write(dir_a, 'state.txt', 'version one')
        sync.commit(dir_a, message='v1')
        sync.push(dir_a)

        branches   = sync.branches(dir_a)
        clone_info = next(b for b in branches['branches'] if b['is_current'])
        v1_commit  = clone_info['head_commit']

        self._write(dir_a, 'state.txt', 'version two')
        sync.commit(dir_a, message='v2')
        sync.push(dir_a)

        self._write(dir_a, 'state.txt', 'corrupted or wrong content')
        self._write(dir_a, 'junk.tmp', 'temporary garbage')

        reset_result = sync.reset(dir_a, commit_id=v1_commit)
        assert reset_result['commit_id'] == v1_commit

        with open(os.path.join(dir_a, 'state.txt')) as f:
            assert f.read() == 'version one'

        assert not os.path.isfile(os.path.join(dir_a, 'junk.tmp'))
