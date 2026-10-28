"""Vault__User_Signatures — the user signatures (the signer's own SSH / OpenPGP key) on
commits and tags, checked with this verifier's own trust (design__02 §5.3.3).

The payload is the object's signing bytes (the same bytes the clone signature covers),
and the time is the commit's own timestamp, as Git passes -Overify-time. The verdict
is never stored: who a key belongs to comes from this machine's allowed-signers file or
keyring. `lines()` words each verdict as `git log --show-signature` does."""
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.Signing__Config__Resolver   import Signing__Config__Resolver
from   sgit_ai.crypto.signing.User__Signature__Verifier   import User__Signature__Verifier
from   sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from   sgit_ai.safe_types.Enum__User_Signature_Status     import Enum__User_Signature_Status
from   sgit_ai.schemas.Schema__User_Signature__Result     import Schema__User_Signature__Result
from   sgit_ai.storage.Vault__Commit                      import Vault__Commit

STATUSES = [s.value for s in Enum__User_Signature_Status]


class Vault__User_Signatures(Type_Safe):
    verifier : User__Signature__Verifier = None

    def setup(self, config=None) -> 'Vault__User_Signatures':
        self.verifier = User__Signature__Verifier(config=config or Signing__Config__Resolver().resolve())
        return self

    def result_for(self, obj, signing_bytes: bytes = None) -> Schema__User_Signature__Result:
        """The verdict on a loaded commit or tag (NONE when it carries no user signature)."""
        signature = getattr(obj, 'user_signature', None)
        if signature is None or not signature.blob:
            return Schema__User_Signature__Result(status=Enum__User_Signature_Status.NONE)
        if self.verifier is None:
            self.setup()
        if signing_bytes is None:
            signing_bytes = Vault__Commit().signing_bytes(obj.json())
        return self.verifier.verify(signature, signing_bytes, int(obj.timestamp_ms or 0))

    def lines_by_commit(self, directory: str, commit_ids: list, crypto=None) -> dict:
        """{commit id: Git-worded lines} for `--show-signature`; a commit that cannot be
        loaded is left out."""
        from sgit_ai.core.Vault__Sync__Base import Vault__Sync__Base
        from sgit_ai.crypto.Vault__Crypto   import Vault__Crypto
        crypto = crypto or Vault__Crypto()
        c      = Vault__Sync__Base(crypto=crypto)._init_components(directory)
        vc     = Vault__Commit(crypto=crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        out    = {}
        for commit_id in commit_ids:
            try:
                commit = vc.load_commit(str(commit_id), c.read_key)
            except (FileNotFoundError, ValueError):                         # not in this clone, or unreadable
                commit = None
            if commit is not None:
                out[str(commit_id)] = self.lines(self.result_for(commit, vc.signing_bytes(commit.json())))
        return out

    def as_json(self, result: Schema__User_Signature__Result, at_ms: int = 0) -> dict:
        """The design's JSON object (§3.6): every value a string."""
        status = result.status or Enum__User_Signature_Status.NONE
        return {'status'         : status.value,
                'code'           : status.code(),
                'format'         : result.format.value if result.format else '',
                'principal'      : str(result.principal or ''),
                'key_type'       : str(result.key_type or ''),
                'key_fingerprint': str(result.key_fingerprint or ''),
                'signed_at_ms'   : str(at_ms or ''),
                'reason'         : str(result.reason or '')}

    def lines(self, result: Schema__User_Signature__Result) -> list:
        """Git's wording for `--show-signature` (nothing for an unsigned commit)."""
        status = result.status
        if status in (None, Enum__User_Signature_Status.NONE):
            return []
        who  = str(result.principal or result.key_fingerprint or 'an unknown key')
        if result.format == Enum__User_Signature_Format.OPENPGP:
            key  = f'{result.key_type or "OpenPGP"} key {result.key_fingerprint or "?"}'
            text = {Enum__User_Signature_Status.GOOD             : [f'Good signature from "{who}" [{key}]'],
                    Enum__User_Signature_Status.UNTRUSTED        : [f'Good signature from "{who}" [{key}]',
                                                                    f'WARNING: {result.reason or "the key is not certified"}'],
                    Enum__User_Signature_Status.BAD              : [f'BAD signature from "{who}"'],
                    Enum__User_Signature_Status.EXPIRED_SIGNATURE: [f'Expired signature from "{who}" [{key}]'],
                    Enum__User_Signature_Status.EXPIRED_KEY      : [f'Good signature from "{who}" by an expired key [{key}]'],
                    Enum__User_Signature_Status.REVOKED          : [f'Good signature from "{who}" by a revoked key [{key}]']}
        else:
            key  = f'{result.key_type or "SSH"} key {result.key_fingerprint or "?"}'
            text = {Enum__User_Signature_Status.GOOD     : [f'Good "git" signature for {result.principal} with {key}'],
                    Enum__User_Signature_Status.UNTRUSTED: [f'Good "git" signature with {key}', 'No principal matched.'
                                                            if str(result.reason or '') in ('', 'no principal matched')
                                                            else f'No principal matched ({result.reason}).'],
                    Enum__User_Signature_Status.BAD      : [f'BAD signature from {who}' +
                                                            (f' ({result.reason})' if result.reason else '')]}
        return text.get(status, [f'Cannot check the user signature: {result.reason or status.value}'])

    def empty_counts(self) -> dict:
        return {name: 0 for name in STATUSES}
