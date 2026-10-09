"""Fixed in 0.21.0 — a lost race on the shared branch index never overwrites it (review d3b8eef N5).

Since b68497e the index compare-and-swap raises once it gives up retrying. Push caught
that and uploaded its own unmerged copy of the index: a lost race silently removed
`signatures-required` (and any branch registered meanwhile) from the vault.

Threat model: TM-F13.
"""
import os

import pytest

from sgit_ai.core.Vault__Errors                    import Vault__Push_Conflict_Error
from sgit_ai.core.Vault__Sync                      import Vault__Sync
from sgit_ai.network.api.Vault__API__In_Memory     import Vault__API__In_Memory
from tests._helpers.vault_test_env                 import Vault__Test_Env


class Racing_API(Vault__API__In_Memory):
    """The same store, but every compare-and-swap on the index loses: a teammate always wrote first."""

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        if any(op.get('op') == 'write-if-match' and str(op.get('file_id', '')).startswith('bare/indexes/')
               for op in operations):
            return dict(status='conflict')
        return super().batch(vault_id, write_key, operations)


class Test_Fixed__Index_Overwrite:

    def test_N5__a_lost_index_race_fails_the_push_and_keeps_the_policy(self):
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.md': 'a'})
        s = env.restore()
        try:
            s.sync.set_format(s.vault_dir, add_features=['signatures-required'])
            carol = os.path.join(s.tmp_dir, 'carol')
            s.sync.clone(s.vault_key, carol)                          # a new clone branch, registered on first push
            racing = Racing_API(); racing.setup(); racing._store = s.api._store
            with open(os.path.join(carol, 'c.md'), 'w') as f:
                f.write('c')
            sync = Vault__Sync(crypto=s.crypto, api=racing)
            sync.commit(carol, 'c')
            with pytest.raises(Vault__Push_Conflict_Error, match='nothing was overwritten'):
                sync.push(carol)
            assert 'signatures-required' in s.sync.format_info(s.vault_dir)['features']
            s.sync.pull(s.vault_dir)
            assert 'signatures-required' in s.sync.format_info(s.vault_dir)['features']
        finally:
            s.cleanup()
            env.cleanup_snapshot()


class Flaky_Ref_API(Vault__API__In_Memory):
    """The same store; reading a branch ref fails per file (a 5xx for that one object),
    and every write operation is recorded."""

    def setup(self):
        super().setup()
        self.ops = []
        return self

    def batch_read(self, vault_id: str, file_ids: list, failures: dict = None) -> dict:
        from sgit_ai.schemas.Schema__Fetch_Failure        import Schema__Fetch_Failure
        from sgit_ai.safe_types.Enum__Fetch_Failure_Class import Enum__Fetch_Failure_Class
        result = super().batch_read(vault_id, file_ids, failures)
        for fid in file_ids:
            if fid.startswith('bare/refs/'):
                result[fid] = None
                if failures is not None:
                    failures[fid] = Schema__Fetch_Failure(classification=Enum__Fetch_Failure_Class.TRANSIENT)
        return result

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        self.ops.extend((op.get('op'), op.get('file_id')) for op in operations)
        return super().batch(vault_id, write_key, operations)


class Test_Fixed__Ref_Read_Error_Is_Not_Absent:

    def test_S10__a_per_file_read_error_never_turns_the_ref_write_into_a_blind_write(self):
        """`_named_ref_absent_on_server` read a per-file error as "absent", so the branch
        ref was written without compare-and-swap (review d3b8eef S10)."""
        from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.md': 'a'})
        s = env.restore()
        try:
            Vault__Branch_Switch(crypto=s.crypto).branch_new(s.vault_dir, 'feature')
            with open(os.path.join(s.vault_dir, 'f.md'), 'w') as f:
                f.write('f')
            flaky = Flaky_Ref_API().setup(); flaky._store = s.api._store
            sync  = Vault__Sync(crypto=s.crypto, api=flaky)
            sync.commit(s.vault_dir, 'f')
            c     = sync._init_components(s.vault_dir)
            index = c.branch_manager.load_branch_index(s.vault_dir, c.branch_index_file_id, c.read_key)
            ref   = f'bare/refs/{c.branch_manager.get_branch_by_name(index, "feature").head_ref_id}'
            try:
                sync.push(s.vault_dir)
            except Exception:
                pass                                                       # refusing is fine; a blind write is not
            assert ('write', ref) not in flaky.ops
        finally:
            s.cleanup()
            env.cleanup_snapshot()


class Refusing_API(Vault__API__In_Memory):
    """The same store; writes to one kind of file come back 'error' and are not stored."""

    def setup(self, prefix: str = ''):
        super().setup()
        self.prefix = prefix
        return self

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        if any(str(op.get('file_id', '')).startswith(self.prefix) and op.get('op') != 'read' for op in operations):
            return dict(status='ok', results=[dict(status='error', message='storage unavailable')])
        return super().batch(vault_id, write_key, operations)


class Test_Fixed__Tag_Writes_Are_Confirmed:
    """Review d3b8eef: the index upload treated anything but 'conflict' as success, and the
    tag object's write result was never checked: `tag create` could report success with
    nothing written."""

    @pytest.mark.parametrize('prefix', ['bare/data/', 'bare/indexes/'])
    def test_tag_create_fails_when_the_server_does_not_write(self, prefix):
        from sgit_ai.core.actions.tag.Vault__Sync__Tag import Vault__Sync__Tag
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.md': 'a'})
        s = env.restore()
        try:
            api = Refusing_API().setup(prefix); api._store = s.api._store
            with pytest.raises(Exception, match='did not write'):
                Vault__Sync__Tag(crypto=s.crypto, api=api).create(s.vault_dir, 'v1.0', s.commit_id)
            c     = s.sync._init_components(s.vault_dir)
            raw   = s.api._store.get(f'{c.vault_id}/bare/indexes/{c.branch_index_file_id}')
            index = Vault__Sync__Tag(crypto=s.crypto, api=s.api)._index(c, s.vault_dir, refresh=True)
            assert raw is not None and not [t for t in index.tags if str(t.name) == 'v1.0']
        finally:
            s.cleanup()
            env.cleanup_snapshot()
