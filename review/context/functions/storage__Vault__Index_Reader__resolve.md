## `resolve` in sgit_ai/storage/Vault__Index_Reader.py (L58-L88)

```python
# L62-L88
horizon = int(now_ms if now_ms is not None else time.time() * 1000) + TAG_CLOCK_SKEW_MS
groups  = {}
for entry in entries:
    if isinstance(entry, Schema__Tag_Ref): entry = entry.json()
    text = self.canonical(entry)
    name = entry.get('name') if isinstance(entry, dict) else None
    key  = name if isinstance(name, str) else '\x00' + (self.canonical(name) if isinstance(entry, dict) else text)
    groups.setdefault(key, {})[text] = entry
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
    if unjudged:
        carried.extend(sorted(unjudged) + ([best[1]] if best else []))
    elif self.readable(best[2]):
        tags.append(Schema__Tag_Ref.from_json(best[2]).json())
    else:
        carried.append(best[1])
return tags, carried
```

**Purpose:** One winner per tag name across any number of index copies (local + server on merge), with the merge rule "later timestamp, then tag id, then tombstone; a date beyond the clock-skew horizon loses; an entry whose timestamp cannot be read wins and nothing is dropped" (docstring L14-L19). Decides what `tags` this clone acts on and what it `carries` verbatim.

**Inputs & Assumptions:**
- `entries` (list of dict or `Schema__Tag_Ref`): raw tag entries, possibly from several copies. Trust: semi-trusted (read-key authentic; a teammate or A3-with-host can write anything).
- `now_ms` (int, optional): test hook; default wall clock (L62). Implicit: the local clock. `TAG_CLOCK_SKEW_MS` = 24 h (L28).
- Non-dict entries (a string, a list) are grouped under a `'\x00'+canonical` key (L69) and are *unjudged* (L75 `ts = None`) → carried (L82-L83).

**Outputs & Effects:** Pure (except the clock read). Returns `(tags, carried)`: `tags` are re-serialised dicts of readable winners; `carried` are canonical JSON strings.

**Block-by-Block:**

```python
# L64-L70 grouping
```
- **What:** Dedupe identical entries across copies by canonical text (L70), group by `name`.
- **Assumes:** `canonical` (L90-L91: `json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=True)`) is total — it raises `TypeError` for non-serialisable values, but input came from `json.loads` so all values are serialisable.

```python
# L73-L80 judging
```
- **What:** An entry is judged only if `timestamp_ms` is a non-bool, non-negative int. `rank = (ts <= horizon, ts, tag_id, deleted, text)` — within-horizon beats beyond-horizon; then later ts; then larger `tag_id` string; then tombstone over live; then canonical text as the final tiebreak (deterministic).
- **Assumes:** a far-future timestamp cannot be used to pin a name forever: it sorts *below* every in-horizon entry (first tuple element False < True). But a far-future entry still wins against *no* in-horizon entry, and it wins against other far-future entries by `ts` — so once all live entries for a name are beyond the horizon the largest timestamp wins; and when the clock catches up (after the skew window) the far-future entry becomes in-horizon and beats everything older. `nothing found` that bounds how far ahead an entry may be and still eventually win; the design is "loses while beyond the horizon", not "rejected".

```python
# L81-L87 verdict
```
- **What:** If anything in the group is unjudged, **every** unjudged entry is carried plus the best judged one (L83) — nothing is used, nothing dropped; a tombstone this version cannot parse still hides the live entry (docstring L17-L18). Otherwise the winner is used if `readable`, else carried.
- **Assumes:** carrying the best judged entry alongside unjudged ones lets a future client judge them; a *second-best* judged entry is dropped on write (only `best[1]` is kept, L83) — by design: it lost to `best` under a rule every client shares.

**Cross-Function Dependencies:**
- Callees: `canonical` L90, `readable` L44, `Schema__Tag_Ref.from_json`.
- Callers: `parse` L39; merge code in `Vault__Index_Sync`/`Vault__Sync__Tag` (via `entries()`+`resolve` or `parse` — not read).
- Tests: `tests/unit/review/test_Review__eed8084.py` (`test_a_tombstone_this_build_cannot_read_still_deletes_the_tag`, `test_an_entry_whose_timestamp_cannot_be_read_wins_and_nothing_is_dropped`, `test_a_readable_later_entry_beats_an_older_unreadable_tombstone`, `test_a_name_held_by_an_unreadable_entry_is_not_taken_silently`).

**Open Questions:**
- Unbounded growth: `carried` keeps every unjudged variant of a name across merges; each `serialize` writes them all back; nothing caps the count or size per name (`Safe_Str__Index_Entry_Json` caps one entry at 1 MiB, L5 of its file). A read-key writer can grow the index monotonically — recorded, not rated.
- Whether `Vault__Index_Sync` merges by calling `resolve` over local+remote entries or by `parse` on each — affects whether the "same entry from two copies counts once" claim (L70) is exercised; not read.
