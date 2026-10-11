## `canonical_segment` in sgit_ai/storage/Vault__Path_Guard.py (L106-L113)

```python
# L110-L113
name = _IGNORABLE_CODEPOINTS.sub('', str(segment or ''))
name = unicodedata.normalize('NFC', name).casefold()
name = name.split(':', 1)[0]
return name.rstrip('. ')
```

**Purpose:** Models how a case-insensitive, normalising filesystem (macOS, Windows/NTFS) would resolve one path segment, so `is_protected` can compare against the protected names on every platform (L29-L34).

**Inputs & Assumptions:**
- `segment` (str): one path component. Trust: untrusted.
- Precondition: none; `None`/empty → `''`.

**Outputs & Effects:** Pure, returns str, never raises.

**Block-by-Block:**
- L110: strips the ignorable code points listed in `_IGNORABLE_CODEPOINTS` (L35: soft hyphen, U+200B–U+200F, U+202A–U+202E, U+2060–U+2064, U+206A–U+206F, U+FEFF). **Assumes** this list is the set HFS+ ignores; it is a fixed list, not derived from Unicode properties (e.g. `Default_Ignorable_Code_Point` also includes U+034F, U+115F-U+1160, U+17B4-U+17B5, U+180B-U+180E, U+FE00-U+FE0F, U+FFF0-U+FFF8, U+E0000-U+E0FFF). Whether the filesystems in question ignore those is not checked here; `nothing found`.
- L111: NFC then `casefold()`.
- L112: cuts an NTFS alternate-data-stream suffix (`.git::$DATA` → `.git`).
- L113: strips trailing dots and spaces (Windows drops them).

**Cross-Function Dependencies:**
- Callers: `is_protected` L96 only.
- No callees beyond stdlib `re`/`unicodedata`.

**Open Questions:**
- Completeness of `_IGNORABLE_CODEPOINTS` versus what each target filesystem actually ignores (see above).
