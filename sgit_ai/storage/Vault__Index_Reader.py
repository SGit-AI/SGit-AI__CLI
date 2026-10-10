"""Vault__Index_Reader — the one way a decrypted branch index becomes a schema, and back.

The index is shared by every client of the vault (old and new sgit, the web UI). One
entry this version cannot read must not make the whole index unreadable: a tag named
under another version's rule broke every clone, and deleting it did not help because
the tombstone keeps the name (review 0a0707d R1).

Nor may it be lost. Skipping such an entry on read and then writing the index back
erased it for every client, and a tombstone this version could not read stopped hiding
the tag it deleted, so the tag came back (review eed8084 B1). So an entry this version
cannot read is CARRIED: kept as its exact JSON (`carried_tags`), never used, and written
back inside `tags` by `serialize`. Branches and everything else stay strict.

Per name, one entry wins, decided the way a client that can read every entry decides
(later timestamp, then tag id, then the tombstone; a date beyond the clock-skew horizon
loses). An entry whose timestamp this version cannot read cannot be judged: it wins, so
a tombstone this version cannot parse still hides a live entry of the same name, and the
entry it beat is carried with it for a client that can judge them.
"""
import json
import re
import sys
import time
from osbot_utils.type_safe.Type_Safe            import Type_Safe
from sgit_ai.schemas.Schema__Branch_Index       import Schema__Branch_Index
from sgit_ai.schemas.Schema__Tag_Ref            import Schema__Tag_Ref

TAG_CLOCK_SKEW_MS = 24 * 3600 * 1000                     # how far ahead of this clock a tag entry may be dated and still count
COMMIT_SHAPED     = re.compile(r'^obj-cas-imm-[0-9a-f]+\Z')  # a tag must never read as a commit id (review eed8084 F6)


class Vault__Index_Reader(Type_Safe):
    WARNED = set()                                                   # entries already reported in this process

    # ----------------------------------------------------------------- read
    def parse(self, data: dict) -> Schema__Branch_Index:
        data          = dict(data or {})
        data.pop('carried_tags', None)                               # never a key on disk; the entries live in `tags`
        tags, carried = self.resolve(list(data.get('tags') or []))
        data['tags']         = tags
        data['carried_tags'] = carried
        return Schema__Branch_Index.from_json(data)

    def readable(self, entry) -> bool:
        """True when this version reads the entry exactly: it parses, has no field this
        version does not know, and parsing changes nothing (a field it would drop or
        coerce is a field it does not understand)."""
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str):
            return False
        if COMMIT_SHAPED.match(entry['name']):
            return False
        try:
            parsed = Schema__Tag_Ref.from_json(entry).json()
        except Exception:
            return False
        return all(k in parsed and parsed[k] == v for k, v in entry.items())

    def resolve(self, entries: list, now_ms: int = None) -> tuple:
        """(tags, carried): one winner per name among `entries` (raw dicts, from any
        number of copies of the index). Winners this version reads go to `tags`;
        everything kept that it cannot read goes to `carried` as canonical JSON text."""
        horizon = int(now_ms if now_ms is not None else time.time() * 1000) + TAG_CLOCK_SKEW_MS
        groups  = {}
        for entry in entries:
            if isinstance(entry, Schema__Tag_Ref):
                entry = entry.json()
            text = self.canonical(entry)
            name = entry.get('name') if isinstance(entry, dict) else None
            key  = name if isinstance(name, str) else '\x00' + (self.canonical(name) if isinstance(entry, dict) else text)
            groups.setdefault(key, {})[text] = entry                 # the same entry from two copies counts once
        tags, carried = [], []
        for key in sorted(groups):
            judged, unjudged = [], []
            for text, entry in groups[key].items():
                ts = entry.get('timestamp_ms', 0) if isinstance(entry, dict) else None
                if isinstance(ts, int) and not isinstance(ts, bool) and ts >= 0:
                    rank = (ts <= horizon, ts, str(entry.get('tag_id') or ''), bool(entry.get('deleted')), text)
                    judged.append((rank, text, entry))
                else:
                    unjudged.append(text)
            best = max(judged, key=lambda j: j[0]) if judged else None
            if unjudged:                                              # cannot be judged here: it wins, and nothing is dropped
                carried.extend(sorted(unjudged) + ([best[1]] if best else []))
            elif self.readable(best[2]):
                tags.append(Schema__Tag_Ref.from_json(best[2]).json())
            else:
                carried.append(best[1])
        return tags, carried

    def canonical(self, value) -> str:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

    def entries(self, index) -> list:
        """Every tag entry of an index as raw dicts: the ones it reads and the ones it carries."""
        if index is None:
            return []
        return ([t.json() for t in (index.tags or [])] +
                [json.loads(str(c)) for c in (getattr(index, 'carried_tags', None) or [])])

    # ---------------------------------------------------------------- write
    def to_json(self, index: Schema__Branch_Index) -> dict:
        """The index as it goes on disk and to the server: carried entries back in `tags`."""
        data    = index.json()
        carried = data.pop('carried_tags', None) or []
        data['tags'] = list(data.get('tags') or []) + [json.loads(str(c)) for c in carried]
        return data

    def serialize(self, index: Schema__Branch_Index) -> bytes:
        return json.dumps(self.to_json(index)).encode()

    # -------------------------------------------------------------- report
    def carried_names(self, index) -> list:
        names = []
        for text in (getattr(index, 'carried_tags', None) or []) if index is not None else []:
            entry = json.loads(str(text))
            names.append(str(entry.get('name') if isinstance(entry, dict) else entry)[:100])
        return names

    def warn_new(self, before, after) -> None:
        """One warning per carried entry the first time this clone sees it (when it
        arrives with a refresh or a clone), not on every command (review eed8084 nit)."""
        seen = set(self.carried_names(before))
        for name in self.carried_names(after):
            if name not in seen:
                self.warn_skipped(name)

    def warn_skipped(self, name: str) -> None:
        if name in Vault__Index_Reader.WARNED:                       # the index is read many times per command
            return
        Vault__Index_Reader.WARNED.add(name)
        print(f'warning: tag entry {name!r} in the branch index is one this sgit cannot read; it is '
              f'kept as it is for the clients that can, and the rest of the index is used', file=sys.stderr)
