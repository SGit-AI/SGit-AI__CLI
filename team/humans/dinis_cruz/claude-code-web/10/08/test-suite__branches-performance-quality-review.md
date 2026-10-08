# Branches check, test performance, test quality — 8 Oct 2026

*CLI team. Done as part of the 0.21.0 release.*

## 1. Branches: broken, now fixed and covered

An end-to-end check (create, list, switch in and out, work on a branch, push to it, pull from
it, merge either way) found that **branches did not work**: push, pull and fetch looked up the
named branch called `current` by name, so work committed on `feature` was pushed to main and the
feature ref never reached the server. Fixed, together with everything the check turned up behind
it (first push of a new branch, signing keys of new clone branches, switch dropping unpushed
commits and tripping a false rewind, switch not fetching, duplicate names, `--from` not checking
out, no way to merge a branch) and one bug that was not about branches at all: **every merge
commit a pull created was unsigned**, because the pull state carried the key id in a type that
turns `-` into `_`.

| | Where | Tests |
|---|---|---|
| Unit, two real clones on the in-memory API | `tests/unit/review/test_Branches__End_To_End.py` | 22 |
| Integration, real SG/Send server | `tests/integration/test_Branches_Tags_Integrity__Integration.py` | 5 (branches, tags, format 2, signatures-required, rewind + lease) |
| Live dev API, through the CLI | manual run, two clones | create, push, switch, two people on one branch, diverged merge into main |

Why the existing tests missed it: the step tests for pull, push and fetch run against fake
branch managers whose `get_branch_by_name` returns the main branch whatever is asked; they
could not see work going to the wrong branch. The end-to-end tests run the real objects.

## 2. Performance: 70 s → 45 s, all 4,042 unit tests

| Change | Effect |
|---|---|
| Test vaults use a fixed key (`TEST_VAULT_KEY`) instead of a random one | Deriving a vault's keys is two PBKDF2 runs, ~190 ms by design. With one key, the process-level KDF cache makes every test vault after the first per worker nearly free. Each test still has its own directories and its own in-memory server |
| Test HTTP servers poll every 20 ms (static server 100 ms) | `shutdown()` waited up to 500 ms per test; 28 tests |
| Unit tests no longer reach the internet | 20 tests waited on the live dev server |

Checked and left: xdist scheduling (`load`/`loadscope`/`loadfile` within 2 s of each other),
collection (4 s), the vault-move test (22 real PBKDF2 runs is what a move does), two timing tests
whose subject is the timer itself (retry back-off, idle-socket age).

## 3. Quality

**Integration tests run real things.** All 12 files start the real SG/Send User Lambda on a
local port (in-memory storage) and nothing in them is mocked. They were all failing locally:
`mcp` 2.x breaks `fastapi-mcp` 0.4.0, which the server mounts at startup; CI pins `mcp<2`, the
local setup did not. Fixed in CLAUDE.md. 68 integration tests pass in 18 s.

**Unit tests are hermetic now.** `tests/unit/conftest.py` sends the default server to a closed
local port and fails, by name, any unit test that opens a connection to a non-loopback host.
Twenty were doing so: CLI commands on test vaults without a remote fell back to the live dev
server, one prompt test only passed because the live server answered, and `push`'s local dirty
check built a network client with no server. Production fixes for the last two.

**Where the mocking is.** It is concentrated, and it is the part of the suite that hid the
branch bug:

| | Count |
|---|---|
| unit test files | 335 (4,042 tests) |
| files that monkeypatch sgit_ai internals | 20 (258 patches) |
| files with hand-written Fake classes | 4 (37 classes) |
| tests named after a source line number | 82 |

Almost all of it is in files named `*__Coverage*`, written to reach lines rather than to check
behaviour. Recommendation, in order:

1. For new work, prefer the pattern the review tests use: real clones on the in-memory API
   (`Vault__Test_Env`), built once per class, restored per test (5 ms).
2. Replace the fake-based step tests (`test_Step__Pull/Push/Fetch__Coverage.py`) with workflow
   tests on real clones; delete the line-number tests whose behaviour another test already
   covers.
3. Treat a monkeypatch of an sgit_ai method in a unit test as a review flag: it usually means the
   code needs a seam (a parameter, a field) instead.
