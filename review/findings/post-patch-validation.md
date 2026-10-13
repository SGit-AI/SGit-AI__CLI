# Post-patch validation — TM-F29 (`f624d3b` → `d970599`)

Tool: Trail of Bits `post-patch-validation` skill (runner `post_patch_validation.py`, result schema 2.0), run
2026-10-11 by the sgit-ai CLI agent as part of security-review round 1. Artifacts copied next to this file:
`post-patch-validation__result.json`, `post-patch-validation__report.md`. The plan and the harness live in the
session scratchpad (`ppv/plan.json`, `ppv/checks/b1_harness.py`, `ppv/checks/run_pytest.py`); the harness bytes
are also archived content-addressed by the runner under `results/helpers/`.

## Finding under validation

**TM-F29** — index entries this build could not read were erased from the server by its next index write
(push, tag create/delete, `vault format`, move, the pull refresh), and a deleted tag whose tombstone it could not
read came back (review eed8084 B1). **Introduced by** `f624d3b` (TM-F25: an unparsable tag entry is *skipped* on
read) — the skip was then written back. **Fixed by** `d970599`: unreadable entries are carried as canonical JSON
(`Schema__Branch_Index.carried_tags : list[Safe_Str__Index_Entry_Json]`) and written back inside `tags`
(`Vault__Index_Reader.serialize`); per name the later entry wins as a reader of both would decide, an entry with
an unreadable timestamp wins outright and the entry it beat is carried too.

Pinned inputs: base `f624d3b8e8f3b91504db464c3e823f044945def4`, patched `d970599df3f1a9d30238d69c8f4788fb4692023c`,
patch SHA-256 `4611ce4e36ca1f7452fbd952801252c78ef8179d39ee8c08cd1882d51fa5d2dc`, submodules none, forwarded environment
none (per-check env: `PYTHONDONTWRITEBYTECODE=1`). **Evidence level: runtime** — every exploit/variant executes the
reported behaviour against the in-memory host (`Vault__API__In_Memory`, via `tests/_helpers/vault_test_env.py`, which
is byte-identical in both revisions) and asserts the safety postcondition on the *server's raw index bytes*.

## Outcome

**Assessment: `complete`. Supported findings: 1 (behavior check, ordering only — see below). Gaps: 0.
`human_review_required: true` (always).** Runner exit code 1 (complete, with a finding).

| Check | Kind | Base | Patched | Verdict |
|---|---|---|---|---|
| `01-control-readable-tag-survives-push` | control | exit 0 | exit 0 | harness trusted on both revisions |
| `02-exploit-push-erases-unreadable-entries` | exploit | **exit 1, `PPV_REACHED`**, `AssertionError: NOT_A_NAME erased from the server index: [{'name': 'v1.0', …}]` | exit 0, `PPV_REACHED` | reproduced on base by the assertion written; fixed on patch |
| `03-variant-unreadable-tombstone-resurrects-tag` | variant | **exit 1, marker**, `tombstone not carried unchanged; server has [{'name': 'v0.9', 'deleted': True, …}]` (the tombstone lost its unknown field `reason`, i.e. was rewritten from Bob's copy) | exit 0, marker | reproduced; fixed |
| `04-variant-tag-create-delete-path` | variant | **exit 1, marker**, `erased by tag create/delete: [v1.0 tombstone, v2]` | exit 0, marker | reproduced; fixed |
| `05-variant-pull-refresh-path` | variant | **exit 1, marker**, `erased by the pull refresh: []` | exit 0, marker | reproduced; fixed |
| `06-behavior-readable-index-parses-identically` | behavior | exit 0 | exit 0 | **stdout differs** (see below) |
| `07-regression-tags-still-work` (`test_Tags_Reflog_Lease.py::Test_Tags`, 8 tests) | regression | 8 passed | 8 passed | no regression |
| `08-security-tm-r06-far-future-entries` (`Fixed__Trust_And_Policy::Test_Fixed__Tags`, 3 tests) | security | 3 passed | 3 passed | adjacent property intact (TM-R06) |
| `09-suite-security-tests` (`tests/security`, 157 tests at `d970599`) | suite | not run (patched passed) | 157 passed in 22 s | — |

All four exploit/variant base-side failures were read in their raw stderr: each is the harness's own
`AssertionError` after the `PPV_REACHED` line (stdout), preceded by the base's `warning: skipping tag entry …`
lines — the harness reached the vulnerable call, not an import or setup error.

### Coverage: what the four exploit/variant checks establish

- **Exploit** (push path): two raw entries this build cannot read (`not a name!` live, `bad;tombstone` tombstone)
  planted on the server survive a teammate's push *byte-for-byte* (`NOT_A_NAME in server`, dict equality).
- **Variant 1** (merge rule, unknown field): a tombstone with a field this build does not know (`reason`) still
  hides its tag on this build and is carried unchanged; on the base it was skipped so Bob's stale live entry won and
  the deleted tag came back on the server.
- **Variant 2** (sibling writer: `tag create` + `tag delete` rewrite the index through `with_tag_entry`/`upload`).
- **Variant 3** (sibling writer: a pull by a write-key clone refreshes and writes the merge back through `refresh`).
- Not covered here (named so the gap is visible): the `vault format` and `vault move` writers (the fix routes both
  through the same `Vault__Index_Reader.serialize`, but no check executed them); an entry with an *unreadable
  timestamp* (`test_an_entry_whose_timestamp_cannot_be_read_wins_and_nothing_is_dropped` in the project suite covers
  it; not replayed side-blind); the 1 MiB cap on a carried entry (3e099ee N5).

### The behavior finding (06) — an ordering change, not a semantic one

The behavior check parses a fully readable index (one branch, gate fields, tags `v1` live and `v0` tombstone, in that
input order) and prints tags/branches/features/format/min_client as sorted-key JSON. Base and patched outputs are
set-equal; the only difference is the **order of the `tags` list**: the base keeps input order (`v1`, `v0`), the patch
emits names sorted (`v0`, `v1`) because `Vault__Index_Reader.resolve` groups per name and iterates `sorted(groups)`
(`Vault__Index_Reader.py:71`). The index's tags are a map by name (one entry per name, resolved by `name`), so
callers do not depend on list order; this is an expected consequence of the fix. The check was written stricter
than the invariant (byte-identical list) and is reported as the runner reported it rather than re-run with a
looser assertion. **Recommendation to the patch author**: none required; optionally note in the `Schema__Branch_Index`
docstring that `tags` is written sorted by name since 0.21.0.

### Validation gaps and limits

- None left by the runner (status `complete`). Scope limits: in-memory host only (the live server's `write-if-match`
  semantics are not exercised); `vault format` / `vault move` writers not executed; the project's own
  `test_Review__eed8084.py` (B1 ×10) was *not* reused as the exploit, because that file does not exist on the base
  revision — the side-blind harness carries the same scenarios instead (`checks/b1_harness.py`), so the checks
  are identical by construction on both sides.
- First run (`results.run1-venv-python/`, kept): every check failed on both sides with `ModuleNotFoundError`
  (`osbot_utils`, `pytest`) because the runner's child `python3` resolved to `uv run`'s ephemeral venv interpreter
  (its `argv0_sha256` equals `.venv/bin/python3`), not the system interpreter that has the project's dependencies.
  Fix: `argv[0] = /usr/bin/python3` in every check; plan re-validated and re-run. That run is the pinned result here.
  The host also has an editable install of the *working tree* (`sgit_ai.pth`), so both helper scripts put the
  checkout first on `sys.path` and assert `sgit_ai.__file__` is under it.

## Verdict for the register

TM-F29 is **fixed as claimed, with runtime evidence**: the original B1 exploit and three root-cause variants fail on
`f624d3b` and pass on `d970599`; tags still work; TM-R06 still holds; the security suite passes on the patched
revision. Human review of the archived harness (`results/helpers/<sha256>`) remains required before this is treated
as more than the runner's claim. The same question asked of the *whole* index ("what happens to a server index this
build cannot parse?") is **not** fixed — see `differential-review.md` DR-001.
