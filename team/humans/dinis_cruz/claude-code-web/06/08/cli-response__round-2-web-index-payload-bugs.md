# CLI Response (round 2) — verifying the web's v0.33.5 fixes against the CLI schema

**To:** the SG/App + sg-vault loader team
**From:** SGit-AI CLI team (Claude Code web session)
**Date:** 2026-06-08
**Re:** your v0.33.5 reply — `web-response__cli-interop-fixed-branch-index-and-reconcile.md`
**Companions:** `cli-response__open-loads-clone-branch-shadows-cli-pushes.md` and
`cli-response__clone-fails-no-branch-index-web-only-vault.md` (same date)

---

## TL;DR

**Fix 2 (reconcile-on-open) is correct and well-placed — ship it.**
**Fix 1 (writing the branch index) has the right *approach* but ships a payload my CLI clone path
cannot read — and as written it would *regress* newly-created web vaults from "works" (via the CLI
fallback I shipped) to "crashes on parse". Please don't roll it to users in its current form.**

| Your fix | CLI verdict | Notes |
|---|---|---|
| `open()` reconcile-on-open (named canonical when clone strictly behind) | ✅ correct | View-only, library-level, no clone-ref rewrite — matches `Step__Pull__RO__Load_Named_Head` reference |
| Write `branch_index_v1` at `bare/indexes/…` on create + push (best-effort, head=named only) | ✅ approach | Right place, right path, right semantics |
| **Index payload — `branch_id:"branch-named-main"`** | ❌ blocking | Fails `Safe_Str__Branch_Id` regex — `load_branch_index` throws before any lookup |
| **Index payload — `name:"main"`** | ❌ blocking | The CLI hardcodes `"current"` for the named branch in 10+ places — `get_branch_by_name(index, 'current')` returns NONE → "Named branch 'current' not found" |
| Path is `bare/indexes/` (path mismatch finding stale) | ✅ confirmed | Matches `Step__Clone__Download_Index.py:45` |
| Drop Option B (CLI reconcile escape-hatch) | ✅ agreed | The canonical fix lives where you put it |
| Co-author Option A (architect interop contract) | ✅ yes, please | The need for it is exactly the kind of drift we just hit |

Two-line web fix unblocks everything else: emit `name:"current"` and an opaque hex `branch_id`.

---

## What's right — affirm and ship

**Reconcile-on-open** is exactly the shape recommended in the first brief and mirrors the CLI's
`Step__Pull__RO__Load_Named_Head` reference implementation:

- Clone strictly behind named (clone ancestor of named) → adopt named head → CLI pushes are no
  longer shadowed.
- Clone ahead/diverged → keep clone head + flag divergence in the HUD → unpublished web work is
  never lost.
- View-only correction; no clone-ref rewrite at open; library-level so every `SGVault.open` caller
  benefits.

That closes the second brief properly. No notes.

**Index on create AND push, head_ref_id = named ref only, `bare/indexes/` path, `branch_type:"named"`,
best-effort writes** — all correct. The CLI's `Enum__Branch_Type.NAMED='named'` matches.

---

## What's wrong — two blocking bugs in the index *payload*

I ran your exact documented JSON through the CLI's real `Schema__Branch_Index.from_json`:

### 🔴 Bug A — `branch_id:"branch-named-main"` fails to parse

```
ValueError: in Safe_Str__Branch_Id, value does not match required pattern:
            ^branch-(named|clone)-[0-9a-f]{8,64}$
```

(`sgit_ai/safe_types/Safe_Str__Branch_Id.py:5`)

`branch_id` is an **opaque hex identifier**, not a human label. `main` is neither hex nor long
enough. `load_branch_index` raises here — before the CLI ever looks at a branch name.

### 🔴 Bug B — `name:"main"` ≠ the CLI's hardcoded `"current"`

Even with a valid hex `branch_id`, the parse succeeds but the lookup fails:

```python
get_branch_by_name(index, 'current')   # returns None
# → RuntimeError: 'Named branch "current" not found on remote'
```

`'current'` is hardcoded in clone, pull, push, fetch, status, diff, restore — at minimum:

- `sgit_ai/core/Vault__Sync.py:88` — created as `'current'`
- `sgit_ai/workflow/clone/Step__Clone__Download_Index.py:53`
- `sgit_ai/workflow/pull/Step__Pull__Load_Branch_Info.py:42`
- `sgit_ai/workflow/pull/Step__Pull__RO__Load_Named_Head.py:48` (via `_tracked_branch_name`, default `'current'`)
- `sgit_ai/workflow/push/Step__Push__Local_Inventory.py:36`
- `sgit_ai/workflow/fetch/Step__Fetch__Load_Branch_Info.py:34`
- `sgit_ai/core/actions/status/Vault__Sync__Status.py:109`
- `sgit_ai/core/actions/push/Vault__Sync__Push.py:73`
- `sgit_ai/core/actions/diff/Vault__Diff.py:652`
- `sgit_ai/core/actions/backup/Vault__Restore.py:196`
- `sgit_ai/workflow/clone/Step__Clone__ReadOnly__Setup_Config.py:22` — `DEFAULT_BRANCH_NAME = 'current'`

A `name:"main"` index won't break only clone — it breaks every CLI workflow that looks up the named
branch.

### ⚠️ Why this is worse than no index — the regression you'd ship

My shipped CLI fallback (`Step__Clone__Download_Index.py`) only triggers when the index is **absent**.

- **Today** (pre-v0.33.5): web-only vault has no index → CLI fallback kicks in → clone succeeds.
- **After v0.33.5 ships as written**: index *exists* → fallback is skipped → CLI hits
  `load_branch_index` → **crashes on Bug A**.

So a brand-new web vault would go from "clones fine" to "crashes". An existing web vault would break
on its next push (when the index is written). **A malformed index is strictly worse than no index.**

Please don't roll this to users until the payload is conformant.

---

## The exact shape the web must emit

```json
{
  "schema": "branch_index_v1",
  "branches": [
    {
      "branch_id":   "branch-named-0123456789abcdef",   // ^branch-(named|clone)-[0-9a-f]{8,64}$
      "name":        "current",                          // MUST be "current", not "main"
      "branch_type": "named",                            // 'named' | 'clone'
      "head_ref_id": "ref-pid-muw-…"                     // the deterministic named ref
    }
  ]
}
```

**Two-line web fix:** change `name:"main"` → `name:"current"`, and change `branch-named-main` →
any valid `branch-named-<hex>` id (it's opaque — the human-readable label lives in `name`).

### What I verified is flexible (good news)

I tested these too — all parse fine and don't need any web change:

- `created_at` accepts ISO-8601 strings (`"2026-06-08T12:00:00Z"`) **and** int milliseconds — pick whichever fits.
- `public_key_id`, `private_key_id`, `creator_branch` are all optional/nullable.
- Unknown extra fields are tolerated (silently ignored) — you can add web-only fields without breaking the CLI.

So the contract is tight in exactly two places and forgiving everywhere else.

### Why I'm asking the web to use `"current"` (not asking the CLI to use `"main"`)

`"current"` is the literal hardcoded in ~10 CLI sites *and* is what existing CLI-created vaults already use. Changing the CLI default would break every CLI-created vault in the wild on its next pull/push. The web can absolutely **display** "main" in its UI; this is about the on-disk wire name only.

If you want a different display label per vault, the right place is a separate `display_name` field in
`Schema__Branch_Meta`, and the contract (Option A) can specify it. Happy to add that field.

---

## What I'd like to do next on this side

### 1. Optional CLI hardening (defense in depth) — recommend

I can make `Step__Clone__Download_Index` tolerant of a foreign/malformed index:

- If `load_branch_index` raises **or** the index parses but has no `'current'` branch yet has exactly
  one named branch → treat it like a missing index, fall back to the deterministic named ref (the
  fallback you already saw).

That would absorb **your current v0.33.5 payload as-is** (single named branch, malformed id/name) and
any future drift in the index schema, without the CLI depending on the web shipping the wire fix
first. I'd ship this if you'd like the safety net — it's a small, well-isolated change.

### 2. Architect interop contract (Option A — co-author)

You offered, and we should. The whole reason this round happened is that two teams independently
picked incompatible conventions (`main` + label vs `current` + opaque hex) with nothing pinning
them. Fields the contract should pin:

- Named-branch wire name (`"current"`)
- `branch_id` grammar (`^branch-(named|clone)-[0-9a-f]{8,64}$`)
- `branch_type` encoding (`"named" | "clone"`)
- `head_ref_id` = named ref only (the rule you already follow)
- `created_at` encodings (ISO-8601 string **and** int-ms both accepted)
- `schema` value (`"branch_index_v1"`)
- Branch-index file id derivation: `'idx-pid-muw-' + HMAC-SHA256(read_key, "sg-vault-v1:file-id:branch-index:{vault_id}")[:12]`
- The crypto envelope for the index ciphertext (refs already interop fine; the index deserves an
  explicit byte-vector test like the ref vectors)

I'll draft v0 from the CLI side citing `Schema__Branch_Index` + the live `derive_*` code; you can
mark up. If we both sign it, future drift becomes much harder.

### 3. Re: live-deployment checks

Once your wire fix lands, your suggested three checks are exactly the right ones — happy to run
them end-to-end against `test-vault-1` (assuming the Access Key piece is unblocked):

1. Create a vault in the web → `sgit clone <key>` → succeeds with no fallback message.
2. CLI push → re-open in web → web shows the CLI's content.
3. Web edit (unpushed) → CLI push → re-open web → web keeps unpushed edit + flags divergence.

---

## Evidence index (this round)

- `sgit_ai/safe_types/Safe_Str__Branch_Id.py:5` — `branch_id` regex (Bug A)
- `sgit_ai/safe_types/Safe_Str__Branch_Name.py:5` — branch-name regex (allows `current`/`main`/etc; the issue is the lookup hardcode, not this regex)
- `sgit_ai/safe_types/Enum__Branch_Type.py` — `NAMED='named'` (your encoding matches)
- `sgit_ai/core/Vault__Sync.py:88` — `'current'` is the canonical named-branch name
- 10+ call sites of `get_branch_by_name(index, 'current')` listed above (Bug B impact)
- `sgit_ai/workflow/clone/Step__Clone__Download_Index.py` — shipped fallback (triggers only on absent index, hence the regression risk)
- `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__open-loads-clone-branch-shadows-cli-pushes.md` — companion brief 1
- `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__clone-fails-no-branch-index-web-only-vault.md` — companion brief 2
