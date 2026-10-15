# Differential security review — sgit-ai `v0.20.0..v0.21.0` (slice: review/slice.json)

Tool: Trail of Bits `differential-review` skill (Phases 0–6), run 2026-10-11 by the sgit-ai CLI agent as part of
security-review round 1. Target: `git diff v0.20.0..v0.21.0 -- <45 slice files>`: 27 files changed, +1566/−172,
58 commits, 2026-10-08 → 2026-10-10 (`09c6cac` → `5502314`). Strategy: **MEDIUM / FOCUSED** (1-hop
dependencies read for every HIGH hunk). Baseline context: `team/explorer/appsec/threat-model/v0.21.0__threat-model.md`
(actors A1–A8, mechanisms §5, register §6). Every line number below is in the named revision (`v0.21.0` unless
stated); every claim of behaviour marked *(ran)* was reproduced with a command run during this review
(scripts under the session scratchpad `diffreview/`).

## 1. Executive summary

| Severity | Count | Ids |
|---|---|---|
| 🔴 CRITICAL | 0 | — |
| 🟠 HIGH | 0 | — |
| 🟡 MEDIUM | 1 | DR-001 (VULN, reproduced; pre-existing, not a regression of this range) |
| 🟢 LOW | 3 | DR-002, DR-003 (VERIFY), DR-004 (hardening) |
| ✅ CLEARED / KNOWN | 12 | DR-005 … DR-016 |

**Overall risk of the range: LOW–MEDIUM. Recommendation: CONDITIONAL** — the 0.21.0 release stands (none of the
findings is a regression introduced between the two tags, and the two known regression pairs TM-F25→F29 and
TM-F27→F30 are closed in code and, for F29, by runtime evidence below); DR-001 should land in 0.21.1 with a
`Fixed__Index_Overwrite` test and a TM-F row, because it is the same failure class as TM-F29 one level up
(the whole index instead of one tag entry) and the format gate cannot protect against it.

**Key metrics**
- Files analysed: 27/27 changed slice files (18 HIGH read hunk by hunk with 1-hop context; 7 MEDIUM surface-read; 2 LOW).
- Removed or weakened checks blamed: 7 (`git log -S` / `git blame`, §6). All seven are replacements by a stricter or equivalent check; none is a regression.
- Test gaps on HIGH hunks: 4 functions with no direct test (§4): `_ensure_public_key`, `_server_rewound`, `_exit_if_moved_command`/`_first_positional`, `CLI__Token_Store._unrecorded_server`. None is a security boundary on its own.
- High blast radius (≥21 callers): `Vault__Branch_Manager.load_branch_index` (64, every call now goes through `Vault__Index_Reader.parse`), `safe_join` (23). P0 analysis depth was applied to both.
- Security regressions detected in the range: 0. Pre-existing weakness surfaced by the range's own lens: 1 (DR-001).

## 2. What changed (Phase 0 triage)

Risk triggers: HIGH = crypto, keys, host boundary (bytes sent/received, shared-state writes), local boundary (paths,
secrets, symlinks), verify-then-accept, validation removed/narrowed; MEDIUM = business logic / state; LOW = CI
metadata, version, help text. Blast radius = callers in `sgit_ai/` of the changed public methods (Phase 3).

| File | +/− | Risk | Why | Blast radius |
|---|---|---|---|---|
| `sgit_ai/storage/Vault__Index_Reader.py` (new) | +132 | HIGH | shared-state parser/serialiser; TM-F25/F29 | CRITICAL — reached by `load_branch_index` (64 callers), `Index_Sync.merge/upload` |
| `sgit_ai/storage/Vault__Path_Guard.py` | +157/−4 | HIGH | path guard, `read_regular` (TM-F27/F30), new spellings | HIGH — `safe_join` 23, `read_regular` 12, `is_link` 12, `is_protected` 9 |
| `sgit_ai/core/Vault__Secret_Guard.py` (new) | +135 | HIGH | last check before bytes enter a commit (TM-F18/F27) | LOW — 2 + 3 callers |
| `sgit_ai/core/actions/commit/Vault__Sync__Commit.py` | +129/−26 | HIGH | what gets committed; `write_file` guard; amend | MEDIUM — `.commit(` 7, `write_file(` 5 |
| `sgit_ai/core/actions/push/Vault__Batch.py` | +109/−12 | HIGH | CAS, batch results, presigned PUT | MEDIUM — `execute_batch` 10, `execute_individually` 13 |
| `sgit_ai/core/actions/push/Vault__Sync__Push.py` | +173/−42 | HIGH | shared-state writes, lease, index merge, first-push | LOW — `.push(` 4 |
| `sgit_ai/network/api/Vault__API.py` | +50/−9 | HIGH | presigned URL policy, default server | MEDIUM — `fetch_presigned` 7, `check_presigned_url` 4, `default_base_url` 9 |
| `sgit_ai/core/actions/pull/Vault__Incoming_Check.py` (new) | +90 | HIGH | the one verify-then-accept gate | LOW — `require_signatures` 4 |
| `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` | +28/−10 | HIGH | presigned fetch, reset revision, read-only rewind | LOW — `.pull(` 5 |
| `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` | +15/−8 | HIGH | presigned fetch replaces bare `urlopen` | LOW |
| `sgit_ai/core/actions/verify/Vault__Key_Fetch.py` (new) | +59 | HIGH | writes key files fetched from the host | LOW — 5 + 6 |
| `sgit_ai/core/actions/verify/Vault__Signatures.py` | +10/−2 | HIGH | key lookup now fetches | LOW |
| `sgit_ai/crypto/Vault__Secret_File.py` (new) | +35 | HIGH | the one secret writer (TM-F05/F16) | HIGH — `write_private` 17 + direct 7 |
| `sgit_ai/crypto/Vault__Key_Manager.py` | +9/−8 | HIGH | signing key write path | LOW — 2 |
| `sgit_ai/crypto/pki/PKI__Key_Store.py` | +7/−5 | HIGH | private PEM writes | LOW |
| `sgit_ai/crypto/pki/PKI__Known_Keys.py` (new) | +45 | MEDIUM | own keys as trusted signers for `pki verify` | LOW — 5 |
| `sgit_ai/crypto/PKI__Crypto.py` | +10/−4 | MEDIUM | extra (unverified) fields in decrypt result | LOW |
| `sgit_ai/secrets/Secrets__Store.py` | +5/−3 | HIGH | store written 0600 | LOW |
| `sgit_ai/cli/CLI__Token_Store.py` | +71/−15 | HIGH | token write, read-key parsing, server default | LOW — 2/3 |
| `sgit_ai/cli/CLI__Main.py` | +155/−6 | HIGH | server pin per command, stdin key, exit codes | n/a (entry point) |
| `sgit_ai/cli/CLI__Vault.py` | +214/−24 | HIGH | restore glob, lease, check verify server, warnings | n/a |
| `sgit_ai/storage/Vault__Branch_Manager.py` | +31/−7 | HIGH | no private key stored (TM-R02); index via reader | HIGH — `load_branch_index` 64, `save_branch_index` 12, `tracked_named_branch` 12 |
| `sgit_ai/storage/Vault__Storage.py` | +17 | HIGH | `write_private`, link-safe `secure_unlink` | HIGH — 17 |
| `sgit_ai/storage/Vault__Ref_Manager.py` | +6 | MEDIUM | reflog append on every ref move | HIGH — `.write_ref(` 19 |
| `sgit_ai/storage/Vault__Object_Store.py` | +22 | MEDIUM | short-id resolution (TM-F26 lives in Vault__Revision) | LOW — 3 |
| `.github/workflows/ci-pipeline.yml` | +22/−2 | LOW | adds the security job (SHA-pinned checkout) | — |
| `pyproject.toml` | +1/−1 | LOW | version | — |

Not changed in the range (slice files read as 1-hop context only): `Vault__Crypto.py`, `PKI__Keyring.py`,
`Vault__Verified_Write.py`, `Vault__Object_Store` (verify paths), `Vault__Ref_Guard.py`, `Vault__Pull__Guard.py`,
`Vault__HTTP_Pool.py`, `Vault__Backend*.py`, `Vault__API__Auto/Static/In_Memory.py`, `Vault__Transport_Errors.py`,
`Vault__Ignore.py`, `CLI__Credential_Store.py`, `CLI__Debug_Log.py`, the two other workflow files.

## 3. Findings

### 🟡 DR-001 — MEDIUM — A server index this build cannot *parse* is replaced by the pushing clone's local copy (VULN, reproduced)

**File**: `sgit_ai/core/actions/index/Vault__Index_Sync.py:50-52` (`read_remote` returns `(raw, None)` when
`decode` fails), `:56-60` (`decode` swallows every exception), `:176,:180` (`upload` decodes `expected_raw`, gets
`None`, and `server_copy(current, None)` is `current`); consumers `sgit_ai/core/actions/push/Vault__Sync__Push.py:847-849`
(`merged = sync.merge(local, remote) if remote is not None else local` → `upload(..., expected_raw=raw)`),
`sgit_ai/core/actions/tag/Vault__Sync__Tag.py:172-175`, `sgit_ai/core/actions/format/Vault__Sync__Format.py:29-31,64`.
**Commits**: the `(raw, None)` contract and the push line are `bc0a530` (2026-10-07, "format gate, 128-bit ids, shared
branch index"), so this predates `v0.20.0`; the range touched the enclosing block in `5c33c19` (N5: the `except`
fallback that uploaded the local bytes blindly was turned into a refusal) and `d970599` (TM-F29) without
changing the `remote is None` arm. **Blast radius**: 3 writers (push, tag create/delete, vault format).
**Test coverage**: NO — `Fixed__Index_Overwrite` (5 tests) covers a *lost CAS race* (N5) and an *unreadable local*
index; `test_Review__eed8084.py` B1 covers unreadable *tag entries*. No test plants a server index with a branch
entry this build's strict schema rejects.

**Description.** TM-F29 taught that "an entry this version cannot read is CARRIED, never dropped". The same
question asked one level up has the old answer: when the *whole* server index decrypts but does not parse
(`Schema__Branch_Index.from_json` raises — a `branch_type` value outside `Enum__Branch_Type`, a `format` that is
not a uint, a `min_client` that is not semver, a `features` item outside `^[a-z0-9][a-z0-9-]{0,39}$`), `decode`
returns `None`, `read_remote` returns `(raw, None)` with `raw` set, and the three writers treat that as "nothing to
merge": they take their *local* copy and write it with compare-and-swap against `raw`. The CAS succeeds (the bytes
did not move), and the server's index — every branch, tag, tombstone and gate field the other client wrote since
this clone last merged — is replaced. The `refresh` path (`Vault__Index_Sync.py:280-282`) already treats
`remote is None` as "do not write"; push, tag and format do not. The format gate cannot help: `check_client`
(`:53`) runs *after* the parse that fails, so a newer client cannot keep a 0.21 client out by raising `min_client`
in the very index that 0.21 cannot parse.

**Historical context.** `bc0a530` wrote `read_remote` with the docstring "(None, None) when absent/unreadable" and
the merge fallback; `5c33c19` (review d3b8eef N5) made "could not merge" a refusal but kept "nothing parsed" as
"merge with nothing"; `d970599` (TM-F29) fixed the per-entry version of the same skip for tags only
(`Vault__Index_Reader.py` docstring: "Branches and everything else stay strict").

**Attack scenario** (actor A8, other clients; realistically A4 running a newer sgit, or the web UI):
1. Precondition: a vault shared by a 0.21.0 clone (Bob, write key) and a newer client (Alice).
2. Alice's client writes an index with a branch of a type 0.21 does not know (e.g. `branch_type: 'archived'`) and a
   new named branch `release`; she pushes.
3. Bob commits and runs `sgit push`. `read_remote` → `(raw, None)`; `merged = local`; `upload` CAS-writes Bob's
   local index over Alice's. Bob's push reports `pushed`.
4. Alice's `release` branch (and the archived one, and any tag or policy change she made) is gone from the server's
   index; her next pull merges Bob's copy back and keeps her local entries, but every third clone that pulls in
   between never sees them, and a tombstone she wrote is dropped (TM-F29's symptom, now for whole entries).
   **Exploitability: MEDIUM** (needs a client this build cannot parse; no hostile intent needed).
   **Impact**: silent loss of shared index state for the team; a policy switched on by the newer client
   (`features`) is dropped if 0.21 cannot parse one feature name.

**Proof of concept** *(ran — `diffreview/repro_index_overwrite.py`)*: two in-memory clones via `Vault__Test_Env`;
plant on the server a copy of the index with an extra branch `branch-named-ffff…` of `branch_type='archived'`;
`Vault__Index_Sync(...).decode(raw, read_key)` → `None`; Bob commits and pushes → `status='pushed'`; the server
index bytes changed and `any(b['branch_id']=='branch-named-ffff…')` is `False`. (Control in the same script, first
run: a planted *feature* `Signatures-Required-v2` is not rejected but **coerced** to `signatures-required-v2` by
`Safe_Str__Feature.to_lower_case` and written back changed — the "coerced value" class `readable()` guards for
tags, unguarded for the gate fields; LOW, noted here rather than as its own finding.)

**Working-tree note (end of review).** Uncommitted edits by another agent of this round were present in `Vault__Sync__Push.py`, `Vault__Index_Sync.py` and `Vault__Batch.py` when this review finished (TM-F34, TM-F35: empty or short batch replies). They **do not** touch the `remote is None` arm; DR-001 stands. The PoC was re-run against a pristine `git archive v0.21.0` extraction with the same result (`diffreview/repro_index_overwrite__clean.py`).

**Recommendation.**
```python
# Vault__Index_Sync.read_remote: distinguish absent / undecryptable / unparsable
if index is None:
    raise Vault__Index_Unreadable_Error(...)        # raw exists: fail closed, as refresh already does
```
In push (`:848`), tag (`:173`) and format (`:30`), refuse when `raw is not None and remote is None` (the message:
"the server's branch index was written by a client this sgit cannot read; update sgit") instead of
`merged = local`; read `min_client` from the raw dict *before* the strict parse so the gate still speaks. Add
`Fixed__Index_Overwrite::test_an_index_this_build_cannot_parse_is_never_overwritten` (push, tag create, format) and
a TM-F row; consider carrying unknown branch entries the way tags are carried.

### 🟢 DR-002 — LOW — A batch reply with no `results` (an empty body, `{}`, `None`) counts as a complete success (VERIFY)

**File**: `sgit_ai/core/actions/push/Vault__Batch.py:301-317` (`_checked`: `result = result or {}`; `status`
defaults to `'ok'`; `failed` is empty when `results` is absent), `sgit_ai/network/api/Vault__API.py:394-399`
(`_request` returns `{}` for an HTTP 2xx with an empty body), `sgit_ai/core/actions/index/Vault__Index_Sync.py:246-252`
(`require_written`, same shape). After `execute_batch` returns, push moves the local named ref and the baseline
(`Vault__Sync__Push.py:366-367`). **Commit**: `b68497e` (2026-10-09, "push results … batch per-op errors") — the
check that was added is strict about what it sees and silent about what is missing. **Blast radius**: `_checked`
6 call sites, `execute_batch` 10. **Test coverage**: PARTIAL — `Fixed__Host_Substitution::test_any_op_that_is_not_ok_fails_the_push`
and `Fixed__Index_Overwrite::test_tag_create_fails_when_the_server_does_not_write` test a *present* non-ok status; no test
for an absent `results` list or an empty body. *(ran)*: `Vault__Batch()._checked({})`, `_checked(None)`,
`_checked({'results': []})` all return without raising.

**Scenario** (A2 on an `http://` server — TM-R10 — or a proxy/CDN that answers 200 with an empty body while the
origin never saw the request): the clone believes the push landed, writes `last_remote_head`/baseline for a head the
server does not hold, and reports success to the agent that ran it. Nothing is lost locally; the next push finds the
server "behind" or "rewound" (`:116-118`) and says so, which is a confusing message for what was a dropped write.
A1 gains nothing (it can answer `{"status":"ok"}` already). **Exploitability: HARD. Impact: integrity of the clone's
record of what the server holds, not of the vault.**

**Recommendation**: in `_checked` and `require_written`, require `len(results) == len(operations)` and every op `ok`;
treat a missing `results` key as "the server did not confirm the write". One test with a `Vault__API__In_Memory`
subclass whose `batch` returns `{}`.

**Working-tree note (end of review).** Another agent of this round has an uncommitted fix for exactly this in the working tree (`Vault__Batch._checked(result, expected)` requiring one result per operation, `_answered` for the op-by-op fallback, `require_written` refusing an empty `results`; labelled TM-F34, TM-F35 / review AC-H-003). DR-002 is therefore a duplicate of that work; it is kept here as independent confirmation *(ran against a pristine `v0.21.0` extraction: `_checked({})` → `{}`)*.

### 🟢 DR-003 — LOW — `init --restore` finds `*__uninit.zip` but the path guard protects only the exact 0.20.0 spelling (VERIFY)

**File**: `sgit_ai/cli/CLI__Vault.py:341-346` (glob `*__uninit.zip`, newest by mtime), `sgit_ai/storage/Vault__Path_Guard.py:44-49,102`
(`_LEGACY_BACKUP_ZIP = ^[a-z0-9]{4,24}__<timestamp>__[a-z0-9_-]+\.zip`). **Commit**: both halves `5c33c19`
(TM-F18 remediation). **Test coverage**: the guard side `Fixed__Secrets_In_Commits::test_a_0_20_0_named_backup_is_not_committed_either`,
the restore side `Test_Fixed__Restore_Finds_Both_Names`; none for the names between the two rules. *(ran)*:
`Vault__Path_Guard().is_protected('evil__uninit.zip')` → `False`; `'My Vault__uninit.zip'` → `False`;
`'abcd1234__2026-10-10t00-00-00z__uninit.zip'` → `True`.

**Scenario** (A5, hostile vault author): the vault contains `notes__uninit.zip`, a backup of the *attacker's* vault
(its `VAULT-KEY`, `.sg_vault/local/config.json` naming the attacker's server). Clone writes it (not protected). A victim
who runs `sgit init --restore` in that folder (the README in the vault tells them to) is offered
`Found vault backup: notes__uninit.zip — Restore? [Y/n]` and, on yes, gets `.sg_vault/` rebuilt from the attacker's
backup: later commits go to the attacker's vault and server with the attacker's key. **Impact is bounded**: the folder
already *is* the attacker's vault content, the prompt names the file, the restore allow-list (TM-F03) writes only store
members, and mtimes are not preserved on checkout so a real `.vault__*.zip` written by `uninit` is always newer.
The commit direction is covered by content (`Vault__Secret_Guard.refuse_bytes` refuses any zip holding `VAULT-KEY`).
**Exploitability: HARD (needs the user to run `init --restore` and answer yes). Impact: LOW.**

**Recommendation**: make the two rules one — either glob only names `_LEGACY_BACKUP_ZIP` matches, or protect
`*__uninit.zip` in `is_protected` (it is a sgit-reserved suffix either way). One parametrised test on both.

### 🟢 DR-004 — LOW — Hardening: a named-ref push with no local ref file is a plain `WRITE` (CLEARED as regression)

**File**: `sgit_ai/core/actions/push/Vault__Batch.py:101-104` (`else: WRITE` when `expected_ref_hash` is falsy),
`sgit_ai/core/actions/push/Vault__Sync__Push.py:201-206`. **Commit**: `ba5a765` (2026-10-08). The removed code
(v0.20.0 `Vault__Batch.py:96-101`, blame `895848f`) sent `write-if-match` *without* `match`, which
`Vault__API__In_Memory.batch` (`:62-67`: `expected is None` → no comparison) and, per TM-F08's live-server notes, the
real server also treat as an unconditional write — so v0.21.0 made explicit what v0.20.0 already did; **not a
regression**. Reachability: `expected_ref_hash` is the hash of the *local* named-ref file (`Vault__Ref_Manager.get_ref_file_hash:65-76`,
`None` when the file is missing). A non-force push pulls first (`:165-171`), and a pull that accepts writes the local
named ref (TM-F19), so the file is missing only when the server has no ref either (first push of a branch, TM-R33) or
after a refused pull, which raises before this line. `--force` is a blind write by contract; `--force-with-lease`
replaces the value with the server's current bytes (`_check_lease:937-960`). **Recommendation**: refuse instead of
`WRITE` when `not force and not first_push and not absent and expected_ref_hash is None` — one line that turns an
unreachable blind write into an error.

### ✅ DR-005 — CLEARED — The two known regression pairs hold (TM-F25→F29, TM-F27→F30)

*TM-F29*: `carried_tags : list[Safe_Str__Index_Entry_Json]` (`Schema__Branch_Index.py:29`) cannot alter a carried
entry: `canonical()` emits `ensure_ascii` JSON, `INDEX_ENTRY_JSON__REGEX = ^[\x20-\x7E]*\Z` matches every such
string, `trim_whitespace=False`, `strict_validation=True` raises rather than sanitises, and the 1 MiB cap is the
listed 3e099ee N5. `to_json` (`Vault__Index_Reader.py:101-105`) re-inserts `json.loads(str(c))` — an exact
round trip. Runtime evidence: `review/findings/post-patch-validation.md`. *TM-F30*: every `None` from
`read_regular` (gone / ELOOP-link / ENXIO socket / fstat non-regular, `Vault__Path_Guard.py:181-224`) is kept as
the committed entry: in the scan (`Vault__Sync__Base.py:449-456` → `_keep_tracked_under_links`), in the non-sparse
tree build (`Vault__Sub_Tree.py:48-53`) and in the sparse commit (`Vault__Sync__Commit.py:99-105`); every other
`OSError` raises `Vault__Unreadable_File_Error`, which commit/pull/switch refuse on and status lists
(`CLI__Vault.py:922-932`). Tests: `test_Review__eed8084.py` B2 ×6 + 3e099ee ×4, `Fixed__Symlinks_And_Local::Test_Fixed__No_Follow_Reads`.

### ✅ DR-006 — KNOWN — A name whose entry has an unreadable timestamp is hidden on 0.21 clients
`Vault__Index_Reader.py:82-83` (an unjudged entry "wins", both are carried). Register: 3e099ee **N4** (§6.4), needs
the write key; residual of TM-R06. Nothing new.

### ✅ DR-007 — CLEARED — `require_signatures` returns "no policy" when the local index *file* is missing
`Vault__Incoming_Check.py:28-29`. Unreachable through pull, switch and push: each loads the same index through
`_init_components`/`load_branch_index` first and raises `FileNotFoundError` there; TM-R25 (present-but-unreadable
fails closed) holds (`:30` raises). Only A6 can remove the file, and A6 can edit `config.json` anyway.

### ✅ DR-008 — CLEARED — What `Vault__Secret_Guard.refuse_files` skips is never committed unchecked
`Vault__Secret_Guard.py:46-49` (`lstat` error, non-regular, link component → `continue`). The same path then meets
`read_regular` in `Sub_Tree.build:51` (raises → commit refuses) or keeps its committed entry (`:48-50`). The zip check
runs for *changed* paths only by design (eed8084 F2: "committed once with `--allow-secret-file` is not refused again");
the hard-link check is never skipped for a changed regular file (`:50-55`). Tests: `Fixed__Secrets_In_Commits` ×18.

### ✅ DR-009 — CLEARED — Server pin (`_pin_vault_server`, `CLI__Main.py:915-968`)
`_CREATES_VAULT` and `remote_command` exemptions are the documented remedies (R2); an unrecorded vault with
`SGIT_DEFAULT_BASE_URL` ≠ default exits 1 before any network call (`:949-955`); the pin is restored in `finally`
(`:889`). Tests: `Fixed__Server_Pin` ×6, `Fixed__Symlinks_And_Local::Test_Fixed__Server_URL` ×2.

### ✅ DR-010 — CLEARED — `Vault__Key_Fetch.fetch_missing` (`:27-50`)
Paths come from `wanted` (regex `^key-rnd-imm-[0-9a-f]{8,64}$`), never from the response key alone; a file is saved
only if it decrypts under the read key to `{"type":"public", pem: "...PUBLIC KEY..."}` — A1 cannot plant one,
A3+A1 can (TM-R01, by design). Written with plain `open` — correct, it is public. `_key_for` fetch failure → `no-key`
→ fail closed under the policy.

### ✅ DR-011 — CLEARED — `_ensure_public_key` (`Vault__Sync__Push.py:916-935`)
Uploads `bare/keys/<kid>` (`Vault__Key_Manager._key_path:78-79` → `bare/keys`, the *public*, read-key-encrypted
file), never `.sg_vault/local/*.pem`; a plain `write` only when the server has nothing at that id. Best-effort,
no test (named in §4).

### ✅ DR-012 — CLEARED — Presigned URLs (`Vault__API.py:36-67`, `Vault__Batch.py:139`, clone/pull call sites)
`https` to any host, `http` only to loopback or to the vault's own `http://` server, every redirect hop re-checked,
300 s timeout; the bytes are still verified by `Vault__Verified_Write`. TM-F07/TM-R10. Tests: `Fixed__Host_Substitution`
12 URL cases + 2 redirect + `test_fetch_presigned_checks_before_any_request`.

### ✅ DR-013 — CLEARED — `Vault__Secret_File.write` (`:14-35`)
`mkstemp` (0600, `O_EXCL`) in the target folder, `fsync`, `os.replace` (a link *at the path* is replaced, never
followed); the temp file is unlinked on any failure. A link at the *folder* (`.sg_vault/local` itself) is the
documented limit ("links above the vault root"). Callers: `write_private` 17, direct 7. Tests:
`Fixed__Symlinks_And_Local::Test_Fixed__Secret_Files` ×4, `test_Vault__Sync__File_Modes`.

### ✅ DR-014 — CLEARED — Exit codes after the new `return` in `_print_friendly_error` (`CLI__Main.py:1032-1033`)
`run()` still calls `sys.exit(1)` after the handler (`:881-889`); a refused push/commit never exits 0.

### ✅ DR-015 — CLEARED — `Vault__Branch_Manager.create_named_branch` stores no private key (`:30-41`)
Removed `store_private_key` (blame `c0d8854` 2026-05-05; removed in `574d6d5`, TM-R02). `tracked_named_branch`
returns `None` for a vanished creator branch and every caller refuses by name (S11). Tests: `Fixed__Trust_And_Policy`
×3, `test_Review__0a0707d.py::Test_S11` ×2.

### ✅ DR-016 — CLEARED — Smaller hunks
`Vault__Storage.secure_unlink` unlinks a link without zeroing its target (TM-F04); `Vault__Ref_Manager.write_ref`
appends ids only to a local reflog (no plaintext content); `Vault__Object_Store.resolve_id` raises on ambiguity and is
only an input to `_check_lease`/`Vault__Revision` (TM-F26 lives there); `CLI__Token_Store.read_key_from_credential`
takes a bare 64-hex head as a read key — the same rule clone uses, no privilege change; `PKI__Known_Keys` lets `pki verify`
trust the machine's own keys (reported as `signer_source`), `PKI__Crypto.decrypt` exposes the *unverified* `f`
fingerprint but `CLI__PKI.cmd_verify` (`:124-149`) verifies before reporting `valid`; CI adds the security job
with a SHA-pinned `actions/checkout` and a local composite action.

## 4. Test coverage of the HIGH hunks (Phase 2)

| Hunk | Test(s) | Status |
|---|---|---|
| `Vault__Index_Reader.parse/resolve/to_json/serialize` | `test_Review__eed8084.py::Test_B1*` (10), `test_Review__0a0707d.py::Test_R1` (3), `Fixed__Trust_And_Policy::Test_Fixed__Tags` (TM-R06 ×3) | YES |
| `Vault__Index_Sync.read_remote` → `None` consumers (DR-001) | — | **no test found** |
| `Vault__Path_Guard.read_regular / is_protected / canonical_segment / safe_join / has_link_component` | `Fixed__Symlinks_And_Local::Test_Fixed__No_Follow_Reads` ×2, `Fixed__Hostile_Paths::Test_Fixed__Path_Guard_Leftovers`, `::Test_Fixed__Write_Path_Guard` ×4, `test_Review__eed8084.py::Test_B2` ×6 + `Test_3e099ee` ×4 | YES |
| `Vault__Secret_Guard.refuse_files/refuse_bytes` | `Fixed__Secrets_In_Commits` ×18 (precision, allow-list scope, hard link, FIFO link) | YES |
| `Vault__Sync__Commit.commit` (changed-set guard, link handling), `_amend_plan`, `write_file/_write_targets` | `Fixed__Secrets_In_Commits`, `Fixed__Hostile_Paths::Test_Fixed__Write_Path_Guard`, `test_History_Edit_And_Revisions.py` (amend) | YES |
| `Vault__Batch._checked / execute_individually / _atomic_move / _require_current / _holds` | `Fixed__Host_Substitution::Test_Fixed__Push_Results`, `Fixed__Index_Overwrite` ×5, `test_Push__Concurrent_CAS.py` ×2 | YES (DR-002 edge: missing `results` untested) |
| `Vault__Batch.build_operations` ref op (DR-004) | `test_Push__Concurrent_CAS.py` (CAS path), `Fixed__Index_Overwrite::test_S10` (absent vs error) | PARTIAL (no-local-ref path untested; unreachable) |
| `Vault__Sync__Push`: `_is_first_push`, `_server_has_named_ref` raise; `_named_ref_absent_on_server`; index merge refusal; `_check_lease` | `Fixed__Index_Overwrite::test_S10`, `::test_N5`, `test_Tags_Reflog_Lease.py::Test_Force_With_Lease` ×3, `Fixed__Baselines::test_B2` | YES |
| `Vault__Sync__Push._ensure_public_key`, `_server_rewound` | — | **no test found** (`rewound` status is tested via `Fixed__Baselines`/`test_Review__d3b8eef__Lower_Priority.py`; the helper's `except → False` is not) |
| `Vault__Sync__Push.push` → `require_signatures` before send (L5) | `Fixed__Trust_And_Policy` (L5 row), `test_Signature_Policy_And_Rewind__Fixes.py` | YES |
| `Vault__API.fetch_presigned / check_presigned_url / default_base_url` | `Fixed__Host_Substitution::Test_Fixed__Presigned_URLs` ×14, `::Test_Fixed__Presigned_Redirects` ×2, `Fixed__Server_Pin` | YES |
| `Vault__Incoming_Check.require_signatures / local_history / policy_start` | `Fixed__Verify_Then_Accept` ×7, `Fixed__Trust_And_Policy::test_TM_F10`, `::test_K2` | YES |
| `Vault__Key_Fetch.fetch_missing / _is_public_key`, `Vault__Signatures._key_for` | `tests/unit/.../test_Vault__Key_Fetch*` (5 unit files mention `fetch_missing`), `test_Branches__End_To_End.py` (no-key) | YES (unit), none adversarial for `_is_public_key` |
| `Vault__Secret_File.write`, `Vault__Storage.write_private/write_local_config`, `Key_Manager.store_private_key_locally`, `PKI__Key_Store.save`, `Secrets__Store.save`, `CLI__Token_Store.save_token` | `Fixed__Symlinks_And_Local::Test_Fixed__Secret_Files` ×4, `::test_vault_writes_key_bearing_files_owner_only`, `test_Review__0a0707d.py::test_F10__write_local_config_is_atomic_and_private`, `test_Vault__Sync__File_Modes` | YES |
| `CLI__Main._pin_vault_server/_unpin`, `_key_from_stdin` | `Fixed__Server_Pin` ×6, `test_Review__0_20_0__Field_Report.py` (clone `-`) | YES |
| `CLI__Main._exit_if_moved_command/_first_positional`, `CLI__Token_Store._unrecorded_server` | — | **no test found** (UX; not a boundary) |
| `CLI__Vault.cmd_init --restore` glob (DR-003) | `Fixed__Secrets_In_Commits::Test_Fixed__Restore_Finds_Both_Names` | PARTIAL (no negative case) |
| `CLI__Vault.cmd_push` lease handling, `cmd_check_verify` server | `test_Review__0a0707d.py::Test_S15`, `test_Tags_Reflog_Lease.py::Test_Force_With_Lease` | YES |
| `Vault__Branch_Manager.create_named_branch/tracked_named_branch` | `Fixed__Trust_And_Policy::Test_Fixed__Signing_Keys` ×3, `test_Review__0a0707d.py::Test_S11` ×2, `test_Branches__End_To_End.py` | YES |

Risk elevation applied: DR-001 (modified shared-state write path, no test) is rated MEDIUM rather than LOW.

## 5. Blast radius (Phase 3)

| Changed method | Callers in `sgit_ai/` | Class | Priority |
|---|---|---|---|
| `Vault__Branch_Manager.load_branch_index` (→ `Index_Reader.parse`) | 64 | CRITICAL | P0 — deep + runtime (PPV) |
| `Vault__Path_Guard.safe_join` | 23 | HIGH | P1 |
| `Vault__Ref_Manager.write_ref` (+ reflog) | 19 | MEDIUM | P1 |
| `Vault__Storage.write_private` / `write_local_config` | 17 / 17 | MEDIUM | P1 |
| `Vault__Batch.execute_individually` / `execute_batch` | 13 / 10 | MEDIUM | P1 |
| `Vault__Path_Guard.read_regular` / `is_link` / `is_writable` | 12 / 12 / 10 | MEDIUM | P1 |
| `Vault__Branch_Manager.tracked_named_branch` / `save_branch_index` | 12 / 12 | MEDIUM | P1 |
| `Vault__Index_Reader()` (direct) / `.resolve(` | 11 / 10 | MEDIUM | P1 |
| `Vault__API.default_base_url` / `fetch_presigned` | 9 / 7 | MEDIUM | P1 |
| `Vault__Key_Fetch(` / `fetch_missing` | 6 / 5 | MEDIUM | P2 |
| `Vault__Incoming_Check.require_signatures` | 4 | LOW | P2 (HIGH risk → deep anyway) |
| `Vault__Secret_Guard.refuse_files` / `refuse_bytes` | 2 / 3 | LOW | P2 |

## 6. Historical context (Phase 1 red flags)

Every removed or weakened check in the range, with where its replacement lives:

| Removed (v0.20.0) | Blame | Replaced by (v0.21.0) | Verdict |
|---|---|---|---|
| `_is_first_push: except Exception: return True`; `_server_has_named_ref: except: return False` (`Vault__Sync__Push.py:817-843`) | `000a5fa` 2026-08-20 | raise `RuntimeError` (S10, `b68497e`) — an error is never "empty"/"absent" | stricter |
| `store_private_key(priv_key_id, …)` for named branches (`Vault__Branch_Manager.py:33-38`) | `c0d8854` 2026-05-05 | not stored (TM-R02, `574d6d5`) | stricter |
| `with open(full_path,'rb')` in commit, bare upload (`Vault__Sync__Commit.py:96-97`) | `65a3589` 2026-06-09 | `read_regular` O_NOFOLLOW + unreadable raises (`6ce75c3`, `f624d3b`, `d970599`) | stricter |
| `plain_chunks` classified by op only (`Vault__Batch.py`) | `ba5a765` 2026-10-08 | any `bare/refs/*` op is last | stricter |
| `else: WRITE_IF_MATCH` + optional `match` (`Vault__Batch.py:96-101`) | `895848f` 2026-05-04 | explicit `WRITE` when no hash | equivalent (DR-004) |
| index merge `except → upload local bytes` (`Vault__Sync__Push.py:813-818`) | `bc0a530` 2026-10-07 | raise `Vault__Push_Conflict_Error` (N5, `5c33c19`) | stricter; the `remote is None` arm beside it is DR-001 |
| bare `urlopen(s3_url)` ×4 (clone ×2, pull, API) | `000a5fa` | `fetch_presigned` (`84ab2a0`, `b68497e`) | stricter |
| `if base_url: save_base_url` on read-only clone (`CLI__Vault.py:243-244`) | `000a5fa` | always recorded (S1, `3c1e256`) | stricter |
| `load_private_key_locally … except: pass` (commit, write_file) | `65a3589` | `_load_signing_key` warns on stderr (K5) | equivalent + visible |

No code removed by a "fix/security" commit was re-added in this range (`git log -S` on each removed string finds
only its removal commit and the two unrelated docs/tools commits that carry the whole tree).

## 7. Recommendations

**Immediate (0.21.1)**
- [ ] DR-001: refuse to write when the server index exists but does not parse (push, tag, format); read `min_client`
      before the strict parse; `Fixed__Index_Overwrite` test; TM-F row.
- [ ] DR-002: `_checked`/`require_written` require one `ok` per operation; test with a `{}` reply.
- [ ] DR-003: one rule for legacy backup names (guard and restore glob); negative test.

**Before 0.22**
- [ ] DR-004: refuse instead of plain `WRITE` when a non-force, non-first push has no local named ref.
- [ ] Carry unknown *branch* entries and unknown top-level index keys the way tags are carried (forward compatibility
      with the planned signed key registry, TM-R01 fix-soon), or document that a `min_client` bump must precede any
      schema change.
- [ ] Tests for `_ensure_public_key` (server already holds a different file at the id), `_server_rewound` (`except → False`).

**Technical debt**
- [ ] `Safe_Str__Feature` coerces other clients' feature names on write-back (lowercase); either reject or carry.

## 8. Analysis methodology

**Strategy**: FOCUSED (MEDIUM codebase; 45 slice files, 27 changed). **Scope**: 27/27 changed files; HIGH 18/18 read
hunk by hunk with the v0.21.0 blob and 1-hop callees/callers (`Vault__Sync__Base._scan_local_directory`,
`Vault__Sub_Tree.build`, `Vault__Index_Sync`, `Vault__Reflog`, `Vault__Revision.resolve_soft`,
`Vault__API__In_Memory.batch`, `Schema__Branch_Index`, `Safe_Str__Index_Entry_Json`, `Safe_Str__Key_Id`, `CLI__PKI.cmd_verify`);
MEDIUM 7/7 surface-read; LOW 2/2 read. **Techniques**: `git log -S` and `git blame` on every removed line that
looked like a check; caller counts by grep; test lookup by function name and by keyword; four runtime probes with the
in-memory host (`repro_index_overwrite.py`, `_checked({})`, `is_protected(...)`, the Type_Safe unknown-key probes);
adversarial scenarios against the threat model's actors; the TM-F29/TM-F30 question ("what did the skip do to the
data?") asked of every `continue`, `return None`, `except: pass` in the diff.

**Limitations**: no live server (hermetic in-memory host only; the live server's answer to a `write-if-match` without
`match`, DR-004, is taken from TM-F08's notes, not observed); `sgit_ai/plugins`, `workflow/`, `objects/`,
`safe_types/`, `schemas/` outside the 1-hop set were not read; Windows-specific branches (`O_BINARY`, junctions,
8.3 names) were reasoned about, not executed; the three CI workflow files were read for pins only.

**Confidence**: HIGH for the HIGH-risk files and the two regression pairs; MEDIUM overall (the MEDIUM files were
surface-read; DR-002/DR-003 are VERIFY because the end-to-end path needs an `http://` host or a user prompt
respectively, neither of which this review drove).

**Provenance of the evidence.** Every line number is read from `git show v0.21.0:<file>` blobs, not from the working tree, which other agents of this round were editing concurrently (`git status` at the end of the review listed uncommitted changes to 14 tracked files, none made by this review). The four runtime probes were run twice: once against the working tree and once against a pristine `git archive v0.21.0 sgit_ai tests/_helpers` extraction in the scratchpad (`diffreview/clean-v0.21.0/`); results were identical (DR-001 overwrite reproduced; `_checked({})` accepted; `is_protected("evil__uninit.zip")` False).

## 9. Appendix — commits in the range touching the slice (newest first)

`5502314` `bc8016d` version · `57bbfab` 3e099ee N1/N2 · `d970599` eed8084 B1/B2/S1/F1-F6 (TM-F29–F31) ·
`f624d3b` 0a0707d R1/R2/F2/F4/F5/P1/F6-F11 (TM-F25–F28) · `a8beee8` `110b560` `5c33c19` d3b8eef (TM-F18–F24) ·
`2b92f7b` 0.20.0 field report · `b68497e` 00d6fc1 (TM-F17) · `482c11f` `3c1e256` `c316036` `6ce75c3` K1/K4/K5/S1/B2/B3 (TM-F11–F16) ·
`574d6d5` TM-R02/R04/R05/R06/R25 · `84ab2a0` full review (TM-F01–F07) · `1a20851` push CAS (TM-F08) · `6fcd9d2` hermetic tests ·
`ba5a765` branches · `ff9b499` history · `ac05083` `4dd8fc5` tags/reflog/lease/path spellings · `614ab6e` pull/format/verify.
