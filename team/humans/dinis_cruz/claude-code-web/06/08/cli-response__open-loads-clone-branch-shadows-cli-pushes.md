# CLI Response — SG/App `open()` Loads the Clone Branch, Silently Shadows CLI Pushes

**To:** the SG/App + sg-vault loader team
**From:** SGit-AI CLI team (Claude Code web session)
**Date:** 2026-06-08
**Re:** brief `webappopenloadsclonebranchshadowsclipushes.md` (`harp-make-6182` vault)

---

## TL;DR — verdict

**This is a Vault Web bug. The CLI is the reference implementation of the correct
behavior, and the fix cannot be made from the CLI side.**

All three fix options in the brief (reconcile-on-open, surface divergence,
discard-local-edits) are web-UI changes inside `_common/js/lib/sg-vault/sg-vault.js`.
Nothing in the Python CLI causes the silent shadowing; the CLI is the *victim*
of it (its named-branch pushes are invisible to the web view), not a cause.

That said, because the CLI uses the **identical** two-ref crypto/derivation scheme
as the web, there are two optional CLI-side actions we could take to help —
documented at the end of this brief. They are workarounds, not fixes.

---

## What we verified in the CLI

We traced the two-ref model end-to-end through this codebase to confirm the
brief's claims and identify whether the CLI shares the defect.

### 1. Same ref-derivation scheme as the web

The CLI's `Vault__Crypto.derive_branch_ref_file_id` is the direct analog of the
web's `SGVaultCrypto.deriveBranchRefFileId`:

```python
# sgit_ai/crypto/Vault__Crypto.py:77
def derive_branch_ref_file_id(self, read_key: bytes, vault_id: str,
                              branch_name: str) -> str:
    domain = f'{BRANCH_REF_DOMAIN}:{vault_id}:{branch_name}'
    return self.derive_file_id(read_key, domain)   # HMAC-SHA256(read_key, domain)[:12]
```

`BRANCH_REF_DOMAIN = 'sg-vault-v1:file-id:branch-ref'`
(`sgit_ai/crypto/Vault__Crypto.py:37`).

**Consequence:** the CLI and the web compute the **same** `ref-pid-snw-*` id
for a given `(read_key, vault_id, branch_name)`. The CLI *can* address the web's
clone ref directly if we ever choose to.

### 2. CLI clone-branch names do not collide with the web's

| Tool | clone-branch name | derived `ref-pid-snw-*` |
|---|---|---|
| Web UI | `'web-ui'` | shared by every web session of the vault |
| CLI (`sgit clone`) | `'local'` (`sgit_ai/core/Vault__Sync.py:86-87`) | one per CLI clone |

Different domain strings → different HMAC outputs → different ref ids. The two
clone branches coexist on the server without interference.

### 3. CLI `push` writes only the named ref

```
sgit_ai/workflow/push/Step__Push__Update_Remote_Ref.py:29
    workspace.sync_client.api.write(vault_id, f'bare/refs/{named_ref_id}', ref_data)
```

Confirms the brief: CLI pushes advance `ref-pid-muw-*`, never any
`ref-pid-snw-*` (clone) ref.

### 4. CLI `pull` (read-only) loads the **named** head — the correct behavior

The CLI's read-only pull step is the closest analog of the web's `open()`, and
it does precisely what the web brief recommends `open()` should do:

```
sgit_ai/workflow/pull/Step__Pull__RO__Load_Named_Head.py
  - resolves the tracked named branch via get_branch_by_name
  - re-fetches bare/refs/{named_ref_id} live from the server
  - overwrites the local ref and decrypts the new named HEAD
```

There is **no** `clone_commit_id || named_commit_id` preference. The named ref
is canonical. Working-tree load follows the named head.

---

## Comparison: web `open()` vs CLI pull/checkout

| Concern | Web (`SGVault.open`) | CLI | Evidence |
|---|---|---|---|
| Ref used for working tree | `cloneCommitId \|\| namedCommitId` — **prefers clone** ❌ | re-fetches & loads the **named** head ✅ | `Step__Pull__RO__Load_Named_Head.py` |
| What `push` advances | named ref ✅ | named ref only ✅ | `Step__Push__Update_Remote_Ref.py:29` |
| Reconcile-on-open | never calls `pull()` ❌ | RO pull *is* the named-head reload ✅ | `Workflow__Pull__ReadOnly` |
| Cross-tool ref isolation | clone branch is shared (deterministic, name = `'web-ui'`) | clone branch name = `'local'` — disjoint from web | `Vault__Sync.py:86-87` |

The CLI is essentially the reference implementation of fix option 1 in the
brief ("reconcile on open"). The web `open()` could conform by mirroring the
CLI's read-only pull flow.

---

## Cross-reference: April 2026 two-branch-model debrief

This brief is the natural follow-on to
`team/humans/dinis_cruz/claude-code-web/04/16/vault-debrief--mzrp0li8-two-branch-model.md`.

That earlier debrief established:

- The two-ref model is sound; the CLI uses it correctly.
- At the time, the web's clone ref was **ephemeral** (per browser session) —
  divergence was annoying but recoverable on session close.

The June 2026 brief documents how the situation got structurally worse:

- The web's clone ref is now **deterministic + server-side + shared** across
  every web session of the same vault.
- Combined with `open()`'s `cloneCommitId || namedCommitId` preference, this
  means **once any web-UI commit has ever happened**, every subsequent web open
  of that vault is permanently pinned to the clone branch.

The April recommendations (CAS on web `push`, pull-before-push enforcement,
"Published HEAD" vs "Local HEAD" labelling in the SGIT tab) remain unaddressed
and would compound the impact described here.

---

## Why this cannot be fixed from the CLI

The defective code path is:

```
sg-vault.js  SGVault.open()
    vault._headCommitId = cloneCommitId || namedCommitId   // ← here
    await vault._loadTreeFromCommit(vault._headCommitId)
```

No CLI change can alter what `open()` chooses to load. The web app could:

1. Call its existing `pull()` automatically when the clone head is strictly
   behind the named head (the brief's preferred fix), OR
2. Surface ahead/behind in the HUD using the already-present `getBehindCount()`
   plumbing, OR
3. Add a one-click "repoint clone ref to named head" for the diverged case.

All three are local web-UI changes. None require a server or CLI change.

---

## Optional CLI-side actions (workarounds, not fixes)

Because the CLI shares the derivation scheme, two CLI-side actions are
*possible*. Both are workarounds for the underlying web bug; neither is a fix.

### Option A — Architect interop contract (recommended if anything)

Formalize the open/reconcile semantics as a cross-tool contract document in
`team/explorer/architect/`, in the same form as the existing read-only-clone
contract. The contract would:

- Define the canonical role of the named ref for working-tree load on writable
  open.
- Cite `Step__Pull__RO__Load_Named_Head.py` as the reference implementation the
  web `open()` must conform to.
- Specify the reconcile-on-open precondition and the divergence-visible fallback.

Pure docs, zero risk, gives the web team a spec to implement against. Turns
this informal brief into a durable cross-tool agreement.

### Option B — CLI reconcile escape-hatch command

A `sgit` subcommand that, for a given vault, fast-forwards the web's clone ref
(`'ref-pid-snw-' + derive_branch_ref_file_id(read_key, vault_id, 'web-ui')`) to
the named head — the brief's "immediate workaround" implemented from the CLI.

**Mandatory safety properties:**

1. Read both refs first. Compute ahead/behind via the existing commit-walk
   machinery.
2. Fast-forward **only** when the named head is a strict descendant of the
   web clone head (i.e., the clone has no web-only commits).
3. On true divergence (clone has unpushed web commits AND named has moved),
   **refuse** with a clear message — never silently orphan web work.
4. Hard-code the `'web-ui'` branch name as a CLI ↔ web interop constant; gate
   behind an explicit `--reconcile-web` flag so it cannot happen by accident.

**Downsides:**

- Couples the CLI to the web's `'web-ui'` naming choice. If the web ever
  changes that string, the CLI breaks in lockstep.
- Solves the symptom at the wrong layer. The bug is in `open()`, not in the
  absence of a CLI reconcile command.
- Adds a code path that mutates a ref the CLI does not otherwise own.

Useful for agentic workflows that hit a stuck vault and have no UI affordance
to unstick it. Not a substitute for fixing `open()`.

---

## Recommended next step

1. **Web team:** implement fix option 1 from the original brief —
   reconcile-on-open when the clone is strictly behind the named head. Mirror
   the CLI's `Step__Pull__RO__Load_Named_Head` flow.
2. **Vault docs:** explicitly mark the named ref as the canonical
   working-tree-load source for writable opens, with the CLI cited as the
   conforming implementation.
3. **CLI side (this repo):** no production-code change required. Optional:
   land Option A (architect interop contract) so the contract is durable.

---

## Evidence index (CLI repo paths)

- `sgit_ai/crypto/Vault__Crypto.py:37` — `BRANCH_REF_DOMAIN` constant
- `sgit_ai/crypto/Vault__Crypto.py:77` — `derive_branch_ref_file_id`
- `sgit_ai/core/Vault__Sync.py:86-87` — CLI clone-branch name = `'local'`
- `sgit_ai/storage/Vault__Branch_Manager.py:57` — `ref-pid-snw-*` prefix
- `sgit_ai/safe_types/Safe_Str__Ref_Id.py:5` — ref id regex `(muw|snw)`
- `sgit_ai/workflow/push/Step__Push__Update_Remote_Ref.py:29` — push writes named ref only
- `sgit_ai/workflow/pull/Step__Pull__RO__Load_Named_Head.py` — RO pull loads named head
- `team/humans/dinis_cruz/claude-code-web/04/16/vault-debrief--mzrp0li8-two-branch-model.md`
  — April 2026 prior context
