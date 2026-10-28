"""SSH__Sig__Verifier__Keygen — Git's three ssh-keygen calls, for what the in-process
verifier hands over: SSH certificates, `cert-authority` lines and binary KRLs
(design__02 §5.4.5).

    ssh-keygen -Y find-principals -f <allowed> -s <sig> -Overify-time=<t>
    ssh-keygen -Y verify -n git -f <allowed> -I <principal> -s <sig> [-r <revoked>] -Overify-time=<t>
    ssh-keygen -Y check-novalidate -n git -s <sig>

The armored signature is a 0600 file in a private temporary folder, removed in
`finally`; the payload goes on stdin. Without ssh-keygen: cannot-check, never good."""
import base64
import os
import shutil
import tempfile
import time
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.SSH__Public_Key             import SSH__Public_Key
from   sgit_ai.crypto.signing.SSH__Sig__Blob              import SSH__Sig__Blob
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner, TIMEOUT_VERIFY
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.safe_types.Enum__User_Signature_Status     import Enum__User_Signature_Status
from   sgit_ai.schemas.Schema__User_Signature__Result     import Schema__User_Signature__Result


class SSH__Sig__Verifier__Keygen(Type_Safe):
    runner : Signing__Command_Runner

    def verify(self, signature, payload: bytes, at_time_ms: int, allowed_signers_file: str = None,
               revocation_file: str = None, program: str = 'ssh-keygen') -> Schema__User_Signature__Result:
        result = Schema__User_Signature__Result(format=Enum__User_Signature_Format.SSH)
        if not self.runner.which(program):
            return self.verdict(result, Enum__User_Signature_Status.CANNOT_CHECK,
                                f'{program} is needed (an SSH certificate, a cert-authority line or a binary KRL)')
        blob   = base64.b64decode(str(signature.blob))
        sshsig = SSH__Sig__Blob().parse(blob)
        key    = SSH__Public_Key(blob=sshsig.public_key_blob)
        result.key_type        = key.display_type()
        result.key_fingerprint = key.fingerprint()
        stamp   = time.strftime('%Y%m%d%H%M%S', time.localtime(int(at_time_ms) // 1000))
        tmp_dir = tempfile.mkdtemp(prefix='sgit-verify-')
        try:
            sig_file = os.path.join(tmp_dir, 'signature.sig')
            fd = os.open(sig_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(SSH__Sig__Blob().armor(blob))
            principal = ''
            if allowed_signers_file and os.path.isfile(allowed_signers_file):
                found = self.runner.run([program, '-Y', 'find-principals', '-f', allowed_signers_file, '-s', sig_file,
                                         f'-Overify-time={stamp}'], timeout=TIMEOUT_VERIFY)
                if found['code'] == 0:
                    principal = found['out'].decode('utf-8', 'replace').splitlines()[0].strip()
            if principal:
                argv = [program, '-Y', 'verify', '-n', 'git', '-f', allowed_signers_file, '-I', principal, '-s', sig_file,
                        f'-Overify-time={stamp}']
                if revocation_file and os.path.isfile(revocation_file):
                    argv += ['-r', revocation_file]
                checked = self.runner.run(argv, stdin=payload, timeout=TIMEOUT_VERIFY)
                if checked['code'] == 0:
                    result.principal = principal
                    return self.verdict(result, Enum__User_Signature_Status.GOOD, '')
                return self.verdict(result, Enum__User_Signature_Status.BAD, self.last_line(checked['err']))
            checked = self.runner.run([program, '-Y', 'check-novalidate', '-n', 'git', '-s', sig_file],
                                      stdin=payload, timeout=TIMEOUT_VERIFY)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if checked['code'] == 0:
            return self.verdict(result, Enum__User_Signature_Status.UNTRUSTED, 'no principal matched')
        return self.verdict(result, Enum__User_Signature_Status.BAD, self.last_line(checked['err']))

    def last_line(self, err: bytes) -> str:
        lines = [line.strip() for line in err.decode('utf-8', 'replace').splitlines() if line.strip()]
        return lines[-1][:300] if lines else 'the signature does not verify'

    def verdict(self, result, status, reason: str) -> Schema__User_Signature__Result:
        result.status = status
        result.reason = reason or None
        return result
