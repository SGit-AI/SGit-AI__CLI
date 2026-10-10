"""Vault__Index_Reader — the one way a decrypted branch index becomes a schema.

The index is shared by every client of the vault (old and new sgit, the web UI). One
entry this version cannot read must not make the whole index unreadable: a tag named
under another version's rule broke every clone, and deleting it did not help because
the tombstone keeps the name (review 0a0707d R1). Tag entries that do not parse are
skipped with one warning naming them; branches and everything else stay strict.
"""
import sys
from osbot_utils.type_safe.Type_Safe            import Type_Safe
from sgit_ai.schemas.Schema__Branch_Index       import Schema__Branch_Index
from sgit_ai.schemas.Schema__Tag_Ref            import Schema__Tag_Ref


class Vault__Index_Reader(Type_Safe):
    WARNED = set()                                                   # entries already reported in this process

    def parse(self, data: dict) -> Schema__Branch_Index:
        data = dict(data or {})
        kept = []
        for entry in data.get('tags') or []:
            try:
                Schema__Tag_Ref.from_json(entry)
                kept.append(entry)
            except Exception as error:
                self.warn_skipped(entry, error)
        data['tags'] = kept
        return Schema__Branch_Index.from_json(data)

    def warn_skipped(self, entry, error) -> None:
        name = str(entry.get('name') if isinstance(entry, dict) else entry)[:100]
        if name in Vault__Index_Reader.WARNED:                       # the index is read many times per command
            return
        Vault__Index_Reader.WARNED.add(name)
        print(f'warning: skipping tag entry {name!r} in the branch index: this sgit cannot read it ({error}); '
              f'the rest of the index is used', file=sys.stderr)
