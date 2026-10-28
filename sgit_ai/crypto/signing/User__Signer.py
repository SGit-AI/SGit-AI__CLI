"""User__Signer — the signer's own key (SSH or OpenPGP), picked from a resolved
Schema__Signing_Config: what commit / write / pull / merge / tag hand to the object
writer. sign() raises Vault__Signing_Error, so nothing is written on a failure."""
import base64
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.GPG__Signer                 import GPG__Signer
from   sgit_ai.crypto.signing.SSH__Public_Key             import SSH__Public_Key
from   sgit_ai.crypto.signing.SSH__Sig__Blob              import SSH__Sig__Blob
from   sgit_ai.crypto.signing.SSH__Signer                 import SSH__Signer
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.schemas.Schema__Signing_Config             import Schema__Signing_Config
from   sgit_ai.schemas.Schema__User_Signature             import Schema__User_Signature


class User__Signer(Type_Safe):
    config : Schema__Signing_Config
    runner : Signing__Command_Runner

    def sign(self, payload: bytes) -> Schema__User_Signature:
        if self.config.format == Enum__User_Signature_Format.SSH:
            return SSH__Signer(runner=self.runner).sign(payload, self.config)
        return GPG__Signer(runner=self.runner).sign(payload, self.config)

    def describe(self, signature: Schema__User_Signature) -> str:
        """"ssh key SHA256:… (user.signingKey ~/.ssh/id_ed25519.pub)" for the commit output."""
        where = f' (user.signingKey {self.config.signing_key})' if self.config.signing_key else ''
        if signature.format == Enum__User_Signature_Format.SSH:
            sshsig = SSH__Sig__Blob().parse(base64.b64decode(str(signature.blob)))
            return f'ssh key {SSH__Public_Key(blob=sshsig.public_key_blob).fingerprint()}{where}'
        return f'openpgp key {self.config.signing_key or "(gpg default key)"}'
