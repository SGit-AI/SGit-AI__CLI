# AC-L-001 / TM-R36 — characters outside `[a-zA-Z0-9/\_.- ]` in paths: what really happens

**Status:** documented, **not fixed in this push** (your call, 13 Oct). Reproduced on `dev` at
81a4176 with the Python API over the in-memory host. The fix proposal below follows your
instinct: **raise an alarm, never rewrite silently**. It is narrower than "refuse every such
character", for the reason in §3.

It is worse than the round-1 record (`review/findings/audit-context-local.json` AC-L-001) says.
Two different things share the bug: **where the vault lives** (the host path of the clone) and
**names inside the vault** (file and folder names in the trees).

## 1. The vault root: broken, and silently in the wrong place

`Safe_Str__Vault_Path` and `Safe_Str__File_Path` both use `[^a-zA-Z0-9/\\_.\- ]` in *replace*
mode: every other character becomes `_`. The working directory of the clone, pull, fetch,
push and move workflows (`directory : Safe_Str__File_Path`), `Vault__Context.vault_path` and
`Vault__Storage` go through them; other code uses the raw `str`. So one vault gets two roots.

| Step, under `/tmp/x/josé/vault` | What happened |
|---|---|
| `init` | the working copy and `.sg_vault/{bare,local}` are under `josé/vault`, **and** a second tree `jos_/vault/` is created next to it |
| `commit`, `status` | ok, `clean` |
| first `push` | **`Vault__Push_Conflict_Error`: "the branch moved on the server while this push was in flight"** — false; nothing was pushed |
| `clone` into `josé/clone` | reports success; **the whole clone is written to `jos_/clone`**; `josé/clone` does not exist |
| `pull` in `josé/clone` | `FileNotFoundError: …/josé/clone/.sg_vault/local/vault_key` |
| second `commit` + `push` in `josé/vault` | `FileNotFoundError: …/jos_/vault/.sg_vault/work/pull-…/.tmp-…` |

It is not only accents. What the type does to real folder names:

| Path | Becomes |
|---|---|
| `/Users/x/Dropbox (Personal)/v` | `/Users/x/Dropbox _Personal_/v` |
| `/Users/x/OneDrive - Acme, Inc/v` | `/Users/x/OneDrive - Acme_ Inc/v` |
| `/home/first.last@corp/v` | `/home/first.last_corp/v` |
| `/home/u/my+vault` | `/home/u/my_vault` |
| `C:\Users\Zoë\v` | `C_\Users\Zo_\v` |

**The last row needs a check on Windows.** The colon of every drive letter is rewritten, so if
any of these fields carries an absolute Windows path, every Windows user is affected, not just
users with accented names. I could not run Windows here.

Security reading: a write lands in a directory the user never named. Two roots that sanitise
alike share one store (`josé/` and `josè/` and a real `jos_/`), so one vault's objects, refs and
`work/` files can mix with another's. A local process (A6) that can create `jos_/` next to
`josé/` decides where the store goes. Likelihood M (any European or company folder name, any
Dropbox or OneDrive folder); impact H (a false "conflict", a clone in the wrong place, failures
on the next command). I have raised TM-R36 from M / M to M / H.

## 2. Names inside the vault: the core is right; the display and `--path` are not

Tree entry names are encrypted strings, not `Safe_Str` fields, so the sync path never touches
them. With `café.md`, `naïve dir/résumé.md`, `a+b@c.md`, `日本語.txt` and a `caf_.md` beside
`café.md`:

| Step | Result |
|---|---|
| status, commit, push, clone | every file round-trips byte for byte, with the exact name; `café.md` and `caf_.md` stay two files |
| edit in the clone, push, pull in the first clone | ok; content and name exact |
| `stash` / `stash pop` | ok |
| **`sgit diff`** (`Schema__Diff_File.path`) | **lists `caf_.md` and `na_ve/r_sum_.md`**: the display lies |
| **`sgit clone --path naïve`** (`scope_paths : list[Safe_Str__File_Path]`) | **records the scope `na_ve`, checks out nothing, and says nothing** |
| history file lists, publish entries, stash metadata | typed with the same class, so they rewrite the same way (not each one run) |

So "what happens if the vault creates that": another client, or the web UI, can put such a
name in a vault. This CLI clones, edits and syncs it correctly. Its listings show the wrong
name, and a scoped clone of that folder is silently empty.

Hostile names in a vault are a separate question with an existing answer: `Vault__Path_Guard`
refuses absolute paths, `..` on either separator, `.git` / `.sg_vault`, and writes through a
symlink at checkout (TM-F series). Nothing in this finding weakens that.

## 3. The decision proposed for the next push

**The rule:** a type that names a place must **refuse** what it cannot represent, never rewrite
it. A rewritten path is a silent data change: the user asked for one place and got another.
Worth a line in CLAUDE.md's Type_Safe rules.

1. **Vault roots: the alarm now, the real fix right behind it.**
   - *Stop-gap (S):* at the CLI boundary, before any command uses a vault root (`init`, `clone*`,
     and resolving the root of every other command), refuse a root the type would change:
     > `sgit cannot work in a folder whose path contains 'é' (…/josé/vault) yet. Move the vault, or clone it, to a path made of letters a-z, digits, space, '.', '_' and '-'. (TM-R36)`
   - *Fix (M):* type the host-side fields (`directory`, `vault_path`, the storage root) with
     `Safe_Str__Host_Path`. It already exists, added for `sgit serve`: any printable text,
     control characters refused, never rewritten. Then the alarm is no longer needed.
2. **Names inside a vault: do not refuse them.** They work today, other clients create them,
   and refusing would lock people out of their own vaults. That is the lock-out lesson of R1 and
   TM-F35. Instead:
   - a content-path type (Unicode allowed; NUL, control characters, absolute paths and `..`
     refused) for the display and scope schemas: `Schema__Diff_File`, history lists,
     `scope_paths`, publish entries, stash metadata;
   - `clone --path` refuses a folder that is not in the tree, rather than cloning nothing.
3. **Where an alarm is right for content: names that will not survive another OS.** Add a check
   (rule 9 puts it under `check`), and a warning at `commit` time for new names only (an alarm,
   not a refusal). It covers:
   - case-only collisions (`A.md` and `a.md` are one file on macOS and Windows);
   - Unicode normalisation twins (NFC and NFD `café`; macOS can hand back the other form, so
     status shows a delete and an add);
   - Windows-reserved names (`CON`, `AUX`, `NUL`, `COM1`…, a trailing dot or space, `<>:"|?*`);
   - control characters and newlines;
   - paths too long for Windows.
4. **Tests that land with the fix:**
   - init, commit, push, clone and pull under a root with `é`, `+`, `@`, `(` and a space;
   - clone into `josé/`;
   - `clone --path naïve`;
   - `diff` listing the exact names;
   - a `Fixed` security test that two roots that used to sanitise alike no longer share a store;
   - the check's cases.

Sizes: the stop-gap is under a day. The type change is a day or two, because the type is used by
every path field; the check is about a day.

## Where this is recorded

- Threat model TM-R36: likelihood/impact raised, this evidence linked.
- CHANGELOG `[Unreleased]` → "Known issue".
- Probe scripts were run from the session scratchpad. Their steps are in the tables above.
