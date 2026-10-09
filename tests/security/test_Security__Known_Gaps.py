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
