"""The in-process SSH verifier (design__02 §5.4) and signer, with ssh-keygen as the
oracle when it is installed: its signatures verify here, ours verify there, the
ed25519 blob is byte-identical, fingerprints and find-principals agree."""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time

import pytest
from   cryptography.hazmat.primitives                     import hashes, serialization
from   cryptography.hazmat.primitives.asymmetric          import ec, padding
from   cryptography.hazmat.primitives.asymmetric.ed25519  import Ed25519PrivateKey
from   cryptography.hazmat.primitives.asymmetric.utils    import decode_dss_signature

from sgit_ai.crypto.signing.SSH__Public_Key            import SSH__Public_Key
from sgit_ai.crypto.signing.SSH__Sig__Blob             import SSH__Sig__Blob
from sgit_ai.crypto.signing.SSH__Sig__Verifier         import SSH__Sig__Verifier
from sgit_ai.crypto.signing.SSH__Signer__In_Process    import SSH__Signer__In_Process
from sgit_ai.crypto.signing.SSH__Wire                  import SSH__Wire, Vault__SSH_Format_Error
from sgit_ai.safe_types.Enum__User_Signature_Status    import Enum__User_Signature_Status as S
from sgit_ai.schemas.Schema__User_Signature            import Schema__User_Signature
from tests.unit.crypto.signing.signing_keys            import Signing_Keys, KEY_MAKERS

SSH_KEYGEN = shutil.which('ssh-keygen')
VECTOR     = json.load(open('tests/_fixtures/interop_vectors.json'))['commit_user_signing']
PAYLOAD    = b'{"tree_id":"obj-cas-imm-1b397bef28b6"}'
NOW_MS     = int(time.time() * 1000)


def as_signature(blob: bytes) -> Schema__User_Signature:
    return Schema__User_Signature(format='ssh', blob=base64.b64encode(blob).decode())


class Verifier__Base:

    def setup_method(self):
        self.keys     = Signing_Keys()
        self.signer   = SSH__Signer__In_Process()
        self.verifier = SSH__Sig__Verifier()

    def teardown_method(self):
        self.keys.cleanup()

    def allowed(self, text: str) -> str:
        return self.keys.write('allowed_signers', text)

    def verify(self, signature, payload=PAYLOAD, at_ms=NOW_MS, allowed=None, revoked=None):
        return self.verifier.verify(signature, payload, at_ms, allowed, revoked)


class Test_SSH__Sig__Verifier(Verifier__Base):

    @pytest.mark.parametrize('kind', sorted(KEY_MAKERS))
    def test_every_key_type_signs_and_verifies(self, kind):
        _, path, line = self.keys.make(kind)
        result = self.verify(self.signer.sign(PAYLOAD, path), allowed=self.allowed(f'me@x {line}\n'))
        assert (result.status, str(result.principal)) == (S.GOOD, 'me@x')
        assert str(result.key_fingerprint) == SSH__Public_Key().from_openssh_line(line).fingerprint()

    def test_a_changed_payload_or_signature_byte_is_bad(self):
        _, path, line = self.keys.make()
        signature = self.signer.sign(PAYLOAD, path)
        assert self.verify(signature, payload=PAYLOAD + b' ').status == S.BAD
        blob = bytearray(base64.b64decode(str(signature.blob)))
        blob[-5] ^= 0x01
        assert self.verify(as_signature(bytes(blob))).status == S.BAD

    def test_untrusted_without_a_line_and_without_a_file(self):
        _, path, _       = self.keys.make()
        _, _, other_line = self.keys.make('nistp256')
        signature        = self.signer.sign(PAYLOAD, path)
        assert self.verify(signature).status == S.UNTRUSTED
        assert self.verify(signature, allowed=self.allowed(f'someone@x {other_line}\n')).status == S.UNTRUSTED

    def test_a_namespace_option_excluding_git_is_bad_as_in_git(self):
        _, path, line = self.keys.make()
        result = self.verify(self.signer.sign(PAYLOAD, path), allowed=self.allowed(f'me@x namespaces="file" {line}\n'))
        assert result.status == S.BAD and 'not permitted for use in signature namespace "git"' in str(result.reason)

    def test_validity_window_against_the_commit_time(self):
        _, path, line = self.keys.make()
        allowed   = self.allowed(f'me@x valid-after="20200101Z",valid-before="20250101Z" {line}\n')
        signature = self.signer.sign(PAYLOAD, path)
        assert self.verify(signature, at_ms=1_650_000_000_000, allowed=allowed).status == S.GOOD
        late = self.verify(signature, at_ms=NOW_MS, allowed=allowed)                # git 2.43: U, "No principal matched"
        assert late.status == S.UNTRUSTED and 'valid-before 20250101Z' in str(late.reason)

    def test_a_revoked_key_is_bad_when_a_principal_matched_as_in_git(self):
        _, path, line = self.keys.make()
        signature = self.signer.sign(PAYLOAD, path)
        revoked   = self.keys.write('revoked', line + '\n')
        result    = self.verify(signature, allowed=self.allowed(f'me@x {line}\n'), revoked=revoked)
        assert result.status == S.BAD and 'revocation file' in str(result.reason)
        assert self.verify(signature, allowed=self.allowed('\n'), revoked=revoked).status == S.UNTRUSTED   # git: U

    def test_a_signature_made_for_another_namespace_is_bad(self):
        key, _, _ = self.keys.make()
        sshsig = SSH__Sig__Blob().parse(self.signer.sign_blob(PAYLOAD, key))
        sshsig.namespace      = b'file'
        sshsig.signature_blob = self.signer.signature(key, 'ssh-ed25519', sshsig.signed_data(PAYLOAD))
        result = self.verify(as_signature(sshsig.build()))
        assert result.status == S.BAD and "namespace 'file'" in str(result.reason)

    def test_an_rsa_sha1_signature_is_refused(self):
        key, _, _ = self.keys.make('rsa2048')
        sshsig    = SSH__Sig__Blob().parse(self.signer.sign_blob(PAYLOAD, key))
        wire      = SSH__Wire()
        raw       = key.sign(sshsig.signed_data(PAYLOAD), padding.PKCS1v15(), hashes.SHA1())
        sshsig.signature_blob = wire.string(b'ssh-rsa') + wire.string(raw)
        assert self.verify(as_signature(sshsig.build())).status == S.BAD

    def test_a_signature_algorithm_that_does_not_match_the_key_is_bad(self):
        key, _, _   = self.keys.make('ed25519')
        other, _, _ = self.keys.make('nistp256', name='other')
        sshsig      = SSH__Sig__Blob().parse(self.signer.sign_blob(PAYLOAD, key))
        sshsig.signature_blob = self.signer.signature(other, 'ecdsa-sha2-nistp256', sshsig.signed_data(PAYLOAD))
        assert self.verify(as_signature(sshsig.build())).status == S.BAD

    def test_garbage_is_bad_never_an_exception(self):
        for blob in (b'', b'SSHSIG', os.urandom(300)):
            assert self.verify(as_signature(blob + b'\x00' * 16)).status == S.BAD

    def test_a_certificate_is_delegated(self):
        wire = SSH__Wire()
        key  = SSH__Public_Key(blob=wire.string(b'ssh-ed25519-cert-v01@openssh.com') + wire.string(b'x' * 40))
        sig  = SSH__Sig__Blob(public_key_blob=key.blob, namespace=b'git', reserved=b'', hash_algorithm=b'sha512',
                              signature_blob=wire.string(b'ssh-ed25519') + wire.string(b'y' * 64)).build()
        assert self.verify(as_signature(sig)).status == S.CANNOT_CHECK


class Test_SSH__Sig__Verifier__Security_Keys(Verifier__Base):
    """sk- types (FIDO): the authenticator signs SHA256(app) | flags | counter | SHA256(data)."""

    def sk_signature(self, kind: str, flags: int) -> tuple:
        wire, app = SSH__Wire(), b'ssh:'
        sshsig    = SSH__Sig__Blob(namespace=b'git', reserved=b'', hash_algorithm=b'sha512')
        if kind == 'ed25519':
            key  = Ed25519PrivateKey.generate()
            raw  = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            name = b'sk-ssh-ed25519@openssh.com'
            sshsig.public_key_blob = wire.string(name) + wire.string(raw) + wire.string(app)
        else:
            key   = ec.generate_private_key(ec.SECP256R1())
            point = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            name  = b'sk-ecdsa-sha2-nistp256@openssh.com'
            sshsig.public_key_blob = wire.string(name) + wire.string(b'nistp256') + wire.string(point) + wire.string(app)
        message = (hashlib.sha256(app).digest() + bytes([flags]) + (7).to_bytes(4, 'big') +
                   hashlib.sha256(sshsig.signed_data(PAYLOAD)).digest())
        if kind == 'ed25519':
            inner = wire.string(key.sign(message))
        else:
            r, s  = decode_dss_signature(key.sign(message, ec.ECDSA(hashes.SHA256())))
            inner = wire.string(wire.mpint(r) + wire.mpint(s))
        sshsig.signature_blob = wire.string(name) + inner + bytes([flags]) + (7).to_bytes(4, 'big')
        line = SSH__Public_Key(blob=sshsig.public_key_blob).openssh_line()
        return as_signature(sshsig.build()), line

    @pytest.mark.parametrize('kind', ['ed25519', 'ecdsa'])
    def test_sk_signatures_verify_and_need_user_presence(self, kind):
        signature, line = self.sk_signature(kind, flags=0x01)
        result = self.verify(signature, allowed=self.allowed(f'me@x {line}\n'))
        assert result.status == S.GOOD and str(result.key_type) in ('ED25519-SK', 'ECDSA-SK')
        untouched, line = self.sk_signature(kind, flags=0x00)
        assert self.verify(untouched, allowed=self.allowed(f'me@x {line}\n')).status == S.BAD
        assert self.verify(untouched, allowed=self.allowed(f'me@x no-touch-required {line}\n')).status == S.GOOD

    def test_verify_required(self):
        signature, line = self.sk_signature('ed25519', flags=0x01)
        assert self.verify(signature, allowed=self.allowed(f'me@x verify-required {line}\n')).status == S.BAD
        verified, line = self.sk_signature('ed25519', flags=0x05)
        assert self.verify(verified, allowed=self.allowed(f'me@x verify-required {line}\n')).status == S.GOOD


class Test_SSH__Public_Key:

    def test_dss_and_unknown_types_never_verify(self):
        wire = SSH__Wire()
        key  = SSH__Public_Key(blob=wire.string(b'ssh-dss') + wire.string(b'x'))
        assert key.verify(wire.string(b'ssh-dss') + wire.string(b'y'), b'data') is False

    def test_a_line_whose_type_does_not_match_its_key_is_refused(self):
        keys = Signing_Keys()
        _, _, line = keys.make()
        with pytest.raises(Vault__SSH_Format_Error, match='does not match'):
            SSH__Public_Key().from_openssh_line('ssh-rsa ' + line.split()[1])
        keys.cleanup()


class Test_SSH__Interop_Vector(Verifier__Base):

    def test_the_ssh_keygen_signature_verifies_and_the_in_process_signer_reproduces_it(self):
        key_path = self.keys.write('vector_key', VECTOR['ssh_private_key_openssh'])
        os.chmod(key_path, 0o600)
        payload  = VECTOR['signing_bytes_utf8'].encode()
        stored   = VECTOR['stored_commit_json']['user_signature']
        result   = self.verify(Schema__User_Signature(**stored), payload=payload,
                               allowed=self.allowed(VECTOR['allowed_signers_line'] + '\n'))
        assert (result.status, str(result.principal)) == (S.GOOD, 'test@example.com')
        assert self.signer.sign(payload, key_path).blob == stored['blob']             # ed25519: byte for byte


@pytest.mark.skipif(SSH_KEYGEN is None, reason='ssh-keygen is the oracle (CI installs openssh-client)')
class Test_SSH__Keygen_Oracle(Verifier__Base):

    def keygen(self, *args, stdin: bytes = b'') -> subprocess.CompletedProcess:
        return subprocess.run([SSH_KEYGEN] + list(args), input=stdin, capture_output=True)

    @pytest.mark.parametrize('kind', sorted(KEY_MAKERS))
    def test_ssh_keygen_signatures_verify_here(self, kind):
        _, path, line = self.keys.make(kind)
        armored = self.keygen('-Y', 'sign', '-n', 'git', '-f', path, stdin=PAYLOAD).stdout.decode()
        blob    = SSH__Sig__Blob().dearmor(armored)
        assert self.verify(as_signature(blob), allowed=self.allowed(f'me@x {line}\n')).status == S.GOOD

    @pytest.mark.parametrize('kind', sorted(KEY_MAKERS))
    def test_our_signatures_verify_in_ssh_keygen(self, kind):
        _, path, line = self.keys.make(kind)
        blob    = base64.b64decode(str(self.signer.sign(PAYLOAD, path).blob))
        sigfile = self.keys.write('payload.sig', SSH__Sig__Blob().armor(blob))
        allowed = self.allowed(f'me@x {line}\n')
        check   = self.keygen('-Y', 'verify', '-n', 'git', '-f', allowed, '-I', 'me@x', '-s', sigfile, stdin=PAYLOAD)
        assert check.returncode == 0, check.stderr
        tampered = self.keygen('-Y', 'verify', '-n', 'git', '-f', allowed, '-I', 'me@x', '-s', sigfile, stdin=PAYLOAD + b'!')
        assert tampered.returncode != 0

    @pytest.mark.parametrize('kind', sorted(KEY_MAKERS))
    def test_fingerprints_equal_ssh_keygen_l(self, kind):
        _, path, line = self.keys.make(kind)
        printed = self.keygen('-l', '-f', path + '.pub').stdout.decode().split()[1]
        assert SSH__Public_Key().from_openssh_line(line).fingerprint() == printed

    @pytest.mark.parametrize('options, at', [
        ('',                                                 'now'),
        ('namespaces="git"',                                 'now'),
        ('namespaces="file"',                                'now'),
        ('valid-after="20200101Z",valid-before="20250101Z"', 'in-2022'),
        ('valid-after="20200101Z",valid-before="20250101Z"', 'now'),
        ('valid-after="20300101"',                           'now'),
    ])
    def test_find_principals_agrees(self, options, at):
        at_ms = NOW_MS if at == 'now' else 1_650_000_000_000
        _, path, line = self.keys.make()
        signature = self.signer.sign(PAYLOAD, path)
        allowed   = self.allowed(f'me@x {options} {line}\n'.replace('  ', ' '))
        sigfile   = self.keys.write('p.sig', SSH__Sig__Blob().armor(base64.b64decode(str(signature.blob))))
        stamp     = time.strftime('%Y%m%d%H%M%S', time.localtime(at_ms // 1000))
        found     = self.keygen('-Y', 'find-principals', '-f', allowed, '-s', sigfile, f'-Overify-time={stamp}')
        ours      = self.verify(signature, at_ms=at_ms, allowed=allowed)
        if found.returncode != 0:                                               # git: check-novalidate -> U
            assert ours.status == S.UNTRUSTED, ours.json()
            return
        principal = found.stdout.decode().splitlines()[0]
        verified  = self.keygen('-Y', 'verify', '-n', 'git', '-f', allowed, '-I', principal, '-s', sigfile,
                                f'-Overify-time={stamp}', stdin=PAYLOAD)
        assert (verified.returncode == 0) == (ours.status == S.GOOD), (verified.stderr, ours.json())
        if verified.returncode == 0:
            assert principal == str(ours.principal)
        else:
            assert ours.status == S.BAD


@pytest.mark.skipif(SSH_KEYGEN is None or shutil.which('git') is None, reason='git and ssh-keygen are the oracle')
class Test_SSH__Git_Oracle(Verifier__Base):
    """A commit Git signed with an SSH key, checked by `git log --format=%G?` and by this
    verifier over the same payload (the commit object without its gpgsig header): the
    same letter for every allowed-signers / revocation case."""

    CASES = {'plain'             : ('me@x {pub}',                           None),
             'namespace git'     : ('me@x namespaces="git" {pub}',          None),
             'namespace file'    : ('me@x namespaces="file" {pub}',         None),
             'expired'           : ('me@x valid-before="20250101Z" {pub}',  None),
             'not yet valid'     : ('me@x valid-after="20300101Z" {pub}',   None),
             'no line'           : ('',                                     None),
             'revoked'           : ('me@x {pub}',                           'revoked'),
             'revoked, no line'  : ('',                                     'revoked')}

    def git(self, repo, *args) -> str:
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.path.join(self.keys.dir, 'gitconfig'), GIT_CONFIG_NOSYSTEM='1')
        return subprocess.run(['git', '-C', repo] + list(args), capture_output=True, env=env, check=True).stdout.decode()

    def signed_repo(self) -> tuple:
        _, key_path, line = self.keys.make()
        repo  = os.path.join(self.keys.dir, 'repo')
        os.makedirs(repo)
        self.git(repo, 'init', '-q')
        for name, value in (('gpg.format', 'ssh'), ('user.signingkey', key_path + '.pub'), ('user.name', 't'),
                            ('user.email', 't@t'), ('gpg.ssh.allowedSignersFile', os.path.join(self.keys.dir, 'allowed_signers'))):
            self.git(repo, 'config', '--global', name, value)
        with open(os.path.join(repo, 'a'), 'w') as f:
            f.write('a\n')
        self.git(repo, 'add', 'a')
        self.git(repo, 'commit', '-q', '-S', '-m', 'one')
        raw = self.git(repo, 'cat-file', 'commit', 'HEAD')
        payload, armored, in_sig = [], [], False
        for row in raw.splitlines(keepends=True):
            if row.startswith('gpgsig '):
                in_sig = True
                armored.append(row[len('gpgsig '):])
            elif in_sig and row.startswith(' '):
                armored.append(row[1:])
            else:
                in_sig = False
                payload.append(row)
        committed_ms = int(self.git(repo, 'log', '-1', '--format=%ct').strip()) * 1000
        blob = SSH__Sig__Blob().dearmor(''.join(armored))
        return repo, line, ''.join(payload).encode(), as_signature(blob), committed_ms

    @pytest.mark.parametrize('case', sorted(CASES))
    def test_the_same_letter_as_git(self, case):
        repo, line, payload, signature, at_ms = self.signed_repo()
        allowed_text, revoked = self.CASES[case]
        allowed = self.allowed(allowed_text.format(pub=line) + '\n')
        revoked_path = None
        if revoked:
            revoked_path = self.keys.write('revoked', line + '\n')
            self.git(repo, 'config', '--global', 'gpg.ssh.revocationFile', revoked_path)
        git_letter = self.git(repo, 'log', '-1', '--format=%G?').strip()
        ours       = self.verify(signature, payload=payload, at_ms=at_ms, allowed=allowed, revoked=revoked_path)
        assert ours.status.code() == git_letter, ours.json()
