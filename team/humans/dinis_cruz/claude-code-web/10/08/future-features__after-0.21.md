# Possible future features, after 0.21.0

*CLI team, 8 Oct 2026. The ideas from "Fix merge and undo, then claim the browser" (the git and
sgit feature comparison) and "Git security features → sgit" that are NOT in 0.21.0, with what
each would take and what it could break. 0.21.0 already ships: reflog, signed tags, short ids and
revision shorthand, `history undo`, log filters and `--stat`, `revert --as-commit`,
`commit --amend`, `push --force-with-lease`, the path-guard hardening.*

## The constraint every commit-level idea must respect

**A new field in commit objects breaks signature verification on clients from 0.19.0 on.** They
parse the commit, drop the field they do not know, rebuild the canonical bytes without it, and
the signature no longer matches: the commit shows as `bad`, and under `signatures-required` the
pull is refused. (Verified with sgit-ai 0.20.0.) So any idea that adds a commit field needs the
format gate: the vault owner raises `--min-client` first. Two fields are already in every
client's schema and are safe to fill: `attestations` (a list) and `author_signature`.

The branch index is different: unknown index fields are dropped by older clients when they
rewrite the index and restored by the next current client (how tags work). New object types
in `bare/data` are invisible to older clients.

## Ranked

| # | Idea | Value | Cost | Side effects / constraints |
|---|---|---|---|---|
| 1 | **Union merge driver for declared paths** (`.sgattributes`: `runs/*.md merge=union`, `*.jsonl merge=union`) | High: concurrent appends by agents to one log stop conflicting | Medium: decrypt base/ours/theirs, line-merge, write a new blob inside the merge | Limited to opted-in paths. Clients without it still produce today's conflict (not a wrong merge). The attributes file is itself in the vault, so it is versioned and encrypted |
| 2 | **Line-level three-way merge for all text files** (diff3) | High | Medium | Changes merge results for every text file; conflict markers inside files instead of `.conflict` copies. Ship after 1 has proven out, behind a setting at first |
| 3 | **Shared operation log**: the reflog as encrypted, append-only objects that sync | High and distinctive: team-wide undo and audit, no git equivalent | Medium–large: a new object type and its sync | New objects only; old clients ignore them. Needs a retention rule |
| 4 | **Author identity**: a display name per signing key | Medium: `log --author "Alice"` | Small if the name lives in the branch index entry (index field, safe); large if in the commit (format gate) | Put it in the index |
| 5 | **Agent provenance in `attestations`**: prompt/tool/run records, encrypted | Medium–high for agent teams | Medium | Safe: the field exists in every client's schema |
| 6 | **Conflicts as data**: commit a conflict as an object a human or another agent resolves later | High for agents that cannot stop mid-task | Large | Needs a conflict object type and every command to understand it |
| 7 | **`history grep` / pickaxe / blame** | Medium | Medium: decrypts every changed blob in the walk; cache needed | Read-only. Must say where `--depth`/`--path` truncates the walk |
| 8 | **Branch merge / delete / rename, cherry-pick** | Medium | Low–medium | Merge any branch reuses the three-way merge; delete needs the index tombstone pattern tags use |
| 9 | **Stable change ids** | Medium | Medium | A commit field: format gate (see the constraint above) |
| 10 | **Resumable push** | Medium | Medium | Verify today's behaviour first (large files already chunk) |
| 11 | **Format 2 (128-bit ids) by default for new vaults** | Security default | One line in `init` | Clients ≤ 0.18 cannot read such a vault and call it corrupt. Do it once 0.19+ is the norm |
| 12 | **Per-folder keys** | Distinctive: scoped clone becomes an access boundary | Large: key hierarchy, rekey, scope semantics | Crypto design work; an architect review first |
| 13 | **Bisect, local hooks, aliases** | Low | Low each | Hooks only local, never read from vault content |
| 14 | **`history restore`** as the name for today's file-level `history revert`, so `revert` can mean git's inverse commit | Clarity for git users | Low | Renaming breaks agents' scripts: add `restore`, keep `revert` working with a one-line note, decide later |

## Out of scope by design

- **Server-side enforcement, per-writer authorisation, push certificates**: need the server to
  know writers (per-writer write keys or server-verified signed writes). An SG/Send API design
  question.
- **Server-side search, forge-style review, CI status**: need a host that reads content.
- **`format-patch` / `am`**: plaintext patches by email defeat the encryption.
- **Partial staging**: refused by design (whole-file commits).
- **Prune / gc**: only a key-holding client can compute reachability, and deleting objects other
  clones still reference conflicts with rewind detection. Needs a design of its own.

## Suggested order

1 (union driver) → 4 (names in the index) → 3 (shared oplog, building on the reflog) → 5
(provenance) → 2 (full line merge). Each is useful alone, none needs the format gate, and 1–3 are
the ones the comparison note identifies as both valuable to agent teams and ahead of git.
