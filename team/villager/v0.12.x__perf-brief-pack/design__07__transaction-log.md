# Design — Transaction Log

**Status:** Architecture decision captured. Default OFF; opt-in via config / flag / env / debug mode.
**Owners:** Architect (schema), Dev (implementation hook in workflow framework — B05 small extension).

## The principle

> Every state-changing workflow can emit an append-only transaction
> record summarising what happened. The log is OFF by default to avoid
> surprise disk growth and operation overhead. It's trivially turned
> on for users / agents who want the audit trail.

## Why a transaction log distinct from workflow workspaces

| | Workflow workspace | Transaction log |
|---|---|---|
| Lifetime | Per execution; cleaned up on success by default | Persistent, append-only |
| Granularity | Every step's input + output JSON | One summary record per workflow run |
| Audience | Debugger / replay tooling for THIS run | Audit, monitoring, post-hoc analysis across MANY runs |
| Default state | Always created (ephemeral) | OFF |

The transaction log is the *aggregated, persistent* form of what the
workflow workspace already captures per-run. Implementation-wise:
the workflow runner emits one record at workflow completion — the log
is that stream of records.

## Record schema

```python
class Schema__Transaction_Record(Type_Safe):
    record_version  : Safe_Str__Semver       # for forward compat ("1.0.0")
    workflow_name   : Safe_Str__Workflow_Name
    workflow_version: Safe_Str__Semver
    work_id         : Safe_Str__Work_Id
    started_at      : Safe_Str__ISO_Timestamp
    completed_at    : Safe_Str__ISO_Timestamp
    duration_ms     : Safe_UInt
    status          : Enum__Workflow_Status   # success / failed / aborted
    vault_id        : Safe_Str__Vault_Id      = None
    branch_name     : Safe_Str__Branch_Name   = None
    parent_commit   : Safe_Str__Commit_Id     = None
    new_commit      : Safe_Str__Commit_Id     = None
    steps_summary   : list[Schema__Step_Summary]   # one entry per step
    error           : Safe_Str__Error_Message      = None  # if status != success
```

```python
class Schema__Step_Summary(Type_Safe):
    name        : Safe_Str__Step_Name
    status      : Enum__Step_Status
    duration_ms : Safe_UInt
    bytes_in    : Safe_UInt = None
    bytes_out   : Safe_UInt = None
```

The schema is intentionally **summary-level**. Full step inputs/outputs
stay in the workflow workspace (if `--keep-work`); the transaction log
stores only what's useful for post-hoc analysis without bloating disk.

Round-trip invariant test required, per project rule.

## On-disk location

```
.sg_vault/local/transactions/
├── transactions__2026-05.log          (current month's records, JSONL)
├── transactions__2026-04.log
└── ...
```

- **Append-only** — each line is one `Schema__Transaction_Record` JSON.
- **Monthly rotation** — easy to garbage-collect by file rather than by-line scan.
- **Default retention** — keep last 3 months. Older files deleted on rotation.
- **Configurable** — retention months + max total size as config knobs.

## Three modes

| Mode | Behaviour | When chosen |
|---|---|---|
| `off` (default) | Records emitted in-memory but not written. Workflow framework knows about transaction logging but the disk path is a no-op. | Normal flow |
| `writes` | State-changing workflows (Clone, Push, Pull, Fetch, Commit, Rekey, Init, Create, Delete-on-Remote) write records. Read-only workflows / fast plugins don't. | Opt-in via config: `transaction_log: writes` |
| `all` | Every workflow + every Plugin invocation that touches state writes a record. | Opt-in via config: `transaction_log: all`, OR per-command `--trace`, OR `SGIT_TRACE=1` env, OR `sgit dev workflow trace <command>` |

The runtime config check happens once per workflow invocation; cost is negligible.

## Activation

In priority order:
1. `--trace` flag on a single command → `all` for that invocation.
2. `SGIT_TRACE=1` env var → `all` for the process.
3. `transaction_log: <mode>` in `.sg_vault/local/config.json` → persistent.
4. Default: `off`.

`sgit_config` (top-level user config, not vault-specific) can also set the mode globally.

## Privacy

- Records contain operation **metadata**: timestamps, vault-ids, commit-ids, branch names, byte counts.
- Records do NOT contain plaintext file contents, file names, file paths, or key material.
- File and directory names mentioned in commit metadata stay encrypted (only the encrypted name shows).
- The log lives in `.sg_vault/local/`, same trust boundary as `vault_key`. Per AppSec F07: filesystem-mode hygiene applies (`chmod 0600`).

When `transaction_log: all` is enabled, even read-only access patterns become observable on disk. Document in user-facing docs as "verbose mode reveals what you accessed when, locally — useful for debugging, sensitive in shared environments".

## Concurrency

Single process: records emitted in workflow runner; serialised by the runner.

Multiple concurrent `sgit` invocations on the same vault: possible but rare. Mitigation:
- **One file per process** — append to `transactions__2026-05__<pid>.log`. Rotation merges per-pid files monthly.
- **OR file-locking** — `fcntl.flock` for the append. Simpler but blocks briefly if many concurrent writers.

Pick during B05 implementation. Per-pid is simpler and avoids any lock contention; merge cost on rotation is negligible.

## Schema versioning

`record_version` field is mandatory and explicit. Reading mixed-version logs:
- Records with version ≤ current → load directly.
- Records with version > current → log + skip (forward compatibility for older binaries reading newer logs).
- Records with unknown version → log + skip.

Major version bumps are coordinated with a `vault migrate` step (per brief B10).

## CLI surface

Lives under `sgit dev workflow <…>` (per design D2 / D4):

```
sgit dev workflow log [--since <duration>]      # show recent transaction records
sgit dev workflow log --vault PATH              # for a specific vault
sgit dev workflow log --filter <workflow-name>  # filter
sgit dev workflow stats                         # aggregate: count, avg duration per workflow
```

These commands read the transaction log, even when logging is `off` for new writes — they just won't see new records.

## Acceptance for this design

- Three modes (`off` / `writes` / `all`) agreed; default `off`.
- Schema (Type_Safe, versioned) agreed.
- On-disk location + monthly rotation + 3-month retention agreed.
- Privacy boundary agreed (no plaintext, metadata only, `chmod 0600`).
- Activation precedence agreed.
- Concurrency strategy decided during B05.

Brief B05 (workflow framework) gets a small additive requirement to emit records via a hook; this design is consumed there.
