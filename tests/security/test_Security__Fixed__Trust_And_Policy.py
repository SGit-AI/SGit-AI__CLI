"""Fixed after the 0.21.0 review — signing keys, the signature policy, rollback, tags.

Each test here was a `Known_Gaps` proof (or a bug found while closing one) and now
asserts the attack fails. Threat model rows: TM-R02, TM-R04, TM-R05, TM-R06, TM-F09,
TM-F10.
"""
import json
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Ref_Rewind_Error, Vault__Signature_Error, Vault__Tag_Error
from sgit_ai.core.actions.index.Vault__Index_Sync     import Vault__Index_Sync
from sgit_ai.core.actions.tag.Vault__Sync__Tag        import Vault__Sync__Tag
from sgit_ai.core.actions.verify.Vault__Signatures    import Vault__Signatures, VERIFIED
from sgit_ai.schemas.Schema__Object_Tag               import Schema__Object_Tag
from sgit_ai.schemas.Schema__Tag_Ref                  import Schema__Tag_Ref
from tests._helpers.vault_adversary                   import Vault__Adversary
from tests._helpers.vault_test_env                    import Vault__Test_Env


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _write(path: str, content: str) -> None:
    with open(path, 'w') as f:
        f.write(content)


class Test_Fixed__Signing_Keys:
    """TM-R02: the named branch's private key is never stored where a read-key
    holder can load it. TM-F09: a moved clone keeps signing."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'alpha'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()

    def teardown_method(self):
        self.s.cleanup()

    def _host_key_types(self, adv) -> list:
        prefix = f'{adv.vault_id}/bare/keys/'
        return [json.loads(adv.crypto.decrypt(adv.read_key, data)).get('type')
                for key, data in self.s.api._store.items() if key.startswith(prefix)]

    def test_a_new_vault_stores_no_private_key(self):
        adv = Vault__Adversary(self.s.api, self.s.vault_key)
        try:
            assert all(not b.private_key_id for b in adv.index().branches)
            types = self._host_key_types(adv)
            assert types and set(types) == {'public'}
        finally:
            adv.cleanup()

    def test_vault_move_drops_a_legacy_named_private_key(self):
        """A vault made before this fix has the named key in bare/keys; moving it to a
        new vault is the remediation: the new vault carries no private key."""
        c       = self.s.sync._init_components(self.s.vault_dir)
        index   = c.branch_manager.load_branch_index(self.s.vault_dir, c.branch_index_file_id, c.read_key)
        named   = c.branch_manager.get_branch_by_name(index, 'current')
        private, _public = c.key_manager.generate_branch_key_pair()
        legacy_id = 'key-rnd-imm-' + c.key_manager.generate_key_id()
        c.key_manager.store_private_key(legacy_id, private, c.read_key)                 # what older clients did
        named.private_key_id = legacy_id
        c.branch_manager.save_branch_index(self.s.vault_dir, index, c.read_key, index_file_id=c.branch_index_file_id)

        result  = self.s.sync.move(self.s.vault_dir, reason='drop legacy key')
        new_key = _read(os.path.join(self.s.vault_dir, '.sg_vault', 'local', 'vault_key')).strip()
        adv     = Vault__Adversary(self.s.api, new_key)
        try:
            assert adv.vault_id == str(result['new_vault_id'])
            assert all(not b.private_key_id for b in adv.index().branches)
            assert set(self._host_key_types(adv)) == {'public'}
        finally:
            adv.cleanup()

    def test_a_moved_clone_keeps_signing(self):
        """TM-F09: move did not carry the clone's .pem into the new vault, so every
        commit after a move was unsigned (and refused by teammates' pulls under
        `signatures-required`); the sentinel only verified because it used the
        shared named key."""
        self.s.sync.move(self.s.vault_dir, reason='keep signing')
        _write(os.path.join(self.s.vault_dir, 'b.txt'), 'after move')
        commit_id = self.s.sync.commit(self.s.vault_dir, 'after move')['commit_id']
        c     = self.s.sync._init_components(self.s.vault_dir)
        index = c.branch_manager.load_branch_index(self.s.vault_dir, c.branch_index_file_id, c.read_key)
        assert Vault__Signatures(crypto=self.s.crypto).status_of(c, c.read_key, commit_id, index) == VERIFIED


class Test_Fixed__Signature_Policy_And_Rollback:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'policy.md': 'pay alice'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s   = self._env.restore()
        self.adv = Vault__Adversary(self.s.api, self.s.vault_key)

    def teardown_method(self):
        self.adv.cleanup()
        self.s.cleanup()

    def _forge_on_named(self, files: dict, sign: bool, parent: str = None) -> str:
        self.adv.pull_host()
        named  = self.adv.named_branch()
        forged = self.adv.forge_commit(files, parent=parent or self.adv.head_of(named),
                                       branch_id=str(named.branch_id), sign=sign)
        self.adv.move_branch(named, forged)
        return forged

    def _policy_on(self):
        self.s.sync.set_format(self.s.alice_dir, add_features=['signatures-required'])

    def test_TM_R04__clone_refuses_an_unsigned_head(self):
        self._policy_on()
        self._forge_on_named({'policy.md': b'unsigned head'}, sign=False)
        carol = os.path.join(self.s.tmp_dir, 'carol')
        with pytest.raises(Vault__Signature_Error, match='clone was refused'):
            self.s.sync.clone(self.s.vault_key, carol)
        assert not os.path.exists(os.path.join(carol, 'policy.md'))

    @pytest.mark.parametrize('entry', ['clone_branch', 'clone_range'])
    def test_K3__every_clone_entry_point_checks_signatures(self, entry):
        """Review K3: the check was wired into clone and read-only clone only;
        clone-branch and clone-range took an unsigned head without a word."""
        self._policy_on()
        self._forge_on_named({'policy.md': b'unsigned head'}, sign=False)
        dest = os.path.join(self.s.tmp_dir, entry)
        with pytest.raises(Vault__Signature_Error):
            getattr(self.s.sync, entry)(self.s.vault_key, dest)

    def test_K2__a_refused_read_only_pull_refuses_again(self):
        """Review K2: the read-only pull wrote the server's ref and its baseline
        BEFORE the signature check, so the second pull saw "already up to date" and
        every later signed commit on top of the refused one passed."""
        keys = self.s.crypto.derive_keys_from_vault_key(self.s.vault_key)
        ro   = os.path.join(self.s.tmp_dir, 'reader')
        self.s.sync.clone_read_only(keys['vault_id'], keys['read_key'], ro)
        self._policy_on()
        self.s.sync.pull_read_only(ro)
        unsigned = self._forge_on_named({'policy.md': b'unsigned'}, sign=False)
        for _ in range(2):
            with pytest.raises(Vault__Signature_Error):
                self.s.sync.pull_read_only(ro)
        self._forge_on_named({'policy.md': b'signed on top'}, sign=True, parent=unsigned)
        with pytest.raises(Vault__Signature_Error):
            self.s.sync.pull_read_only(ro)
        assert _read(os.path.join(ro, 'policy.md')) == 'pay alice'

    def test_TM_R04__clone_refuses_an_unsigned_commit_under_a_signed_head(self):
        self._policy_on()
        hidden = self._forge_on_named({'policy.md': b'hidden unsigned'}, sign=False)
        self._forge_on_named({'policy.md': b'hidden unsigned', 'cover.md': b'x'}, sign=True, parent=hidden)
        with pytest.raises(Vault__Signature_Error):
            self.s.sync.clone(self.s.vault_key, os.path.join(self.s.tmp_dir, 'carol'))

    def test_TM_F10__history_from_before_the_policy_is_not_held_against_anyone(self):
        """The policy applies from when it is switched on (`signed-since-` records the
        head then). Before: pull walked past what the clone already held, so the first
        push after switching it on, in a vault with older unsigned commits, was refused;
        and a whole-history clone check would have refused such a vault outright."""
        self._forge_on_named({'policy.md': b'old client commit'}, sign=False)           # pre-policy, unsigned
        self.s.sync.pull(self.s.alice_dir)
        self.s.sync.pull(self.s.bob_dir)
        self._policy_on()
        assert any(f.startswith('signed-since-') for f in self.s.sync.format_info(self.s.alice_dir)['features'])

        _write(os.path.join(self.s.alice_dir, 'next.md'), 'signed')
        self.s.sync.commit(self.s.alice_dir, 'signed after policy')
        self.s.sync.push(self.s.alice_dir)                                              # was refused
        self.s.sync.pull(self.s.bob_dir)
        assert _read(os.path.join(self.s.bob_dir, 'next.md')) == 'signed'

        carol = os.path.join(self.s.tmp_dir, 'carol')
        self.s.sync.clone(self.s.vault_key, carol)
        assert _read(os.path.join(carol, 'policy.md')) == 'old client commit'

        self.s.sync.set_format(self.s.alice_dir, remove_features=['signatures-required'])
        assert not any(f.startswith('signed-since-') for f in self.s.sync.format_info(self.s.alice_dir)['features'])

    def test_TM_R05__read_only_clone_refuses_a_rollback(self):
        _write(os.path.join(self.s.alice_dir, 'policy.md'), 'v2')
        self.s.sync.commit(self.s.alice_dir, 'v2')
        self.s.sync.push(self.s.alice_dir)
        keys = self.s.crypto.derive_keys_from_vault_key(self.s.vault_key)
        ro   = os.path.join(self.s.tmp_dir, 'reader')
        self.s.sync.clone_read_only(keys['vault_id'], keys['read_key'], ro)

        self.adv.pull_host()
        self.adv.move_branch(self.adv.named_branch(), self.s.commit_id)                  # host rolls the branch back
        with pytest.raises(Vault__Ref_Rewind_Error):
            self.s.sync.pull_read_only(ro)
        assert _read(os.path.join(ro, 'policy.md')) == 'v2'

        self.s.sync.pull_read_only(ro, accept_rewind=True)                               # the reader can still choose to follow
        assert _read(os.path.join(ro, 'policy.md')) == 'pay alice'

    def test_TM_R05__read_only_clone_still_follows_forward_moves(self):
        keys = self.s.crypto.derive_keys_from_vault_key(self.s.vault_key)
        ro   = os.path.join(self.s.tmp_dir, 'reader')
        self.s.sync.clone_read_only(keys['vault_id'], keys['read_key'], ro)
        for n in (2, 3):
            _write(os.path.join(self.s.alice_dir, 'policy.md'), f'v{n}')
            self.s.sync.commit(self.s.alice_dir, f'v{n}')
            self.s.sync.push(self.s.alice_dir)
            self.s.sync.pull_read_only(ro)
            assert _read(os.path.join(ro, 'policy.md')) == f'v{n}'


class Test_Fixed__Tags:

    def test_TM_R06__a_far_future_entry_loses_to_an_honest_one(self):
        now      = 1_800_000_000_000
        future   = Schema__Tag_Ref(name='v1.0', tag_id='obj-cas-imm-aaaaaaaaaaaa', timestamp_ms=4_102_444_800_000)
        honest   = Schema__Tag_Ref(name='v1.0', tag_id='obj-cas-imm-bbbbbbbbbbbb', timestamp_ms=now - 1000)
        tomb     = Schema__Tag_Ref(name='v2.0', tag_id='obj-cas-imm-cccccccccccc', timestamp_ms=4_102_444_800_000, deleted=True)
        live     = Schema__Tag_Ref(name='v2.0', tag_id='obj-cas-imm-dddddddddddd', timestamp_ms=now - 1000)
        merged   = {t['name']: t for t in Vault__Index_Sync().merge_tags([honest, live], [future, tomb], now_ms=now)}
        assert merged['v1.0']['tag_id'] == 'obj-cas-imm-bbbbbbbbbbbb'
        assert merged['v2.0']['deleted'] is False

    def test_TM_R06__a_tag_within_clock_skew_still_wins(self):
        now   = 1_800_000_000_000
        older = Schema__Tag_Ref(name='v1', tag_id='obj-cas-imm-aaaaaaaaaaaa', timestamp_ms=now - 5000)
        newer = Schema__Tag_Ref(name='v1', tag_id='obj-cas-imm-bbbbbbbbbbbb', timestamp_ms=now + 3_600_000)   # an hour fast
        merged = Vault__Index_Sync().merge_tags([older], [newer], now_ms=now)
        assert merged[0]['tag_id'] == 'obj-cas-imm-bbbbbbbbbbbb'

    def test_TM_R06__an_unsigned_tag_is_not_resolved(self, tmp_path):
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.txt': 'alpha'})
        s   = env.restore()
        try:
            c     = s.sync._init_components(s.vault_dir)
            tag   = Schema__Object_Tag(schema='tag_v1', name='v-forged', commit_id=s.commit_id, message='',
                                       timestamp_ms=1_800_000_000_000)                       # no signature, no tagger key
            tag_id = c.obj_store.store(s.crypto.encrypt(c.read_key, json.dumps(tag.json()).encode()))
            index  = c.branch_manager.load_branch_index(s.vault_dir, c.branch_index_file_id, c.read_key)
            index.tags = Vault__Index_Sync().merge_tags(index.tags, [Schema__Tag_Ref(name='v-forged', tag_id=tag_id,
                                                                                       timestamp_ms=1_800_000_000_000)])
            c.branch_manager.save_branch_index(s.vault_dir, index, c.read_key, index_file_id=c.branch_index_file_id)
            with pytest.raises(Vault__Tag_Error, match='unsigned'):
                Vault__Sync__Tag(crypto=s.crypto, api=s.api).resolve(s.vault_dir, 'v-forged')
        finally:
            s.cleanup()
            env.cleanup_snapshot()
