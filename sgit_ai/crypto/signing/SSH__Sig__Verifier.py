"""SSH__Sig__Verifier — Git's SSH verification, in-process (design__02 §5.4.4).

Git runs `ssh-keygen -Y find-principals` (the key's lines valid at the commit time;
namespaces are not looked at), then `-Y verify -n git -I <principal> -r <revocations>
-Overify-time=<commit time>`, and with no principal `-Y check-novalidate`. Measured on
git 2.43 / OpenSSH 9.6, and reproduced here:

    the signature does not verify (or wrong namespace / hash / algorithm)  -> bad (B)
    no line for the key valid at the commit time, or no file               -> untrusted (U),
                                                                              with the line's reason
    a valid line whose namespaces exclude "git"                            -> bad (B)
    a valid line, but the key is in the revocation file                    -> bad (B)
    a valid line otherwise                                                 -> good (G), its principals
    a certificate, a cert-authority line or a binary KRL                   -> delegated (cannot-check
                                                                              until ssh-keygen does it)

Never raises on vault data: a malformed signature is `bad` with the reason."""
import base64
import binascii
import os
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.SSH__Allowed_Signers        import SSH__Allowed_Signers
from   sgit_ai.crypto.signing.SSH__Public_Key             import SSH__Public_Key
from   sgit_ai.crypto.signing.SSH__Revocation_List        import SSH__Revocation_List
from   sgit_ai.crypto.signing.SSH__Sig__Blob              import SSH__Sig__Blob, HASHES
from   sgit_ai.crypto.signing.SSH__Wire                   import Vault__SSH_Format_Error
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.safe_types.Enum__User_Signature_Status     import Enum__User_Signature_Status
from   sgit_ai.schemas.Schema__User_Signature__Result     import Schema__User_Signature__Result

NAMESPACE = 'git'


class SSH__Sig__Verifier(Type_Safe):

    def verify(self, signature, payload: bytes, at_time_ms: int, allowed_signers_file: str = None,
               revocation_file: str = None) -> Schema__User_Signature__Result:
        result = Schema__User_Signature__Result(format=Enum__User_Signature_Format.SSH)
        try:
            blob   = base64.b64decode(str(signature.blob), validate=True)
            sshsig = SSH__Sig__Blob().parse(blob)
            key    = SSH__Public_Key(blob=sshsig.public_key_blob)
            result.key_type        = key.display_type()
            result.key_fingerprint = key.fingerprint()
        except (Vault__SSH_Format_Error, binascii.Error, ValueError) as e:
            return self.verdict(result, Enum__User_Signature_Status.BAD, f'malformed SSH signature: {e}')
        if sshsig.namespace != NAMESPACE.encode():
            return self.verdict(result, Enum__User_Signature_Status.BAD,
                                f'signature namespace {sshsig.namespace.decode("ascii", "replace")!r}, not {NAMESPACE!r}')
        if sshsig.hash_algorithm.decode('ascii', 'replace') not in HASHES:
            return self.verdict(result, Enum__User_Signature_Status.BAD, 'signature hash is not sha256 or sha512')

        allowed, revoked = self.load_trust(allowed_signers_file, revocation_file)
        if key.is_certificate() or (allowed and allowed.has_cert_authority) or (revoked and revoked.is_krl()):
            return self.verdict(result, Enum__User_Signature_Status.CANNOT_CHECK,
                                'needs ssh-keygen (an SSH certificate, a cert-authority line or a binary KRL)')

        at_time_s = int(at_time_ms) // 1000
        signed    = sshsig.signed_data(payload)
        lines     = allowed.lines_for_key(key.blob) if allowed else []
        in_time   = [line for line in lines if not allowed.time_problem(line, at_time_s)]
        if not in_time:                                                  # Git: no principal -> check-novalidate
            if not key.verify(sshsig.signature_blob, signed):
                return self.verdict(result, Enum__User_Signature_Status.BAD, 'the signature does not verify')
            reason = allowed.time_problem(lines[0], at_time_s) if lines else 'no principal matched'
            return self.verdict(result, Enum__User_Signature_Status.UNTRUSTED, reason)
        reason = 'the signature does not verify'
        for line in in_time:                                             # Git: verify -I each principal in turn
            if not key.verify(sshsig.signature_blob, signed, not line.no_touch_required, line.verify_required):
                continue
            if line.namespaces is not None and not allowed.pattern_list_matches(NAMESPACE, str(line.namespaces)):
                reason = f'key is not permitted for use in signature namespace "{NAMESPACE}"'
                continue
            if revoked and revoked.is_revoked(key.blob):
                return self.verdict(result, Enum__User_Signature_Status.BAD, 'the key is in the revocation file')
            result.principal = str(line.principals)
            return self.verdict(result, Enum__User_Signature_Status.GOOD, '')
        return self.verdict(result, Enum__User_Signature_Status.BAD, reason)

    def load_trust(self, allowed_signers_file: str, revocation_file: str) -> tuple:
        allowed = SSH__Allowed_Signers().load(allowed_signers_file) \
                  if allowed_signers_file and os.path.isfile(allowed_signers_file) else None
        revoked = SSH__Revocation_List().load(revocation_file) \
                  if revocation_file and os.path.isfile(revocation_file) else None
        return allowed, revoked

    def verdict(self, result, status, reason: str) -> Schema__User_Signature__Result:
        result.status = status
        result.reason = reason or None
        return result
