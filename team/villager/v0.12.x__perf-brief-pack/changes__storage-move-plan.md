# Architect Move Plan — B12 Storage Layer Restructure

**Produced by:** Villager Architect (B12)
**Status:** Approved — implementing
**Date:** 2026-05-04

---

## Decision: `secrets/` placement

`sgit_ai/secrets/Secrets__Store.py` stays in `secrets/` for now.

Rationale: `Secrets__Store` wraps OS keyring / dotfile credential storage — not vault object I/O. It is closer to `crypto/` semantically (credential derivation) but does not belong in `storage/` (vault on-disk structure). B13 will decide whether to fold into `crypto/` alongside `Vault__Key_Manager`. For B12 we leave it untouched.

## Decision: `Vault__Key_Manager` placement

`Vault__Key_Manager` is already at `sgit_ai/crypto/Vault__Key_Manager.py` — it was moved to `crypto/` in a prior sprint. D6 listed it as coming from `sync/`; that move has already happened. No action needed for B12.

---

## Files to move (6 files)

| # | Current path | New path | Import count | Risk |
|---|---|---|---|---|
| 1 | `sgit_ai/objects/Vault__Object_Store.py` | `sgit_ai/storage/Vault__Object_Store.py` | 68 | High — most-imported file in objects/ |
| 2 | `sgit_ai/objects/Vault__Ref_Manager.py` | `sgit_ai/storage/Vault__Ref_Manager.py` | 56 | High |
| 3 | `sgit_ai/objects/Vault__Commit.py` | `sgit_ai/storage/Vault__Commit.py` | 35 | Medium |
| 4 | `sgit_ai/sync/Vault__Storage.py` | `sgit_ai/storage/Vault__Storage.py` | 117 | Very high — widest import footprint |
| 5 | `sgit_ai/sync/Vault__Branch_Manager.py` | `sgit_ai/storage/Vault__Branch_Manager.py` | 32 | Medium |
| 6 | `sgit_ai/sync/Vault__Sub_Tree.py` | `sgit_ai/storage/Vault__Sub_Tree.py` | 30 | Medium |

**NOT moving:**
- `sgit_ai/objects/Vault__Inspector.py` → deferred to B14 (Plugins layer)
- `sgit_ai/sync/Vault__Sync*.py` → deferred to B13 (Core+Network split)
- `sgit_ai/secrets/Secrets__Store.py` → see decision above
- `sgit_ai/crypto/Vault__Key_Manager.py` → already in crypto, correct layer

---

## Internal dependencies within moved files

The moved files reference each other. Move order must respect these dependencies:

```
Vault__Storage        (no deps on other moved files)
Vault__Object_Store   (no deps on other moved files)
Vault__Ref_Manager    (imports Vault__Object_Store)
Vault__Commit         (imports Vault__Object_Store, Vault__Ref_Manager)
Vault__Sub_Tree       (imports Vault__Object_Store)
Vault__Branch_Manager (imports Vault__Ref_Manager, Vault__Storage, Vault__Key_Manager from crypto)
```

**Move order:** Storage → Object_Store → Ref_Manager → Commit → Sub_Tree → Branch_Manager

---

## Files needing import updates

Total: ~94 unique files across `sgit_ai/` and `tests/`.

### By module being moved

**`Vault__Storage`** (117 references) — widest footprint:
- `sgit_ai/cli/` — CLI__Dump, CLI__Export, CLI__Main, CLI__Publish, CLI__Share, CLI__Token_Store, CLI__Vault
- `sgit_ai/sync/` — Vault__Bare, Vault__Batch, Vault__Branch_Switch, Vault__Components, Vault__Context, Vault__Diff, Vault__Dump, Vault__Errors, Vault__Fetch, Vault__GC, Vault__Ignore, Vault__Merge, Vault__Remote_Manager, Vault__Revert, Vault__Stash, Vault__Sync, Vault__Sync__*.py
- `tests/unit/sync/`, `tests/unit/cli/`

**`Vault__Object_Store`** (68 references):
- `sgit_ai/objects/` — Vault__Inspector, Vault__Commit, Vault__Ref_Manager
- `sgit_ai/sync/` — Vault__Sub_Tree, Vault__Branch_Manager, Vault__Sync__*.py
- `sgit_ai/workflow/clone/` — Clone__Workspace, multiple Step files

**`Vault__Ref_Manager`** (56 references):
- `sgit_ai/objects/` — Vault__Commit
- `sgit_ai/sync/` — Vault__Branch_Manager, Vault__Sync__*.py
- `sgit_ai/workflow/clone/` — multiple Step files

**`Vault__Commit`** (35 references):
- `sgit_ai/sync/` — Vault__Sync__Commit, Vault__Sync__Pull, etc.
- `sgit_ai/workflow/clone/` — Step__Clone__Walk_Commits, etc.
- `sgit_ai/cli/dev/` — Dev__Server__Objects, Dev__Tree__Graph

**`Vault__Branch_Manager`** (32 references):
- `sgit_ai/sync/` — Vault__Sync__Branch_Ops, Vault__Sync__Clone, etc.
- `sgit_ai/workflow/clone/` — Step__Clone__Create_Clone_Branch

**`Vault__Sub_Tree`** (30 references):
- `sgit_ai/sync/` — Vault__Sync__Commit, Vault__Sync__Pull, etc.
- `sgit_ai/workflow/clone/` — Step__Clone__Walk_Trees

---

## Commit plan (per B12 hard constraints)

1. **Commit 1:** Create `sgit_ai/storage/__init__.py`
2. **Commit 2:** Move `Vault__Storage` + update all imports
3. **Commit 3:** Move `Vault__Object_Store` + update all imports
4. **Commit 4:** Move `Vault__Ref_Manager` + `Vault__Commit` + update all imports
5. **Commit 5:** Move `Vault__Sub_Tree` + `Vault__Branch_Manager` + update all imports
6. **Commit 6:** Add `tests/unit/architecture/test_Layer_Imports.py`
7. **Commit 7:** Clean up empty `sgit_ai/objects/` (keep `Vault__Inspector.py` for B14)

---

## Risk notes

- **`os.path.join` with `Safe_Str__Vault_Path`**: Already documented in session — not a B12 concern, no logic changes.
- **`Vault__Inspector`** remains in `objects/` (1 file left). `objects/__init__.py` stays for now.
- **Inline imports** (inside function bodies): `CLI__Export.py`, `CLI__Main.py`, `CLI__Publish.py`, `CLI__Token_Store.py`, `CLI__Vault.py` use `from sgit_ai.sync.Vault__Storage import ...` inside function bodies — sed/grep must catch these too.
- **Test file imports**: No `__init__.py` in tests (per CLAUDE.md rule) — plain file updates.
