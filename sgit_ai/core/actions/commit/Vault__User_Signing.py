"""Vault__User_Signing — whether, and with which key, a command signs with the user's own
key: its flags, then the user's Git config (`sgit.gpgSign`, `user.signingKey`, `gpg.*`).
None when the command does not sign (the default), so callers pass nothing on."""
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.Signing__Config__Resolver   import Signing__Config__Resolver
from   sgit_ai.crypto.signing.User__Signer                import User__Signer
from   sgit_ai.schemas.Schema__Signing_Flags              import Schema__Signing_Flags


class Vault__User_Signing(Type_Safe):

    def signer_for(self, flags: Schema__Signing_Flags = None):
        config = Signing__Config__Resolver().resolve(flags)
        return User__Signer(config=config) if config.sign else None
