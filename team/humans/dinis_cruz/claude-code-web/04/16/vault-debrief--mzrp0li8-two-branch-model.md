# Debrief: Vault `mzrp0li8` — Two-Branch Model in the Wild

**Date:** 16 April 2026
**From:** SGit/CLI team
**To:** SG/Send Explorer (Vault) team
**Vault:** `mzrp0li8` (key: `j4pyy0lhny8jx7osqn4lclhq:mzrp0li8`)
**Context:** Perplexity agent + web UI both accessing the same vault

---

## What We Were Looking At

A user ran a Perplexity agent against the vault and then compared what the CLI saw
vs what the web vault showed. The CLI and web appeared to show different files and
different history. This is what we found.

---

## The Actual Commit Graph

Reconstructed from CLI `sgit log --graph` + web SGIT history tab:

```
660af8b10130  init
│
42b41e1feb46  "Commit: 1 added" — Perplexity adds hello.txt
│             ← named ref pointed here when web UI opened
│
├── b07c84b690bd  "Commit: 1 added" — Perplexity adds second.txt, PUSHES
│                 ← named ref advanced here (CLI clone captured this)
│                 ← CLI clone HEAD at time of clone
│
└── 65a828f25e43  "Edit hello.txt" — web UI edits (parent = 42b41e1feb46)
     │            ← web UI was already open, still working from old named HEAD
     │
     └── f6fa9ee85d68  "Add PXL_20260415_204618566.jpg" — web UI adds image
                       ← what web UI SGIT tab shows as HEAD
```

The graph forked at `42b41e1feb46`. Both sides added different files. Neither
conflicted on the same file.

---

## Why `sgit pull` Said "Already Up to Date"

The CLI `sgit pull` reads the **named ref** (`ref-pid-muw-*`) from the server:

```
Remote HEAD: obj-cas-imm-b07c84b690bd
Local HEAD:  obj-cas-imm-b07c84b690bd
→ Already up to date.
```

This is **correct**. The named ref is `b07c84b690bd`. The CLI cloned from `b07c84b690bd`.
There is nothing to pull.

The web SGIT tab shows `f6fa9ee85d68` as HEAD — but this is the web session's
**clone HEAD** (`ref-pid-snw-*`), not the named HEAD. These are two different refs.

The web UI's two commits (`65a828f25e43`, `f6fa9ee85d68`) were committed to the
web session's clone branch but **never pushed to the named ref**. The vault was
opened **Read-only** (no write key), so `push()` was never called.

```
named ref   (ref-pid-muw-*)  →  b07c84b690bd  ← what CLI reads, what is shared
web clone   (ref-pid-snw-*)  →  f6fa9ee85d68  ← local to that browser session only
```

When the browser session closes, those two web commits become unreachable. The
blobs (`65a828f25e43`, `f6fa9ee85d68`, and all their tree/file objects) remain on
the server permanently (immutable blobs), but no ref points to them.

---

## Summary of Vault State Right Now

| | State |
|---|---|
| Named branch (canonical) | `b07c84b690bd` — hello.txt + second.txt |
| Web session clone (ephemeral) | `f6fa9ee85d68` — hello.txt (edited) + PXL jpg |
| CLI local clone | `b07c84b690bd` — correctly in sync with named branch |

The vault is **consistent** from a protocol perspective. The CLI is not broken.
The web is showing local (unpushed) work.

---

## The Root Issue: Pull Before Push

The situation that created this fork was:

1. Web UI **opened the vault** → read named HEAD = `42b41e1feb46`
2. Perplexity agent **pushed** `b07c84b690bd` → named ref = `b07c84b690bd`
3. Web UI **did not refresh** → still working from `42b41e1feb46`
4. Web UI committed on top of `42b41e1feb46`, creating a diverged fork

The correct flow for any agent or client before making changes is:

```
sgit pull           ← sync with current named branch first
# ... make changes
sgit push           ← now push from an up-to-date base
```

This is the same rule as git: **always pull before you push**.

For the Perplexity agent specifically: the agent should call `sgit pull` (or the
equivalent API call) at the start of every session before making any commits.
This ensures the agent is working from the current named branch state, not a
snapshot from when it first opened the vault.

### What the CLI enforces today

The Python CLI `push()` uses a `write-if-match` CAS header:

```
PUT /bare/refs/{refFileId}
If-Match: {current_known_commit_id}
```

If another client has pushed since this client last synced, the server returns
`412 Precondition Failed`. The CLI then knows to pull before retrying.

This means if Perplexity's agent had been working from a stale named HEAD and
another client had already pushed, the CLI push would have **rejected**, not
silently overwritten. The user would have been prompted to pull first.

### What the web UI does not enforce yet

The web UI `push()` is an **unconditional PUT** — no `If-Match` check. This means
two web sessions pushing simultaneously can silently overwrite each other. This is
documented in our review (Finding 1, CRITICAL) and is the most important fix
needed on the web UI side.

---

## What Needs to Happen to Recover the Web Edits

The web edits (`65a828f25e43` and `f6fa9ee85d68`) contain:
- `hello.txt` edited with "Edited by DC on the vault web"
- `PXL_20260415_204618566.jpg` (1.1 MB image)

To bring these into the named branch:

1. Open the vault in the web UI **with the full vault key** (not read-only)
2. The web will see its clone HEAD (`f6fa9ee85d68`) as ahead of the named HEAD
3. Click **Push** → named ref advances to `f6fa9ee85d68`

Then from the CLI:
```
sgit pull
```
This will detect that the named ref has moved from `b07c84b690bd` to `f6fa9ee85d68`.

The LCA of the two diverged commits is `42b41e1feb46`:

```
base (42b41e1feb46):  hello.txt
ours (b07c84b690bd):  hello.txt + second.txt
theirs (f6fa9ee85d68): hello.txt (edited) + PXL jpg
```

No file was modified by both sides. The three-way merge produces a clean result:
- `hello.txt` — edited version (only web modified it)
- `second.txt` — kept (only Perplexity added it)
- `PXL_20260415_204618566.jpg` — kept (only web added it)

The CLI's three-way merge handles this automatically. No conflicts.

---

## Recommendations for the Vault Team

### P0 — Add `If-Match` CAS to web UI `push()`

```javascript
// In sg-vault-ref-manager.js writeRef():
const headers = { 'x-sgraph-vault-write-key': this._writeKey }
if (expectedCurrentId) headers['If-Match'] = expectedCurrentId

// In sg-vault.js push():
await this._refManager.writeRef(
    this._refFileId,
    this._headCommitId,
    this._namedHeadId   // ← current known named HEAD as expected value
)
// On 412: surface "Someone else pushed — pull first" to the user
```

Without this, concurrent web sessions silently overwrite each other.

### P1 — Enforce pull-before-push in the web UI

Before showing the Push button as active:
1. Call `getBehindCount()`
2. If behind > 0: disable Push, show "Pull required first" 
3. If behind == 0: Push is safe

This is a UI-layer defence. The CAS (P0) is the server-layer defence. Both are needed.

### P2 — Agent documentation: always pull first

For the Perplexity agent and any future AI agent using the vault:

```
# Correct agent workflow:
sgit pull           ← always sync before starting work
# ... add/edit/delete files
sgit push           ← publish
```

The agent currently opens the vault and starts working immediately without checking
if the named branch has advanced. Adding `sgit pull` as the first operation removes
the stale-snapshot risk entirely.

---

## What the SGIT Tab in the Web UI Should Show

This is a UX clarification point for the Vault team.

Currently the web SGIT tab shows the **clone HEAD** as "HEAD". This is technically
correct (it is the HEAD of the current working session) but can confuse users who
expect to see the published named branch state.

Suggested improvement:
- Label the named HEAD commit clearly as **"Published HEAD"** or **"Remote HEAD"**
- Label the clone HEAD (if ahead) as **"Local HEAD (unpushed)"**
- Show a push prompt when clone HEAD is ahead of named HEAD

This would make the two-branch model visible to users rather than hidden.

---

*All `obj-cas-imm-*` objects from both sides of the fork remain on the server.*
*Nothing is lost. The situation is fully recoverable.*
