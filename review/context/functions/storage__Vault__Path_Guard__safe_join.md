## `safe_join` in sgit_ai/storage/Vault__Path_Guard.py (L115-L151)

```python
# L128-L151
if self.is_protected(rel_path):
    raise Vault__Unsafe_Path_Error(...)
raw = '' if rel_path is None else str(rel_path)
if not raw.strip():
    raise Vault__Unsafe_Path_Error(...)
if raw.startswith('/') or raw.startswith('\\') or os.path.isabs(raw):
    raise Vault__Unsafe_Path_Error(...)
if any(part == '..' for part in raw.replace('\\', '/').split('/')):
    raise Vault__Unsafe_Path_Error(...)
base_abs = os.path.abspath(base_dir)
full     = os.path.abspath(os.path.join(base_abs, raw))
if full != base_abs and not full.startswith(base_abs + os.sep):
    raise Vault__Unsafe_Path_Error(...)
if self.has_link_component(base_abs, full):
    raise Vault__Unsafe_Path_Error(...)
if not self.is_inside(base_abs, os.path.realpath(full)):
    raise Vault__Unsafe_Path_Error(...)
return full
```

**Purpose:** The one function that turns a vault-, archive-, host- or user-supplied relative path into an absolute on-disk destination. Every write loop that consumes decrypted tree names (checkout, pull, revert, switch, stash pop, sparse, restore, merge), every verified store write (`Vault__Verified_Write.save`), the mirror writer and the static server resolve through it. Without it a tree entry named `../x`, `/etc/x` or `.git/hooks/x` would be written where it says (threat model §5 "Path guard", TM-R rows on hostile vault authors / A5).

**Inputs & Assumptions:**
- `base_dir` (str): the containment root. Trust: trusted — callers pass the working copy (`Vault__Sub_Tree.py:L193`, `Vault__Sync__Base.py:L518`), the `.sg_vault` dir (`Vault__Verified_Write.py:L82`), a mirror destination (`Vault__Mirror.py:L166`) or a served root (`Vault__Static_Server.py:L128,L132`). Never vault data.
- `rel_path` (str or None): the candidate. Trust: **untrusted** — decrypted tree names (A5), zip member names (`Vault__Stash.py:L96`, `Vault__Publish__Bundles.py:L75` via `save`), host file ids (`Vault__Verified_Write.py:L82`, `Vault__Mirror.py:L92,L166`), HTTP paths (`Vault__Static_Server.py:L132`), CLI arguments (`Vault__Sync__Commit.py:L348`).
- Implicit: the filesystem at call time — `has_link_component` (L145) and `realpath` (L148) read the live directory tree, so the verdict is about the tree as it is at that instant.
- Precondition: `base_dir` itself is not something the guard needs to check — links *above* `base_abs` are explicitly out of scope (L153-L155 docstring, `is_inside` L169 resolves them on both sides). Established by design, documented in threat model §5 ("links above the vault root are allowed").

**Outputs & Effects:**
- Returns the absolute joined path (`full`, L151) built from the **original** `raw` string, not the separator-normalised copy (L141, comment L123-L126), so a POSIX filename containing `\` stays one file (`tests/unit/storage/test_Vault__Path_Guard.py::test_safe_join__literal_backslash_filename_preserved`).
- Raises `Vault__Unsafe_Path_Error` on six conditions (L128, L131, L133, L137, L142, L145, L148). No state is written.
- Postcondition on return: `full == base_abs` or `full` starts with `base_abs + os.sep` (L142); no path component between `base_abs` and `full` is a symlink at check time (L145); `realpath(full)` lies under `realpath(base_abs)` (L148); no segment of `rel_path` spells a protected directory (L128).

**Block-by-Block:**

```python
# L128-L129
if self.is_protected(rel_path):
    raise ...
```
- **What:** Refuses any segment naming `.git`, `.sg_vault*`, 8.3 short names, NTFS streams, or a backup zip name.
- **Why here:** First, before any string handling: a protected path is refused even when it would otherwise be contained. This is what lets callers use `safe_join` alone (e.g. `Vault__Merge__Resolve.py:L91-L92`, `Vault__Sync__Commit.py:L320,L348`, `Vault__Mirror.py:L166`) without a separate `is_protected` call.
- **Assumes:** `is_protected` handles `None` (it does, L94).
- **Establishes:** no structural write from this call.
- **Depended on by:** every caller that does not call `is_writable` first.

```python
# L130-L134
raw = '' if rel_path is None else str(rel_path)
if not raw.strip(): raise
if raw.startswith('/') or raw.startswith('\\') or os.path.isabs(raw): raise
```
- **What:** Rejects empty/whitespace and absolute paths on either separator convention.
- **Why here:** `os.path.join(base, '/x')` would discard `base` (module docstring L4-L6); must precede L141.
- **Assumes:** `os.path.isabs` on the running platform plus the two literal prefixes cover every absolute spelling. A Windows drive-letter path (`C:x`, `C:\x`) is caught by `isabs` only on Windows; on POSIX `C:\x` is a relative name with a backslash, which L141 then keeps as a literal filename inside `base_abs`, so containment still holds via L142.
- **Establishes:** `raw` is non-empty and relative.

```python
# L137-L138
if any(part == '..' for part in raw.replace('\\', '/').split('/')): raise
```
- **What:** Rejects any `..` component, splitting on both separators (detection only).
- **Why here:** Belt for the containment check at L142; also makes the refusal explicit for `a/../../x` (`tests/unit/storage/test_Vault__Path_Guard.py::test_safe_join__rejects_embedded_parent_component`).
- **Assumes:** nothing further; `a/../b` with no escape is *not* rejected here — wait, it is: any `..` part is rejected regardless of whether it stays inside. The unit test named `test_safe_join__inner_dotdot_that_stays_inside_is_allowed` (L24-L27) in fact passes `'a/b'`, not a `..` path, so the name overstates what is tested. The code rejects every `..`.
- **Establishes:** no `..` component in `raw`.

```python
# L140-L144
base_abs = os.path.abspath(base_dir)
full     = os.path.abspath(os.path.join(base_abs, raw))
if full != base_abs and not full.startswith(base_abs + os.sep): raise
```
- **What:** Lexical containment of the joined path.
- **Why here:** The actual containment property; the earlier checks make its failure modes nameable.
- **Assumes:** `abspath` normalises `.` and redundant separators but does **not** resolve symlinks; symlinks are handled next. A `rel_path` equal to `.` or `./` yields `full == base_abs`, which is allowed here — `Vault__Sync__Commit._write_targets` (L344-L347) rejects that case itself before calling; other callers pass tree entry names that always carry a leaf.
- **Establishes:** `full` is lexically under `base_abs`.

```python
# L145-L147
if self.has_link_component(base_abs, full): raise
```
- **What:** Refuses when `full` or any directory between `base_abs` and `full` is a symlink right now.
- **Why here:** Lexical containment says nothing about a link `docs -> /outside`; this is what makes "sgit never writes through a link inside the working copy" true (threat model §5 "Symlinks", `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_a_write_through_a_symlinked_folder_is_refused`, `::test_a_write_through_an_in_tree_symlinked_folder_is_refused`).
- **Assumes:** the check and the caller's subsequent `open(full, 'wb')` see the same tree. The caller opens later (`Vault__Sync__Base.py:L522`, `Vault__Sub_Tree.py:L209`, `Vault__Revert.py:L81`, `Vault__Branch_Switch.py:L421`, `Vault__Stash.py:L100`, `Vault__Restore.py:L185`, `Vault__Sync__Sparse.py:L132`, `Vault__Merge.py:L101`, `Vault__Verified_Write.py:L86`, `Vault__Mirror.py:L170`) with a plain `open()`, which follows links. Nothing in this slice re-checks at open time; the time-of-check/time-of-use window between L145 and each caller's `open` is **nothing found** (contrast `read_regular`, which closes the equivalent window for reads with `O_NOFOLLOW`, L204-L206).
- **Establishes:** no in-tree link component at check time.

```python
# L148-L151
if not self.is_inside(base_abs, os.path.realpath(full)): raise
return full
```
- **What:** Resolves `full` fully and checks it against the resolved base ("belt and braces", L148 comment).
- **Why here:** Catches what the component walk could miss (e.g. a link whose target is itself a link chain), and tolerates a symlinked base (`/tmp -> /private/tmp`).
- **Assumes:** `realpath` of a not-yet-existing leaf resolves the existing prefix and appends the rest, so a fresh file under a real directory passes.
- **Establishes:** resolved containment.

**Cross-Function Dependencies:**
- Callee `is_protected` (internal, L89-L104): read in full; see its own record. It is what makes the "structural" half of the guarantee; it never raises.
- Callee `has_link_component` (internal, L153-L164): walks `rel.split(os.sep)` from `base_abs`, `islink` on each prefix. Note it splits on `os.sep` only; on POSIX a `\` inside `full` is part of one component, consistent with L141.
- Callee `is_inside` (internal, L166-L170): `realpath(base_dir)` compared with `rstrip(os.sep) + os.sep` prefix.
- External `os.path.abspath/realpath/isabs/islink` (black box, stdlib).
- Callers (all checked): `Vault__Verified_Write.save` L82; `Vault__Sub_Tree.checkout` L193; `Vault__Sync__Base._checkout_flat_map` L518; `Vault__Sync__Sparse` L128; `Vault__Revert.revert_*` L74; `Vault__Branch_Switch` L419; `Vault__Stash.pop` L96, L109; `Vault__Restore._extract_working_copy` L181; `Vault__Merge._write_conflict_files` L97; `Vault__Merge__Resolve` L84, L91, L92; `Vault__Merge__Abort` L48; `Vault__Sync__Commit.write_file` L320, `_write_targets` L348; `Vault__Mirror` L92, L166; `Vault__Static_Server._resolve` L128, L132, L134; `is_safe` L84. Of these, the ones that **also** call `is_writable`/`is_protected` first and skip-with-warning rather than raise: Sub_Tree L188, Sync__Base L511, Sparse L124, Revert L71, Switch L413, Stash L94/L107, Restore L178, Resolve L82 (ours only), Abort L46. The ones that let the exception propagate or catch it generically: Merge L97 (inside `try/except Exception: pass`, L95-L105 — a refused path is silently skipped, no warning), Resolve `_resolve_theirs` L91-L92 (propagates), Commit L320/L348 (propagates; `tests/security/test_Security__Fixed__Hostile_Paths.py::Test_Fixed__Write_Path_Guard`), Mirror (caught, `failed`/`False`), Verified_Write (caught, `REFUSED`), Static_Server (propagates to the HTTP handler).
- Shared state: none in the function; `WARNED` (L72) is not touched.
- Invariant couplings: the threat model's claim "vault data never writes outside the tree or into .git/.sg_vault" rests on (a) this function and (b) every write site actually calling it. The regression net for (b) is `tests/unit/appsec/test_AppSec__Path_Traversal__Write_Sites.py::Test_AppSec__Guard_Coverage_Invariant` (L115-L123 lists seven modules; it checks only that the strings `Vault__Path_Guard` and `safe_join` appear in each file). Write sites outside that list are enumerated in the cross-function note of the index.

**Open Questions:**
- The check-then-open window (L145 vs. each caller's later `open(…, 'wb')`): whether any write site re-validates or opens with `O_NOFOLLOW` — none found in the callers listed above; the local-attacker row of the threat model (A6, "plant files and symlinks in the working copy") is the context in which this matters.
- Whether any caller passes a `base_dir` that is itself vault-derived (none found; all are `directory`, `sg_dir`, `dest_dir`, `config.root_dir`).
