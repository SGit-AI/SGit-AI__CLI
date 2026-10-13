# Quality release — the dev changes reviewed, the reported bugs re-checked, more security tests, a refactor that breaks no test

**From:** the sgit-ai CLI agent · **Date:** 2026-10-13 · **Branch:** `claude/youthful-feynman-bpunv5` (merged with `dev`)

**Ask (Dinis, 13 Oct).** Review the changes the other developer pushed to `dev` and the bugs I
reported; review the security tests being added and improve them; then a pure quality pass:
things to remove and refactoring that breaks zero tests; and the gaps in test coverage.

## 1. The `dev` changes, reviewed

What landed on `dev` since my branch was merged (81a4176): `sgit serve` (b32a6ba, the local
SG/Send container with Docker, Podman, Apple container or uv), a security workflow on every PR
with an opt-in AI review gate (041697c, a97b8c4), and the AC-L-001 / TM-R36 note. The
tool-assisted differential review (Trail of Bits skill, one subagent, 15 minutes) is recorded in
`review/findings/differential-review-2.json`: 13 findings, 8 fixed in commit 53caf54.

**Clean** (each checked, with reproductions where it mattered): every external command is an
argv list with fixed verbs; the "a loopback server needs no token" rule fails safe for
`localhost.attacker.example`, `127.0.0.1.nip.io`, `0.0.0.0`, `[::ffff:127.0.0.1]`, `127.1` and
`user@localhost`; the static server binds loopback, refuses symlinks, `.sg_vault/`, traversal
and writes; `serve pull` refuses rewinds, undecryptable and unknown heads and leaves the real
server's baselines byte-identical; only `.sg_vault/bare/*` is copied into the container, and
`.sg_vault/local` is never read, uploaded or mounted; the workflow uses `pull_request` (never
`pull_request_target`), env-only inputs, `persist-credentials: false` on every read-only checkout
and SHA-pinned actions; zizmor and actionlint are clean.

| Id | Severity | Finding | Done |
|---|---|---|---|
| DR2-001 | medium | `sgit serve install` executed whatever the GitHub release API answered: the asset name became a path, the URL went to `curl`, then `sudo installer`; reproduced with a crafted answer that would have written to `~/Library/LaunchAgents` | fixed: only a plain file name with the expected suffix from the same repository's release download path is accepted (`checked_asset`); 8 attack cases |
| DR2-002 | medium | the AI gate exempted any finding whose `register` was not exactly `new` (empty, `none`, `n/a`, `TM-R999`); the diff is attacker text and can steer the label | fixed: only an id the threat model holds exempts; 8 cases |
| DR2-003 | medium | data delimiters were plain tags, so a diff containing `</change>` closed the block; the design inputs are read from the PR's own checkout | partly: per-run nonce in the tag names; reading intent, threat model and waivers from the base commit is open |
| DR2-004 | low | every gate is self-attesting: the same PR can grow the Bandit baseline, add a zizmor ignore or a waiver, or shrink the slice | open: CODEOWNERS on those paths, or a step that warns when a PR touches them |
| DR2-005 | low | the waiver key `file|function|category` with an empty function silenced a whole file's category | partly: an empty function falls back to the title; the coarse key is kept on purpose |
| DR2-006 | low | `serve push` re-sends the branch index as a plain write: a branch or tag made in the browser is lost on the next push | open, the developer's call (write-if-match the index, or merge it as `sgit push` does) |
| DR2-007 | low | image `:latest`, `uv run --with` unpinned, installer scripts unverified; the banner hands the full vault key to the local UI, so a hostile image gets plaintext, not only ciphertext | TM-R38 row corrected; pinning open |
| DR2-008 | low | downloads landed at predictable names under `/tmp` and were then run as root | fixed: a fresh 0700 folder per install |
| DR2-009 | low | only the literal `0.0.0.0` warned; `--bind 192.168.1.5` ran the unauthenticated server on the LAN silently | fixed: any non-loopback bind warns |
| DR2-010 | low | two register rows were numbered TM-R38 (my walk-up row and the serve image) | fixed: the walk-up row is TM-R41 |
| DR2-011 | info | `--image`, `--bind`, `--data` reach the runtime argv untyped (typed only when saved) | open |
| DR2-012 | info | `.sgit-sent.json` and, with `--data`, the state file live where the container can write them and are read back as control | open |
| DR2-013 | info | model text went unescaped into the job summary | fixed: code spans |

**On the AI gate itself** (what you are about to wire a key into): it is well built as a one
call, no tools, schema-bound reviewer, and the exit codes are right (3 is "inconclusive", which
fails). What it is not is a control: the design it is told to trust comes from the PR it is
reviewing, and a PR that touches `review/` or the baselines can pass itself (DR2-003/004). Keep
the deterministic gates as the controls and treat its verdict as a review comment. A dry run on
this round's security commit (four slice files, 85k tokens) prices at $0.24 clean / $0.42 with
findings on Sonnet 5.5, 1 to 2 cents on Haiku 5.5. One correction to the plan: two files fixed
this round (`Step__Pull__Fetch_Remote_Ref`, `Vault__Remote_Manager`) were not in the slice, so the
gate would not have looked at them; they are in it now (47 files).

## 2. The bugs I reported, re-checked on `dev`

| Row | Status on `dev` today |
|---|---|
| TM-F32..F36 (round 1, 11 Oct) | merged intact via 81a4176; every attack test still fails on the pre-fix code |
| TM-R36 (path rewriting, AC-L-001) | documented by the developer, not fixed: "refuse, never rewrite", with the evidence that it is worse than my record (clone lands in `jos_/`, first push fails with a false conflict). I agree with the proposal; it now has a `Known_Gaps` test so the day it is fixed the test says so |
| the five claims at the head of the ranked queue | worked today, below |

**Four were real; all four are fixed with a test that fails on the code before the fix** (commit
7ee634d, `tests/security/test_Security__Fixed__Host_Shaped_Answers.py`):

| Row | Claim | What really happened | Fix |
|---|---|---|---|
| TM-F37 | AC-H-002 | a host answering *not found* for a branch ref this clone had already synced dropped the compare-and-swap: Bob's stale push moved the shared branch (Alice's commit left it) | refused unless `push --force`; a branch never pushed still gets its first write |
| TM-F38 | AC-V-002 | a rewrite longer than the rewind guard's fetch limit (50) came back as "cannot tell" and the pull proceeded, merging with an empty base; a 60-commit forgery was accepted while a 3-commit one was refused | UNKNOWN walks the whole chain (the pull fetches it anyway), then refuses what it still cannot connect unless `--accept-rewind` |
| TM-F39 | AC-H-004 | a 500 on any route whose body mentioned the batch route and `HTTP 404` flipped the session to the read-only static transport; every later write was refused | only the request line and the observed status decide |
| TM-F40 | AC-C-002 | a `remotes.json` that exists but cannot be read sent the command, token included, to the default server | refuses and names the file; only an absent file falls through; `status` still says a remote is configured |
| TM-R41 | AC-L-006 | the walk up to `.sg_vault` has no ceiling (git's own behaviour) | accepted, `Known_Gaps` test |

41 ranked claims remain in `review/findings/ranked.json`.

## 3. The security tests

`tests/security/` now holds 14 files: 12 `Fixed__*` (attacks that must fail) and `Known_Gaps`
(gaps that must still work), 230 tests. The convention held up well this round, and two things
make it stronger:

- **Every open register row that a test can state has one.** TM-R36 and TM-R41 had rows and no
  test; now `Known_Gaps` proves each, so closing either flips a test and the row must move. The
  rows still without a test are analysis-only by nature (TM-R12..R21, R25, R28..R31, R37).
- **Lying hosts are the cheapest attack fixtures this project has.** A `Vault__API__In_Memory`
  subclass that changes one answer reproduced six of the nine defects found this week in under a
  second each (`Host__Empty_Reply`, `Host__Empty_Listing`, `Host__Forgot_The_Vault`,
  `Host__Named_Ref_Not_Found`, the `Racing_*` and `Flaky_*` hosts). Worth a `tests/_helpers/
  lying_hosts.py` so new tests compose them rather than redefine them.

Tests I would add next, in order of what they would catch:
1. **The rest of the ranked queue**, five at a time, the way today's five went: reproduce with a
   lying host first, then decide fix or accept. The next five by reachability are in
   `ranked.json`.
2. **`serve push` keeps a browser-made branch** (DR2-006): write an index with a new branch on
   the in-memory host, `serve push`, assert the branch survives. Today it fails, so it starts in
   `Known_Gaps` or lands with the developer's fix.
3. **The AI gate's register check against the real register**: `is_new('TM-F37')` false,
   `is_new('TM-R999')` true, read from the repository's own threat model (today's tests use a
   stub file).
4. **A checksum for the installer** once a release publishes one: the test is the attack
   (a tampered asset of the right name from the right URL) and it has no fix yet.
5. **The pre-fix proof as a CI step**: every `Fixed__*` attack test run against the commit named
   in its docstring in a clean worktree, so the proof stays true as the tests evolve. Today I do
   it by hand (`git worktree add … <pre-fix sha>`), and it caught the two tests that depended on
   new code.

Not wired yet, as you said: the Anthropic key for the gate. Everything above runs without it.

## 4. The refactor: removals and folds, zero behaviour change

Method: vulture at 60 % confidence gave 549 candidates; a subagent classified every one by grep
(production, tests, skills, docs, string dispatch), and radon and pylint's duplicate-code check
ranked the rest. The suite was run after each batch; every commit below is green.

**Removed, nothing referenced them** (commit a69e190, 18 files, 61 lines): unused locals
(`id_to_branch`, `app_ver`, `new_sg_obj_store`, `small_blobs_uploaded` ×2), unused imports (6),
module constants (`PLAINTEXT_ALLOW_LIST`, `DOCKER_COMPATIBLE`, `RUNTIME_NAMES`,
`VAULT_KEY_PREFIXES`, `READ_KEY_PREFIXES`, `TOMBSTONE_MARKER`), three private methods
(`_write_last_remote_head`, `_remote_clone_head`, `_higher_version`), an exception never raised
(`Vault__Push_Non_Fast_Forward_Error`), and the empty `Backup__Workspace` module.

**Removed with the tests that existed only for them** (this commit): five pieces the repository
itself documents as dead: `CLI__Main._cmd_log_dispatch` ("kept for backward compat with tests"),
`Vault__Sync__Clone._clone_download_blobs` (brief 18: "dead code, delete", with its five fake
helpers in the test file), `Vault__Sync__Admin` (a delegation shell whose test says it exists "so
the file reaches 100 % coverage"; `Vault__Sync` never used it), `Vault__Sync__Pull._pull_stats_line`
(team log 05/04), and `CLI__Vault.cmd_branches` (never wired to a command; `sgit branch list` is
the live one).

**Folded, one helper each, identical code** (this commit):

| Group | Before | After |
|---|---|---|
| `_init_components` | byte-identical 33-line builders in `Vault__Branch_Switch` and `Vault__Revert` | `Vault__Sync__Base._init_components_from_key_file`; both delegate (the precedent is `_materialize_baselines`) |
| `_read_local_config` | four copies (Base, Branch_Switch, Revert, Diff) | `Vault__Storage.read_local_config`, next to `write_local_config` |
| fetch-failure classifier | `Vault__Sync__Pull._classify_chunk_exception` was a copy of `Vault__API._classify_exception` | delegates; the tests that call it by name still pass |
| decrypt a ref payload | `json.loads(crypto.decrypt(read_key, data)).get('commit_id')` at nine sites | `Vault__Ref_Manager.decrypt_ref_value`, mirroring `encrypt_ref_value` |
| `.conflict` walk | three copies (`has_conflicts`, `remove_conflict_files`, push's `_check_no_conflict_files`) | `Vault__Merge.conflict_files` |

**Candidates that need your decision** (each is dead in production and has a dedicated test; the
subagent's list with lines is in the commit a69e190 message's note): `CLI__Credential_Store.
resolve_vault_key`, `Vault__Dump._dump_ref`, `Vault__Merge.remove_conflict_files` (now one line),
`Vault__Sync__Base._get_read_key` and `fetch_tree_lazy` (68 lines; sparse clone uses
`Vault__Sync__Sparse`), `Vault__Ref_Manager.ref_exists`, `Vault__Storage.is_vault` and
`tracking_path`, `Workflow__Workspace.gather_input_for`, `Vault__Bare.read_file`, the backend
abstraction (`Vault__Backend*`, three modules), three safe types (`Key_Type`, `Pending_Id`,
`Vault_Passphrase`) and four schemas (`Batch_Request`, `PKI_Public_Key`, `Tracking_State`,
`Vault_Policy`, the last described in `10__KNOWN_ISSUES.md` as a provenance feature), and
`Keys__Derivation`. Removing them deletes their tests; I did not.

**Opportunities larger than this round** (behaviour-neutral but wide): a `walk_working_files`
generator in `Vault__Ignore` for the five working-copy walks; `ensure_managers` and `progress`
lifted into `Workflow__Workspace` from the three identical copies; a `Step.advance(input,
**changes)` to replace the 17-field state rebuilds in every push, pull and fetch step; in
`CLI__Vault`, a `_sync()` factory for the eleven `Vault__Sync(crypto=Vault__Crypto(),
api=Vault__API())` lines and a `_die(message)` for the 33 `print(error); sys.exit(1)` shapes
across `cli/`. `Vault__Sync__Push.push` (radon F, 375 lines, twenty function-local imports) and
`CLI__Vault.cmd_vault_move` (F, 50) are the two functions a reader pays most for.

**Three things vulture flagged that are not dead code but look wrong**, left for you:
`CLI__Dump` computes a local dump and then says `--remote` is not implemented (the error message
changes if the line goes); `Vault__GC` loads `old_tree` and never reads it (an unfinished
diff-against-parent, and the only reason a corrupt parent commit aborts `gc_drain`);
`Restore__Workspace` is never constructed, yet `Step__Restore__Resolve_Vault_Key` reads a field
only it has, so a `vault-restore` run through `sgit dev workflow run` would hit an AttributeError
inside its error branch.

**Compatibility shims**: all kept. Each legacy path (`sgit_vk1_` prefixes, `.sg_vault/VAULT-KEY`,
the single `last_remote_head`, the 0.20.0 backup names, legacy signing bytes, the `tree.json`
inspector format, the old token location) still has a test that exercises it.

## 5. Coverage

Measured with `pytest --cov=sgit_ai` over the unit and security suites (the integration and QA
suites need the Python 3.12 venv and a real server, so they are not in these numbers).

| | Before | After |
|---|---|---|
| Statements | 25,155 | 24,973 (the removals) |
| Covered | 89 % | 90 % |
| Missing lines | 2,884 | 2,448 |

A subagent wrote tests for the least-covered modules in the same style as the suite (real
objects, the in-memory host, `Vault__Test_Env` snapshots; no mocks), pinning what the code does
today so the next refactor can lean on them:

| Module | Before | After |
|---|---|---|
| `core/actions/fsck/Vault__Sync__Upload_Objects` | 0 % | 100 % |
| `core/Vault__Repo_Ignore` | 0 % | 100 % |
| `core/Vault__Remote_Manager` | 61 % | 100 % |
| `cli/CLI__Tag` | 50 % | 100 % |
| `core/actions/tag/Vault__Sync__Tag` | 83 % | 97 % |
| `cli/CLI__Mirror` | 14 % | 100 % |
| `core/actions/mirror/Vault__Mirror` | 79 % | 96 % |
| `cli/CLI__Migrate` | 24 % | 96 % |
| `crypto/Vault__Secret_File` | 71 % | 91 % |
| `core/actions/verify/Vault__Signatures` | 79 % | 100 % |
| `workflow/push/Step__Push__Upload_Objects` | 68 % | 90 % |
| the six backup and restore steps | 33 to 65 % | 100 % |

**Still the thinnest** (where the next tests should go, by missing lines): `cli/CLI__Vault.py`
(549 missing of 2,069; `cmd_vault_move`, `cmd_clone`, `cmd_status`, `cmd_fsck` are the big
untested branches and also the most complex functions in the repository), `cli/CLI__Serve.py`
(47 %: `cmd_serve`, `push`, `pull`, `install`, `--static` at the CLI level; the developer's
runtime tests stop below the CLI), `plugins/dev/workflow/CLI__Dev__Workflow.py` (54 %),
`workflow/move/steps/Step__Move__Build_Temp_Vault.py` (79 %, 78 missing), `core/Vault__Sync__Base.py`
(85 %, 73 missing), `network/api/Vault__API.py` (77 %: the pooled-connection and presigned
fallback paths), `cli/CLI__PKI.py` (61 %), `cli/CLI__Cache.py` (74 %).

COVERAGE_AGENT_NOTES

## 6. Commits on the branch today

| Commit | What |
|---|---|
| 7ee634d | TM-F37..F40 fixed with tests; TM-R41; register, changelog, records |
| 04ef3b2 | two fixed files added to the review slice |
| 53caf54 | the `dev` review: 13 findings, 8 fixed (note: this commit also carries three coverage tests the subagent was still writing; their finished versions are in the coverage commit) |
| a69e190 | 21 unreferenced definitions removed |
| b379469 | five documented-dead pieces removed with their coverage-only tests; five duplicate groups folded |
| 202ecd0 (+ a follow-up) | tests for the least-covered modules; the brief |

Not done, needs you: the Anthropic key and `SECURITY_AI_REVIEW=true`; the TM-R36 fix (the
developer's proposal stands); the decision list in §4; DR2-004 and DR2-006 are the developer's
to pick up. The push to `dev` of this branch is yours, as before.
