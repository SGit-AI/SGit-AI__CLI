"""Fixed in 0.21.1 — PKI stores built paths from an unvalidated fingerprint.

Threat model: TM-F32. Found by the round-1 security review (sharp-edges SE-001,
`review/findings/sharp-edges.json`): `sgit pki delete <fingerprint>` joined the argv string
into `<sg-send-dir>/keys/<fingerprint>` and rmtree'd it, so `..` emptied `~/.sg-send`
(credential store, keyring and keys) before failing on the final rmdir. The read paths
(`pki export`, keyring lookups) followed the same join.

Every test here performed the attack and succeeded on the code before the fix; the
controls pass on both.
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.PKI__Crypto           import PKI__Crypto
from sgit_ai.crypto.pki.PKI__Key_Store    import PKI__Key_Store
from sgit_ai.crypto.pki.PKI__Keyring      import PKI__Keyring

_pki        = PKI__Crypto()
_PASSPHRASE = 'test-passphrase'
_GOLDEN     = tempfile.mkdtemp(prefix='sgit-pki-golden-')            # one RSA-4096 generation per worker
_GOLDEN_FP  = PKI__Key_Store(keys_dir=os.path.join(_GOLDEN, 'keys'), crypto=_pki) \
                  .generate_and_store('golden', _PASSPHRASE)['encryption_fingerprint']

# Every hostile value stays inside the sandbox even on the code before the fix: the sg-send
# home sits three directories below the sandbox root, and nothing here climbs more than two.
# Absolute paths are tested on the read paths only (they open files; they never delete).
HOSTILE          = ['..', '../..', 'sha256:../x', '../keys', 'sha256:0123456789abcdef/..', '', ' ']
HOSTILE_ABSOLUTE = ['/', '/etc']


class Test_Fixed__PKI_Key_Store_Paths:
    """The keys folder sits inside the sg-send home next to vaults.enc and keyring/."""

    def setup_method(self):
        self.sandbox = tempfile.mkdtemp(prefix='sgit-pki-sandbox-')
        self.home    = os.path.join(self.sandbox, 'level1', 'level2', 'sg-send')
        shutil.copytree(os.path.join(_GOLDEN, 'keys'), os.path.join(self.home, 'keys'))
        with open(os.path.join(self.home, 'vaults.enc'), 'wb') as f:
            f.write(b'credential store stand-in')
        os.makedirs(os.path.join(self.home, 'keyring'))
        self.store = PKI__Key_Store(keys_dir=os.path.join(self.home, 'keys'), crypto=_pki)
        self.before = self._snapshot()

    def teardown_method(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def _snapshot(self):
        out = []
        for root, dirs, files in os.walk(self.home):
            for name in sorted(dirs) + sorted(files):
                out.append(os.path.relpath(os.path.join(root, name), self.home))
        return sorted(out)

    @pytest.mark.parametrize('fingerprint', HOSTILE)
    def test_delete_key_refuses_anything_that_is_not_a_fingerprint_and_touches_nothing(self, fingerprint):
        """Before: delete_key('..') removed vaults.enc, keyring/ and keys/ from the sg-send
        home (rmtree walked the parent) and raised FileNotFoundError at the end."""
        with pytest.raises(ValueError):
            self.store.delete_key(fingerprint)
        assert self._snapshot() == self.before

    @pytest.mark.parametrize('fingerprint', HOSTILE + HOSTILE_ABSOLUTE)
    def test_read_paths_refuse_anything_that_is_not_a_fingerprint(self, fingerprint):
        """Before: export_public_bundle('../x') opened <home>/x/public_key.pem; load_key_pair the same."""
        with pytest.raises(ValueError):
            self.store.export_public_bundle(fingerprint)
        with pytest.raises(ValueError):
            self.store.load_key_pair(fingerprint, _PASSPHRASE)
        assert self._snapshot() == self.before

    def test_control__a_real_fingerprint_still_deletes_its_own_folder_only(self):
        assert self.store.export_public_bundle(_GOLDEN_FP)['fingerprint'] == _GOLDEN_FP
        assert self.store.delete_key(_GOLDEN_FP) is True
        assert not os.path.isdir(os.path.join(self.home, 'keys', _GOLDEN_FP.replace(':', '_')))
        assert os.path.isfile(os.path.join(self.home, 'vaults.enc'))
        assert os.path.isdir(os.path.join(self.home, 'keyring'))

    def test_control__a_fingerprint_is_normalised_not_refused(self):
        """Upper case and surrounding whitespace are the type's business (lower-cased, trimmed);
        they never become a different path."""
        assert self.store.export_public_bundle(' ' + _GOLDEN_FP.upper() + ' ')['fingerprint'] == _GOLDEN_FP

    def test_control__an_unknown_but_well_formed_fingerprint_is_simply_not_found(self):
        assert self.store.delete_key('sha256:0123456789abcdef') is False
        assert self.store.export_public_bundle('sha256:0123456789abcdef') is None
        assert self.store.load_key_pair('sha256:0123456789abcdef', _PASSPHRASE) is None


class Test_Fixed__PKI_Keyring_Paths:

    def setup_method(self):
        self.sandbox = tempfile.mkdtemp(prefix='sgit-pki-sandbox-')
        self.home    = os.path.join(self.sandbox, 'level1', 'level2', 'sg-send')
        os.makedirs(self.home)
        self.keyring = PKI__Keyring(keyring_dir=os.path.join(self.home, 'keyring'))
        with open(os.path.join(self.home, 'outside.json'), 'w') as f:
            f.write('{"label": "planted"}')

    def teardown_method(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    @pytest.mark.parametrize('fingerprint', HOSTILE + HOSTILE_ABSOLUTE + ['../outside'])
    def test_contact_paths_refuse_anything_that_is_not_a_fingerprint(self, fingerprint):
        """Before: get_contact('../outside') read <home>/outside.json; add_contact wrote there;
        remove_contact deleted it. A lookup answers 'unknown' (no path is built); a write or
        a delete refuses."""
        assert self.keyring.get_contact(fingerprint) is None
        with pytest.raises(ValueError):
            self.keyring.add_contact('x', fingerprint, 'pem')
        with pytest.raises(ValueError):
            self.keyring.remove_contact(fingerprint)
        assert os.path.isfile(os.path.join(self.home, 'outside.json'))

    def test_control__a_real_fingerprint_round_trips(self):
        fp = 'sha256:0123456789abcdef'
        self.keyring.add_contact('alice', fp, 'pem-enc', 'pem-sig', 'sha256:fedcba9876543210')
        assert self.keyring.get_contact(fp)['label'] == 'alice'
        assert self.keyring.lookup_by_signing_fingerprint('sha256:fedcba9876543210')['label'] == 'alice'
        assert self.keyring.remove_contact(fp) is True
        assert self.keyring.get_contact(fp) is None
