## `parse` in sgit_ai/storage/Vault__Index_Reader.py (L36-L42)

```python
# L37-L42
data          = dict(data or {})
data.pop('carried_tags', None)
tags, carried = self.resolve(list(data.get('tags') or []))
data['tags']         = tags
data['carried_tags'] = carried
return Schema__Branch_Index.from_json(data)
```

**Purpose:** The one way a decrypted branch index dict becomes `Schema__Branch_Index`. Tag entries this version cannot read are carried as exact JSON rather than dropped or allowed to break the parse (module docstring L1-L19; reviews 0a0707d R1, eed8084 B1).

**Inputs & Assumptions:**
- `data` (dict): the JSON of the index after AES-GCM decryption under the read key. Trust: **semi-trusted** — authentic under the read key, but any read-key holder (A3) with host help, or the host replaying an old copy (TM-R29), chooses its contents. Every field except `tags` is parsed strictly by `Schema__Branch_Index.from_json` (L42): `branches` → `Schema__Branch_Meta` with strict `Safe_Str__Branch_Id`/`Safe_Str__Branch_Name`/`Safe_Str__Ref_Id`/`Safe_Str__Key_Id` regexes; `format : Safe_UInt`; `min_client : Safe_Str__Semver`; `features : list[Safe_Str__Feature]`.
- `carried_tags` on disk is removed first (L38): it is never a key on disk (schema comment L25-L29); a host-supplied one is discarded, not merged.
- Implicit: clock (`resolve` L62 uses `time.time()`).
- Precondition: a non-dict `data` → `dict(data)` raises `TypeError`/`ValueError`; callers (`Vault__Branch_Manager.load_branch_index` L94) let it propagate.

**Outputs & Effects:** Returns the schema; raises on anything the strict fields reject (unknown top-level keys: `Type_Safe__Step__From_Json.deserialize_from_dict` L30-L32 ignores unknown attributes unless `raise_on_not_found` — default False — so **an unknown top-level key is silently dropped**, and a writer then omits it on the next `serialize`; this is the fail-open the `Vault__Format` docstring describes (L76-L77) and the TM-R29 row).

**Cross-Function Dependencies:**
- Callee `resolve` L58 (internal).
- Callee `Schema__Branch_Index.from_json` (external-source-available, osbot_utils): unknown keys dropped; known keys coerced through the Safe_* types; a `Safe_Str` in MATCH/strict mode raises on a non-matching value — so one malformed `branch_id` makes the whole index unreadable (the strictness the docstring L12 keeps: "Branches and everything else stay strict").
- Callers: `Vault__Branch_Manager.load_branch_index` L94 (every read of the local index), and index-merge code (`Vault__Index_Sync`, `Vault__Sync__Format`, `Vault__Sync__Tag` — not read).
- Tests: `tests/unit/review/test_Review__eed8084.py` B1 group (`test_a_tombstone_this_build_cannot_read_still_deletes_the_tag`, `test_an_entry_whose_timestamp_cannot_be_read_wins_and_nothing_is_dropped`, `test_round_trip_puts_carried_entries_back_in_tags`, `test_unknown_fields_and_coerced_values_are_not_read`).

**Open Questions:**
- The exact set of top-level keys that `from_json` silently drops is whatever is not in `Schema__Branch_Index.__annotations__` — recorded as the mechanism behind TM-R29 rather than re-derived here.
