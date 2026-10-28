"""SSH__Signer — `ssh-keygen -Y sign -n git`, as Git signs (design__02 §5.5).

The payload goes on stdin and the armored SSHSIG comes back on stdout, so it never
touches disk. A literal key (`ssh-…` / `key::ssh-…`, or the first such line printed by
gpg.ssh.defaultKeyCommand) goes into a 0600 temporary file with `-U` (the private half
is in ssh-agent). Without ssh-keygen, an unencrypted private-key file is signed with
in-process (D4). The signer checks its own output verifies before returning it."""
import base64
import os
import shlex
import shutil
import tempfile
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.Vault__Signing_Error        import Vault__Signing_Error
from   sgit_ai.crypto.signing.SSH__Public_Key             import SSH__Public_Key
from   sgit_ai.crypto.signing.SSH__Sig__Blob              import SSH__Sig__Blob
from   sgit_ai.crypto.signing.SSH__Signer__In_Process     import SSH__Signer__In_Process
from   sgit_ai.crypto.signing.SSH__Wire                   import Vault__SSH_Format_Error
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner, TIMEOUT_SIGN, TIMEOUT_CONFIG
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.schemas.Schema__User_Signature             import Schema__User_Signature


class SSH__Signer(Type_Safe):
    runner : Signing__Command_Runner

    def sign(self, payload: bytes, config) -> Schema__User_Signature:
        key     = self.key_spec(config)
        program = str(config.ssh_program or 'ssh-keygen')
        literal = self.literal_key(key)
        if not self.runner.which(program):
            if literal is None:
                return SSH__Signer__In_Process().sign(payload, self.private_key_path(key))
            raise Vault__Signing_Error(f'{program} is not installed, and the signing key is a public key '
                                       f'(its private half is in ssh-agent, which only ssh-keygen can use)')
        tmp_dir = tempfile.mkdtemp(prefix='sgit-sign-')
        try:
            if literal is not None:
                key_file = os.path.join(tmp_dir, 'signing.pub')
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(literal + '\n')
                argv = [program, '-Y', 'sign', '-n', 'git', '-f', key_file, '-U']
            else:
                argv = [program, '-Y', 'sign', '-n', 'git', '-f', os.path.expanduser(key)]
            result = self.runner.run(argv, stdin=payload, timeout=TIMEOUT_SIGN)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if result['code'] != 0:
            raise Vault__Signing_Error(f'{program}: ' + self.first_line(result['err'], 'signing failed'))
        return self.checked(result['out'], payload, program)

    def key_spec(self, config) -> str:
        key = str(config.signing_key or '').strip()
        if key:
            return key
        if config.default_key_command:
            result = self.runner.run(shlex.split(str(config.default_key_command)), timeout=TIMEOUT_CONFIG)
            for line in result['out'].decode('utf-8', 'replace').splitlines():
                if line.startswith(('ssh-', 'ecdsa-', 'sk-', 'key::')):
                    return line.strip()
            raise Vault__Signing_Error('gpg.ssh.defaultKeyCommand printed no key')
        raise Vault__Signing_Error('no SSH signing key: set user.signingKey (git config --global user.signingKey '
                                   '~/.ssh/id_ed25519.pub) or pass -S<key>')

    def literal_key(self, key: str):
        if key.startswith('key::'):
            return key[len('key::'):].strip()
        if key.startswith(('ssh-', 'ecdsa-', 'sk-')):
            return key
        return None

    def private_key_path(self, key: str) -> str:
        path = os.path.expanduser(key)
        if path.endswith('.pub') and os.path.isfile(path[:-4]):
            return path[:-4]
        return path

    def checked(self, armored: bytes, payload: bytes, program: str) -> Schema__User_Signature:
        try:
            blob   = SSH__Sig__Blob().dearmor(armored.decode('ascii', 'replace'))
            sshsig = SSH__Sig__Blob().parse(blob)
        except Vault__SSH_Format_Error as e:
            raise Vault__Signing_Error(f'{program} printed no SSH signature ({e})') from None
        key = SSH__Public_Key(blob=sshsig.public_key_blob)
        if not key.is_certificate() and not key.algorithm().startswith('sk-') and \
                not key.verify(sshsig.signature_blob, sshsig.signed_data(payload)):
            raise Vault__Signing_Error(f'{program} produced a signature that does not verify')
        return Schema__User_Signature(format=Enum__User_Signature_Format.SSH, blob=base64.b64encode(blob).decode())

    def first_line(self, err: bytes, default: str) -> str:
        lines = [line.strip() for line in err.decode('utf-8', 'replace').splitlines() if line.strip()]
        return lines[-1] if lines else default
