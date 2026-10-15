## `is_protected` in sgit_ai/storage/Vault__Path_Guard.py (L89-L104)

```python
# L94-L104
raw = '' if rel_path is None else str(rel_path)
for segment in raw.replace('\\', '/').split('/'):
    canonical = self.canonical_segment(segment)
    for name in {segment, canonical, canonical.upper().lower()}:
        if name in VAULT_PROTECTED_DIRS:                         return True
        if any(name.startswith(prefix) for prefix in VAULT_PROTECTED_PREFIXES): return True
        if _SHORT_NAME.match(name) or _VAULT_BACKUP_ZIP.match(name) or _LEGACY_BACKUP_ZIP.match(name): return True
return False
```

**Purpose:** Decides whether any segment of a path names something vault data must never write (and a commit must never pick up): `.git`, `.sg_vault`, `.sg_vault_new`, `.sg_vault_old_*` (L26-L27), their case/normalisation/8.3/NTFS-stream spellings (L29-L36), and the uninit backup zip names old and new (L39-L49). It is the structural half of `safe_join` (L128) and the non-grandfathered half of `Vault__Ignore` (L110, L128, L193).

**Inputs & Assumptions:**
- `rel_path` (str or None): Trust: **untrusted** (tree names, zip members, host file ids, CLI args).
- Implicit: the module constants `VAULT_PROTECTED_DIRS`, `VAULT_PROTECTED_PREFIXES`, `_SHORT_NAME`, `_VAULT_BACKUP_ZIP`, `_LEGACY_BACKUP_ZIP`.
- Precondition: none; `None` and non-str are stringified (L94).

**Outputs & Effects:**
- Pure; returns bool; never raises (relies on `canonical_segment` never raising — it only does regex/unicodedata/str ops, L110-L113).

**Block-by-Block:**

```python
# L95-L96
for segment in raw.replace('\\', '/').split('/'):
    canonical = self.canonical_segment(segment)
```
- **What:** Walks every segment on either separator and computes the name a case-folding/normalising filesystem would resolve it to.
- **Why here:** Protection must hold at any depth (`a/b/.SG_VAULT/local/vault_key` in `tests/unit/storage/test_Vault__Path_Guard.py:L88`).
- **Assumes:** `canonical_segment` produces what macOS/Windows/NTFS would (ignorable code points dropped, NFC, casefold, `:` stream cut, trailing `. ` stripped). HFS+ actually uses a variant of NFD; the code normalises to NFC and then casefolds, which is enough for the compared ASCII names — the protected names are all ASCII after folding.
- **Establishes:** three candidate spellings per segment (L97).

```python
# L97
for name in {segment, canonical, canonical.upper().lower()}:
```
- **What:** Also tests the upper-then-lower round trip so `.gıt` (dotless i, U+0131) which NTFS upper-cases to `.GIT` is caught (comment L97; `tests/security/test_Security__Fixed__Hostile_Paths.py::Test_Fixed__Path_Guard_Leftovers`).
- **Assumes:** Python's `str.upper().lower()` models the filesystem's case mapping closely enough. `casefold()` alone maps `ı` to `ı`, so the extra step is what catches it.

```python
# L98-L103
```
- **What:** Exact set membership, prefix match, three regexes.
- **Assumes:** The regexes describe the forms that matter: `_SHORT_NAME` (L36) covers `git~N`, `sg_vau~N`, and hashed `sg[0-9a-f]{4}~N`; `_VAULT_BACKUP_ZIP` (L44) covers `.vault__*.zip` and its `.sha256`/`.manifest.json` sidecars; `_LEGACY_BACKUP_ZIP` (L48-L49) covers the 0.20.0 `<id>__<ts>__<label>.zip` shape. The legacy regex is lowercase-only on the timestamp letter (`t`, `z`) and the vault id; it is matched against `canonical` (casefolded) as well as the raw segment, so an upper-case file name is still caught via the canonical candidate.
- **Establishes:** the verdict.

**Cross-Function Dependencies:**
- Callee `canonical_segment` (internal, L106-L113).
- Callers: `safe_join` L128; `is_writable` L79; `Vault__Verified_Write.is_store_path` L37 (on a whole file id, so `bare/data/.git` would be refused — see that record); `Vault__Sub_Tree.checkout` L188; `Vault__Sync__Base._checkout_flat_map` L511; `Vault__Ignore.should_ignore_dir` L110, `should_ignore_file` L128, `explain` L193.
- Tests: `tests/unit/storage/test_Vault__Path_Guard.py::Test_Vault__Path_Guard__Other_Spellings` (HOSTILE L86-L88, BENIGN L89-L90); `tests/security/test_Security__Fixed__Hostile_Paths.py::Test_Fixed__Backup_Zip_Names`, `::Test_Fixed__Path_Guard_Leftovers`; `tests/security/test_Security__Fixed__Secrets_In_Commits.py::test_uninit_backup_has_the_protected_name`, `::test_a_0_20_0_named_backup_is_not_committed_either`.
- Invariant coupling: `Vault__Ignore` relies on this being strictly stronger than `ALWAYS_IGNORED_DIRS ∩ {structural}` so tracked-wins can never grandfather a structural path (L18-L25 comment; `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py::Test_A2__Structural_Not_Written_On_Checkout`).

**Open Questions:**
- `.github` is in `ALWAYS_IGNORED_DIRS` (Vault__Ignore L8) but deliberately not here (L23-L25), so a tracked `.github/workflows/x.yml` is still written on checkout; the threat model's decision 17 accepts this. Recording it as the one preference-level name that *can* reach disk from vault data.
- Whether `_LEGACY_BACKUP_ZIP`'s `[a-z0-9]{4,24}` vault-id range matches every id `Vault__Backup` ever produced — `VAULT_ID_PATTERN` in `Vault__Crypto.py:L24` is the same `[a-z0-9]{4,24}`; a backup made with an empty `vault_id` (`Vault__Backup.py:L70` allows `vault_id` unset → `'__<ts>__label.zip'`) does not match (`{4,24}` requires 4+). Not checked further.
