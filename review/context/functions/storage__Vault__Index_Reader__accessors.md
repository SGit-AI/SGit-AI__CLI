# Remaining methods in sgit_ai/storage/Vault__Index_Reader.py

## `canonical` (L90-L91)
`json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)`. Deterministic text for grouping and for `Safe_Str__Index_Entry_Json` (which requires printable ASCII: regex `^[\x20-\x7E]*\Z`, max 1 MiB, strict — `ensure_ascii` is what satisfies it). An entry whose canonical text exceeds 1 MiB would make `Schema__Branch_Index.from_json` raise in `parse` (L42) — the whole index unreadable; `nothing found` that bounds entry size before that point.

## `entries` (L93-L98)
`[t.json() for t in index.tags] + [json.loads(str(c)) for c in index.carried_tags]` — every tag entry as raw dicts, for merging. `None` → `[]`.

## `to_json` (L101-L106)
`index.json()`, pop `carried_tags`, append the parsed carried entries back into `tags`. This is why `carried_tags` is never on disk (schema comment L25-L29).

## `serialize` (L108-L109)
`json.dumps(to_json(index)).encode()` — the bytes `Vault__Branch_Manager.save_branch_index` encrypts (L81). Note `json.dumps` default `ensure_ascii=True`; no `sort_keys` — the index bytes are not canonical, so two clients writing the same logical index produce different ciphertexts anyway (random IV).

## `carried_names` (L112-L117)
`str(name)[:100]` per carried entry (for warnings). Non-dict carried entries are stringified whole.

## `warn_new` (L119-L125)
Warns once per carried name that appears in `after` but not `before`. Caller: `Step__Clone__Download_Index` L106 (`before=None`).

## `warn_skipped` (L127-L132)
Process-global `WARNED` set (L33) + stderr. Prints `name!r` — attacker-chosen (read-key holder) text reaches the terminal through `repr`, which escapes control characters.
