# SGit-AI CLI — Sprint Overview: Week of Apr 20 – May 1, 2026

**Version range:** v0.10.30 branch sprint  
**Scope:** Performance, new vault lifecycle commands, agent-friendly API, pull UX, crypto correctness

---

## Summary

This sprint delivered seven distinct capability clusters across the sgit-ai CLI and its underlying crypto architecture. The work falls into three themes:

### Theme 1: Vault Lifecycle Commands
New commands that let agents and users manage vaults from the outside without full clones. `sgit probe` identifies token types in two API calls. `sgit delete-on-remote` destroys a vault on the server while preserving the local clone. `sgit rekey` rotates the encryption key by re-encrypting from plaintext-on-disk. The combination lets an agent safely rotate a compromised vault in ~3 commands.

### Theme 2: Performance (Pull + Graph-Walk)
Pull went from a 146-second silent wait to a sub-10-second interactive operation for a 55-file vault. The root cause was 1019 individual HTTP requests for tree objects. The fix introduced BFS-wave batch downloading (the same pattern already used by clone). Separately, a fundamental crypto design issue — non-deterministic AES-GCM IVs causing every commit to create entirely new tree objects — was resolved with HMAC-derived IVs. This makes pull fast AND shrinks server storage for long-lived vaults.

### Theme 3: Agent-Friendly API (Surgical Editing + Sparse Clone)
`sgit write` allows an agent to write a single file to a vault HEAD without scanning the entire working directory. `sgit cat --id / --json` and `sgit ls --ids / --json` add machine-readable output to inspection commands. Sparse clone lets agents load vault structure instantly without downloading any blob content, then `sgit cat` or `sgit fetch` individual files on demand.

---

## Feature Index

| # | Feature | Date | Commits |
|---|---------|------|---------|
| 1 | Sparse clone + on-demand fetch | Apr 20 | `bc10167`, `543aa6d` |
| 2 | sgit reset improvements + vault root discovery | Apr 20–22 | `136b41f`, `1fff8d7` |
| 3 | Resumable push with blob checkpointing | Apr 24 | `ca50dfd` |
| 4 | Surgical vault editing (sgit write, cat/ls extensions) | Apr 27 | `7c5d2f7` |
| 5 | sgit probe, delete-on-remote, rekey | Apr 28 | `f8d75fa`, `cd07b76`, `5ddd54d`, `143a79e` |
| 6 | Pull UX overhaul + BFS batch tree download | Apr 30 | `35ad09a`, `0c29c72`, `1d88371` |
| 7 | Deterministic HMAC IV — tree CAS deduplication | May 1 | `4d53f79` |

---

## Test Coverage

Every feature shipped with unit tests. Coverage highlights:
- Sparse clone: 8 new tests covering `ls`, `fetch`, `cat`, sparse status
- Probe: 11 tests (vault token, share token, invalid, non-simple-token guard)
- Delete-on-remote: 7 tests with in-memory API stub
- Rekey: 6 core + 6 corner-case tests (binary files, subdirs, double-rekey, post-rekey push)
- Pull BFS: verified via existing integration path; timing validated in real vault
- HMAC IV: 3 determinism assertions (same-map → same-ID, round-trip, different-maps → different-IDs)

Running total: **2104 unit tests passing** as of May 1, 2026.
