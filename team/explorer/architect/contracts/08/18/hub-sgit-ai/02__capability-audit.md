# 02 — Capability Audit

The hub specification (v0.33.58, Part B) is explicit: **the first deliverable is an
inventory, not architecture**, because "a design written without that knowledge will be
wrong in one of two expensive directions: rebuilding something that exists, or assuming
something that does not."

That audit was scoped to the **vault web** codebase. This file does the **CLI half** — which
nobody had done, and which turned up the two findings below — and gives the web team the
template for theirs.

---

## 1. CLI-side audit (done — facts, not design)

Established against the shipped tree on 2026-08-18. "Adding" means the forge would be
building a capability sgit does not have, per the spec's surfacing/adding/absent rule.

### Present — the forge would be *surfacing* these

| Capability | Where | Note |
|---|---|---|
| Open a vault from a **read key alone** | `clone_read_only`, `import_read_key` | shipped v0.14.26+; verified against GitHub Pages |
| Open from a full vault key | `derive_keys_from_vault_key` | |
| List a tree / navigate directories | `Vault__Sub_Tree.flatten`, `resolve_path_target` | |
| Fetch + decrypt a single object by path | `sparse_cat`, `Vault__Sub_Tree` | |
| Walk commit history | `CLI__Main history`, `Vault__Commit` | |
| Diff two versions | `CLI__Diff`, `Vault__Diff` | |
| Branch / merge / conflict handling | `CLI__Branch`, `CLI__Merge`, `Vault__Merge__State` | client-side already |
| **Sparse / partial fetch** | `Vault__Sync__Sparse` (27 files touch it) | the performance answer, already present |
| **Per-path index (1-request reads)** | `Vault__Cache_Manager` + `Vault__Cache_Reader` | **the v0.33.56 per-path-index brief, shipped as the cache layer** |
| Read over plain GETs (no server) | `Vault__API__Static` (spike, productionising) | clone from Pages / folder / dumb HTTP proven |
| Rekey = fork | `sgit vault rekey`, `vault move` | forks share **zero** object ids (measured) |
| Local object store / caching | `Vault__Object_Store` | |

### Present but **unused** — the finding worth acting on

| Capability | Where | Why it matters |
|---|---|---|
| **Structure key** — decrypts metadata (refs, branches, trees, commits) but **not blob content** | `Vault__Crypto.derive_structure_key`, `Vault__Dump.dump_with_structure_key` | A **third access tier** the briefing pack does not mention. Exactly "browse the shape without reading the files": paths, history, sizes, commit graph — with content withheld. One consumer (`sgit vault dump --structure-key`), fully tested (`tests/unit/crypto/test_Vault__Crypto__Structure_Key.py`). It is derived one-way from the read key, so holding it reveals nothing about the read or vault key. |

This is a shipped primitive looking for a product. See [`04__permissions-topology.md`](04__permissions-topology.md)
and [`05__commercialisation.md`](05__commercialisation.md) — it is a permissions tier and a
pricing tier at the same time.

### Absent — the forge would be *adding*, or cannot

| Capability | State | Consequence |
|---|---|---|
| **Sub-vaults / link files** | **ABSENT** — no such primitive anywhere in the CLI | **The permissions-as-topology model has nothing to stand on.** See §2 |
| `blame` | absent | The spec's correction is confirmed: a forge computing blame is **adding**, not surfacing |
| `bisect`, `rebase`, `cherry-pick`, submodules, tags | absent | Same category |
| Write / push **from the browser** | CLI-side exists; browser-side is the web team's audit | gates whether the forge is read-only at first |
| Cross-vault search without a key | impossible by construction | one of the four stated absences |

---

## 2. Finding 1 — the permissions model rests on a primitive that does not exist

Every brief in the pack builds granularity the same way:

> "granularity comes from **shape**… separate vaults, **sub-vaults with their own keys**,
> link files, and read keys distinct from write keys."

and the CI answer depends on it too — "a build runs against a **sub-vault containing only
what the build needs**, holding only that key."

**There is no sub-vault or link-file primitive in the CLI.** A vault is a flat namespace with
one key pair. What exists instead:

- separate **vaults** (works today — the coarse tier),
- read key vs vault key (works today — the read/write tier),
- **structure key** (works today, unused — the metadata tier).

So the worked topologies the spec asks for can be written *today* only in terms of separate
vaults plus three key tiers. Anything finer — "secrets/ is a sub-vault with its own key" —
is **a protocol feature nobody has built**.

**This should be settled before hub architecture is written**, because it decides whether
permissions are "several vaults and a link convention" (assembly, cheap) or "a nested-vault
protocol" (new format, cross-runtime, expensive). Options in
[`04__permissions-topology.md`](04__permissions-topology.md) §4.

## 3. Finding 2 — three tiers exist, and the middle one is free

```
vault key       ──►  read + write         everything
read key        ──►  read                 everything, no writes        (one-way derived)
structure key   ──►  metadata only        tree shape, history, sizes;  (one-way derived)
                                          NO file contents
(no key)        ──►  custody              hold and mirror; read nothing
```

Four usable positions, all shipped, none requiring server policy. The briefing pack works
with two. Adding the structure key to the model gives the hub a genuinely useful public
surface for private vaults — you can show a repository's *shape* without showing a byte of
its content — and it costs nothing to implement because it is already there.

---

## 4. The web-side audit — still the first deliverable

Unchanged from the specification, and it remains **the gate on hub architecture**. For each
capability record: **present / partial / absent**, where it lives, and whether it is
reachable from a page. *Report gaps as plainly as presences — a partial capability is more
dangerous to a plan than an absent one, because it gets assumed complete.*

| Capability | Present? | Where | Reachable from a page? |
|---|---|---|---|
| Open a vault in the browser from a read key | | | |
| Open from a full vault key | | | |
| **Open with a structure key only** (new — see §3) | | | |
| List a tree, navigate directories | | | |
| Fetch and decrypt a single object by path | | | |
| Render markdown, highlight code | | | |
| Walk commit history | | | |
| Fetch two versions and compare (diff) | | | |
| Sparse / partial fetch | | | |
| Local caching between sessions | | | |
| Sub-vault traversal and link files | | | *(see finding 1 — likely absent both sides)* |
| The app runtime and its permission model | | | |
| Write and push from the browser | | | |
| Merge and conflict handling client-side | | | |

Two additions to the original list, both from this audit: **structure-key open**, and an
explicit row for **sub-vault traversal** so its absence is recorded on both sides rather
than assumed present on the other.
