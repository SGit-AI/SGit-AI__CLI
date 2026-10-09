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
