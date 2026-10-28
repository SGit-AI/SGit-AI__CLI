# Git parity, priority 1 and 2: index, shared foundations and reconciliation (28 Oct 2026)

**What this is:** the entry point to the seven design documents for the Git-parity roadmap
(`roadmap__git-parity.md`). Each document was written against the code at `640069a` and ends with an acceptance
checklist. This index does three things:

- it lists the parts several designs need, to be built once;
- it settles the places where two designs disagree;
- it collects the bugs found in today's code and every decision waiting on Dinis.

**Where this index and a design disagree, this index wins.** The designs were written in parallel, and section 2
records the outcome of checking them against each other.

---

## 1. The documents

| Doc | Roadmap items | Priority | Estimate | Decisions |
|---|---|---|---|---|
| [`design__01__line-merge-and-cherry-pick.md`](design__01__line-merge-and-cherry-pick.md) | 2.1 line-level merge (opt-in), 2.8 cherry-pick | 1 (merge), 2 (cherry-pick) | 4.5 d (3.25 + 1.25) | D1–D11 |
| [`design__02__signing-with-your-own-key.md`](design__02__signing-with-your-own-key.md) | 2.2 SSH/GPG signing, Git's config, allowed signers | 1 | 4 d | D1–D12 |
| [`design__03__partial-commits-and-hooks.md`](design__03__partial-commits-and-hooks.md) | 2.3 `commit <paths>`, `commit -p`; 2.9 hooks | 1 (paths, -p), 2 (hooks) | 7.5 d (4.5 + 3) | D1–D10 |
| [`design__04__renames-blame-and-grep.md`](design__04__renames-blame-and-grep.md) | 2.4 renames, 2.5 blame, 2.7 grep and `log -S/-G` | 2 | 7.5 d | D1–D12 |
| [`design__05__bisect.md`](design__05__bisect.md) | 2.6 bisect | 2 | 5–6 d | D1–D8 |
| [`design__06__worktree.md`](design__06__worktree.md) | 2.13 worktree (shared objects), local branch merge | 2 | 3.25 d + 1–1.5 d | D1–D8 |
| [`design__07__rebase.md`](design__07__rebase.md) | 2.12 rebase, `pull --rebase`, `rebase -i` | 2 | 6.5–7.5 d | D1–D10, X1 |

**Totals:**

| Scope | As written | After building the shared parts once (section 2) |
|---|---|---|
| Priority 1 (2.1, 2.2, 2.3) | ~11.75 days | — |
| All seven documents | ~40 days | ~36–37 days |

The roadmap's estimates were roughly half of this. Each design explains its own gap; the same three causes recur:

- prerequisites in today's code (section 3);
- making every clone shape work: scoped, shallow, sparse, selective and pack;
- the Git oracle tests, run against git 2.43.

---

## 2. Shared foundations and reconciliation

Build these once, before the features that use them. Each one names the design that owns it.

| # | Foundation | Used by | Owner | What was reconciled |
|---|---|---|---|---|
| F1 | **One line differ:** `Vault__Line_Diff` in `sgit_ai/core/text/`. Myers diff, linear space, with a cost cap and `Vault__Line_Diff__Too_Different`. Includes `Vault__Line_Splitter` and `Schema__Line_Hunk`. | merge (01), blame, diff, pickaxe (04), rebase (07 via 01) | 01 | 01 and 04 each specified a `Vault__Line_Diff`: 01 in `core/text/` with `diff(a_ids, b_ids)`, 04 in `core/actions/diff/` with `split_lines`, `opcodes()`, `matching_blocks` and `-w`. **01's location and core win.** 04's needs become methods on the same class: `opcodes()` and `matching_blocks()` derived from the hunks, and the whitespace-ignore mode as a splitter option. 04's step 3 already allows "if design 01 lands first, step 3 uses it". |
| F2 | **One commit graph:** `Vault__Commit_Graph`, with parents, generation numbers (from index packs, else computed and memoised), a generation-ordered painting walk, ancestry, and a merge base with **no 200-commit cap**. | bisect (05), rebase range (07), cherry-pick ranges (01), `log --follow` (04) | 05 | 05 named it `Vault__Bisect__Graph`; 07 D9 asked for it to be shared. It is named `Vault__Commit_Graph`, and the bisect-only parts (weights, best, skip_away) stay in `Vault__Bisect__Graph` on top of it. |
| F3 | **Tree building that costs the change.** | partial commits and `write` (03), merges (01), rebase replays (07), cherry-pick (01) | 03 | 03 adds folder reuse to `build_from_flat(..., old_tree_ids=)`; 07 adds `Vault__Sub_Tree.apply_changes(tree_id, changes, read_key)`, which walks only the spine. **Both are kept, in one commit:** `apply_changes` for callers that hold a change list (replays, picks, path commits), `old_tree_ids` reuse for callers that hold a full flat map. A shared test pins the invariant that both give exactly the ids `build_from_flat` gives today (07's I6). |
| F4 | **Same content on both sides is not a conflict.** | every merge path: pull, `branch merge`, revert, cherry-pick, rebase, rewind re-apply | 01 | Found independently by 04 and 07 (X1). Blobs use a random IV, so two clones writing the same content get different blob ids. `three_way_merge` compares ids only, so today it reports a conflict. Fix: when ids differ, compare `content_hash` and `size`; if equal, decrypt both and compare bytes (04's `verify_exact`), then take ours. This changes the **default** whole-file merge too, so it is decision **X-D1** (section 5). |
| F5 | **One "operation in progress" guard:** `Vault__Operation_Guard.check(directory, action)`. It reads `merge_state.json` (01: merge, cherry-pick), `bisect.json` (05) and `rebase/state.json` (07), and refuses an action with the one message pattern each design already uses ("Cannot <action>: a <op> is in progress … finish it with … or abort with …"). | commit, write, pull, push, branch switch/checkout, stash, rebase, bisect, cherry-pick, worktree remove | 01 | 01, 05 and 07 each specify their own refusals (01 D3, 05 D1, 07 D8 and `check_not_in_progress`). The table in 2.1 below is the combined rule; each design's own list follows it. |
| F6 | **Hooks runner:** `Vault__Hooks`, `Enum__Hook_Name`, `VERIFY_HOOKS`, `Vault__Hooks.environment` (secrets stripped). | commit (03), rebase `exec` and hooks (07), cherry-pick (01) | 03 | 03 D9 says "commit hooks run for `commit` only"; 07 runs `pre-commit` / `commit-msg` on a `reword`, as Git does. **Resolution:** follow Git. Automatic commits (pull merges, `pick`, `cherry-pick` without an edit) run no commit hooks. A commit whose message the user edits (`reword`, an interactive squash, `cherry-pick -e`) runs `pre-commit`, `prepare-commit-msg`, `commit-msg` and `post-commit`. 07 adds `PRE_REBASE` and `POST_REWRITE`. |
| F7 | **Signing at commit creation:** `create_commit(..., user_signer=)` (02). | every commit path, including merges (01), picks (01), replays (07) | 02 | Consistent. Replayed and picked commits are re-signed by this clone's key and, if configured, the current user's key (07's `--sign/--no-sign`). 02 D10 (drop user signatures and report the count) applies to whole-history rewrites only: pack import/export, migrate. |
| F8 | **Atomic object writes:** temp file, fsync, rename. | worktree (06), and any two sgit processes on one store | 06 | 06 found object files are written in place, so a concurrent reader can see half a file. This lands first, on its own (06 commit 0). |
| F9 | **Pruned diff:** `history show` / `diff` / `log --patch` read only the changed paths. | blame, rename display (04), and the cost of every rebase and cherry-pick report | 04 | It is 04's step 3; it moves into the foundations because 07 and 01 print diffs too. |

### 2.1 What is allowed while an operation is in progress (F5)

Git's rules, with one deliberate difference: Git allows `push` during these operations, but sgit's push runs an implicit pull that writes the working copy, so sgit refuses it (it already does for a merge, `Vault__Sync__Push.py:50`). "✗" means refused by name, with the way out.

| Action ↓ / in progress → | merge or cherry-pick conflict | bisect | rebase (stopped) |
|---|---|---|---|
| `commit` | only once every conflict is resolved (01 D3, D4) | ✗ (05 D1) | ✗: use `rebase --continue` (07 D8) |
| `write` | ✗ | ✗ | ✗ |
| `pull`, `branch merge`, `cherry-pick`, `rebase` | ✗ | ✗ | ✗ |
| `push` | ✗ | ✗ | ✗ |
| `branch switch` / `checkout <commit>` | ✗ | ✗ (bisect moves the working copy itself) | ✗ |
| `bisect start` | ✗ | — | ✗ |
| `stash` | ✗ | ✗ | ✗ (`--autostash` is rebase's own) |
| `status`, `log`, `diff`, `show`, `blame`, `grep`, `cat`, `ls` | ✓, and `status` shows the operation (01's status block) | ✓ | ✓ |
| `worktree add` / `remove` of *another* worktree | ✓ (state is per clone) | ✓ | ✓ |

Every operation's state lives under that clone's `.sg_vault/local/`, so each worktree (06) has its own and they never
block each other.

---

## 3. Bugs and gaps found in today's code

The designs found these while reading the code. Fixes for real bugs can ship before any feature.

| # | Found by | What | Kind | Ship |
|---|---|---|---|---|
| B1 | 01 (reproduced) | `sgit commit` during an unresolved merge **commits the `.conflict` files into the vault**; every teammate who pulls gets them | bug | now, as F5's first use |
| B2 | 01 | `sgit status` never shows an in-progress merge, though pull's output points there | bug | with B1 |
| B3 | 04, 07 | Same content on both sides is reported as a conflict (random-IV blob ids) | bug | F4 |
| B4 | 06 | Object files are written in place, not atomically | bug (concurrency) | F8, now |
| B5 | 06 | The working-copy scan descends into a nested vault folder and would commit its files | bug | now |
| B6 | 05, 07 | `find_lca` and `_walk_commit_ids` stop after 200 commits | limit | F2 |
| B7 | 03 | `build_from_flat` rebuilds every folder, so `sgit write` of one file costs the whole vault | performance | F3 |
| B8 | 04 | `history show/diff/log --patch` decrypt every file of both commits; `log --file` flattens the whole tree per commit | performance | F9 |
| B9 | 03 | `sgit push` refuses any uncommitted change, so a partial commit could never be pushed | behaviour (prerequisite of 2.3) | with 2.3 |
| B10 | 04 | The snapshot index's `file-commits` member is written but never read | unused | blame uses it (04) |

---

## 4. Implementation order

Each step leaves `pytest tests/unit -n auto` and `pytest tests/security` green. Each feature lands with its
CHANGELOG entry and any threat-model rows its design lists.

**Phase 0: foundations and bug fixes (~4 days)**
1. F8 atomic object writes (B4); B5 nested-vault scan.
2. F5 operation guard, with B1 and B2 (merge state only at first).
3. F4 same-content merge (B3), *after X-D1 is decided*.
4. F3 tree building (B7).
5. F1 line differ and F2 commit graph (B6).

**Phase 0 status (28 Oct): done** on `claude/charming-babbage-5hzcxq` (not yet merged to `dev`):

| Step | Commit | What |
|---|---|---|
| 1 | `6ea436d` | F8 atomic object writes (B4, TM-F39); B5 nested vault never scanned or committed (TM-F38) |
| 2 | `e4e05fb` | F5 `Vault__Operation_Guard`; B1 commit refuses unresolved conflicts (01 D3); B2 status merge block |
| 3 | `dac3416` | F4 same content is not a conflict (B3, X-D1) |
| 4 | `bbc3f92` | F3 `build_from_flat` folder reuse and `apply_changes` (B7) |
| 5a | `8a1d6ec` | F1 `Vault__Line_Diff`, `Vault__Line_Splitter` (`sgit_ai/core/text/`) |
| 5b | `21a4bf6` | F2 `Vault__Commit_Graph`, no 200-commit cap (B6) |

F9 (pruned diff) stays with design 04, as planned. Each step's tests fail on the code before it.

**Phase 1: priority 1 (~10 days after phase 0)**

6. 2.1 line-level merge, opt-in (01 steps for 2.1).
7. 2.3 `commit <paths>` and `commit -p`, with the push prerequisite B9 (03 steps for 2.3).
8. 2.2 signing with your own key (02); the signing half waits on the web UI check (02 D7).

**Phase 2: priority 2 (~22 days)**

9. F9 pruned diff, then 2.4 renames, 2.5 blame, 2.7 grep (04).
10. 2.8 cherry-pick (01).
11. 2.9 hooks (03), then F6 extended by rebase.
12. 2.12 rebase (07).
13. 2.6 bisect (05).
14. 2.13 worktree, phases 1 and 2 (06).

A release can follow each phase. Phase 1 is the "line merges, signing with your own key, partial commits" release.

---

## 5. Decisions waiting on Dinis

72 decisions are recorded across the seven documents, each with a recommendation. Most follow Git and need only a
glance. These are the ones that change behaviour, the command surface or a dependency:

| # | Decision | Recommendation | Doc |
|---|---|---|---|
| X-D1 | Same content on both sides stops being a conflict, **including in the default whole-file merge** | Yes. It is a bug fix: the `.conflict` file would hold the same bytes as the working file. | this index (F4) |
| 01 D3 | `commit` refuses while conflicts are unresolved, including for the default `.conflict` style | Yes (fixes B1) | 01 |
| 01 D1 / D10 | How line merge is switched on: `--merge lines`, `merge_style` in local config, `SGIT_MERGE_STYLE`; no `config` command yet | As recommended | 01 |
| 02 D2 | What turns user signing on | `sgit.gpgSign` in Git config, off by default. Not Git's own `commit.gpgSign`, which would make agents start signing, or failing, on upgrade. | 02 |
| 02 D7 | Hold *signing* until the web UI team confirms its signing bytes exclude the new field; *verification* ships regardless | Yes | 02 |
| 03 D1 | Staging area | None for now: pathspec plus `-p` | 03 |
| 03 D2 | `sgit commit -m msg a b` makes `a b` paths (`sgit commit "msg"` unchanged) | Yes | 03 |
| 03 D5 / D6 | Hooks from inside the vault only with an explicit opt-in; configured under `sgit vault hooks` | Yes | 03 |
| 04 D1 | `grep` becomes a top-level command (edit `TOP_LEVEL_COMMANDS`), also `file grep` | Yes | 04 |
| 04 D2 | Python regex syntax, not Git's basic regex | Yes | 04 |
| 04 D4 | Renames detected by default; JSON gains `files_renamed` | Yes | 04 |
| 05 D1 | Commits refused during a bisect | Yes | 05 |
| 05 D3 | `bisect run` takes argv; a shell only with `--shell` | Yes | 05 |
| 06 D1 | `worktree` becomes a top-level command | Yes | 06 |
| 06 D2 | The worktree copies the vault key (0600) rather than pointing at the main's | Yes | 06 |
| 06 D6 | No worktrees of read-only clones in v1 | Yes | 06 |
| 07 D2 | Rebase never rewrites pushed commits in v1 | Yes | 07 |
| 07 D3 | Replaying another clone's commits needs `--allow-foreign` | Yes | 07 |
| 07 D5 | `pull_rebase` is off by default (merge stays the pull default) | Yes | 07 |

Top-level command changes in total: `grep` and `worktree` (CLAUDE.md rule 9). Everything else goes under `history`
(blame, bisect, cherry-pick, rebase), `vault` (hooks) or existing commands (`commit`, `pull`, `branch merge`).
