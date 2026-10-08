"""Fixed in 0.21.0 — a hostile host serving other bytes, or no bytes.

Every object id is sha256(ciphertext), so a reader can check what the host serves
with no key and no trust. Clone, pull and fetch already did; fsck --repair, the
`vault move` auto-repair, sparse fetch/cat and the cache pointer did not, and clone
quietly checked out a HEAD with a file missing (which then read as deleted, so the
next commit deleted it for everyone). Presigned URLs from the host were followed
with any scheme and no timeout. Threat model: TM-F01, TM-F02, TM-F07.
The concurrent-push lost update (TM-F08) is covered by
tests/unit/review/test_Push__Concurrent_CAS.py.
"""
import os

import pytest

from sgit_ai.core.Vault__Errors                               import Vault__Integrity_Error
from sgit_ai.crypto.Vault__Crypto                             import Vault__Crypto
from sgit_ai.network.api.Vault__API                           import Vault__API
from sgit_ai.workflow.move.steps.Step__Move__Validate_Local   import Step__Move__Validate_Local
from tests._helpers.vault_test_env                            import Vault__Test_Env


class Test_Fixed__Host_Substitution:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'the real readme', 'docs/a.md': 'doc a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s        = self._env.restore()
        self.crypto   = Vault__Crypto()
        keys          = self.crypto.derive_keys_from_vault_key(self.s.vault_key)
        self.vault_id = keys['vault_id']
        self.read_key = keys['read_key_bytes']
        self.data_dir = os.path.join(self.s.vault_dir, '.sg_vault', 'bare', 'data')
        self.readme_blob = self._blob_holding(b'the real readme')

    def teardown_method(self):
        self.s.cleanup()

    def _blob_holding(self, plaintext: bytes) -> str:
        for name in os.listdir(self.data_dir):
            try:
                with open(os.path.join(self.data_dir, name), 'rb') as f:
                    if self.crypto.decrypt(self.read_key, f.read()) == plaintext:
                        return name
            except Exception:
                continue
        raise AssertionError('blob not found')

    def _host_serves(self, object_id: str, data):
        key = f'{self.vault_id}/bare/data/{object_id}'
        if data is None:
            self.s.api._store.pop(key, None)
        else:
            self.s.api._store[key] = data

    def _forged(self) -> bytes:
        return self.crypto.encrypt(self.read_key, b'the attacker readme')       # decrypts fine, wrong id

    def test_fsck_repair_refuses_substituted_bytes(self):
        os.remove(os.path.join(self.data_dir, self.readme_blob))
        self._host_serves(self.readme_blob, self._forged())
        result = self.s.sync.fsck(self.s.vault_dir, repair=True)
        assert self.readme_blob in result['missing']
        assert not os.path.exists(os.path.join(self.data_dir, self.readme_blob))

    def test_fsck_repair_still_repairs_with_the_real_bytes(self):
        with open(os.path.join(self.data_dir, self.readme_blob), 'rb') as f:
            real = f.read()
        os.remove(os.path.join(self.data_dir, self.readme_blob))
        self._host_serves(self.readme_blob, real)
        result = self.s.sync.fsck(self.s.vault_dir, repair=True)
        assert result['ok'] is True
        assert os.path.isfile(os.path.join(self.data_dir, self.readme_blob))

    def test_vault_move_auto_repair_never_launders_a_substitution(self):
        """Before: the substituted object was written under the real id and then
        re-encrypted into the NEW vault — where it hashes correctly forever."""
        os.remove(os.path.join(self.data_dir, self.readme_blob))
        self._host_serves(self.readme_blob, self._forged())
        sg_dir   = os.path.join(self.s.vault_dir, '.sg_vault')
        repaired = Step__Move__Validate_Local()._try_repair_missing([self.readme_blob], sg_dir, None,
                                                                    self.vault_id, self.s.api)
        assert repaired == set()
        assert not os.path.exists(os.path.join(self.data_dir, self.readme_blob))

    def test_clone_refuses_a_head_with_a_withheld_blob(self):
        self._host_serves(self.readme_blob, None)
        dest = os.path.join(self.s.tmp_dir, 'newcomer')
        with pytest.raises(Vault__Integrity_Error, match='clone incomplete'):
            self.s.sync.clone(self.s.vault_key, dest)
        assert not os.path.isfile(os.path.join(dest, '.sg_vault', 'local', 'vault_key'))   # not a usable clone

    def test_clone_refuses_a_head_with_a_substituted_blob(self):
        self._host_serves(self.readme_blob, self._forged())
        dest = os.path.join(self.s.tmp_dir, 'newcomer2')
        with pytest.raises(Vault__Integrity_Error):
            self.s.sync.clone(self.s.vault_key, dest)
        assert not os.path.exists(os.path.join(dest, 'readme.md')) or \
               open(os.path.join(dest, 'readme.md')).read() != 'the attacker readme'


class Test_Fixed__Presigned_URLs:
    """Large blobs come from a URL the host hands out: only https (or http to a
    loopback host, for local servers) is followed — never file://, ftp://, data:
    or an internal http address — and always with a timeout."""

    @pytest.mark.parametrize('url', ['file:///etc/passwd', 'ftp://host/x', 'data:,abc',
                                     'http://169.254.169.254/latest/meta-data/', 'http://intranet/x',
                                     'https://', '', None])
    def test_refused(self, url):
        with pytest.raises(ValueError):
            Vault__API().check_presigned_url(url)

    @pytest.mark.parametrize('url', ['https://bucket.s3.amazonaws.com/obj?sig=1',
                                     'http://127.0.0.1:9000/obj', 'http://localhost/obj'])
    def test_allowed(self, url):
        assert Vault__API().check_presigned_url(url) == url

    def test_fetch_presigned_checks_before_any_request(self):
        with pytest.raises(ValueError):
            Vault__API().fetch_presigned('file:///etc/passwd')
