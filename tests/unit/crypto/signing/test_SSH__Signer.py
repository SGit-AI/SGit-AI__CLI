"""SSH signing through ssh-keygen (key file, public key + agent, literal key,
defaultKeyCommand, certificates) and in-process without it; the ssh-keygen
delegation for certificates, cert-authority lines and KRLs (design__02 §5.4.5, 5.5)."""
import base64
import os
import shutil
import signal
import subprocess
import time

import pytest

from sgit_ai.core.Vault__Errors                        import Vault__Signing_Error
from sgit_ai.crypto.signing.SSH__Signer                import SSH__Signer
from sgit_ai.crypto.signing.User__Signature__Verifier  import User__Signature__Verifier
from sgit_ai.crypto.signing.User__Signer               import User__Signer
from sgit_ai.safe_types.Enum__User_Signature_Status    import Enum__User_Signature_Status as S
from sgit_ai.schemas.Schema__Signing_Config            import Schema__Signing_Config
from tests.unit.crypto.signing.signing_keys            import Signing_Keys

SSH_KEYGEN = shutil.which('ssh-keygen')
PAYLOAD    = b'{"tree_id":"obj-cas-imm-1b397bef28b6"}'


class SSH__Signer__Base:

    def setup_method(self):
        self.keys = Signing_Keys()

    def teardown_method(self):
        self.keys.cleanup()

    def config(self, **kw) -> Schema__Signing_Config:
        return Schema__Signing_Config(format='ssh', **kw)

    def check(self, signature, line, at_ms=None, **config):
        allowed = self.keys.write('allowed_signers', f'me@x {line}\n')
        verifier = User__Signature__Verifier(config=self.config(allowed_signers_file=allowed, **config))
        return verifier.verify(signature, PAYLOAD, at_ms or int(time.time() * 1000))


class Test_SSH__Signer__In_Process(SSH__Signer__Base):

    def test_without_ssh_keygen_a_private_key_or_its_pub_path_signs_in_process(self):
        _, path, line = self.keys.make()
        for key in (path, path + '.pub'):
            signature = SSH__Signer().sign(PAYLOAD, self.config(signing_key=key, ssh_program='no-such-ssh-keygen'))
            assert self.check(signature, line).status == S.GOOD

    def test_without_ssh_keygen_a_literal_key_cannot_sign(self):
        _, _, line = self.keys.make()
        with pytest.raises(Vault__Signing_Error, match='not installed'):
            SSH__Signer().sign(PAYLOAD, self.config(signing_key='key::' + line, ssh_program='no-such-ssh-keygen'))

    def test_no_key_configured(self):
        with pytest.raises(Vault__Signing_Error, match='set user.signingKey'):
            SSH__Signer().sign(PAYLOAD, self.config())

    def test_the_user_signer_describes_the_key(self):
        _, path, line = self.keys.make()
        signer    = User__Signer(config=self.config(signing_key=path, ssh_program='no-such-ssh-keygen'))
        signature = signer.sign(PAYLOAD)
        assert signer.describe(signature).startswith('ssh key SHA256:') and path in signer.describe(signature)


@pytest.mark.skipif(SSH_KEYGEN is None, reason='real ssh-keygen (CI installs openssh-client)')
class Test_SSH__Signer__Keygen(SSH__Signer__Base):

    def agent(self) -> dict:
        socket = os.path.join(self.keys.dir, 'agent.sock')
        out    = subprocess.run(['ssh-agent', '-a', socket], capture_output=True, text=True, check=True).stdout
        pid    = int(out.split('SSH_AGENT_PID=')[1].split(';')[0])
        self.agent_pid = pid
        return dict(SSH_AUTH_SOCK=socket)

    def teardown_method(self):
        if getattr(self, 'agent_pid', None):
            os.kill(self.agent_pid, signal.SIGTERM)
        super().teardown_method()

    @pytest.mark.parametrize('kind', ['ed25519', 'nistp256', 'rsa2048'])
    def test_a_private_key_file(self, kind):
        _, path, line = self.keys.make(kind)
        assert self.check(SSH__Signer().sign(PAYLOAD, self.config(signing_key=path)), line).status == S.GOOD

    def test_a_public_key_and_a_literal_key_sign_through_the_agent(self, monkeypatch):
        _, path, line = self.keys.make()
        for name, value in self.agent().items():
            monkeypatch.setenv(name, value)
        subprocess.run(['ssh-add', path], capture_output=True, check=True, env=dict(os.environ))
        for key in (path + '.pub', 'key::' + line, line):
            signature = SSH__Signer().sign(PAYLOAD, self.config(signing_key=key))
            assert self.check(signature, line).status == S.GOOD, key

    def test_default_key_command(self, monkeypatch):
        _, path, line = self.keys.make()
        for name, value in self.agent().items():
            monkeypatch.setenv(name, value)
        subprocess.run(['ssh-add', path], capture_output=True, check=True, env=dict(os.environ))
        signature = SSH__Signer().sign(PAYLOAD, self.config(default_key_command='ssh-add -L'))
        assert self.check(signature, line).status == S.GOOD

    def test_an_agent_without_the_key_fails_with_ssh_keygens_reason(self, monkeypatch):
        _, _, line = self.keys.make()
        for name, value in self.agent().items():
            monkeypatch.setenv(name, value)
        with pytest.raises(Vault__Signing_Error, match='ssh-keygen'):
            SSH__Signer().sign(PAYLOAD, self.config(signing_key='key::' + line))

    def ca_and_certificate(self) -> tuple:
        _, ca_path, ca_line = self.keys.make(name='ca')
        _, user_path, line  = self.keys.make(name='user')
        subprocess.run(['ssh-keygen', '-q', '-s', ca_path, '-I', 'alice', '-n', 'alice@x', '-V', '-1d:+52w',
                        user_path + '.pub'], capture_output=True, check=True)
        return ca_line, user_path, line

    def test_a_certificate_signs_and_is_checked_by_ssh_keygen_against_a_cert_authority_line(self):
        ca_line, user_path, _ = self.ca_and_certificate()
        signature = SSH__Signer().sign(PAYLOAD, self.config(signing_key=user_path + '-cert.pub'))
        allowed   = self.keys.write('allowed_signers', f'*@x cert-authority {ca_line}\n')
        result    = User__Signature__Verifier(config=self.config(allowed_signers_file=allowed)).verify(
                        signature, PAYLOAD, int(time.time() * 1000))
        assert (result.status, str(result.principal)) == (S.GOOD, 'alice@x')
        tampered  = User__Signature__Verifier(config=self.config(allowed_signers_file=allowed)).verify(
                        signature, PAYLOAD + b'!', int(time.time() * 1000))
        assert tampered.status == S.BAD

    def test_a_krl_revokes_through_ssh_keygen(self):
        ca_line, user_path, _ = self.ca_and_certificate()
        signature = SSH__Signer().sign(PAYLOAD, self.config(signing_key=user_path + '-cert.pub'))
        allowed   = self.keys.write('allowed_signers', f'*@x cert-authority {ca_line}\n')
        krl       = os.path.join(self.keys.dir, 'revoked.krl')
        subprocess.run(['ssh-keygen', '-q', '-k', '-f', krl, user_path + '.pub'], capture_output=True, check=True)
        result    = User__Signature__Verifier(config=self.config(allowed_signers_file=allowed, revocation_file=krl)).verify(
                        signature, PAYLOAD, int(time.time() * 1000))
        assert result.status == S.BAD

    def test_without_ssh_keygen_a_certificate_cannot_be_checked(self):
        ca_line, user_path, _ = self.ca_and_certificate()
        signature = SSH__Signer().sign(PAYLOAD, self.config(signing_key=user_path + '-cert.pub'))
        allowed   = self.keys.write('allowed_signers', f'*@x cert-authority {ca_line}\n')
        result    = User__Signature__Verifier(config=self.config(allowed_signers_file=allowed,
                                                                 ssh_program='no-such-ssh-keygen')).verify(
                        signature, PAYLOAD, int(time.time() * 1000))
        assert result.status == S.CANNOT_CHECK and 'is needed' in str(result.reason)
