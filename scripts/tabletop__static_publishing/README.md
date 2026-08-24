# Tabletop lab — static publishing via a single GitHub repo

Runnable companions to
`team/explorer/dev/impl-plans/08/17/static-publishing/10__tabletop__github-pages-one-repo.md`.

| Script | Role | Real / simulated |
|---|---|---|
| `run_server.py` | in-memory SG/Send server (Python ≥3.12, `sgraph-ai-app-send`) | real server |
| `reader_clone.py` | read-only static clone from any GET base URL | real (`Vault__Sync.clone_read_only` + static transport) |

Retired stand-ins — replaced by shipped commands (the retirement each was
named for in the pack's acceptance criteria):

| Was | Replaced by |
|---|---|
| `simulate_publish.py` | `sgit publish` (P2 — `Vault__Publish`) |
| `attach_simulated.py` | `sgit vault attach` (P9 — `Vault__Attach`) |
| `ci_publish_readkey.py` | `sgit vault attach --read-key … && sgit publish` — publish from a read-only clone is a shipped, tested path |
