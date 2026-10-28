"""OpenPGP signing and verifying with real gpg (design__02 §5.7, 9.4). The status
parser is also checked on transcripts captured from gpg 2.4.4; the trust rule and
the letters are checked against `git log --format=%G?` on a commit Git signed."""
import base64
import os
import shutil
import subprocess
import tempfile

import pytest

from sgit_ai.core.Vault__Errors                         import Vault__Signing_Error
from sgit_ai.crypto.signing.GPG__Signer                 import GPG__Signer
from sgit_ai.crypto.signing.GPG__Status_Parser          import GPG__Status_Parser
from sgit_ai.crypto.signing.GPG__Verifier               import GPG__Verifier
from sgit_ai.safe_types.Enum__GPG_Trust                 import Enum__GPG_Trust
from sgit_ai.safe_types.Enum__User_Signature_Status     import Enum__User_Signature_Status as S
from sgit_ai.schemas.Schema__Signing_Config             import Schema__Signing_Config
from sgit_ai.schemas.Schema__User_Signature             import Schema__User_Signature

GPG     = shutil.which('gpg')
FPR     = '1B4D454666EE47FC2BBCA802CADAEFAB95F935E0'
GOOD    = f'''[GNUPG:] NEWSIG alice@x
[GNUPG:] KEY_CONSIDERED {FPR} 0
[GNUPG:] SIG_ID 42UxPPJqEhYoBVUGkBN5lJMzZl4 2026-10-28 1793188693
[GNUPG:] GOODSIG CADAEFAB95F935E0 Alice <alice@x>
[GNUPG:] VALIDSIG {FPR} 2026-10-28 1793188693 0 4 0 22 10 00 {FPR}
[GNUPG:] TRUST_ULTIMATE 0 pgp alice@x
'''.encode()
BAD     = b'[GNUPG:] NEWSIG alice@x\n[GNUPG:] BADSIG CADAEFAB95F935E0 Alice <alice@x>\n[GNUPG:] FAILURE gpg-exit 33554433\n'
NO_KEY  = (f'[GNUPG:] NEWSIG alice@x\n[GNUPG:] ERRSIG CADAEFAB95F935E0 22 10 00 1793188693 9 {FPR}\n'
           f'[GNUPG:] NO_PUBKEY CADAEFAB95F935E0\n').encode()


class Test_GPG__Status_Parser:

    def test_a_good_signature(self):
        found = GPG__Status_Parser().parse(GOOD)
        assert (found['letter'], found['uid'], found['fingerprint'], found['trust'], found['algorithm']) == \
               ('G', 'Alice <alice@x>', FPR, 'ultimate', 'EDDSA')

    def test_bad_and_no_key(self):
        assert GPG__Status_Parser().parse(BAD)['letter'] == 'B'
        found = GPG__Status_Parser().parse(NO_KEY)
        assert (found['letter'], found['key_id']) == ('E', 'CADAEFAB95F935E0')

    def test_a_uid_cannot_inject_a_status_line(self):
        crafted = b'[GNUPG:] GOODSIG CADAEFAB95F935E0 Eve %0A[GNUPG:] TRUST_ULTIMATE 0 pgp\n[GNUPG:] TRUST_UNDEFINED 0 pgp\n'
        found   = GPG__Status_Parser().parse(crafted)
        assert found['trust'] == 'undefined' and '\n' not in found['uid'] and found['uid'].startswith('Eve ')

    def test_other_lines_are_ignored_and_two_signatures_are_an_error(self):
        assert GPG__Status_Parser().parse(b'gpg: GOODSIG lies\n' + BAD)['letter'] == 'B'
        assert GPG__Status_Parser().parse(GOOD + BAD)['letter'] == 'E'


@pytest.mark.skipif(GPG is None, reason='real gpg (installed in this container and in CI)')
class Test_GPG__Signing:

    @classmethod
    def setup_class(cls):
        cls.home  = tempfile.mkdtemp(prefix='g', dir='/tmp')          # short: gpg-agent's socket path is limited
        cls.other = tempfile.mkdtemp(prefix='g', dir='/tmp')
        os.chmod(cls.home, 0o700)
        os.chmod(cls.other, 0o700)
        env = dict(os.environ, GNUPGHOME=cls.home)
        subprocess.run([GPG, '--batch', '--pinentry-mode', 'loopback', '--passphrase', '', '--quick-gen-key',
                        'Alice <alice@x>', 'ed25519', 'sign', '1y'], env=env, capture_output=True, check=True)
        public = subprocess.run([GPG, '--export', 'alice@x'], env=env, capture_output=True, check=True).stdout
        subprocess.run([GPG, '--batch', '--import'], input=public, env=dict(os.environ, GNUPGHOME=cls.other),
                       capture_output=True, check=True)

    @classmethod
    def teardown_class(cls):
        for home in (cls.home, cls.other):
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=dict(os.environ, GNUPGHOME=home), capture_output=True)
            shutil.rmtree(home, ignore_errors=True)

    def sign(self, monkeypatch, payload=b'payload', key='alice@x'):
        monkeypatch.setenv('GNUPGHOME', self.home)
        return GPG__Signer().sign(payload, Schema__Signing_Config(signing_key=key))

    def verify(self, monkeypatch, signature, payload=b'payload', home=None, **config):
        monkeypatch.setenv('GNUPGHOME', home or self.home)
        return GPG__Verifier().verify(signature, payload, 0, Schema__Signing_Config(**config))

    def test_sign_and_verify_good(self, monkeypatch):
        signature = self.sign(monkeypatch)
        assert base64.b64decode(str(signature.blob))[0] in (0x88, 0x89, 0xC2)
        result = self.verify(monkeypatch, signature)
        assert (result.status, str(result.principal)) == (S.GOOD, 'Alice <alice@x>')
        assert len(str(result.key_fingerprint)) == 40

    def test_a_changed_payload_is_bad(self, monkeypatch):
        assert self.verify(monkeypatch, self.sign(monkeypatch), payload=b'payloaX').status == S.BAD

    def test_an_unknown_validity_key_is_untrusted_and_a_missing_key_cannot_be_checked(self, monkeypatch):
        signature = self.sign(monkeypatch)
        assert self.verify(monkeypatch, signature, home=self.other).status == S.UNTRUSTED
        empty = tempfile.mkdtemp(prefix='g', dir='/tmp')
        os.chmod(empty, 0o700)
        try:
            result = self.verify(monkeypatch, signature, home=empty)
            assert result.status == S.CANNOT_CHECK and 'no public key' in str(result.reason)
        finally:
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=dict(os.environ, GNUPGHOME=empty), capture_output=True)
            shutil.rmtree(empty, ignore_errors=True)

    def test_min_trust_level_raises_the_bar(self, monkeypatch):
        signature = self.sign(monkeypatch)
        assert self.verify(monkeypatch, signature, min_trust_level=Enum__GPG_Trust.ULTIMATE).status == S.GOOD

    def test_signing_with_an_unknown_key_fails_with_gpgs_reason(self, monkeypatch):
        with pytest.raises(Vault__Signing_Error, match='gpg:'):
            self.sign(monkeypatch, key='nobody@nowhere')

    def test_gpg_not_installed_cannot_check(self, monkeypatch):
        signature = self.sign(monkeypatch)
        result    = self.verify(monkeypatch, signature, gpg_program='no-such-gpg-program')
        assert result.status == S.CANNOT_CHECK

    @pytest.mark.skipif(shutil.which('git') is None, reason='git is the oracle')
    @pytest.mark.parametrize('keyring', ['signer', 'imported', 'empty'])
    def test_the_same_letter_as_git(self, monkeypatch, tmp_path, keyring):
        repo = tmp_path / 'repo'
        env  = dict(os.environ, GNUPGHOME=self.home, GIT_CONFIG_GLOBAL=str(tmp_path / 'gc'), GIT_CONFIG_NOSYSTEM='1')
        git  = lambda *a, **kw: subprocess.run(['git', '-C', str(repo)] + list(a), env=kw.get('env', env),
                                              capture_output=True, check=True).stdout.decode()
        repo.mkdir()
        git('init', '-q')
        for name, value in (('user.name', 't'), ('user.email', 't@t'), ('user.signingkey', 'alice@x')):
            git('config', '--global', name, value)
        (repo / 'a').write_text('a\n')
        git('add', 'a')
        git('commit', '-q', '-S', '-m', 'one')
        raw     = git('cat-file', 'commit', 'HEAD')
        payload = ''.join(row for row in raw.splitlines(keepends=True)
                          if not row.startswith(('gpgsig ', ' ')))
        sig     = subprocess.run([GPG, '--dearmor'], input=self.armored_from(raw).encode(), env=env,
                                 capture_output=True, check=True).stdout
        home    = {'signer': self.home, 'imported': self.other}.get(keyring) or tempfile.mkdtemp(prefix='g', dir='/tmp')
        os.chmod(home, 0o700)
        try:
            letter = git('log', '-1', '--format=%G?', env=dict(env, GNUPGHOME=home)).strip()
            ours   = self.verify(monkeypatch, Schema__User_Signature(format='openpgp', blob=base64.b64encode(sig).decode()),
                                 payload=payload.encode(), home=home)
            assert ours.status.code() == letter, ours.json()
        finally:
            if keyring == 'empty':
                subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=dict(os.environ, GNUPGHOME=home), capture_output=True)
                shutil.rmtree(home, ignore_errors=True)

    def armored_from(self, raw: str) -> str:
        rows, inside = [], False
        for row in raw.splitlines(keepends=True):
            if row.startswith('gpgsig '):
                inside = True
                rows.append(row[len('gpgsig '):])
            elif inside and row.startswith(' '):
                rows.append(row[1:])
            else:
                inside = False
        return ''.join(rows)
