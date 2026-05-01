# Brief B12 — Layered Restructure: Storage Layer (first move)

**Owner role:** **Architect** (move plan + import audit) + **Villager Dev** (mechanical move)
**Status:** BLOCKED until B06 lands.
**Prerequisites:** B05 (workflow framework) + B06 (apply workflow to clone) merged.
**Estimated effort:** ~1–2 days
**Touches:** mechanical file moves under `sgit_ai/`, import updates, tests. **Behaviour-preserving.**

---

## Why this brief exists

Per `design__06__layered-architecture.md`: 5-layer model (Crypto / Storage / Core / Network / Plugins). Layered restructure happens in two briefs — Storage first (this brief), then Core+Network (B13). Storage is the lowest-risk move because it groups data-handling primitives that are already cohesive in the current code.

This brief is **also** the moment to ship the import-audit enforcement test. Once Storage exists as a separated layer, the test catches any future upward import.

---

## Required reading

1. This brief.
2. `design__06__layered-architecture.md` (the 5-layer model + migration map).
3. `team/villager/architect/architect__ROLE.md` and `team/villager/dev/dev__ROLE.md`.
4. The current `sgit_ai/` tree:
   ```
   sgit_ai/{api,cli,crypto,objects,pki,safe_types,schemas,secrets,sync,transfer}/
   ```
5. After B06 has landed: the new `sgit_ai/workflow/` framework.

---

## Scope

### Step 1 — Architect move plan

Produce: `team/villager/v0.11.x__perf-brief-pack/changes__storage-move-plan.md`

For every file currently under `sgit_ai/objects/` and the storage-flavoured subset of `sgit_ai/sync/`, list:
- Current path
- New path under `sgit_ai/storage/`
- Imports that need updating (which other files import this)
- Risk note (is the file used in tests? in many places?)

Per design D6 §"Migration map", the candidates:

| Current | New |
|---|---|
| `sgit_ai/objects/Vault__Object_Store.py` | `sgit_ai/storage/Vault__Object_Store.py` |
| `sgit_ai/objects/Vault__Ref_Manager.py` | `sgit_ai/storage/Vault__Ref_Manager.py` |
| `sgit_ai/objects/Vault__Commit.py` | `sgit_ai/storage/Vault__Commit.py` |
| `sgit_ai/objects/Vault__Sub_Tree.py` | `sgit_ai/storage/Vault__Sub_Tree.py` (note: B06 may have already moved per-step files; reconcile) |
| `sgit_ai/sync/Vault__Storage.py` | `sgit_ai/storage/Vault__Storage.py` (rename to avoid duplication if needed; Architect picks final names) |
| `sgit_ai/sync/Vault__Branch_Manager.py` | `sgit_ai/storage/Vault__Branch_Manager.py` |
| `sgit_ai/sync/Vault__Key_Manager.py` | `sgit_ai/storage/Vault__Key_Manager.py` |
| `sgit_ai/objects/Vault__Inspector.py` | **Plugins**, not Storage. Defer to B14. |

`sgit_ai/secrets/` — Architect decides during this brief whether to fold into `crypto/` or keep separate as a sibling of Storage. Capture the decision in the move plan.

### Step 2 — Mechanical move

For each file in the move plan:
1. `git mv <old> <new>` — preserves git history.
2. Update imports across the whole `sgit_ai/` tree.
3. Update test imports.
4. Run full suite. Must pass.
5. Commit per logical group (one commit per couple of files, never one mega-commit).

### Step 3 — Import-audit enforcement test

Add `tests/unit/architecture/test_Layer_Imports.py`:

```python
class Test_Layer_Imports(TestCase):
    def test_crypto_has_no_upward_imports(self):
        """Crypto layer must not import from storage / core / network / plugins / cli."""
        ...

    def test_storage_imports_only_crypto(self):
        ...

    def test_no_upward_imports_anywhere(self):
        """Walk source tree; for each file, parse imports;
        assert each layer follows the dep rules in D6."""
        ...
```

Use Python's `ast` module to parse imports without executing code. Tests run in CI; a violation fails the build.

### Step 4 — Verify behaviour

After all moves + import updates:
- Full suite passes (2,105+ tests).
- Coverage delta non-negative.
- Phase B parallel CI shape ≤ 80s combined.
- Layer-import test passes.

---

## Hard constraints

- **Behaviour preservation.** Identical bytes for identical inputs. Only file paths change.
- **`git mv` not delete-and-create.** Preserves blame.
- **No source-content change inside files.** Only the file path + the imports inside change.
- **One commit per logical group.** Easy to review, easy to revert if a single move breaks something.
- **No mocks introduced.**
- Coverage must not regress.
- Suite must pass under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] Architect move plan exists and is Dinis-approved.
- [ ] Every file in the plan is moved via `git mv`.
- [ ] Imports updated across `sgit_ai/` and `tests/`.
- [ ] `tests/unit/architecture/test_Layer_Imports.py` exists and passes.
- [ ] Full suite ≥ 2,105 passing.
- [ ] Coverage delta non-negative.
- [ ] No file content changed (audit: `git log --diff-filter=R` shows pure renames).
- [ ] `secrets/` decision documented in move plan.

---

## Out of scope

- Splitting `Vault__Sync.py` into `core/actions/` (brief B13).
- Moving `api/` + `transfer/` into `network/` (brief B13).
- Moving `Vault__Inspector` into plugins (brief B14).
- Folding `pki/` into `crypto/` (brief B13 or later).

---

## Deliverables

1. Architect move plan doc.
2. Renamed files + updated imports.
3. Layer-import enforcement test.
4. Closeout note in `01__sprint-overview.md`.

---

## When done

Return a ≤ 250-word summary:
1. Files moved (count + summary list).
2. Layer-import test status (passing).
3. Suite + coverage deltas.
4. `secrets/` decision made.
5. Anything in the move plan that turned out trickier than expected.
