# Design — Layered Architecture (5 layers)

**Status:** Architecture decision captured. Implementation per briefs B12 + B13.
**Owners:** **Architect** (design freeze + dep enforcement) + **Dev** (the move).

## The principle

> All `sgit_ai/` source code organised into five layers, each in its
> own folder, each with explicit dependency rules. No upward imports.
> Adding a feature touches the smallest possible set of layers.

## The five layers

| Layer | Folder | What it contains | Depends on |
|---|---|---|---|
| 1. Crypto | `sgit_ai/crypto/` | AES-GCM, HKDF, PBKDF2, hashing, signature primitives, future PKI primitives. **Pure functions.** | nothing |
| 2. Storage | `sgit_ai/storage/` | On-disk read+write of encrypted objects: `Vault__Object_Store`, `Vault__Ref_Manager`, `Vault__Sub_Tree`, `Vault__Branch_Manager`, `Vault__Key_Manager`, `Vault__Storage` | Crypto |
| 3. Core | `sgit_ai/core/` | State-changing workflows: `Workflow__Clone`, `Workflow__Push`, `Workflow__Pull`, `Workflow__Fetch`, `Workflow__Commit`, `Workflow__Init`, `Workflow__Merge`, etc. plus their step classes | Crypto, Storage, Network |
| 4. Network | `sgit_ai/network/` | API client, transfer envelope, in-memory transfer server (the real implementation we test against). Existing `Vault__API`, `API__Transfer`, `Transfer__Envelope`, `Vault__Backend*` move here. | Crypto |
| 5. Plugins | `sgit_ai/plugins/` | Read-only operations packaged as runtime-loadable plugins. Each plugin = a feature-flaggable namespace (history, inspect, file, check, dev, search, blame, …). | Storage, Network |

Plus cross-cutting (not layered):
- `sgit_ai/safe_types/` — used by all layers, no behaviour
- `sgit_ai/schemas/` — used by all layers, no behaviour
- `sgit_ai/workflow/` — framework primitives (`Step`, `Workflow`, `Workflow__Workspace`); used by Core
- `sgit_ai/cli/` — thin CLI wrapper; calls Core (writes) + Plugins (reads)

## Dependency graph

```
                     ┌───────────┐
                     │  Plugins  │
                     └─────┬─────┘
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
            ┌─────┐     ┌─────────┐  ┌─────────┐
            │Core │ ──► │ Storage │  │ Network │
            └──┬──┘     └────┬────┘  └────┬────┘
               │             │            │
               └─────────────┴────────────┘
                             │
                             ▼
                          ┌─────────┐
                          │ Crypto  │
                          └─────────┘
                          (pure)
```

Concrete rules:
- **Crypto imports nothing from layers 2–5.**
- **Storage imports Crypto. Nothing else.**
- **Network imports Crypto. Nothing else.**
- **Core imports Crypto, Storage, Network. Not Plugins.**
- **Plugins import Storage and Network for read paths. Not Core's write actions.**
- `cli/` imports Core (for writes) and Plugins (for reads). Not Storage / Network / Crypto directly.

## Enforcement

A test under `tests/unit/architecture/test_Layer_Imports.py` walks the source tree, parses imports per file, asserts no upward imports. Runs in CI; fails the build if violated.

## "Swappable, not mockable"

The Network layer presents a clean interface (`Vault__API`-shaped). Tests use the real **in-memory transfer server** as the implementation, not a mock. The in-memory server is real Python code that satisfies the network contract without hitting the wire. This is a "swappable implementation" pattern — not a mock — and it stays consistent with the project's "no mocks, no patches" rule.

## Migration map (current → new)

| Current path | Becomes | Notes |
|---|---|---|
| `sgit_ai/crypto/Vault__Crypto.py` | `sgit_ai/crypto/` | Stays |
| `sgit_ai/secrets/*` | `sgit_ai/crypto/secrets/` (or fold into crypto) | Confirm during B12 |
| `sgit_ai/objects/Vault__Object_Store.py` | `sgit_ai/storage/` | Move |
| `sgit_ai/objects/Vault__Ref_Manager.py` | `sgit_ai/storage/` | Move |
| `sgit_ai/objects/Vault__Inspector.py` | `sgit_ai/plugins/inspect/` | Read-only → plugin |
| `sgit_ai/objects/Vault__Commit.py` | `sgit_ai/storage/` | Move |
| `sgit_ai/sync/Vault__Storage.py` | `sgit_ai/storage/` | Move (pre-existing name match) |
| `sgit_ai/sync/Vault__Branch_Manager.py` | `sgit_ai/storage/` | Move |
| `sgit_ai/sync/Vault__Key_Manager.py` | `sgit_ai/storage/` | Move |
| `sgit_ai/sync/Vault__Diff.py` | split: read parts → `plugins/`, write parts → `core/` | Inspect carefully during B13 |
| `sgit_ai/sync/Vault__Sync.py` (2,986 LOC) | dissolve: each top-level method → `core/actions/<command>/` workflow | The big one — brief B13 |
| `sgit_ai/api/*` | `sgit_ai/network/` | Move |
| `sgit_ai/transfer/*` | `sgit_ai/network/transfer/` | Move |
| `sgit_ai/pki/*` | `sgit_ai/crypto/pki/` | Move |
| `sgit_ai/cli/CLI__Vault.py` (read-only commands) | `sgit_ai/plugins/<namespace>/` | Per plugin migration |
| `sgit_ai/cli/CLI__Vault.py` (write commands) | thin wrappers calling `core/` | Stays in `cli/` |
| `sgit_ai/safe_types/`, `sgit_ai/schemas/` | stay | Cross-cutting |
| `sgit_ai/workflow/` (new from B05) | stays | Framework |

## Migration sequencing

Three briefs (per the sequencing graph in `00__index.md`):

1. **B12 — Storage extraction first.** Lowest-risk move (data-handling primitives moving as a group, no API changes).
2. **B13 — Core + Network split.** The big one. `Vault__Sync.py` dissolves into `core/actions/<command>/` workflows; `api/` + `transfer/` consolidate under `network/`. Best AFTER the workflow framework (B05/B06) so each command is already a workflow before being moved.
3. **B14 — Plugin system.** Read-only namespaces become plugins.

After all three: `Vault__Sync.py` is gone; `sgit_ai/sync/` is empty (or holds residual cross-layer plumbing).

## PKI motivation

PKI lands cleaner with the layers in place. New PKI work touches:
- **Crypto** — sign / verify primitives (already partly there in `pki/`)
- **Storage** — sign-on-write hooks for refs and objects
- **Core** — sign-on-commit step in `Workflow__Commit`; verify-on-pull step in `Workflow__Pull`
- **Network** — key-exchange endpoints

If those four layers are clean and well-separated before PKI starts, the PKI implementation is a focused set of additions — not a sprawling change touching everything. **This brief-pack does not implement PKI; it makes PKI tractable.**

## Acceptance for this design

- 5-layer model agreed.
- Dependency graph + rules agreed.
- Migration map agreed (with confirmation pass during B12 / B13).
- Import-audit enforcement strategy agreed.
- "Swappable, no mocks" reframing agreed.
- PKI prep framing agreed (motivation, not deliverable).

Briefs B12, B13, B14 implement.
