# Tabletop lab — static publishing via a single GitHub repo

Runnable companions to
`team/explorer/dev/impl-plans/08/17/static-publishing/10__tabletop__github-pages-one-repo.md`.

| Script | Role | Real / simulated |
|---|---|---|
| `run_server.py` | in-memory SG/Send server (Python ≥3.12, `sgraph-ai-app-send`) | real server |
| `simulate_publish.py` | stand-in for `sgit publish` (P2) — assembles `.sg_vault/publish/` per spec `07` §2 | folder assembly simulated; key derivation, ref decrypt, commit parent-walk are real sgit crypto |
| `reader_clone.py` | read-only static clone from any GET base URL | real (`Vault__Sync.clone_read_only` + spike transport) |
| `ci_publish_readkey.py` | proves publish needs only the read key, recovered from the committed `sgit_public_read_*` filename | real crypto |

`simulate_publish.py` is, in effect, the first draft of P2's `Vault__Publish`.
