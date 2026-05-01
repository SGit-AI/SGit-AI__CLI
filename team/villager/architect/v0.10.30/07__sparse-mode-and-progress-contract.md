# Finding 07 — Sparse mode and progress-bar contract

**Verdict:** `BOUNDARY OK` for the sparse mechanism itself.
**Verdict:** `BOUNDARY DRIFT` between debrief 01 (which describes
`clone_mode.json` as the sparse switch) and the implementation (which uses
`local_config.json`'s `sparse` field). See finding 03/05 for the schema
implication. **No SEND-BACK-TO-EXPLORER.**

---

## 1. How sparse state is stored

`_clone_with_keys` at clone time:
```python
local_config_data = dict(Schema__Local_Config(...).json())
if sparse:
    local_config_data['sparse'] = True
```

That `sparse: True` is then read at runtime in two places:
1. `Vault__Sync.status` line 458 — adds the `sparse` flag and the
   `files_total / files_fetched` counts to the status dict.
2. `Vault__Sync.pull` line 662 — passes `include_blobs=not _sparse` into
   `_fetch_missing_objects`, so trees are fetched but blobs are skipped.

`clone_mode.json` is for **read-only** clones, not for sparse. The two
concepts are orthogonal in the implementation but conflated in debrief 01.

## 2. Mode promotion: sparse → full?

There is **no explicit promotion mechanism**. The closest path:

- `sgit fetch` with no argument calls `sparse_fetch(directory, path=None)`,
  which downloads every blob (line 2126: "fetches everything"). After this
  succeeds, the blobs are all in the local object store, so `sparse_ls`
  shows every entry as `✓`.
- BUT `local_config.json` still says `sparse: true`. So a subsequent `pull`
  will still skip blob downloads (via `include_blobs=False`), even though
  the user is operationally "fully cloned".

This is a one-way trapdoor in the wrong direction: once the sprint marked the
clone as sparse, future pulls keep treating it as sparse. The user has to
manually edit `local_config.json` to flip `sparse: false`.

**Severity assessment:** moderate. A user who ran `sgit fetch` thinking
"now I'm fully cloned" will be surprised when the next pull fetches commit
and tree objects but no blobs. They'll have to `sgit fetch` again.

**Architectural question for Sherpa:** is sparse a permanent property of a
clone, or a state that promotes on `sgit fetch`? Pick one explicitly.
Today the implementation says "permanent property" but that may not match
user intuition. A clean fix: when `sparse_fetch(path=None)` completes
successfully, write `sparse: false` to `local_config.json`.

## 3. Sparse pull semantics

`pull` with `_sparse=True`:
- Walks commit graph (downloads commit + tree objects).
- Sets `include_blobs=False` in `_fetch_missing_objects` — blobs are NOT
  collected/downloaded.
- The post-pull "checkout" step (line 667 onwards):
```python
if not _sparse:
    # ... full checkout ...
```
  So in sparse mode, the working directory is **not updated by pull**.
  This is correct per debrief 01 ("commits and trees are fetched as normal,
  but the final checkout only writes blobs that are already locally
  cached"). But the user-facing expectation isn't quite that — debrief
  promised "files not yet fetched remain `·`", implying a partial checkout
  for cached blobs. The actual code skips checkout entirely if sparse.

This means: after `pull` in sparse mode, `sgit ls` correctly shows new files
as `·` (unfetched). But files that WERE locally cached and got changed
upstream will NOT be re-checked-out — the working copy stays stale until
the user explicitly `sgit fetch <path>` or `sgit checkout`.

I'm not sure this is a bug — it's a design choice that matches "sparse =
inspect-only, don't touch the working copy". Just flagging as an observation:
the debrief and the code disagree slightly on what "sparse pull" does to
existing locally-cached files.

## 4. The `✓` / `·` indicator

This is now part of the public CLI output for `sgit ls`. Per Dinis's
directive, sparse-related artefacts in `.sg_vault/local/` are sgit-specific
implementation details. But the CLI output IS user-visible.

**Wrappers/scripts that grep `sgit ls` output now have to know about the
status column.** This isn't a "frozen contract" violation in the strict
sense (because nothing pre-existed to compare against — `ls` was new this
sprint), but it IS new public surface. Designer should sign off that the
glyph choice (`✓` Unicode tick, `·` Unicode middle dot) is fine for
all-locale CLI usage.

## 5. Progress-bar denominator

Per the brief: not a separate finding. Quick note:

The change from "total objects" to "blobs only" is in
`_fetch_missing_objects` lines 2503/2509/2522. The old denominator was an
artefact of pre-BFS pull (which counted commits+trees+blobs together because
they were all fetched in one loop). The new denominator is meaningful — a
user can compute "how much data am I about to download" from "blobs × avg
size" and predict wall-clock.

If any external script parsed `Downloading objects [...] N/M` and assumed
M was the total object count, it's now broken. Per Dinis: noted, not a
finding.

## 6. Hand-off

- **Sherpa (decision):** sparse → full promotion semantics. Pick a model
  and document.
- **Dev (Phase 3):** if "sparse promotes on full fetch" is the chosen
  model, `sparse_fetch(path=None)` should clear the `sparse` flag in
  `local_config.json`.
- **Designer:** review the `✓` / `·` glyphs for terminal compatibility
  (some Windows terminals don't render middle-dot cleanly).
- **QA:** add a test that exercises "sparse clone → modify a file
  upstream → pull → verify working copy state". The current tests
  validate sparse `ls`/`fetch`/`cat` but not the pull-on-sparse path.
