"""Fixes after the sgit.ai team's test of 0.20.0 on the live API (8 Oct 2026).

1. `signatures-required` refused a teammate's legitimate commit as 'no-key' on a
   clone made before that teammate registered: pull never downloaded the new
   bare/keys/<id>. And the owner could not switch the policy off: the index
   merge kept the stronger gate, so the stale clone kept the policy and wrote it
   back to the server.
2. `pull --accept-rewind` left the clone on the removed commits, so status said
   "ahead … sgit push" and pushing put the removed history back.
3. A pull without write access warned "Could not refresh the branch index …
   HTTP 401" every time.
4. `history reset` / `history show` refused the id `history log` prints.
"""
import json
import os
import pytest

from tests._helpers.vault_test_env                 import Vault__Test_Env
from sgit_ai.core.Vault__Errors                    import Vault__Ref_Rewind_Error
from sgit_ai.storage.Vault__Format                 import Vault__Format, FEATURE_SIG_REQUIRED
from sgit_ai.schemas.Schema__Branch_Index          import Schema__Branch_Index
from sgit_ai.core.actions.index.Vault__Index_Sync  import Vault__Index_Sync
from sgit_ai.network.api.Vault__API__In_Memory     import Vault__API__In_Memory


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)

def _read(d, rel):
    with open(os.path.join(d, rel)) as f: return f.read()


class _Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files={'a.txt': 'a v1', 'b.txt': 'b v1'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync; self.api = self.env.api
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir
        self.c = self.sync._init_components(self.alice); self.vid = str(self.c.vault_id)

    def teardown_method(self):
        self.env.cleanup()

    def _push(self, d, files, message='m'):
        for rel, content in files.items(): _write(d, rel, content)
        self.sync.commit(d, message=message); return self.sync.push(d)

    def _server_index(self):
        raw = self.api._store[f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}']
        return Schema__Branch_Index.from_json(json.loads(self.env.crypto.decrypt(self.c.read_key, raw)))

    def _local_index(self, d):
        c = self.sync._init_components(d)
        return c.branch_manager.load_branch_index(d, c.branch_index_file_id, c.read_key)

    def _head(self, d):
        c = self.sync._init_components(d)
        cfg = self.sync._read_local_config(d, c.storage)
        meta = c.branch_manager.get_branch_by_id(self._local_index(d), str(cfg.my_branch_id))
        return c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)


# ------------------------------------------------- 1. signatures-required

class Test_Signature_Policy__Long_Lived_Clone(_Base):

    def _new_teammate(self):
        carol = os.path.join(self.env.tmp_dir, 'carol')
        self.sync.clone(self.env.vault_key, carol)
        return carol

    def test_a_clone_older_than_a_teammate_accepts_the_teammates_signed_commits(self):
        self.sync.set_format(self.alice, add_features=[FEATURE_SIG_REQUIRED])
        carol = self._new_teammate()                                     # registered after alice's clone was made
        c3 = self._push(carol, {'a.txt': 'from carol'}, 'c3')['commit_id']
        assert self.sync.pull(self.alice)['status'] == 'merged'          # 0.20.0: "c3 is no-key; the pull was refused"
        assert _read(self.alice, 'a.txt') == 'from carol'
        c4 = self._push(carol, {'b.txt': 'from carol'}, 'c4')['commit_id']
        assert self.sync.pull(self.alice)['status'] == 'merged'          # and every later one
        rep = self.sync.verify_signatures(self.alice)
        assert rep['counts']['no-key'] == 0 and rep['counts']['bad'] == 0 and c3 and c4

    def test_check_verify_fetches_a_teammates_key(self):
        carol = self._new_teammate()
        self._push(carol, {'a.txt': 'from carol'}, 'c3')
        self.sync.pull(self.bob)                                         # bob's own pull already fetches it ...
        self.sync.pull(self.alice)
        keys = os.path.join(self.alice, '.sg_vault', 'bare', 'keys')
        for name in os.listdir(keys):                                    # ... so drop alice's copies to test verify itself
            if name not in {str(b.public_key_id) for b in self._local_index(self.alice).branches
                            if str(b.branch_id) == str(self.sync._read_local_config(self.alice, self.c.storage).my_branch_id)}:
                os.remove(os.path.join(keys, name))
        rep = self.sync.verify_signatures(self.alice)
        assert rep['counts']['no-key'] == 0 and rep['counts']['verified'] == rep['total']

    def test_the_owner_can_switch_the_policy_off_for_a_stale_clone(self):
        self.sync.set_format(self.alice, add_features=[FEATURE_SIG_REQUIRED])
        self.sync.pull(self.bob)                                         # bob's local index now carries the policy
        assert Vault__Format().has_feature(self._local_index(self.bob), FEATURE_SIG_REQUIRED)
        self.sync.set_format(self.alice, remove_features=[FEATURE_SIG_REQUIRED])
        self._push(self.alice, {'a.txt': 'after'}, 'after')
        self.sync.pull(self.bob)
        assert not Vault__Format().has_feature(self._local_index(self.bob), FEATURE_SIG_REQUIRED)
        assert not Vault__Format().has_feature(self._server_index(), FEATURE_SIG_REQUIRED)   # and not written back

    def test_set_format_from_a_stale_clone_keeps_the_gate_the_server_has(self):
        self.sync.set_format(self.alice, format=2)
        self.sync.set_format(self.bob, add_features=[FEATURE_SIG_REQUIRED])  # bob never pulled the raise
        idx = self._server_index()
        assert Vault__Format().format_of(idx) == 2 and Vault__Format().has_feature(idx, FEATURE_SIG_REQUIRED)

    def test_an_owner_write_always_carries_an_explicit_format(self):
        self.sync.set_format(self.alice, add_features=[FEATURE_SIG_REQUIRED])
        self.sync.set_format(self.alice, remove_features=[FEATURE_SIG_REQUIRED])
        idx = self._server_index()
        assert idx.format == 1 and Vault__Index_Sync().has_gate(idx)


# ------------------------------------------------------ 2. accepted rewind

class Test_Accept_Rewind__Drops_The_Removed_Commits(_Base):

    def _rollback_server_ref_to(self, commit_id):
        named = next(b for b in self._server_index().branches if str(b.name) == 'current')
        self.api._store[f'{self.vid}/bare/refs/{named.head_ref_id}'] = self.c.ref_manager.encrypt_ref_value(commit_id, self.c.read_key)

    def _ancestors(self, d, head):
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        from sgit_ai.crypto.PKI__Crypto    import PKI__Crypto
        c  = self.sync._init_components(d)
        vc = Vault__Commit(crypto=self.env.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        seen, queue = set(), [head]
        while queue:
            cid = queue.pop()
            if cid and cid not in seen and c.obj_store.exists(cid):
                seen.add(cid); queue.extend(str(p) for p in (vc.load_commit(cid, c.read_key).parents or []))
        return seen

    def _rewind(self):
        c1 = self._push(self.bob, {'a.txt': 'a v2'}, 'c1')['commit_id']
        c2 = self._push(self.bob, {'a.txt': 'a v3'}, 'c2')['commit_id']   # the commit the owner removes
        self.sync.pull(self.alice)
        self._rollback_server_ref_to(c1)
        return c1, c2

    def test_a_clone_with_no_work_of_its_own_moves_to_the_new_head(self):
        c1, c2 = self._rewind()
        r = self.sync.pull(self.alice, accept_rewind=True)
        assert r['rewound'] is True and r['reapplied'] is False
        assert self._head(self.alice) == c1 and _read(self.alice, 'a.txt') == 'a v2'
        st = self.sync.status(self.alice)
        assert st['push_status'] == 'up_to_date', st                     # 0.20.0: "1 ahead … run: sgit push"
        self.sync.push(self.alice)
        assert c2 not in self._ancestors(self.alice, self._head(self.alice))

    def test_own_work_is_re_applied_on_top_and_the_removed_commit_is_not_pushed_back(self):
        c1, c2 = self._rewind()
        _write(self.alice, 'b.txt', 'b mine'); self.sync.commit(self.alice, message='mine')
        r = self.sync.pull(self.alice, accept_rewind=True)
        assert r['rewound'] is True and r['reapplied'] is True
        head = self._head(self.alice)
        assert c2 not in self._ancestors(self.alice, head) and c1 in self._ancestors(self.alice, head)
        assert _read(self.alice, 'a.txt') == 'a v2' and _read(self.alice, 'b.txt') == 'b mine'
        self.sync.push(self.alice)
        self.sync.pull(self.bob, accept_rewind=True)
        assert _read(self.bob, 'a.txt') == 'a v2' and _read(self.bob, 'b.txt') == 'b mine'
        assert c2 not in self._ancestors(self.bob, self._head(self.bob))

    def test_own_work_that_conflicts_with_the_rewind_refuses_and_changes_nothing(self):
        c1, c2 = self._rewind()
        _write(self.alice, 'a.txt', 'a mine'); self.sync.commit(self.alice, message='mine on a')
        before = self._head(self.alice)
        with pytest.raises(Vault__Ref_Rewind_Error, match='a.txt'):
            self.sync.pull(self.alice, accept_rewind=True)
        assert self._head(self.alice) == before and _read(self.alice, 'a.txt') == 'a mine'


# ------------------------------------------------ 3. no write access: quiet

class _No_Write_API(Vault__API__In_Memory):
    def batch(self, vault_id, write_key, operations):
        if any(op.get('op', '').startswith('write') for op in operations):
            raise RuntimeError('HTTP 401 Unauthorized')
        return super().batch(vault_id, write_key, operations)


class Test_Index_Refresh__Without_Write_Access(_Base):

    def test_refresh_merges_locally_and_does_not_raise(self):
        before = len(self._local_index(self.alice).branches)
        named  = next(b for b in self._server_index().branches if str(b.name) == 'current')
        single = Schema__Branch_Index(schema='branch_index_v1', branches=[named])
        self.api._store[f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}'] = \
            Vault__Index_Sync(crypto=self.env.crypto).encrypt(single, self.c.read_key)
        ro = _No_Write_API(); ro.setup(); ro._store = self.api._store
        out = Vault__Index_Sync(crypto=self.env.crypto, api=ro).refresh(self.c, self.alice, write_key=str(self.c.write_key))
        assert out['remote'] is True and out['uploaded'] is False
        assert len(self._local_index(self.alice).branches) == before      # nothing lost locally


# --------------------------------------------- 4. the id history log prints

class Test_Short_Commit_Ids(_Base):

    def test_reset_and_show_accept_the_hex_history_log_prints(self):
        c1 = self._push(self.alice, {'a.txt': 'a v2'}, 'c1')['commit_id']
        self._push(self.alice, {'a.txt': 'a v3'}, 'c2')
        short = c1[len('obj-cas-imm-'):]
        from sgit_ai.core.actions.diff.Vault__Diff import Vault__Diff
        info, _ = Vault__Diff(crypto=self.env.crypto).show_commit(self.alice, short)
        assert info['commit_id'] == c1
        assert self.sync.reset(self.alice, short[:8])['commit_id'] == c1
        assert _read(self.alice, 'a.txt') == 'a v2'

    def test_an_ambiguous_prefix_is_refused_by_name(self):
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        store = Vault__Object_Store(vault_path=os.path.join(self.env.tmp_dir, 'ambig'), crypto=self.env.crypto)
        data  = os.path.join(self.env.tmp_dir, 'ambig', 'bare', 'data'); os.makedirs(data)
        for oid in ('obj-cas-imm-abcd00000001', 'obj-cas-imm-abcd00000002'):
            open(os.path.join(data, oid), 'wb').close()
        assert store.resolve_id('abcd00000001') == 'obj-cas-imm-abcd00000001'
        with pytest.raises(ValueError, match='ambiguous'):
            store.resolve_id('abcd')
        assert store.resolve_id('ffff') == 'ffff'                        # no match: unchanged, the caller reports it
        assert store.resolve_id('../etc') == '../etc'                    # not hex: never globbed
