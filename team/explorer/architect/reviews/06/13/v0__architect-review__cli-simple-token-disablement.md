# Architect Review — CLI Simple-Token Disablement (commit `2dd1bd7`)

**Version:** v0.1.0 (per `sgit_ai/_version.py`)
**Date:** 13 June 2026
**Role:** Architect (Explorer Team)
**Scope:** Post-implementation review of commit `2dd1bd7` on branch `claude/setup-architect-agent-RskQe`, which disables the four user-facing CLI surfaces that *create* Simple Tokens (`vault export`, `vault share`, `share send`, `share publish`) and strips simple-token branches from `sgit init` / `sgit create`. Backend implementations are retained for the upcoming security rework.

**Inputs:**
- Implementer brief (this session's user message)
- `sgit_ai/cli/CLI__Main.py` (full file; subparser wiring for the four targets at lines 463-472, 550-557, 607-615, 623-632; probe at 500-504; `share` namespace help at 607)
- `sgit_ai/cli/CLI__Vault.py` (`cmd_init`:222-327, `cmd_share`:1132-1183, `cmd_clone`:98-220, `cmd_probe`:1705-1731, push hints:1036-1049)
- `sgit_ai/cli/CLI__Create.py` (full file; `cmd_create`:16-119)
- `sgit_ai/cli/CLI__Share.py` (full file; `cmd_share`:45-114, `cmd_send`:185-250)
- `sgit_ai/cli/CLI__Publish.py` (full file; `cmd_publish`:17-132)
- `sgit_ai/cli/CLI__Export.py` (full file; `cmd_export`:15-112)
- `sgit_ai/core/Vault__Sync.py` (`init`:43-142; `probe_token` dispatch)
- `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py` (`probe_token`:90-123 — explicitly Simple-Token-only)
- `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` (`clone`:9-16 dispatches simple-token vault_key to `_clone_resolve_simple_token` → `clone_from_transfer`)
- `sgit_ai/workflow/clone/Step__Transfer__Init_Vault.py` (lines 21-25 — still generates a Simple Token inside the transfer-import workflow)
- `tests/unit/cli/test_CLI__B07__Namespace_Moves.py` (full file; 3 assertions on `cmd_export`/`cmd_send`/`cmd_publish` at lines 44-66)
- `tests/unit/cli/test_CLI__Vault__Coverage.py` (`cmd_share`+`cmd_init` tests at 545-794)

**Related reviews:**
- `06/08/v0.1.0__architect-review__multi-agent-legibility-a3-a4-a6.md` (most recent review, sets precedent for the bug+side-effect framing used here)
- `06/04/v0.1.0__architect-review__read-only-clone-contract.md` (the surrounding contract for read-only flows that interact with the kept surfaces)

> **Note on commit availability:** the working tree at review time does NOT contain the new files (`CLI__Disabled_Command.py`, `Safe_Str__CLI_Command_Label.py`) — `git log` does not show `2dd1bd7`. This review is therefore against the implementer's described changes plus the pre-disablement code in the working tree (lines cited reference the existing surfaces being modified). Where a finding depends on the exact disabled-stub text, it is called out as "depends on implementer's exact stub."

---

## 1. Executive Summary

The disablement strategy (keep argparse wiring, stub the four handlers, retain the backend) is the right shape for a temporary security gate: it preserves the rollback path, leaves test fixtures intact, and gives users a clear "disabled" message instead of an obscure crash. The four primary surfaces named in the brief are correctly scoped against the parser wiring at `CLI__Main.py:472, 557, 615, 632`.

However, the implementer left **at least four still-reachable paths that mint or rely on Simple Tokens** from user-facing surfaces, and a further set of help/hint strings that still actively advertise the disabled commands to users. These are not "the wrong surface was disabled" — the four declared surfaces are correctly disabled — but they are **incomplete coverage of the user-facing Simple-Token attack surface** the user asked to shut down.

The two biggest gaps are:

1. **`sgit init word-word-NNNN`** (positional simple-token detection at `CLI__Vault.py:233` and `CLI__Main.py:891, 923, 957` for clone-family commands) still hands a simple token to `Vault__Sync.init(token=...)` — which still produces a Simple-Token vault (`Schema__Local_Config.mode = SIMPLE_TOKEN`, `edit_token = vault_key`). The implementer's brief says "strip simple-token-detection branches from `cmd_init`/`cmd_create`" but only describes scenario C (bare `sgit init` auto-mint). The positional-token branches at line 233 (init) and line 50-55 (create) reportedly still need to go — or the disablement claim is overstated.
2. **`sgit clone <simple-token>`** (`Vault__Sync__Clone.py:12`) routes simple-token inputs into the `Workflow__Clone__Transfer` pipeline, whose **`Step__Transfer__Init_Vault`** (`Step__Transfer__Init_Vault.py:21`) **generates a new Simple Token and calls `Vault__Sync.init(token=new_token)`**. This is a user-reachable command (kept by policy) that still mints Simple Tokens via the consume path. Not in the implementer's "consume token" list.

The non-blocking but high-importance items are (a) 7+ help-text/next-step strings still routing users to the disabled commands across `CLI__Vault.py`, `CLI__Create.py`, `CLI__Share.py`, `CLI__Publish.py`, `CLI__Export.py`; (b) the dead `CLI__Vault.cmd_share` at line 1132 (no live caller; unreachable via CLI but reachable via tests/programmatic API), and (c) the `vault probe` help text + Lifecycle's `probe_token` design that makes Simple Tokens a routine concept in a kept command.

There are **no zero-knowledge violations** in the disablement itself. The retained backend is byte-equivalent to the pre-disablement crypto, and the disabled-stub message is local to the CLI process.

**Verdict: SHIP after F1+F2 are decided (block / re-scope / accept-and-document). F3-F8 are high-priority hygiene that should land in the same PR or the next. F9-F11 are advisory.**

---

## 2. Findings Summary

| # | Severity | Title |
|---|----------|-------|
| F1 | BLOCKER (re-scope or fix) | `sgit init word-word-NNNN` still mints a Simple-Token vault (positional-token branch at `CLI__Vault.py:233` + simple-token-in-vault_key branch at `:278-280`) |
| F2 | BLOCKER (re-scope or fix) | `sgit clone <simple-token>` still generates a NEW Simple Token via `Step__Transfer__Init_Vault.py:21` (Workflow__Clone__Transfer); user-reachable from the kept `sgit clone` surface |
| F3 | IMPORTANT | 7+ help-text "next step" lines still advertise the disabled commands; `share` namespace parent help (`CLI__Main.py:607`) still lists send/publish as features |
| F4 | IMPORTANT | `vault probe` help text and backend semantics (`Vault__Sync__Lifecycle.py:90-98`) make "simple token" a routine, advertised concept of a kept command |
| F5 | IMPORTANT | Dead method `CLI__Vault.cmd_share` (lines 1132-1183) — no live CLI caller, but reachable via tests / programmatic import; visible attack surface |
| F6 | IMPORTANT | `Vault__Sync.init(token=...)` parameter retained but no live caller passes a non-None value; live contract gap that the rework can refactor in place, but document the policy now |
| F7 | NIT | Argparse args on disabled commands (`--as`, `--no-inner-encrypt`, `--rotate`, `--token`) still parsed and silently ignored — user sets `--as foo` and gets a disabled message that doesn't acknowledge the flag |
| F8 | NIT | Disabled message: exit code 1 (convention says 2 for "command unavailable"), no tracking link, no doc URL, no timeline |
| F9 | ADVISORY | Backend test files (`test_CLI__Share.py`, `test_CLI__Publish.py`, `test_CLI__Export.py`) retained with no docstring explaining the kept-backend rationale; future readers will be confused |
| F10 | ADVISORY | Round-trip invariant on `CLI__Disabled_Command` (per CLAUDE.md §5/6): no enforcement test described in the brief. Should be a test class field test, even if trivial |
| F11 | ADVISORY | UX regression: bare `sgit init` previously created a subdirectory named after the auto-minted simple token; post-disablement it initialises in CWD. Not necessarily wrong, but a user-visible default change worth documenting in CHANGELOG |

---

## 3. Findings (detail)

### F1 — `sgit init word-word-NNNN` still mints a Simple-Token vault (BLOCKER)

**Evidence:** `sgit_ai/cli/CLI__Vault.py:232-236, 277-280`

```python
# Allow `sgit init coral-equal-1234` — if directory arg is a simple token, treat it as token
if directory and Simple_Token.is_simple_token(directory):
    if not vault_key:
        vault_key = directory
        directory = vault_key   # vault dir will be named after token
```

and

```python
# Simple token handling: if vault_key is a simple token, use token= arg
init_token = None
if vault_key and Simple_Token.is_simple_token(vault_key):
    init_token = vault_key
    vault_key  = None
```

The implementer's brief says they "stripped its simple-token-detection branches" — but the brief only enumerates the bare-`sgit init` scenario C auto-mint (lines 281-285). The two branches above are **separate**: they fire when the user explicitly supplies a Simple Token as either the positional directory or `--vault-key`. With Simple Token still recognised here, `Vault__Sync.init(token='word-word-1234')` is invoked, which dispatches to `derive_keys_from_simple_token` (`Vault__Sync.py:65`) and writes `Schema__Local_Config(mode=SIMPLE_TOKEN, edit_token=vault_key)` (`:124-125`). **This is exactly the construction the user asked to shut down.**

The same shape exists in `CLI__Create.py:50-55`:

```python
init_token = None
if vault_key and Simple_Token.is_simple_token(vault_key):
    init_token = vault_key
    vault_key  = None
elif not vault_key:
    if Simple_Token.is_simple_token(vault_name):
        init_token = vault_name
    # Otherwise let sync.init() auto-generate
```

`sgit create word-word-1234` → simple-token vault.

And in `CLI__Main.py:891, 923, 957` for `clone-branch`/`clone-headless`/`clone-range` — each uses `Simple_Token.is_simple_token(token_str)` purely for directory-naming, which doesn't itself mint a token, but it does mean the simple-token user journey is still supported across the clone family (the kept "consume" surfaces — which is fine for clone-branch but contradicts F2).

**Risk:** The disablement is a SECURITY gate per the user brief. F1 leaves a credible path for a user to create a Simple-Token vault from a current-CLI install. A user who reads "Simple Tokens are disabled pending rework" and then succeeds with `sgit init my-cool-1234` will have lost trust in the gate. The security claim is also unverifiable — anyone auditing the CLI will find the path.

**Recommendation:** Either (a) **strip the positional branches at `CLI__Vault.py:233-236, 277-280` and `CLI__Create.py:50-55`** so that any Simple-Token-shaped input is rejected at the CLI boundary with a disabled-feature message; or (b) re-scope the disablement claim explicitly: "only the four named subcommands are gated; `sgit init <simple-token>` is still supported for backward compatibility." Architect strongly recommends (a) — if Simple Tokens are insecure-pending-rework, every CREATE path must be gated; one open create-path defeats the gate.

---

### F2 — `sgit clone <simple-token>` still mints a NEW Simple Token at the destination (BLOCKER)

**Evidence:**
- `sgit_ai/core/actions/clone/Vault__Sync__Clone.py:11-14`
  ```python
  if Simple_Token.is_simple_token(vault_key) or vault_key.startswith('vault://'):
      token_str = vault_key.removeprefix('vault://')
      return self._clone_resolve_simple_token(token_str, directory, on_progress, sparse=sparse)
  ```
- `sgit_ai/workflow/clone/Step__Transfer__Init_Vault.py:21-25` (entered via `Workflow__Clone__Transfer`):
  ```python
  new_token = str(Simple_Token__Wordlist().setup().generate())
  Vault__Sync(crypto=workspace.sync_client.crypto,
              api=workspace.sync_client.api).init(directory,
                                                  token=new_token,
                                                  allow_nonempty=True)
  ```

The brief lists `sgit clone <token>` among "commands that consume tokens." But this is misleading: when the input is a Simple Token (NOT a `passphrase:vault_id`), the consume path **internally generates a NEW Simple Token** and creates a Simple-Token vault at the destination via `Vault__Sync.init(token=new_token)`. The user therefore ends up with the same insecure construct the gate is trying to prevent — they just received it through a kept command instead of `vault share`.

**Risk:** Same as F1. The user-facing claim "Simple Token CREATION is disabled" is false if `sgit clone <transfer-token>` produces a Simple-Token vault as a side effect. From the user's perspective, they cloned; from the system's perspective, a new Simple Token was minted and persisted into `Schema__Local_Config.edit_token`.

**Recommendation:** Three options, in decreasing scope:
1. Add `Step__Transfer__Init_Vault` to the disablement set — refuse the transfer-clone workflow with the same "pending security rework" message until rework completes.
2. Modify `Step__Transfer__Init_Vault.execute` to call `Vault__Sync.init(directory, allow_nonempty=True)` without a generated token, producing a standard `passphrase:vault_id` vault at the destination. The downside: round-tripping a SG/Send transfer back into a transfer no longer works through Simple Tokens; the user would need to use the new vault key.
3. Re-scope: document explicitly that transfer-clones still produce Simple-Token vaults at the destination, with all the implications. Architect rejects this — it leaves a clear leak.

Architect recommends (1) as the minimum-change safe option. (2) is the right long-term shape but is a behaviour change that needs human routing.

---

### F3 — Help-text "next steps" still advertise the disabled commands (IMPORTANT)

**Evidence (grep of `sgit share|sgit publish|sgit export` across `sgit_ai/`):**

| File:line | Hint string |
|---|---|
| `sgit_ai/cli/CLI__Vault.py:216` | `print( '  sgit share           — re-publish (same URL, updated content)')` (post-clone hint) |
| `sgit_ai/cli/CLI__Vault.py:220` | `print( '  sgit share           — share a read-only snapshot')` (post-clone hint) |
| `sgit_ai/cli/CLI__Vault.py:313` | `print('  sgit share            — share a snapshot via a simple token')` (post-init "Next steps:" — implementer says this was dropped; verify) |
| `sgit_ai/cli/CLI__Vault.py:780` | `print('    Run: sgit export  to save it as a local archive')` (status path: "never-pushed" hint) |
| `sgit_ai/cli/CLI__Vault.py:1036` | `print('  sgit share            — share a snapshot with a simple token')` (post-push hint) |
| `sgit_ai/cli/CLI__Vault.py:1047-1048` | `print('  sgit share ... ');  print('  sgit publish ...')` (post-push hint) |
| `sgit_ai/cli/CLI__Vault.py:1156` | `print('error: sgit share requires a simple_token vault', file=sys.stderr)` (error message in the dead `CLI__Vault.cmd_share` — see F5) |
| `sgit_ai/cli/CLI__Share.py:107` | `print('  sgit share   — share again with a new token')` (inside `CLI__Share.cmd_share` body — the disabled handler's success branch; only fires if not properly stubbed) |
| `sgit_ai/cli/CLI__Create.py:119` | `print( '  sgit share           — share a snapshot via a simple token')` (post-create hint — implementer says this was dropped; verify) |
| `sgit_ai/cli/CLI__Publish.py:130-131` | Inside the disabled handler; only fires if stub not applied |
| `sgit_ai/cli/CLI__Export.py:110-111` | Same |

Also: `CLI__Main.py:607` `share_p = subparsers.add_parser('share', help='SG/Send sharing — send, receive, publish')` — the namespace parent advertises send/publish as features.

**Risk:** A user who runs `sgit push` and reads "Next: sgit share — share a snapshot with a simple token" then runs `sgit share` and hits the disabled message will be confused: the CLI just told them to do it. The disablement gate is also more discoverable as "the CLI nudges me toward something disabled" than as "Simple Tokens are temporarily disabled."

**Recommendation:** In the same PR, replace the kept-command hints with either neutral (omit) or a positive alternative (e.g. `sgit push` already exists, no need to also mention `share` at all). The disabled-stub message handles the case when the user does run the disabled command, but proactive hints in kept-command outputs are wrong. Specifically: lines 216, 220, 313, 780, 1036, 1047-1048 of `CLI__Vault.py`, line 119 of `CLI__Create.py`, and the `share_p` parent help at `CLI__Main.py:607` should be updated.

---

### F4 — `vault probe` advertises and operates on Simple Tokens routinely (IMPORTANT)

**Evidence:**
- `CLI__Main.py:500-503`:
  ```python
  probe_p = vault_sub.add_parser('probe',
                                  help='Identify a simple token as a vault or share (no clone)')
  probe_p.add_argument('token', help='Simple token (word-word-NNNN) or vault:// URL')
  ```
- `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py:90-98`:
  ```python
  def probe_token(self, token_str: str) -> dict:
      """Identify a simple token as vault or share without cloning."""
      from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token as _ST
      token_str = token_str.removeprefix('vault://')
      if not _ST.is_simple_token(token_str):
          raise RuntimeError(
              f"probe only accepts simple tokens (word-word-NNNN format): '{token_str}'"
          )
  ```

`vault probe` is a CONSUME-only path that the implementer correctly kept. But its help text and backend both make Simple Tokens a routine, advertised concept. A user who runs `sgit help vault` sees `probe — Identify a simple token as a vault or share (no clone)` and `Simple token (word-word-NNNN) or vault:// URL`. The disablement message they get from `vault share`/`share publish` will sit awkwardly next to this routinely-displayed help.

**Risk:** Mixed signals — the CLI claims to support Simple Tokens prominently (probe), and rejects them elsewhere. Users will reasonably ask: "is the feature disabled or not?"

**Recommendation:** Two options:
1. **Soft-keep** (architect's preference): leave `vault probe` functional but soften the help text — e.g. `'Identify a token as a vault or share (no clone) — read-only diagnostic'`. The backend stays Simple-Token-only because that's literally what `probe_token` was designed for; document this as a kept consume-path.
2. **Disable** `vault probe` too — it's a consume path but it specifically advertises the disabled token format. Architect rejects this — probe is genuinely useful for diagnosing existing Simple-Token vaults (which still exist on user machines).

Either way, the help-text wording should not say "Simple Token" as the *primary* description.

---

### F5 — `CLI__Vault.cmd_share` is dead code, kept and not gated (IMPORTANT)

**Evidence:**
- `sgit_ai/cli/CLI__Vault.py:1132` defines `cmd_share(self, args)` (53 lines, lines 1132-1183).
- `sgit_ai/cli/CLI__Main.py:557`: `share_p.set_defaults(func=self.share.cmd_share)` — the LIVE wiring routes `vault share` to `CLI__Share.cmd_share`, NOT to `CLI__Vault.cmd_share`.
- Grep confirms no other CLI dispatch references `CLI__Vault.cmd_share`. Tests at `tests/unit/cli/test_CLI__Vault__Coverage.py:545-794` call it directly (3 test methods + 1 in a second class).

The implementer's question 1 was: "is the right surface disabled?" Answer: **yes** — `CLI__Share.cmd_share` is the live one and is correctly in the disablement set. But `CLI__Vault.cmd_share` exists as dead code that is reachable programmatically (`from sgit_ai.cli.CLI__Vault import CLI__Vault; CLI__Vault().cmd_share(...)`), persists the simple-token logic, and continues to be exercised by 4 unit tests that validate the simple-token publish flow. From an audit perspective, **the source still contains a live-looking method that mints Simple Tokens.**

**Risk:** A reader auditing for "what minted Simple Tokens before the gate" finds `CLI__Vault.cmd_share` and assumes the gate missed it. A programmatic caller (e.g. a third-party CLI consumer, a future plugin) can still invoke it. The tests passing reinforces the illusion that the path is live.

**Recommendation:** Either (a) **remove `CLI__Vault.cmd_share` entirely** (it's dead) and remove its tests, or (b) **stub it identically to the live disablement message** so the path is consistent. Architect recommends (a) — deleting dead code is preferable to maintaining two parallel disable points.

---

### F6 — `Vault__Sync.init(token=...)` parameter retained without live CLI caller (IMPORTANT)

**Evidence:** `sgit_ai/core/Vault__Sync.py:43-44`:
```python
def init(self, directory: str, vault_key: str = None,
         allow_nonempty: bool = False, token: str = None) -> dict:
```

After the disablement, `CLI__Vault.cmd_init` and `CLI__Create.cmd_create` both pass `token=None` (per the brief). Grep of the source tree confirms:

| Caller | Token passed |
|---|---|
| `CLI__Vault.py:287` | `init_token` (was simple-token; now should be None after F1 fix) |
| `CLI__Create.py:58` | `init_token` (same) |
| `Step__Transfer__Init_Vault.py:23` | `token=new_token` — generates a Simple Token (see F2) |
| 5 integration tests + perf fixtures | Only `vault_key=...`, no token |

So `token=` is reached by exactly ONE live producer: `Step__Transfer__Init_Vault`, which F2 covers. After F1+F2 are addressed, `token=` has zero live producers from the user-facing CLI.

**Risk:** Retained as a backend surface for the rework — consistent with the user's "kept backend implementations" decision. The retention is justifiable, but it leaves a contract gap: third-party Python consumers can still call `Vault__Sync().init(directory, token='word-word-1234')` and mint a Simple-Token vault. If the rework intends to **remove** Simple Tokens entirely, this surface should also go; if it intends to **rework** them, the parameter should be renamed (e.g. `_legacy_simple_token=None`) to make the deprecation explicit.

**Recommendation:** Add a 2-line docstring to `Vault__Sync.init` stating: "the `token` parameter is retained for the in-progress Simple Token security rework. No production CLI path passes a non-None value as of v0.1.0. Do not call programmatically." This documents the contract gap without changing behaviour.

---

### F7 — Argparse args on disabled commands silently ignored (NIT)

**Evidence:** `CLI__Main.py:463-472, 550-557, 611-615, 623-632` (the four disabled subparsers). Each still defines `--as`, `--no-inner-encrypt`, `--rotate`, `--token`, etc. With the handler stubbed, the user can run e.g. `sgit vault export --as cold-idle-1234 --no-inner-encrypt` and get the same "disabled pending security rework" message — the flags are accepted by argparse and then dropped on the floor.

**Risk:** User confusion. A user who carefully reads the help text, picks flags, runs the command, and gets a generic "disabled" message will wonder if the flags caused the rejection. The disabled message does not acknowledge that flags were even parsed.

**Recommendation:** Either (a) leave as-is and accept the minor UX surprise (preserves the parser for clean re-enablement); or (b) change the disabled message to include the parsed args: "this command (`sgit vault export --as cold-idle-1234 --no-inner-encrypt`) is temporarily disabled pending a security rework of the Simple Token scheme. Your flags were parsed but ignored." Architect prefers (b) for transparency — a one-line `' '.join(sys.argv[1:])` echo costs nothing.

---

### F8 — Disabled-message exit code and lack of tracking link (NIT)

**Evidence:** Implementer brief states: "Stub prints 'temporarily disabled pending a security rework of the Simple Token scheme' and exits 1. No tracking link, no timeline."

**Risk:**
- **Exit code:** Convention for "feature unavailable" is `EX_UNAVAILABLE = 69` on BSD systems; on Linux/CI, `2` is the typical "usage error" code. `1` is "generic error" and may be confused with a runtime failure. Scripts can't distinguish a network failure from a disablement.
- **No tracking link:** users have no path to discover the timeline, the security justification, or to subscribe to re-enablement. This makes the gate feel arbitrary.

**Recommendation:** Exit code `2`. Add a single line to the message: `'see https://docs.sgit.ai/disabled/simple-token for the security rework status and timeline'` (or a GitHub issue link). If neither URL exists yet, register a tracking issue and link it.

---

### F9 — Backend test files retained without explanatory docstring (ADVISORY)

**Evidence:** The brief retains `test_CLI__Share.py`, `test_CLI__Publish.py`, `test_CLI__Export.py`, plus the 4 tests in `test_CLI__Vault__Coverage.py:545-794` that exercise the dead `CLI__Vault.cmd_share`. These call the underlying `cmd_*` methods directly and continue to pass.

**Risk:** A reader scanning the test tree six months from now sees `test_cmd_share_simple_token_vault` passing and assumes `vault share` is a supported, working surface. The kept-backend policy is not visible from the test files themselves.

**Recommendation:** Add a 3-line file-level docstring to each kept-backend test file: `"""Backend tests for the Simple-Token PUBLISH path. The CLI surface that calls this code is DISABLED at the CLI layer (see CLI__Disabled_Command). These tests verify the backend continues to function for the in-progress security rework. Do not remove."""`. This makes the kept-backend rationale visible without changing test behaviour.

---

### F10 — `CLI__Disabled_Command` round-trip invariant not enforced (ADVISORY)

**Evidence:** Per CLAUDE.md §5/6:
> Every schema must pass: `assert cls.from_json(obj.json()).json() == obj.json()`

The implementer's brief describes 8 tests for `CLI__Disabled_Command` and 4 for `Safe_Str__CLI_Command_Label`. The standard round-trip invariant on `CLI__Disabled_Command` (which has the field `command_name: Safe_Str__CLI_Command_Label`) is not enumerated.

**Risk:** Type_Safe class without a documented round-trip test sets a poor precedent. The class is trivial enough that the test will almost certainly pass, but the rule says "every schema," not "every interesting schema."

**Recommendation:** Add a single round-trip test:
```python
def test_round_trip(self):
    obj = CLI__Disabled_Command(command_name=Safe_Str__CLI_Command_Label('vault export'))
    assert CLI__Disabled_Command.from_json(obj.json()).json() == obj.json()
```

This is a 4-line test that proves the rule is held even for a stub class.

---

### F11 — Bare `sgit init` UX change: previously created subdirectory, now initialises in CWD (ADVISORY)

**Evidence:** Pre-disablement `CLI__Vault.cmd_init:281-285`:
```python
elif not vault_key and directory in ('.', '') and not restore:
    # Scenario C: bare `sgit init` → auto-generate a simple token
    generated  = Simple_Token__Wordlist().setup().generate()
    init_token = str(generated)
    directory  = init_token   # use token as directory name
```

This branch had a SIDE EFFECT beyond minting the token: it **rewrote `directory` from `'.'` to the token string**, so bare `sgit init` would create a NEW subdirectory `apple-banana-1234/` rather than initialising in CWD. The implementer is removing this branch entirely. Post-disablement, bare `sgit init` will dispatch through `Vault__Sync.init(directory='.', vault_key=None, token=None)`, which generates a `passphrase:vault_id` and initialises in CWD.

**Risk:** A user who had muscle memory for `cd projects && sgit init` (creating `projects/apple-banana-1234/`) will now find their `projects/` directory has been initialised as a vault. If `projects/` is non-empty, the existing-prompt at `CLI__Vault.py:267-273` will catch this, but for empty `projects/` it will proceed silently.

**Recommendation:** Acceptable behaviour change, but document it in the v0.1.x CHANGELOG / release notes: "Bare `sgit init` now initialises the current directory rather than creating a subdirectory named after an auto-generated simple token. Use `sgit init <name>` for a named subdirectory." Optionally: when `directory == '.'` and `vault_key is None` and the user hasn't passed `--existing`, print a one-line confirmation `'Initialising vault in current directory.'` so the change is visible.

---

## 4. Zero-Knowledge & Crypto Interop

| Concern | Verdict |
|---|---|
| New crypto operations introduced | None. The disablement is pure CLI dispatch + a tiny new `Safe_Str` subclass. |
| New server interaction | None. Disabled stubs print to stderr and exit; no network. |
| Server-observable change to a kept path | None. `vault probe`, `share receive`, `sgit clone <token>` are unchanged behaviourally. |
| Crypto interop | Not affected. Backend retention means byte-for-byte identical outputs for any retained call site. |
| Key-handling change | None. The retained `Vault__Sync.init(token=...)` still produces identical Schema__Local_Config when called. |

**Verdict: zero-knowledge guarantee is preserved by the disablement itself.** The findings above are about completeness of the disablement (F1, F2) and UX hygiene, not crypto/storage contract.

---

## 5. Open Questions (need human / cross-role decision)

1. **F1 routing:** is the disablement intent (a) "every Simple-Token CREATE path at the CLI is gated" — which requires stripping the positional branches at `CLI__Vault.py:233` and `CLI__Create.py:50-55` — or (b) "the four named surfaces only, other Simple-Token creation paths are left as backwards-compat" — which leaves a soft gate? Architect recommends (a) for security defensibility.
2. **F2 routing:** does the transfer-clone path (`sgit clone <transfer-token>`) need to be gated under the same disablement, or is the user-facing claim restricted to the four named subcommands? If (a), `Step__Transfer__Init_Vault` needs the same treatment. Architect recommends (a).
3. **F4 routing:** `vault probe` is intentionally Simple-Token-only at the backend. Soften the help text (architect's recommendation) or disable probe too? Architect prefers softening.
4. **F8 exit code:** is exit `1` deliberate, or did the implementer not consider `2`? If the latter, change to `2` and document.

---

## 6. Hand-Off

**To Dev (binding once F1 + F2 are decided):**
- F1: strip positional simple-token detection at `CLI__Vault.py:233-236, 277-280` and `CLI__Create.py:50-55`, OR re-scope the disablement claim in the brief.
- F2: gate `Step__Transfer__Init_Vault.execute`, OR document the kept transfer-clone behaviour.
- F3: replace the 7+ "next step" hints across CLI__Vault, CLI__Create with neutral / non-disabled alternatives. Update `share` namespace parent help at CLI__Main.py:607.
- F5: delete `CLI__Vault.cmd_share` (lines 1132-1183) and its tests, OR stub it.

**To Dev (recommended in same PR or next):**
- F4 help-text softening on `vault probe`.
- F6 docstring on `Vault__Sync.init`.
- F7 message enhancement (echo parsed args).
- F8 exit code + tracking link.
- F9 docstrings on kept-backend test files.
- F10 round-trip test on `CLI__Disabled_Command`.

**To QA (binding):**
- For F1: add a test that `sgit init word-word-1234` is now rejected (or that the resulting `Schema__Local_Config.mode` is not `SIMPLE_TOKEN`) — depending on chosen routing.
- For F2: same for `sgit clone <transfer-token>`.
- For F11: add a test that bare `sgit init` initialises in CWD with a `passphrase:vault_id`-shaped vault_key, not a simple-token directory.

**To Historian:** picks up automatically.

---

*Architect review produced 13 June 2026. Code references verified against the working tree at HEAD `e68b7d4` on branch `claude/setup-architect-agent-RskQe` — the commit `2dd1bd7` is not present in the local tree at review time; findings against described changes use the pre-disablement code as evidence of what the disablement targets. No CRITICAL findings, no zero-knowledge or crypto-interop blockers. Two BLOCKER findings on disablement completeness (F1, F2) must be routed by the human before ship.*
