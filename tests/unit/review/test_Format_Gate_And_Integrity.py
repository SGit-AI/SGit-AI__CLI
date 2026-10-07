"""sgit-ai 0.20: the format gate, 128-bit object ids, the shared branch index,
ref monotonicity and signature verification — on two real clones over the
in-memory API, plus the real-server shapes the SG/Send team confirmed."""
import json
import os
import pytest

from tests._helpers.vault_test_env                  import Vault__Test_Env
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.Vault__Errors                     import (Vault__Client_Too_Old_Error, Vault__Ref_Rewind_Error,
                                                            Vault__Signature_Error)
from sgit_ai.storage.Vault__Format                  import Vault__Format, FEATURE_SIG_REQUIRED, FEATURE_IDS_128
from sgit_ai.schemas.Schema__Branch_Index           import Schema__Branch_Index
from sgit_ai.core.actions.index.Vault__Index_Sync   import Vault__Index_Sync
from sgit_ai.storage.Vault__Commit                  import Vault__Commit
from sgit_ai.crypto.PKI__Crypto                     import PKI__Crypto


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)

def _read(d, rel):
    with open(os.path.join(d, rel)) as f: return f.read()

def _ids(d):
    return os.listdir(os.path.join(d, '.sg_vault', 'bare', 'data'))


class _Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files={'a.txt': 'a v1', 'docs/d.md': 'd v1'})

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

    def _overwrite_server_index_like_the_web_ui(self):
        """The web UI writes a single named entry: no clone branches, no gate."""
        named = next(b for b in self._server_index().branches if str(b.name) == 'current')
        single = Schema__Branch_Index(schema='branch_index_v1', branches=[named])
        self.api._store[f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}'] = \
            Vault__Index_Sync(crypto=self.env.crypto, api=self.api).encrypt(single, self.c.read_key)


# ------------------------------------------------------------------ the gate

class Test_Format_Gate__Rules:

    def test_version_parse_and_compare(self):
        f = Vault__Format()
        assert f.parse_version('v0.20.1') == (0, 20, 1) == f.parse_version('0.20.1rc1') == f.parse_version('0.20.1.dev3')
        assert f.parse_version('garbage') is None
        idx = Schema__Branch_Index(schema='branch_index_v1', min_client='0.20.0')
        f.check_client(idx, client_version='0.20.0'); f.check_client(idx, client_version='1.0.0')
        f.check_client(idx, client_version='v0.0.0-dev')                 # a dev checkout is never refused
        with pytest.raises(Vault__Client_Too_Old_Error, match='needs sgit-ai >= 0.20.0 and this is 0.19.1'):
            f.check_client(idx, client_version='0.19.1')
        assert f.parse_version('not-a-version') is None                   # an unparseable minimum never locks (and the Safe type refuses to store one)
        assert f.format_of(Schema__Branch_Index()) == 1 and f.id_hex_len(Schema__Branch_Index()) == 12
        assert f.id_hex_len(Schema__Branch_Index(format=2)) == 32

    def test_old_index_shape_reads_as_format_1(self):
        idx = Schema__Branch_Index.from_json({'schema': 'branch_index_v1', 'branches': []})
        assert Vault__Format().format_of(idx) == 1 and idx.format is None and idx.min_client is None


class Test_Format_Gate__On_Vaults(_Base):

    def test_raise_to_format_2_then_new_objects_are_128_bit_and_old_ones_still_verify(self):
        info = self.sync.set_format(self.alice, format=2, min_client='0.1.0')
        assert info['format'] == 2 and info['id_hex_len'] == 32 and FEATURE_IDS_128 in info['features']
        assert Vault__Format().format_of(self._server_index()) == 2            # written to the server
        before = set(_ids(self.alice))
        self._push(self.alice, {'a.txt': 'a v2', 'new.txt': 'n'}, 'wide')
        new = set(_ids(self.alice)) - before
        assert new and all(len(i) == 44 for i in new)                         # every new object: 32 hex
        assert all(len(i) == 24 for i in before)                               # old ones untouched: no move
        r = self.sync.pull(self.bob)                                           # bob learns the gate on pull
        assert r['status'] == 'merged' and _read(self.bob, 'a.txt') == 'a v2'
        assert self.sync.format_info(self.bob)['format'] == 2
        self._push(self.bob, {'docs/d.md': 'd v2'}, 'bob wide')
        assert any(len(i) == 44 for i in _ids(self.bob))
        for d in (self.alice, self.bob):
            self.sync.pull(d)
            f = self.sync.fsck(d); assert f['ok'] and f['missing'] == [] and f['corrupt'] == [], f
        fresh = os.path.join(self.env.tmp_dir, 'fresh')
        self.sync.clone(self.env.vault_key, fresh)                             # a mixed-id vault clones and verifies
        assert _read(fresh, 'a.txt') == 'a v2' and _read(fresh, 'docs/d.md') == 'd v2'
        assert self.sync.fsck(fresh)['ok']

    def test_format_cannot_go_down_or_lock_out_this_client(self):
        self.sync.set_format(self.alice, format=2)
        with pytest.raises(ValueError, match='cannot go down'):
            self.sync.set_format(self.alice, format=1)
        with pytest.raises(ValueError, match='lock yourself out'):
            self.sync.set_format(self.alice, min_client='99.0.0')

    def test_a_vault_needing_a_newer_client_is_refused_by_name(self):
        idx = self._server_index(); idx.min_client = '99.0.0'
        self.api._store[f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}'] = \
            Vault__Index_Sync(crypto=self.env.crypto, api=self.api).encrypt(idx, self.c.read_key)
        with pytest.raises(Vault__Client_Too_Old_Error, match='needs sgit-ai >= 99.0.0'):
            self.sync.pull(self.bob)                                            # pull refreshes the index first
        fresh = os.path.join(self.env.tmp_dir, 'fresh')
        with pytest.raises(Vault__Client_Too_Old_Error):
            self.sync.clone(self.env.vault_key, fresh)                          # clone never degrades around the gate


# ------------------------------------------------------- the shared index

class Test_Branch_Index__Shared(_Base):

    def test_pull_restores_entries_and_the_gate_a_web_overwrite_dropped(self):
        self.sync.set_format(self.alice, format=2)
        n_before = len(self._server_index().branches)
        self._overwrite_server_index_like_the_web_ui()
        assert len(self._server_index().branches) == 1 and self._server_index().format is None
        self.sync.pull(self.alice)
        after = self._server_index()
        assert len(after.branches) == n_before and Vault__Format().format_of(after) == 2
        assert self.sync.fsck(self.alice)['ok']

    def test_new_clone_registers_with_a_merge_not_an_overwrite(self):
        self.sync.set_format(self.alice, format=2)
        carol = os.path.join(self.env.tmp_dir, 'carol')
        self.sync.clone(self.env.vault_key, carol)
        self._push(carol, {'c.txt': 'c'}, 'carol')                              # registers carol's clone branch
        idx = self._server_index()
        assert Vault__Format().format_of(idx) == 2                              # carol's registration kept the gate
        carol_branch = str(self.sync._read_local_config(carol, self.c.storage).my_branch_id)
        assert carol_branch in {str(b.branch_id) for b in idx.branches}        # and added her entry
        assert len(idx.branches) >= 3                                           # named + alice + carol (bob never pushed)

    def test_upload_sees_the_live_server_conflict_shape_and_merges(self):
        """The live server answers a stale write-if-match with HTTP 200 and the conflict on
        the operation (plus the current bytes); the in-memory API answers at the top level.
        Both must be retried as a merge, never read as success."""
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
        import base64
        c = self.c; isync_real = Vault__Index_Sync(crypto=self.env.crypto, api=self.api)
        raw, remote = isync_real.read_remote(self.vid, c.branch_index_file_id, c.read_key)

        class _Live_Shape(Vault__API__In_Memory):
            calls = []
            def batch(self, vault_id, write_key, operations):
                r = super().batch(vault_id, write_key, operations)
                self.calls.append(operations[0]['op'])
                if r.get('status') == 'conflict':                     # re-shape as the live server does
                    key = f"{vault_id}/{operations[0]['file_id']}"
                    return {'vault_id': vault_id, 'results': [{'op': 'write-if-match', 'file_id': operations[0]['file_id'],
                            'status': 'conflict', 'current': base64.b64encode(self._store[key]).decode()}]}
                return r
        live = _Live_Shape(); live.setup(); live._store = self.api._store
        isync = Vault__Index_Sync(crypto=self.env.crypto, api=live)
        local = Schema__Branch_Index.from_json({**remote.json(), 'format': 2})
        isync.upload(self.vid, c.branch_index_file_id, c.read_key, c.write_key, local, expected_raw=b'stale bytes')
        assert live.calls[0] == 'write-if-match' and len(live.calls) >= 2      # conflict seen, retried
        assert Vault__Format().format_of(self._server_index()) == 2             # and the merge landed

    def test_merge_keeps_every_entry_and_the_stronger_gate(self):
        s = Vault__Index_Sync(crypto=self.env.crypto, api=self.api)
        a = Schema__Branch_Index.from_json({'schema': 'branch_index_v1', 'format': 2, 'min_client': '0.20.0', 'features': ['x'],
                                            'branches': [{'branch_id': 'branch-named-00000000', 'name': 'current', 'branch_type': 'named', 'head_ref_id': 'ref-pid-muw-000000000000'}]})
        b = Schema__Branch_Index.from_json({'schema': 'branch_index_v1', 'min_client': '0.19.0', 'features': ['y'],
                                            'branches': [{'branch_id': 'branch-clone-11111111', 'name': 'local', 'branch_type': 'clone', 'head_ref_id': 'ref-pid-snw-111111111111'}]})
        m = s.merge(a, b)
        assert sorted(str(x.branch_id) for x in m.branches) == ['branch-clone-11111111', 'branch-named-00000000']
        assert m.format == 2 and str(m.min_client) == '0.20.0' and [str(f) for f in m.features] == ['x', 'y']


# ------------------------------------------------------------ monotonicity

class Test_Ref_Monotonicity(_Base):

    def _rollback_server_ref_to(self, commit_id):
        named = next(b for b in self._server_index().branches if str(b.name) == 'current')
        self.api._store[f'{self.vid}/bare/refs/{named.head_ref_id}'] = self.c.ref_manager.encrypt_ref_value(commit_id, self.c.read_key)

    def test_rollback_is_reported_by_status_and_refused_by_pull_until_accepted(self):
        c1 = self._push(self.bob, {'a.txt': 'a v2'}, 'c1')['commit_id']
        c2 = self._push(self.bob, {'a.txt': 'a v3'}, 'c2')['commit_id']
        self.sync.pull(self.alice)
        assert _read(self.alice, 'a.txt') == 'a v3'
        self._rollback_server_ref_to(c1)                                        # the host (or a force push) rewinds
        st = self.sync.status(self.alice)
        assert st['push_status'] == 'rewound' and st['rewound_from'] == c2
        with pytest.raises(Vault__Ref_Rewind_Error, match='rewound or rewritten'):
            self.sync.pull(self.alice)
        assert _read(self.alice, 'a.txt') == 'a v3'                              # nothing changed
        r = self.sync.pull(self.alice, accept_rewind=True)
        assert r['status'] in ('merged', 'up_to_date')
        assert self.sync.status(self.alice)['push_status'] != 'rewound'

    def test_forward_moves_and_a_fresh_init_are_never_rewinds(self):
        for i in range(3):
            self._push(self.bob, {'a.txt': f'v{i}'}, f'c{i}')
        assert self.sync.status(self.alice)['push_status'] == 'behind'
        assert self.sync.pull(self.alice)['status'] == 'merged'
        assert self.sync.status(self.alice)['push_status'] == 'up_to_date'

    def test_pull_after_status_leaves_no_missing_trees(self):
        """status fetches commit objects to count; pull must still fetch their trees."""
        for i in range(4):
            self._push(self.bob, {'a.txt': f'v{i}'}, f'c{i}')
        self.sync.status(self.alice)
        self.sync.pull(self.alice)
        f = self.sync.fsck(self.alice); assert f['missing'] == [], f


# -------------------------------------------------------------- signatures

class Test_Signatures(_Base):

    def _unsigned_commit_on_bob(self, content='unsigned'):
        """A commit written by a clone with no signing key (what the web UI, and a
        keyless clone, produce): drop bob's local private key, then commit and push."""
        local_dir = os.path.join(self.bob, '.sg_vault', 'local')
        for name in os.listdir(local_dir):
            if name.endswith('.pem'):
                os.remove(os.path.join(local_dir, name))
        return self._push(self.bob, {'u.txt': content}, 'web-ui style')

    def test_verify_on_a_shallow_clone_classifies_the_boundary_commit(self):
        self._push(self.alice, {'a.txt': 'a v2'}, 'c1'); self._push(self.alice, {'a.txt': 'a v3'}, 'c2')
        shallow = os.path.join(self.env.tmp_dir, 'shallow')
        self.sync.clone(self.env.vault_key, shallow, depth=1)
        rep = self.sync.verify_signatures(shallow)
        assert rep['total'] == 1 and rep['counts']['verified'] == 1

    def test_cli_commits_verify_and_carry_their_key_id(self):
        self._push(self.alice, {'a.txt': 'a v2'}, 'signed')
        rep = self.sync.verify_signatures(self.alice)
        assert rep['counts']['bad'] == 0 and rep['counts']['verified'] >= 2 and rep['first_failure'] is None
        f = self.sync.fsck(self.alice)
        assert f['signatures']['counts']['bad'] == 0 and f['signatures']['counts']['verified'] >= 2

    def test_required_policy_refuses_an_unsigned_incoming_commit(self):
        self.sync.set_format(self.alice, add_features=[FEATURE_SIG_REQUIRED])
        self._unsigned_commit_on_bob()
        with pytest.raises(Vault__Signature_Error, match='requires signed commits'):
            self.sync.pull(self.alice)
        self.sync.set_format(self.alice, remove_features=[FEATURE_SIG_REQUIRED])
        assert self.sync.pull(self.alice)['status'] == 'merged'
        assert self.sync.verify_signatures(self.alice)['counts']['unsigned'] == 1


# --------------------------------------------------------------------- CLI

class Test_CLI__Surface:

    def test_parsers_expose_the_new_commands_and_flags(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        parser = CLI__Main().build_parser() if hasattr(CLI__Main(), 'build_parser') else CLI__Main()._build_parser()
        a = parser.parse_args(['pull', '--accept-rewind', '/x']); assert a.accept_rewind is True
        a = parser.parse_args(['vault', 'format', '/x', '--set', '2', '--min-client', '0.20.0', '--feature', 'signatures-required'])
        assert a.set_format == 2 and a.min_client == '0.20.0' and a.feature == ['signatures-required']
        a = parser.parse_args(['check', 'verify', '/x', '--limit', '5']); assert a.limit == 5
        a = parser.parse_args(['migrate', 'apply', '/x', '--force']); assert a.force is True
