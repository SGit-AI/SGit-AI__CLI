"""Signing__Config__Resolver — flags, then the user's Git config, then defaults
(design__02 §5.6.1) -> Schema__Signing_Config.

The switch is sgit's own `sgit.gpgSign` (D2): an existing `commit.gpgSign = true` does
not make agents start signing after an upgrade. `gpg.format` unset with an SSH-looking
key means ssh (D3b); `x509` is refused by name."""
import os
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.Vault__Signing_Error        import Vault__Signing_Error
from   sgit_ai.crypto.signing.Git__Config__Reader         import Git__Config__Reader
from   sgit_ai.safe_types.Enum__GPG_Trust                 import Enum__GPG_Trust
from   sgit_ai.safe_types.Enum__Sign_Choice               import Enum__Sign_Choice
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.schemas.Schema__Signing_Config             import Schema__Signing_Config
from   sgit_ai.schemas.Schema__Signing_Flags              import Schema__Signing_Flags

OPENSSH_PRIVATE = b'-----BEGIN OPENSSH PRIVATE KEY-----'


class Signing__Config__Resolver(Type_Safe):
    reader : Git__Config__Reader

    def resolve(self, flags: Schema__Signing_Flags = None, values: dict = None) -> Schema__Signing_Config:
        flags  = flags or Schema__Signing_Flags()
        values = self.reader.read() if values is None else values
        config = Schema__Signing_Config()
        if flags.sign == Enum__Sign_Choice.OFF:
            config.sign, config.source = False, 'flag'
        elif flags.sign == Enum__Sign_Choice.ON or flags.key:
            config.sign, config.source = True, 'flag'
        else:
            config.sign   = self.reader.as_bool(values.get('sgit.gpgsign'))
            config.source = 'sgit.gpgSign' if config.sign else None
        config.signing_key          = str(flags.key) if flags.key else values.get('user.signingkey')
        config.format               = self.format_of(values.get('gpg.format'), config.signing_key)
        config.gpg_program          = values.get('gpg.openpgp.program') or values.get('gpg.program') or 'gpg'
        config.ssh_program          = values.get('gpg.ssh.program') or 'ssh-keygen'
        config.allowed_signers_file = self.path(values.get('gpg.ssh.allowedsignersfile'))
        config.revocation_file      = self.path(values.get('gpg.ssh.revocationfile'))
        config.default_key_command  = values.get('gpg.ssh.defaultkeycommand')
        trust = (values.get('gpg.mintrustlevel') or '').strip().lower()
        config.min_trust_level      = Enum__GPG_Trust(trust) if trust in [t.value for t in Enum__GPG_Trust] else None
        return config

    def format_of(self, configured: str, key: str) -> Enum__User_Signature_Format:
        configured = (configured or '').strip().lower()
        if configured == 'x509':
            raise Vault__Signing_Error('gpg.format = x509 is not supported by sgit; use ssh or openpgp')
        if configured in ('ssh', 'openpgp'):
            return Enum__User_Signature_Format(configured)
        return Enum__User_Signature_Format.SSH if self.looks_like_ssh(key) else Enum__User_Signature_Format.OPENPGP

    def looks_like_ssh(self, key: str) -> bool:
        key = (key or '').strip()
        if key.startswith(('ssh-', 'ecdsa-', 'sk-', 'key::')) or key.endswith('.pub'):
            return True
        path = os.path.expanduser(key)
        if key and os.path.isfile(path):
            try:
                with open(path, 'rb') as f:
                    return f.read(len(OPENSSH_PRIVATE)) == OPENSSH_PRIVATE
            except OSError:
                return False
        return False

    def path(self, value: str):
        return os.path.expanduser(value) if value else None
