"""GPG__Signer — `gpg --status-fd=2 -bsu <key>`, Git's call without --armor (the binary
signature is stored compactly). Success needs exit 0, `[GNUPG:] SIG_CREATED` on the
status fd and an OpenPGP signature packet on stdout (design__02 §5.5)."""
import base64
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.Vault__Signing_Error        import Vault__Signing_Error
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner, TIMEOUT_SIGN
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.schemas.Schema__User_Signature             import Schema__User_Signature

PACKET_TAGS = (0x88, 0x89, 0xC2)                            # old-format tag 2 (1- and 2-byte length), new-format tag 2
MAX_B64     = 8192


class GPG__Signer(Type_Safe):
    runner : Signing__Command_Runner

    def sign(self, payload: bytes, config) -> Schema__User_Signature:
        program = str(config.gpg_program or 'gpg')
        key     = str(config.signing_key or '').strip()
        argv    = [program, '--status-fd=2', '-bsu', key] if key else [program, '--status-fd=2', '-bs']
        result  = self.runner.run(argv, stdin=payload, timeout=TIMEOUT_SIGN)
        created = b'[GNUPG:] SIG_CREATED ' in result['err']
        if result['code'] != 0 or not created:
            lines = [l for l in result['err'].decode('utf-8', 'replace').splitlines()
                     if l.strip() and not l.startswith('[GNUPG:]')]
            raise Vault__Signing_Error(f'{program}: ' + (lines[-1].strip() if lines else 'failed to sign the data'))
        signature = result['out']
        encoded   = base64.b64encode(signature).decode()
        if not signature or signature[0] not in PACKET_TAGS or len(encoded) > MAX_B64:
            raise Vault__Signing_Error(f'{program} printed no OpenPGP signature packet (or one over 8 KiB)')
        return Schema__User_Signature(format=Enum__User_Signature_Format.OPENPGP, blob=encoded)
