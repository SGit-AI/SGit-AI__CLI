"""User__Signature__Verifier — one user signature, checked as Git checks it: SSH
in-process (handing certificates, cert-authority lines and KRLs to ssh-keygen),
OpenPGP with gpg. Trust comes from this verifier's own Git config (allowed-signers
file, revocation file, keyring), never from the vault."""
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.GPG__Verifier               import GPG__Verifier
from   sgit_ai.crypto.signing.SSH__Sig__Verifier          import SSH__Sig__Verifier
from   sgit_ai.crypto.signing.SSH__Sig__Verifier__Keygen  import SSH__Sig__Verifier__Keygen
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.safe_types.Enum__User_Signature_Status     import Enum__User_Signature_Status
from   sgit_ai.schemas.Schema__Signing_Config             import Schema__Signing_Config
from   sgit_ai.schemas.Schema__User_Signature__Result     import Schema__User_Signature__Result


class User__Signature__Verifier(Type_Safe):
    config : Schema__Signing_Config
    runner : Signing__Command_Runner

    def verify(self, signature, payload: bytes, at_time_ms: int) -> Schema__User_Signature__Result:
        if signature is None or not signature.blob:
            return Schema__User_Signature__Result(status=Enum__User_Signature_Status.NONE)
        if signature.format == Enum__User_Signature_Format.OPENPGP:
            return GPG__Verifier(runner=self.runner).verify(signature, payload, at_time_ms, self.config)
        allowed = str(self.config.allowed_signers_file) if self.config.allowed_signers_file else None
        revoked = str(self.config.revocation_file)      if self.config.revocation_file      else None
        result  = SSH__Sig__Verifier().verify(signature, payload, at_time_ms, allowed, revoked)
        if result.status == Enum__User_Signature_Status.CANNOT_CHECK:
            return SSH__Sig__Verifier__Keygen(runner=self.runner).verify(
                signature, payload, at_time_ms, allowed, revoked, str(self.config.ssh_program or 'ssh-keygen'))
        return result
