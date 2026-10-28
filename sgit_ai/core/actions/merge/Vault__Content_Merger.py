"""Vault__Content_Merger — the line merge behind the blob-id merge (design__01 §5.5).

Vault__Merge.three_way_merge decides which paths both sides changed by blob id (and
equal bytes, F4); only for those, with the `lines` style, it asks this class to merge
the contents. A clean result becomes a new blob in the store and an ordinary entry;
a conflict returns the marker bytes, which are written to the working copy and never
stored (the commit guard refuses them until they are resolved); anything that cannot
be line-merged (binary, too large, a blob not in the store) falls back to today's
whole-file conflict with the reason.
"""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.core.text.Vault__Line_Merge          import Vault__Line_Merge
from   sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from   sgit_ai.safe_types.Enum__Conflict_Style      import Enum__Conflict_Style
from   sgit_ai.safe_types.Enum__Line_Merge_Outcome  import Enum__Line_Merge_Outcome
from   sgit_ai.schemas.Schema__Conflict_Labels      import Schema__Conflict_Labels
from   sgit_ai.storage.Vault__Object_Store          import Vault__Object_Store


class Vault__Content_Merger(Type_Safe):
    crypto         : Vault__Crypto
    obj_store      : Vault__Object_Store
    line_merge     : Vault__Line_Merge
    labels         : Schema__Conflict_Labels
    conflict_style : Enum__Conflict_Style = Enum__Conflict_Style.MERGE

    def merge_entry(self, path: str, base_entry: dict, ours_entry: dict, theirs_entry: dict, read_key: bytes) -> dict:
        """dict(outcome, entry=<flat entry> on CLEAN, markers=<bytes> and hunks on CONFLICT,
        reason otherwise)."""
        if not ours_entry or not theirs_entry:
            return dict(outcome=Enum__Line_Merge_Outcome.NOT_TEXT_PAIR, reason='changed on one side, deleted on the other')
        try:
            base   = self.read(base_entry, read_key) if base_entry else b''
            ours   = self.read(ours_entry,   read_key)
            theirs = self.read(theirs_entry, read_key)
        except Exception:
            return dict(outcome=Enum__Line_Merge_Outcome.MISSING_BLOB, reason='a version is not in this clone')
        content, result = self.line_merge.merge(base, ours, theirs, labels=self.labels, conflict_style=self.conflict_style)
        if result.outcome == Enum__Line_Merge_Outcome.CLEAN:
            return dict(outcome=result.outcome, entry=self.entry_for(content, ours_entry, theirs_entry, read_key))
        if result.outcome == Enum__Line_Merge_Outcome.CONFLICT:
            return dict(outcome=result.outcome, markers=content, hunks=int(result.hunks))
        return dict(outcome=result.outcome, reason=str(result.reason or result.outcome.value))

    def read(self, entry: dict, read_key: bytes) -> bytes:
        return self.crypto.decrypt(read_key, self.obj_store.load(entry['blob_id']))

    def entry_for(self, content: bytes, ours_entry: dict, theirs_entry: dict, read_key: bytes) -> dict:
        """A flat entry for merged bytes: ours' blob when the result is ours, else a new
        blob (deflated on blob-deflate vaults, as any commit's)."""
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        blob_id, large, content_hash = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store).encrypt_or_reuse_blob(
            content, ours_entry, read_key)
        return dict(blob_id      = blob_id,
                    size         = len(content),
                    content_hash = content_hash,
                    content_type = ours_entry.get('content_type') or theirs_entry.get('content_type') or '',
                    large        = large)
