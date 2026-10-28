"""Known gaps — each test PROVES a weakness the threat model accepts or has by design.

These are not regressions: every test here performs the attack and asserts that it
WORKS today. Each names the row of the risk register it is evidence for
(team/explorer/appsec/threat-model/v0.21.0__threat-model.md, section 6).

When one of these starts failing, the gap has closed (or moved): that is good news,
and the right change is to move the test to a `test_Security__Fixed__*` file with the
assertion inverted, and update the risk-register row in the same commit.
"""
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Signature_Error
from sgit_ai.core.actions.verify.Vault__Key_Fetch     import Vault__Key_Fetch
from sgit_ai.core.actions.verify.Vault__Signatures    import Vault__Signatures, VERIFIED
from sgit_ai.core.Vault__Ignore                       import Vault__Ignore
from sgit_ai.crypto.Vault__Crypto                     import Vault__Crypto
from sgit_ai.network.api.Vault__API                   import Vault__API
from sgit_ai.secrets.Secrets__Store                   import Secrets__Store
from tests._helpers.vault_adversary                   import Vault__Adversary
from tests._helpers.vault_test_env                    import Vault__Test_Env


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


class Test_Known_Gaps__Read_Key_Holder_With_Host_Access:
    """The write key is a bearer token checked by the host; it has no cryptographic
    role. Anyone with the READ key who can also write to the store (the host itself,
    a compromised host, an insider at the host, or someone the host colludes with)
    can therefore author history every clone accepts."""

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

    def _forge_on_named(self, content: bytes, sign: bool = True, parent: str = None) -> str:
        named  = self.adv.named_branch()
        forged = self.adv.forge_commit({'policy.md': content}, parent=parent or self.adv.head_of(named),
                                       branch_id=str(named.branch_id), sign=sign)
        self.adv.move_branch(named, forged)
        return forged

    def test_TM_R01__forged_commit_is_pulled_and_verifies(self):
        """TM-R01 (by design): a self-signed forgery lands on pull and `check verify`
        calls it verified — the verifier trusts any key that decrypts under the read key."""
        forged = self._forge_on_named(b'pay mallory')
        self.s.sync.pull(self.s.bob_dir)
        assert _read(os.path.join(self.s.bob_dir, 'policy.md')) == 'pay mallory'

        c     = self.s.sync._init_components(self.s.bob_dir)
        index = c.branch_manager.load_branch_index(self.s.bob_dir, c.branch_index_file_id, c.read_key)
        sigs  = Vault__Signatures(crypto=self.s.crypto, key_fetch=Vault__Key_Fetch(crypto=self.s.crypto, api=self.s.api))
        assert sigs.status_of(c, c.read_key, forged, index) == VERIFIED

    def test_TM_R01__signatures_required_stops_unsigned_but_not_self_signed(self):
        """TM-R01: `signatures-required` refuses an UNSIGNED forgery, but the same
        forgery signed with a key the adversary minted is accepted."""
        self.s.sync.set_format(self.s.alice_dir, add_features=['signatures-required'])
        self.s.sync.pull(self.s.bob_dir)
        self.adv.pull_host()
        honest_head = self.adv.head_of(self.adv.named_branch())

        self._forge_on_named(b'unsigned forgery', sign=False)
        with pytest.raises(Vault__Signature_Error):
            self.s.sync.pull(self.s.bob_dir)

        self._forge_on_named(b'self-signed forgery', sign=True, parent=honest_head)
        self.s.sync.pull(self.s.bob_dir)
        assert _read(os.path.join(self.s.bob_dir, 'policy.md')) == 'self-signed forgery'

    def test_TM_R27__a_legacy_named_private_key_stays_readable_until_the_vault_is_moved(self):
        """TM-R27 (accepted): vaults created before 10/09 stored the named branch's
        private key in bare/keys/ under the read key. New vaults do not; an existing
        one keeps it (readable by every read-key holder) until `sgit vault move`."""
        private, _public = self.adv.key_manager.generate_branch_key_pair()
        legacy_id = 'key-rnd-imm-' + self.adv.key_manager.generate_key_id()
        self.adv.key_manager.store_private_key(legacy_id, private, self.adv.read_key)   # what an older client wrote
        self.adv.push_host()
        reader = Vault__Adversary(self.s.api, self.s.vault_key)
        try:
            assert reader.key_manager.load_private_key(legacy_id, reader.read_key) is not None
        finally:
            reader.cleanup()

    def test_TM_R03__ref_ciphertext_is_not_bound_to_its_ref_id(self):
        """TM-R03 (accepted): refs are AES-GCM under the read key with no associated
        data, so the host can serve one ref's ciphertext under another ref's id and
        it decrypts as a valid head (e.g. point `current` at a stale clone branch)."""
        named      = self.adv.named_branch()
        other_ref  = 'ref-pid-snw-' + 'a' * 12
        self.adv.ref_manager.write_ref(other_ref, self.s.commit_id, self.adv.read_key)
        stale_ct   = open(os.path.join(self.adv.sg_dir, 'bare', 'refs', other_ref), 'rb').read()
        self.adv.host_write(f'bare/refs/{named.head_ref_id}', stale_ct)        # replayed under the named ref's id
        reader = Vault__Adversary(self.s.api, self.s.vault_key)
        try:
            assert reader.head_of(reader.named_branch()) == self.s.commit_id
        finally:
            reader.cleanup()


class Test_Known_Gaps__Metadata_And_Policy:
    """Cheap characterisations of accepted properties that need no vault history."""

    def test_TM_R07__format_1_object_ids_are_48_bits(self):
        """TM-R07 (accepted; format 2 fixes it): format-1 ids carry 12 hex = 48 bits
        of SHA-256, so a host can grind a colliding ciphertext in ~2^24 tries per
        target for the birthday case. Format 2 writes 32 hex (128 bits)."""
        crypto = Vault__Crypto()
        oid    = crypto.compute_object_id(b'any ciphertext')
        assert len(oid) - len('obj-cas-imm-') == 12
        assert len(crypto.compute_object_id(b'any ciphertext', 32)) - len('obj-cas-imm-') == 32

    def test_TM_R08__ciphertext_reveals_exact_plaintext_size(self):
        """TM-R08 (by design): AES-GCM adds a fixed 28 bytes (12 IV + 16 tag) and
        blobs are not padded, so the host learns each file's exact size."""
        crypto = Vault__Crypto()
        key    = os.urandom(32)
        for n in (0, 1, 1000, 65537):
            assert len(crypto.encrypt(key, b'x' * n)) == n + 28

    def test_TM_R38__pack_names_tell_the_host_the_commit_graph_shape(self):
        """TM-R38 (by design): a pack vault's host folder lists one zip per push named
        <epoch>__<commit id>__<bytes>; the zip's central directory lists each object id
        and size. The host learns when each push happened, which commit it carried, how
        many objects it added and their exact ciphertext sizes (TM-R08 per object), and
        can link a commit id to its pack. It learns no name, content or key."""
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        from tests._helpers.pack_env                import Pack__Env
        from tests._helpers.vault_test_env          import TEST_VAULT_KEYS
        import io, zipfile
        env = Pack__Env()
        sync, d, _ = env.pack_vault(env.text_files(2), vault_key=TEST_VAULT_KEYS[0])
        vid  = sync._init_components(d).vault_id
        name = [p for p in env.api.packs(vid) if '/indexes/' not in p][0]       # a data pack (an index pack sits beside it)
        info = Vault__Packs().parse_name(name)
        assert info['commit_id'].startswith('obj-cas-imm-') and info['epoch'] > 1700000000
        with zipfile.ZipFile(io.BytesIO(env.api.host_files(vid)[name])) as z:
            sizes = {i.filename: i.file_size for i in z.infolist()}
        assert len(sizes) >= 5 and all(n.startswith('bare/data/obj-cas-imm-') for n in sizes)   # ids and sizes, nothing else

    def test_TM_R40__a_deflated_blob_reveals_how_compressible_its_plaintext_is(self):
        """TM-R40 (accepted, pack vaults only): with 'blob-deflate' a blob is deflated
        before encryption and the ciphertext length is the compressed length (+ 33),
        so the host learns the plaintext's compressibility, not only its size
        (TM-R08). Two files of equal length — one prose, one random — are told apart."""
        crypto = Vault__Crypto(deflate_blobs=True)
        key    = os.urandom(32)
        prose  = b'the quick brown fox jumps over the lazy dog ' * 100
        noise  = os.urandom(len(prose))
        assert len(crypto.encrypt(key, prose, deflate=True)) < len(crypto.encrypt(key, noise, deflate=True)) == len(noise) + 28

    def test_TM_R42__an_index_pack_tells_the_host_its_member_sizes_and_count_and_nothing_else(self):
        """TM-R42 (accepted, pack vaults): the index pack beside a data pack is one more
        file whose size, member count and member ciphertext sizes the host sees; its
        member names are sequence numbers, and no path, name or type is in clear."""
        import io, zipfile
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index, PACK_INDEX_SNAPSHOTS, INDEX_HEADER_NAME
        from tests._helpers.pack_env                     import Pack__Env
        from tests._helpers.vault_test_env               import TEST_VAULT_KEYS
        env = Pack__Env()
        sync, d, _ = env.pack_vault({'secret-project/plan.md': b'the plan\n', 'notes.txt': b'n\n'}, vault_key=TEST_VAULT_KEYS[0])
        c    = sync._init_components(d)
        idx  = Vault__Pack_Index(crypto=sync.crypto, api=env.api)
        entry = idx.list_index_packs(str(c.vault_id), PACK_INDEX_SNAPSHOTS)[0]
        data  = idx.fetch_pack(str(c.vault_id), entry)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            sizes = {i.filename: i.file_size for i in z.infolist()}
        assert names[0] == INDEX_HEADER_NAME and all(n[len('index/'):].isdigit() for n in names[1:])   # what the host sees:
        assert len(sizes) >= 5 and all(s > 0 for s in sizes.values())                                 # a count and sizes
        assert b'secret-project' not in data and b'plan.md' not in data and b'flat' not in data          # and nothing of the names
        assert entry['size'] == len(data)                                                               # the name carries the size

    def test_TM_R42__a_signed_index_can_map_a_path_below_the_root_to_another_blob_until_verify_finds_it(self):
        """TM-R42 (accepted, narrowed 26 Oct): a commit index's folder members are anchored
        to their tree objects (test_Security__Fixed__Lying_Index); the snapshot index's
        `flat` is anchored to the head's root tree only, so a lie at its root is dropped
        and a lie below the root in a snapshot index signed by a write-key holder reaches
        a fresh clone's working copy with the standing of that holder's commit, and
        `sgit pack index verify` is what finds it. If this test fails, the reader now
        catches it: update the row, do not just edit the test."""
        import json, os
        from sgit_ai.core.actions.pack.Vault__Packs           import PACK_SNAPSHOTS
        from sgit_ai.core.actions.pack.Vault__Pack_Index      import Vault__Pack_Index
        from tests._helpers.pack_env                          import Pack__Env
        from tests._helpers.vault_test_env                    import TEST_VAULT_KEYS
        env = Pack__Env()
        sync, a, key = env.pack_vault({'raw/uk/a.txt': b'a\n', 'raw/uk/b.txt': b'bb\n', 'top.md': b'# top\n'}, vault_key=TEST_VAULT_KEYS[0])
        c    = sync._init_components(a)
        vid  = str(c.vault_id)
        idx  = Vault__Pack_Index(crypto=sync.crypto, api=env.api)
        snap = idx.list_folder(vid, PACK_SNAPSHOTS)[-1]
        old  = idx.index_pack_for(vid, PACK_SNAPSHOTS, snap)
        fields, members = idx.build_snapshot_members(os.path.join(a, '.sg_vault'), snap['commit_id'], c.read_key)
        doc = json.loads(members['flat'])
        doc['flat']['raw/uk/a.txt']['blob_id'] = doc['flat']['raw/uk/b.txt']['blob_id']      # below the root: a.txt -> b's bytes
        members['flat'] = idx.canonical_json(doc)
        signing_key, key_id = idx.signing_identity(a)                                        # signed by the pusher's own key
        out  = os.path.join(env.root, 'lying.zip')
        size = idx.write_index_pack(out, c.read_key, 'snapshot', fields, members, [snap['name']], signing_key=signing_key, author_key_id=key_id)
        env.api._store.pop(f'{vid}/{old["file_id"]}')
        with open(out, 'rb') as f:
            env.api._store[f'{vid}/{idx.index_folder_of(PACK_SNAPSHOTS)}{idx.pack_name(snap["commit_id"], size, epoch_s=snap["epoch"])}'] = f.read()
        sync_b, b = env.clone(key, 'b')
        assert env.tree(b)['raw/uk/a.txt'] == b'bb\n'                                        # the gap: what the index said
        from sgit_ai.storage.Vault__Sub_Tree import FLAT_CACHE
        FLAT_CACHE.clear()                                                                   # one process, two clones here
        report = idx.verify_indexes(a)
        assert not report['ok'] and {x['member'] for x in report['bad']} == {'flat'}                 # and what finds it

    def test_TM_R41__the_local_caches_hold_the_heads_paths_in_clear(self):
        """TM-R41 (accepted, same boundary as local/vault_key): the flatten cache and the
        scan cache under .sg_vault/local/ name every tracked path in clear, with sizes
        and content hashes. They are 0600 in the 0700 local folder, next to the key a
        reader of that folder already has."""
        import json, stat
        from tests._helpers.pack_env       import Pack__Env
        from tests._helpers.vault_test_env import TEST_VAULT_KEYS
        env = Pack__Env()
        sync, d, _ = env.normal_vault({'secret-project/plan.md': b'the plan\n'}, vault_key=TEST_VAULT_KEYS[0])
        import time
        old = time.time() - 10                                                       # outside the racy window:
        os.utime(os.path.join(d, 'secret-project', 'plan.md'), (old, old))           # a just-written file is not cached
        sync.status(d)
        local = os.path.join(d, '.sg_vault', 'local')
        flat  = [os.path.join(local, 'flat-cache', n) for n in os.listdir(os.path.join(local, 'flat-cache')) if n.endswith('.json')]
        scan  = os.path.join(local, 'scan-cache.json')
        assert flat and os.path.isfile(scan)
        assert all(stat.S_IMODE(os.stat(path).st_mode) == 0o600 for path in flat + [scan])
        def holds_the_path(path):
            with open(path) as f:
                return 'secret-project/plan.md' in json.dumps(json.load(f))      # the path, in clear
        assert holds_the_path(scan) and any(holds_the_path(p) for p in flat)        # (one cache file is the empty first tree)
        assert stat.S_IMODE(os.stat(os.path.join(local, 'vault_key')).st_mode) == 0o600   # the same boundary as the key

    def test_TM_R09__a_tracked_env_file_stays_tracked(self):
        """TM-R09 (by design, tracked-wins): `.env` is ignored by default, but once a
        head tracks it, every later edit to the local `.env` is committed and pushed."""
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('.env') is True
        ignore.tracked_paths = {'.env'}
        assert ignore.should_ignore_file('.env') is False

    def test_TM_R10__plain_http_base_url_is_accepted(self):
        """TM-R10 (accepted): a plain http:// server is allowed (the CLI only warns
        when a private key is used with it); TLS is not enforced by the client."""
        api = Vault__API(base_url='http://sgit.example.invalid').setup()
        assert str(api.base_url).startswith('http://')

    def test_TM_R11__secrets_store_uses_one_global_salt(self):
        """TM-R11 (accepted): the local credential store derives its key with a fixed
        salt, so equal passphrases give equal keys on every machine (one precomputed
        dictionary attacks every store)."""
        a = Secrets__Store(store_path='/nonexistent/a').derive_master_key('correct horse')
        b = Secrets__Store(store_path='/nonexistent/b').derive_master_key('correct horse')
        assert a == b


class Test_Known_Gaps__User_Signatures:
    """Git-parity 2.2 (design__02 §6): what user signatures do not protect, as in Git."""

    def setup_method(self):
        from tests.unit.crypto.signing.signing_keys import Signing_Keys
        self.keys = Signing_Keys()

    def teardown_method(self):
        self.keys.cleanup()

    def test_TM_R44__the_host_can_tell_a_user_signed_commit_by_its_size(self):
        import tempfile
        from sgit_ai.crypto.PKI__Crypto                    import PKI__Crypto
        from sgit_ai.crypto.signing.User__Signer           import User__Signer
        from sgit_ai.schemas.Schema__Signing_Config        import Schema__Signing_Config
        from sgit_ai.storage.Vault__Commit                 import Vault__Commit
        from sgit_ai.storage.Vault__Object_Store           import Vault__Object_Store
        _, key_path, _ = self.keys.make()
        crypto = Vault__Crypto()
        store  = Vault__Object_Store(vault_path=tempfile.mkdtemp(dir=self.keys.dir), crypto=crypto)
        vc     = Vault__Commit(crypto=crypto, pki=PKI__Crypto(), object_store=store)
        read_key, signer = bytes(32), User__Signer(config=Schema__Signing_Config(format='ssh', signing_key=key_path,
                                                                                  ssh_program='no-such-ssh-keygen'))
        plain  = vc.create_commit(read_key=read_key, tree_id='obj-cas-imm-1b397bef28b6', message='m', timestamp_ms=1)
        signed = vc.create_commit(read_key=read_key, tree_id='obj-cas-imm-1b397bef28b6', message='m', timestamp_ms=1,
                                  user_signer=signer)
        assert store.size_of(signed) - store.size_of(plain) > 250             # the host sees ciphertext sizes only

    def test_TM_R45__the_programs_that_run_come_from_the_users_own_git_config(self, monkeypatch):
        from sgit_ai.crypto.signing.Signing__Config__Resolver import Signing__Config__Resolver
        config_file = self.keys.write('gitconfig', '[gpg]\n\tprogram = /opt/whatever/gpg\n[gpg "ssh"]\n\tprogram = /opt/x/ssh-keygen\n')
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', config_file)
        monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
        config = Signing__Config__Resolver().resolve()
        assert (str(config.gpg_program), str(config.ssh_program)) == ('/opt/whatever/gpg', '/opt/x/ssh-keygen')

    def test_TM_R46__a_backdated_commit_is_judged_inside_a_closed_validity_window(self):
        import time
        from sgit_ai.crypto.signing.SSH__Sig__Verifier      import SSH__Sig__Verifier
        from sgit_ai.crypto.signing.SSH__Signer__In_Process import SSH__Signer__In_Process
        from sgit_ai.safe_types.Enum__User_Signature_Status import Enum__User_Signature_Status
        _, key_path, line = self.keys.make()
        allowed   = self.keys.write('allowed_signers', f'me@x valid-before="20250101Z" {line}\n')
        signature = SSH__Signer__In_Process().sign(b'payload', key_path)               # signed today, after the window
        backdated = SSH__Sig__Verifier().verify(signature, b'payload', 1_650_000_000_000, allowed)   # claims 2022
        assert backdated.status == Enum__User_Signature_Status.GOOD
        honest    = SSH__Sig__Verifier().verify(signature, b'payload', int(time.time() * 1000), allowed)
        assert honest.status == Enum__User_Signature_Status.UNTRUSTED
