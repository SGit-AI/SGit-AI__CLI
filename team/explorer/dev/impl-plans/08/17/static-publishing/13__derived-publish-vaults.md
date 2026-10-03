# 13 — Derived publish vaults (`sgit vault derive`)

**Date:** 2026-08-24 · **Status:** BUILD SPEC — awaiting sign-off on decisions 18–21
**Trigger:** maintainer — *"the creation of a rekeyed vault … publish what in essence is a
copy of a vault, without actually exposing the read-only key or the vault key of the vault
to publish"*, in two modes: **nuke history** and **keep all history**.
**Depends on:** P2 (`sgit publish`), and the move graph rewrite shipped in r17.

---

## 1. The problem this solves

`sgit publish --visibility public` writes the vault's **own** read key into the published
folder. That is correct for the case it was built for — a vault whose whole purpose is to
be public — but it forces an uncomfortable coupling for the far more common case:

- The published read key is the **source vault's** read key. It decrypts everything in that
  store, for ever, including content published later and content the publisher never meant
  to expose (other branches, older commits, stashes).
- The published store shares every `obj-cas-imm-*` id with the source, so anyone who can see
  both stores can correlate them — the same linkability we removed from `move` in r17.
- There is no way to publish *a subset in time* (say, "the current state, no history")
  without destroying the source's own history.

A **derived vault** is a separate, rekeyed vault built from the source. It has its own vault
key, its own vault id, and its own object ids. Publishing it exposes *its* read key. The
source's keys never leave the publisher's machine, and the two stores share nothing an
observer can join on.

> **This is not a new cryptosystem.** Both modes are engines that already exist and are
> already tested; §3 says which. The new work is a non-destructive *derive* wrapper plus the
> incremental state that makes refresh cheap and the derived key stable.

## 2. The shape

```
  work/handbook/                        published-handbook/          (the derived vault)
  ├── docs/…                            ├── .sg_vault/
  ├── .sg_vault/                        │   ├── bare/…               ← rekeyed objects
  │   ├── bare/…                        │   └── publish/…            ← sgit publish output
  │   └── local/                        └── (no work tree — bare)
  │       └── derived/
  │           └── <derived-vault-id>.json   ← derived key + id-map + last source head
  └── …
```

Two rules fix the layout:

- **The derived folder MUST NOT be inside the source's work tree.** If it were, the derived
  store would become source vault content on the next commit — the amplification loop that
  `07` §3 already forbids for publish output (a vault containing a rekeyed copy of itself,
  growing on every publish). `derive` refuses a destination under the source directory,
  naming the reason.
- **The derived key and id-map live in the source's `.sg_vault/local/`** — never pushed,
  never published, already covered by the canonical repo `.gitignore` set (decision 13). The
  source vault already holds the source vault key, which is strictly more powerful, so this
  adds no new class of secret to that directory.

The derived vault is an **ordinary vault**. `sgit publish`, `sgit vault serve`,
`sgit vault mirror` and `sgit clone` all work on it unchanged — this spec adds no special
case to any of them.

## 3. The two modes, and the engines behind them

| Mode | Flag | What the derived vault contains | Engine that already exists |
|---|---|---|---|
| **Snapshot** ("nuke history") | `--mode snapshot` *(default)* | One commit per publish, holding the source head's file tree. No source history, no source commit messages, no branch structure. | The flatten-and-build path (`Vault__Sub_Tree.build_from_flat`, as pull's merge uses) — see §3.1 on why not `rekey()` |
| **History** ("keep all history") | `--mode history` | The full commit graph, re-encrypted and re-addressed | `Step__Move__Build_Temp_Vault._rewrite_object_graph` (r17): reachability-typed, bottom-up, blobs → trees (children first) → commits (parents first), every reference remapped including merge parents |

### 3.1 Snapshot mode does not reuse `rekey()`

`Vault__Sync__Lifecycle.rekey()` produces exactly the right *result* (wipe, re-init under a
new key, commit the working tree as one fresh commit) but it does it **in place** and it
commits **the working tree**. Both are wrong here: the source must be untouched, and a
derived vault should not require a second plaintext copy of every file on disk. Snapshot
mode instead flattens the source head tree, maps its blobs through §4, builds one tree with
`build_from_flat` under the derived key, and writes a single commit — no work tree needed.
`rekey()` is left alone; it keeps its own meaning ("rotate this vault's key in place").

### 3.2 History mode must not write the move sentinel

`Step__Move__Write_Sentinel_Commits` writes a commit whose message contains
`from-vault-id: <old_vault_id>` and `to-vault-id: <new>`. In a *move* that is a wanted audit
trail. In a *derived, published* vault it is a disclosure: publishing means handing out the
read key, so every reader decrypts that message and learns the source vault's id — defeating
the entire purpose of §1. **The derive path omits the sentinel step.** It is a separate step
in the move workflow, so this is an omission rather than a change, but it is load-bearing
and must have a test asserting no derived commit message names the source vault id.

## 4. Incremental refresh — the load-bearing mechanism

**Re-running `derive` against an existing derived vault refreshes it in place, keeping its
vault key and vault id.** Previously distributed read keys, URLs and deep links stay valid.

This only works because of a persisted id-map, and the reason is worth stating precisely:

> `emit()` in the r17 rewrite encrypts with `crypto.encrypt`, which uses a **random IV**
> (`os.urandom(GCM_IV_BYTES)`). Re-encrypting the same plaintext twice therefore yields
> different ciphertext and — since the id *is* `sha256(ciphertext)[:12]` — a different object
> id. Without a map, every refresh re-addresses the entire store: the whole manifest churns,
> every bundle is invalidated, and every deep link 404s, even if one file changed.

### 4.1 The state file

`<source>/.sg_vault/local/derived/<derived-vault-id>.json`, `chmod` as tightly as the vault
key file:

| Field | Purpose |
|---|---|
| `schema` | versioning, per house rules |
| `derived_vault_key` | the stable derived key — the secret that makes refresh possible |
| `derived_vault_id` | identity of the derived vault |
| `mode` | `snapshot` \| `history` — **immutable after creation** (see decision 20) |
| `source_head` | the source commit last derived from; lets `derive` report "nothing to do" |
| `derived_head` | the derived commit last written |
| `id_map` | `{source_object_id: derived_object_id}` |
| `last_dest_path` | convenience default only; never authoritative |

### 4.2 The refresh algorithm

1. Read the state file; if absent, this is a first derive (generate a key, create the vault).
2. Walk the source graph from the current head (history mode: the whole reachable graph;
   snapshot mode: the head tree only).
3. For each source object: if it is in `id_map` **and** that derived id is still present in
   the derived store, **skip it entirely** — no decrypt, no re-encrypt, no write. Otherwise
   emit it under the derived key, record the mapping.
4. Rewrite references through the map exactly as r17 does, write the new head commit, repoint
   the derived refs.
5. Write the state file back atomically.

The consequence is the one asked for: an unchanged file is never re-encrypted, and only the
path from a changed blob up to the new root commit is new work — the same shape as an
ordinary commit. A refresh after a one-file change adds a handful of objects, not a store.

**Map everything, not just blobs.** A tempting optimisation is to encrypt trees
deterministically (as the normal commit path does via `encrypt_deterministic`, so unchanged
subtrees dedup for free) and skip mapping them. That works, but mapping uniformly is simpler,
is correct regardless of IV strategy, and avoids reasoning about which object types leak
equality. Treat deterministic trees as a later optimisation with its own decision, not as
part of v1. *(Note for whoever takes that up: the r17 rewrite currently encrypts trees with
a random IV, unlike the normal commit path — so rewritten historical trees do not dedup
against future identical trees. That is a pre-existing inefficiency in `move`, not a defect,
but it is the same question.)*

### 4.3 Snapshot mode must prune, or deletion is cosmetic

**This is the sharpest edge in the feature.** In snapshot mode, refreshing after deleting a
file from the source leaves the old blob in the derived store: unreachable from the new
commit, but still on disk, still enumerated in `manifest.json`, and still decryptable by
anyone holding the published read key. The publisher would reasonably believe the file was
withdrawn. It was not.

So: **snapshot refresh prunes objects unreachable from the new head**, and `derive` reports
what it pruned. History mode does not prune (unreachable content is the point of history) —
but see decision 21, because "I published a secret and then deleted it" has no good answer in
history mode and the command should say so rather than imply otherwise.

## 5. Command surface

```
sgit vault derive <dest> [--mode snapshot|history] [--dry-run]
                         [--source <dir>] [--new-key <vault-key>]
```

- First run creates the derived vault at `<dest>`; later runs against the same `<dest>`
  refresh it. **Idempotent, no separate `--refresh` flag** — running it twice with no source
  commits in between reports "already current" and writes nothing.
- `--mode` is only meaningful on creation; supplying a different one later is an error
  naming the recorded mode (decision 20).
- `--new-key` is an escape hatch for key rotation of the *derived* vault; it invalidates
  every previously distributed read key, so it warns and requires confirmation.
- Refuses when `<dest>` is inside the source work tree (§2), when the source store fails its
  content-address check (reusing the r18 publish-side guard), and when `<dest>` exists but is
  a vault this source did not derive.

Publishing is unchanged and explicit — the derived vault is a normal vault:

```
sgit vault derive ../published-handbook --mode snapshot
sgit publish        ../published-handbook --visibility public
```

## 6. Security analysis

**What this fixes.** The published read key belongs to the derived vault only. It decrypts
the derived store and nothing else — not the source's other branches, not its future
commits, not its history in snapshot mode. Source vault key and source read key never leave
the publisher's machine. The two stores share no object id, so they cannot be joined by an
observer who sees both.

**What it does not fix, and must say so.**

| Exposure | Mode | Note |
|---|---|---|
| Commit messages, timestamps, branch names readable by anyone with the published key | history | The point of the mode, but publishers routinely forget that history is *content*. `derive --mode history` warns once, explicitly. |
| Publish cadence (one commit per refresh) | snapshot | Low; unavoidable if refresh is to be a fast-forward |
| Content withdrawn after publication | both | Snapshot prunes locally (§4.3) but **cannot un-publish bytes already fetched or mirrored**. The only real remedy is key rotation plus redeployment; say this plainly. |
| Rollback of the published copy by its host | both | Unchanged from decision 16 — the derived vault inherits the same accepted risk |

**The id-map is a correlation oracle.** It maps source object ids to derived ones; anyone
holding it can join the published vault back to the source store, which is exactly what §1
set out to prevent. It is therefore secret-grade: local-only, `chmod`'d like the vault key,
never pushed, never inside the published surface, and covered by the canonical `.gitignore`
set. An invariant test must assert it never appears under `.sg_vault/publish/`.

**To verify during implementation (not asserted here):** whether `bare/keys` per-branch
signing public keys carry over the rewrite unchanged, and whether that gives an observer a
join key between source and derived stores. If they do carry over verbatim, they must be
regenerated in the derive path. This was not checked while writing this spec.

## 7. Invariants

Extending the I1–I7 set:

- **I8 — the source's keys never enter the derived vault or its published surface.** No
  file under `<dest>` contains the source vault key, source read key, or source vault id.
- **I9 — no derived object id equals a source object id.** (The r17 linkability property,
  now asserted across the derive boundary.)
- **I10 — refresh is stable and incremental.** Two derives with no source change produce a
  byte-identical derived store; a one-file change adds only the objects on that file's path
  to the root, and the derived vault key and id are unchanged.
- **I11 — snapshot refresh leaves nothing unreachable.** After a snapshot refresh, every
  object in the derived store is reachable from its head.
- **I12 — the id-map never leaves `local/`.**

## 8. Test cells

| # | Cell | Assertion |
|---|---|---|
| 15 | snapshot derive → publish → clone with derived key | content matches source head; derived key ≠ source key |
| 16 | history derive → publish → clone → `log` | full history present; **no commit message contains the source vault id** (§3.2) |
| 17 | refresh after one-file change | derived key/id unchanged; object count grows by the path only; previously distributed key still clones |
| 18 | refresh with no change | "already current"; store byte-identical |
| 19 | snapshot refresh after a deletion | pruned; deleted blob absent from store **and** from `manifest.json` |
| 20 | dest inside the source work tree | refused, reason named, nothing written |
| 21 | id-map containment | absent from `.sg_vault/publish/` and from the composed served root |
| 22 | source store fails content-address check | refused before anything is written (reuses the r18 guard) |
| 23 | derive from a read-only clone | works — derive needs the read key only, like publish |

## 9. Decisions needed from the maintainer

| # | Question | Recommendation |
|---|---|---|
| **18** | Command name and noun | **`sgit vault derive`**, artefact called a *derived vault*. "fork" implies divergent editing that syncs back; this never syncs back |
| **19** | Snapshot refresh: replace the single commit, or append a squash chain? | **Append** — one commit per publish, parented on the previous derived commit. Readers fast-forward instead of seeing rewritten history, which matters now that the key is stable. Leaks only publish cadence |
| **20** | Is `mode` immutable after creation? | **Yes.** Switching snapshot → history would retroactively publish history the publisher had chosen to withhold. Changing mode means a new derived vault with a new key |
| **21** | Does `derive` warn about withdrawn content? | **Yes, once per mode**, per §6 — the publisher's mental model ("I deleted it, so it is gone") is wrong in both modes, differently |

## 10. Phases

| Phase | Scope | Notes |
|---|---|---|
| **PD1** | State schema + `Vault__Derive` skeleton + containment refusals (§2, §5) | Small; unblocks everything |
| **PD2** | Snapshot mode, first derive + refresh + prune | The default mode; cells 15, 17, 18, 19 |
| **PD3** | History mode, reusing the r17 rewrite with the map and no sentinel | Extract the rewrite from the move step into a reusable component; cells 16, 17 |
| **PD4** | CLI, warnings, `--dry-run`, docs | Cells 20–23; I8–I12 |

Estimated shape: one new action class plus a small workflow, one schema, one CLI surface, and
roughly 25–35 tests. **No new crypto primitives, and no change to `publish`, `serve`, `mirror`
or `clone`.**
