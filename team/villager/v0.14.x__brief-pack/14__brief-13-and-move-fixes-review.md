# Brief 13 + Move Cleanup-Pass Implementation Review

**Date:** 2026-05-07
**Reviewer:** Villager orchestrator (Opus deep audit)
**Scope:** Commits since `6507db3` (last review at `11__implementation-review.md`) through `c2a23fb` (current dev tip).
**Verdict: 🟢 GO — brief 13 is cleanly implemented; the move + restore + publish fixes address real bugs.**

---

## Headline

| Item | Status | Notes |
|---|---|---|
| Brief 13 — `history log` range syntax | ✅ DONE | 24 new tests, exact schemas per brief |
| Move fix: API base_url resolution (`a2466dc`) | ✅ Real bug fix | Was crashing with "unknown url type: None/api/..." |
| Move fix: fail-early on missing token (`cedcedc`) | ✅ UX win | Was failing AFTER 6 prompts + 5s countdown |
| Restore fix: blank vault_id (`c925321`) | ✅ Real bug fix | Plus file counts + `--verbose` |
| Publish fix: transfer_id (`faa3c95`) | ✅ Real bug fix | Browse URL was pointing at wrong location |
| `-n / --max-count` on history log (`095c09b`) | ✅ Quality-of-life | Mirrors git's interface |
| Pre-existing diff-direction bug | ✅ Bonus catch | `diff_files()` args swapped at 2 sites in `show_commit` / `diff_commits` |

3,442 unit tests pass (up from 3,418 — exactly +24 from brief 13). Architecture/layer-imports passes; KNOWN_VIOLATIONS unchanged at 7. Zero mocks introduced.

---

## Brief 13 — `history log` range syntax (`c009faa`)

### Implementation summary

13 files touched, ~900 LOC added (incl. tests). Matches the brief's structure exactly.

```
sgit_ai/cli/_helpers.py                       # parse_commit_range, looks_like_range
sgit_ai/core/actions/diff/Vault__Diff.py      # commits_in_range, log_range_with_details
sgit_ai/cli/CLI__Diff.py                      # CLI handler updates for --json / --files / --patch
sgit_ai/plugins/history/CLI__History.py       # new flags: --files, --patch, --json
sgit_ai/schemas/history/                      # 3 new Type_Safe schemas
tests/unit/cli/test_CLI__History__Log__Range.py     (6 tests)
tests/unit/cli/test_CLI__History__Diff__Range.py    (2 tests)
tests/unit/core/actions/diff/test_Vault__Diff__Range.py  (7 tests)
tests/unit/schemas/history/test_Schema__History_Log_Result.py (9 tests)
```

### What's right

- **Schemas match the brief's spec.** `Schema__History_Log_Result`, `Schema__History_Log_Commit_Entry`, `Schema__History_Diff_Result` — all Type_Safe with round-trip; field types correct (`Safe_UInt__Timestamp` for `timestamp_ms`, `Safe_Str__ISO_Timestamp` for `timestamp_iso` — the dual-format pattern from the timestamp-fields debrief).
- **Range parser is robust.** `parse_commit_range('A..B') == ('A', 'B')`, `'A..' == ('A', '')`, `'..B' == ('', 'B')`. Plus the smart `looks_like_range()` helper that disambiguates from filesystem paths (range must contain `..` and no `/`) — clean way to keep the positional argument backwards-compatible with directory-style inputs.
- **`commits_in_range` semantics correct.** `<from>` exclusive, `<to>` inclusive, oldest-first ordering, raises clearly when `<from>` isn't reachable from `<to>`. Open-ended cases (`<from>..` and `..<to>`) work.
- **`log_range_with_details` reuses `show_commit`** rather than duplicating the per-commit walk — clean delegation.
- **The conductor agent's command works end-to-end:** `sgit history log A..B --files --json` produces a `Schema__History_Log_Result` JSON document parseable via `from_json`.

### Bonus catch — pre-existing diff-direction bug

While implementing the range walk, the executor noticed `diff_files()` was being called with swapped args at `show_commit` and `diff_commits`:

```python
# Was:
diff_files = self.diff_files(files_a, files_b)             # files_a=NEW, files_b=OLD — swapped
# Is:
diff_files = self.diff_files(files_b, files_a)             # files_b=NEW, files_a=OLD — correct
```

This bug was invisible because existing tests only covered "modified" files (which look the same in either direction). Brief 13's tests exercised "added" and "deleted" cases, surfacing the swap. The fix labels the args explicitly with comments to prevent regression. **Real bug, real fix, found by good test coverage.**

### Minor observation

The `Schema__History_Log_Commit_Entry` doesn't include the `tree_id` of the commit. Not in the brief, not needed by the conductor use case, but might be nice for visualisation downstream. Trivial to add later if needed; not a blocker.

---

## Move fix — `a2466dc` API base_url resolution

**The bug:** `Vault__Sync(crypto=Vault__Crypto(), api=self.api or Vault__API())` was constructing a `Vault__API` with no `base_url`, causing every subsequent HTTP call to fail with `unknown url type: None/api/vault/...`.

**The fix:**

```python
# move path
resolved_token = self.token_store.resolve_token(access_token, directory)
resolved_url   = self.token_store.resolve_base_url(
                     target_api_url or api_url_now or None, directory)
sync = Vault__Sync(crypto=Vault__Crypto(),
                   api=self.api or Vault__API(base_url=resolved_url or '',
                                              access_token=resolved_token or ''))
```

Resolved AFTER the prompts so any user-supplied `--to` override is honoured. For `--cleanup`, resolution happens immediately from stored config (no prompts to wait for). Both paths now correctly construct the API with the right URL.

**Was this caught by tests?** No — the unit tests for `Vault__Sync__Move` use `Vault__API__In_Memory` which doesn't care about base_url. The bug only surfaced against the real API. This is a known gap in the test strategy that brief 03 §4 (multi-round QA) deliberately accepted; the qa-tier tests would catch it if they ran against the real server, but they use the in-memory fixture too. **Worth flagging as a small follow-up:** add at least ONE end-to-end test that exercises the move command with a real `Vault__API` (against a local SG/Send fixture) — would have caught this. Not urgent enough to warrant a brief; could fold into the next reviewer-fix pass.

---

## Move fix — `cedcedc` fail-early on missing token

**The UX problem:** users running `sgit vault move` without a stored access token would:
1. See 6 confirmation prompts (`[y/N]` × 6).
2. See the 5-second countdown ("Press Ctrl+C to abort").
3. THEN see HTTP 401 from the server during the push step, with the access token showing as 0 chars.

The user has invested ~30 seconds of attention before discovering the simplest preventable failure.

**The fix:** validate the token BEFORE any prompts:

```python
# After dry-run check, before prompts
early_token = self.token_store.resolve_token(access_token, directory)
if not early_token and not self.api:
    print('error: no access token found for this vault.', file=sys.stderr)
    print('  Re-run with:  sgit vault move --token <your-access-token>', file=sys.stderr)
    print('  Or save it:   sgit push --token <your-access-token>  (saves for future use)',
          file=sys.stderr)
    sys.exit(1)
```

The validated token is reused at the actual API construction site (no redundant disk read). Smart, small, high UX value.

---

## Restore fix — `c925321` blank vault_id + file counts

**The bug:** `sgit vault restore` always reported `vault_id: ` (blank) because the code looked for `vault_id` in `local/config.json`, which doesn't have that field. The vault_id is canonically derived from the vault_key.

**The fix:** restore now derives vault_id from the vault_key via `Vault__Crypto.derive_keys_from_vault_key()`. Plus genuinely-useful additions:
- `_extract_bare` and `_extract_working_copy` now return lists of written files.
- They accept an `on_progress` callback for file-by-file reporting.
- A new `--verbose` flag surfaces the per-file progress to the user.

The user now sees something like:
```
Restoring vault abc123...
  bare/data: 247 objects
  bare/refs: 3 refs
  bare/indexes: 1 index
  working copy: 18 files extracted
Done.
```

Instead of a blank `vault_id` and no progress info.

---

## Publish fix — `faa3c95` transfer_id derivation

**The bug:** `sgit share publish` was calling the upload API without specifying a `transfer_id`. The server assigned a random one. The browse URL the CLI printed (`https://send.sgraph.ai/#<token>`) was constructed from the user's token, but the actual transfer was stored at the server's random ID. **The browse URL never resolved to anything.**

**The fix:** derive the `transfer_id` from the token via `Simple_Token.transfer_id()` (which is `SHA256(token)[:12]`) and pass it to the upload call. Now the URL the user clicks matches where the data actually is on the server.

This is a real bug that likely went unnoticed because publishing was probably tested with the assumption that the URL "works" (no one clicked it in the test loop). Worth a regression test: after `sgit share publish`, fetch the browse URL and assert it resolves to the encrypted payload.

---

## `-n / --max-count` on history log (`095c09b`)

Pure quality-of-life addition. `sgit history log -n5`, `sgit history log -n 5`, `sgit history log --max-count=5` all limit output to the last 5 commits. Mirrors git's interface exactly. Useful for the conductor agent and for human users alike.

---

## Concerns and follow-ups

### 🟡 1. Move base_url bug exposes a test-coverage gap

The `Vault__API()`-with-no-URL bug got past the entire 92-test move suite because every test uses `Vault__API__In_Memory`, which ignores `base_url`. The bug only surfaced against a real server.

**Mitigation:** add at least one end-to-end test in the qa-tier that exercises `sgit vault move` against the real local SG/Send fixture (the same one the QA-tier multi-round test already uses, except using the real `Vault__API` not the in-memory one). Catches the whole class of "config plumbing breaks against real HTTP" bugs.

**Severity: 🟡** — non-blocking. Worth folding into the next reviewer-fix pass or a small dedicated brief.

### 🟡 2. Publish browse-URL has no end-to-end regression test

Same family as #1. The `transfer_id` mismatch went unnoticed because no test asserted "the URL we print actually serves the file." A small qa test that publishes via `share publish`, then fetches the resulting URL, would catch it.

**Severity: 🟡** — non-blocking; worth one extra test.

### 🟢 3. Brief 13's `Schema__History_Log_Commit_Entry` doesn't include `tree_id`

Not in the brief; not needed for the conductor case. Nice-to-have for visualisation later. Add when needed.

---

## Outstanding briefs in the v0.14.x pack

For visibility, items still pending:

- **Brief 06** (dotfile tracking) — TODO
- **Brief 07** (`.vault-settings` + initial commit) — TODO
- **Brief 08** (`--vault-key` flag for headless admin) — TODO
- **Brief 09** (schema-parse error handling) — TODO
- **Brief 10** (command graph + suggestions) — TODO
- **Brief 12** (vault move cleanup pass — silent fallbacks, store_at refactor, cleanup state edge case) — **TODO** (the brief 02 follow-ups; haven't seen these land yet)

Total remaining: ~5 days of dev work. Then visualisation track is unblocked.

---

## Recommendation

🟢 **GO.** All fixes are real, tested, and address concrete bugs. Brief 13 ships exactly what was specified plus a bonus catch on the diff-direction bug. The move + restore + publish fixes resolve real production failures.

**Suggested actions:**

1. **Add an end-to-end qa-test for `vault move` against the real API fixture** — covers concern #1 and prevents regressions in the URL-resolution / token-resolution plumbing. ~½ hour, fold into brief 12 when it lands.
2. **Add a regression test for the publish browse URL** — similar shape, ~15 minutes.
3. **Pick up brief 12 next** (the original cleanup pass). The test-gap items above can roll into it.
4. **No release-blocking concerns.** v0.14.x can continue tagging independently of these follow-ups if you want to ship the brief-13 conductor capability now.
