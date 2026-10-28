"""GPG__Verifier — `gpg --keyid-format=long --status-fd=1 --verify <sigfile> -`, Git's call,
with the status read by GPG__Status_Parser and turned into Git's letters: a good
signature whose key validity is below marginal (or below gpg.minTrustLevel) is U,
measured on git 2.43 / gpg 2.4 in the tests. The signature file is 0600 in a private
temporary folder, removed in `finally`; the payload goes on stdin."""
import base64
import binascii
import os
import shutil
import tempfile
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.GPG__Status_Parser          import GPG__Status_Parser
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner, TIMEOUT_VERIFY
from   sgit_ai.safe_types.Enum__GPG_Trust                 import Enum__GPG_Trust
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.safe_types.Enum__User_Signature_Status     import Enum__User_Signature_Status, STATUS_CODES
from   sgit_ai.schemas.Schema__User_Signature__Result     import Schema__User_Signature__Result

BY_LETTER = {letter: Enum__User_Signature_Status(status) for status, letter in STATUS_CODES.items()}


class GPG__Verifier(Type_Safe):
    runner : Signing__Command_Runner

    def verify(self, signature, payload: bytes, at_time_ms: int, config) -> Schema__User_Signature__Result:
        result = Schema__User_Signature__Result(format=Enum__User_Signature_Format.OPENPGP)
        try:
            raw = base64.b64decode(str(signature.blob), validate=True)
        except (binascii.Error, ValueError):
            return self.verdict(result, Enum__User_Signature_Status.BAD, 'the signature is not base64')
        program = str(getattr(config, 'gpg_program', None) or 'gpg')
        tmp_dir = tempfile.mkdtemp(prefix='sgit-verify-')
        try:
            sig_file = os.path.join(tmp_dir, 'signature.sig')
            fd = os.open(sig_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
            run = self.runner.run([program, '--keyid-format=long', '--status-fd=1', '--verify', sig_file, '-'],
                                  stdin=payload, timeout=TIMEOUT_VERIFY)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if run['code'] in (124, 126, 127):
            return self.verdict(result, Enum__User_Signature_Status.CANNOT_CHECK, run['err'].decode('utf-8', 'replace'))
        status = GPG__Status_Parser().parse(run['out'])
        letter = status['letter'] or 'E'
        if status['fingerprint'] and len(status['fingerprint']) in (40, 64):
            result.key_fingerprint = status['fingerprint'].upper()
        result.key_type  = status['algorithm'] or None
        result.principal = status['uid'] or None
        reason = status.get('reason', '')
        if letter == 'G':
            trust   = Enum__GPG_Trust(status['trust']) if status['trust'] in [t.value for t in Enum__GPG_Trust] \
                      else Enum__GPG_Trust.UNDEFINED
            minimum = getattr(config, 'min_trust_level', None) or Enum__GPG_Trust.MARGINAL
            if trust.rank() < max(minimum.rank(), Enum__GPG_Trust.MARGINAL.rank()):
                letter, reason = 'U', f'key validity is {trust.value}'
        elif letter == 'E' and not reason:
            reason = f'cannot check: no public key {status["key_id"]}' if status['key_id'] else 'cannot check the signature'
        return self.verdict(result, BY_LETTER[letter], reason)

    def verdict(self, result, status, reason: str) -> Schema__User_Signature__Result:
        result.status = status
        result.reason = reason[:300] if reason else None
        return result
