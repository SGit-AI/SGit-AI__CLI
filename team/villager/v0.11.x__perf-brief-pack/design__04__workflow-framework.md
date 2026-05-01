# Design — Workflow / Step-Graph Framework

**Status:** Architecture decision captured. Open: granularity, workspace lifetime.
**Owners:** **Explorer Architect** (framework design), Villager Dev (apply to clone per B06).

## The principle

> Every key sgit command (clone, push, pull, fetch) is a sequence of small,
> idempotent, individually inspectable steps. Each step's input and output is
> a Type_Safe schema. Each step's output is persisted to `.sg_vault/work/`.
> Steps can be inspected, executed individually, resumed.

This turns sgit from "magic command with progress bar" into "transparent
state machine that explains itself."

## Why

- **Resumability** — failed clones / pushes pick up where they stopped.
- **Observability** — every step's I/O is on disk, inspectable.
- **Testability** — each step is unit-testable in isolation against a stored input.
- **Debuggability** — when step 7 fails, you have step 6's output.
- **Documentation** — step definitions ARE the documentation.
- **Composability** — `sgit dev workflow run clone:walk_trees` is a real thing.

## Core types

```python
class Step(Type_Safe):
    """Base class. Each step is a Type_Safe class with declared input/output schemas."""
    name           : Safe_Str__Step_Name
    input_schema   : type[Type_Safe]
    output_schema  : type[Type_Safe]

    def execute(self, input: Type_Safe, workspace: Workflow__Workspace) -> Type_Safe:
        """Run the step. Returns an instance of output_schema."""
        raise NotImplementedError

    def is_done(self, workspace: Workflow__Workspace) -> bool:
        """Check whether this step has already produced its output."""
        return workspace.has_output_for(self)

class Workflow(Type_Safe):
    """Base class. Each workflow is a Type_Safe class with an ordered list of step classes."""
    name  : Safe_Str__Workflow_Name
    steps : list[type[Step]]

    def execute(self, input: Type_Safe, workspace: Workflow__Workspace) -> Type_Safe:
        for step_class in self.steps:
            step = step_class()
            if step.is_done(workspace):
                continue
            step_input  = workspace.gather_input_for(step)
            step_output = step.execute(step_input, workspace)
            workspace.persist_output(step, step_output)
        return workspace.final_output()
```

```python
class Workflow__Workspace(Type_Safe):
    """A single execution workspace. Lives at .sg_vault/work/<workflow-name>-<work-id>/."""
    workflow_name : Safe_Str__Workflow_Name
    work_id       : Safe_Str__Work_Id          # uuid4
    workspace_dir : Safe_Str__File_Path
    started_at    : Safe_Str__ISO_Timestamp
    workflow_version : Safe_Str__Semver        # tag for cross-version safety

    def has_output_for(self, step: Step) -> bool: ...
    def gather_input_for(self, step: Step) -> Type_Safe: ...
    def persist_output(self, step: Step, output: Type_Safe) -> None: ...
    def final_output(self) -> Type_Safe: ...
```

## Step schemas — naming convention

Each step gets two schema classes:

```python
class Schema__Step__Clone__Walk_Trees__Input(Type_Safe):
    vault_id     : Safe_Str__Vault_Id
    read_key     : Safe_Bytes__Read_Key
    root_tree_ids: list[Safe_Str__Tree_Id]

class Schema__Step__Clone__Walk_Trees__Output(Type_Safe):
    visited_tree_ids : list[Safe_Str__Tree_Id]
    bytes_downloaded : Safe_UInt
    duration_ms      : Safe_UInt

class Step__Clone__Walk_Trees(Step):
    name          = 'walk_trees'
    input_schema  = Schema__Step__Clone__Walk_Trees__Input
    output_schema = Schema__Step__Clone__Walk_Trees__Output

    def execute(self, input, workspace):
        ...
```

## `.sg_vault/work/` layout

New top-level directory inside `.sg_vault/`, alongside `bare/` and `local/`:

```
.sg_vault/
├── bare/                        existing — encrypted object store
├── local/                       existing — clone_mode.json, vault_key, etc.
└── work/                        NEW — workflow workspaces
    └── clone-2026-05-01T12-34-56-uuid/
        ├── workflow.json        Schema__Workflow__Manifest (steps, status, timings)
        ├── 01__derive-keys.json
        ├── 02__check-directory.json
        ├── 03__download-index.json
        ├── 04__download-branch-meta.json
        ├── 05__walk-commits.json
        ├── 06__walk-trees.json
        ├── 07__download-blobs.json
        ├── 08__create-clone-branch.json
        ├── 09__extract-working-copy.json
        └── 10__setup-local-config.json
```

Properties:
- **One workspace per invocation** — uuid'd directory; concurrent / interrupted runs don't collide.
- **Atomic writes** — each step's output written via `write-temp + os.rename`. Crash-safe.
- **Workflow manifest** — `workflow.json` summarises the run; updated after each step. Used by `sgit dev workflow inspect <work-id>`.
- **Cleanup policy** — see "Workspace lifetime" below.

## Workspace lifetime

Open question (Dinis to confirm). Three options:

| Option | Behaviour |
|---|---|
| **Clean up on success** (default) | Workspace deleted when the workflow completes successfully. Stays on disk if it fails. Minimal disk footprint. |
| **Keep by default** | Workspace stays. User can `sgit dev workflow gc` to clean. Maximum debuggability. |
| **Hybrid** | Clean on success unless `--keep-work` flag was passed. |

Recommendation: **hybrid** (clean-on-success default, opt-in keep). Best of both for normal use vs debugging.

## Versioning

Each `workflow.json` carries the `workflow_version` field (semver of the workflow definition). On `resume`, the runner refuses to resume across versions:

> `sgit dev workflow resume <work-id>` — workspace was created with workflow version 1.2.0; current version is 2.0.0. Refusing to resume; please re-run from scratch (this workspace is preserved at <path> for inspection).

## Granularity

Open question (Dinis to confirm). Sketch for clone (10 steps, my preference):

| # | Step | Input | Output |
|---|---|---|---|
| 1 | derive_keys | vault_key | vault_id, read_key, write_key, branch_index_file_id |
| 2 | check_directory | directory | directory_status (empty / ok / error) |
| 3 | download_index | vault_id, branch_index_file_id | branch_index |
| 4 | download_branch_meta | branch_index | branch_metadata |
| 5 | walk_commits | head_ref_id | commit_ids[], root_tree_ids[] |
| 6 | walk_trees | root_tree_ids | visited_tree_ids[], bytes_downloaded |
| 7 | download_blobs | head_tree_id | blob_count, bytes_downloaded |
| 8 | create_clone_branch | branch_metadata | clone_branch |
| 9 | extract_working_copy | head_tree_id, blobs | files_written, bytes_written |
| 10 | setup_local_config | clone_state | local_config |

Push and pull will share many of these (download_blobs, walk_trees etc.). The framework supports a **shared library of `Step__*` classes** that workflows compose. Per-workflow private steps allowed when needed.

## CLI surface

Per `design__02__cli-command-surface.md`, lives at `sgit dev workflow <…>`:

```
sgit dev workflow list                       known workflows
sgit dev workflow show <command>             list steps + their input/output schemas
sgit dev workflow run <command> [--step <n>] run a step (or all)
sgit dev workflow resume <work-id>           resume an interrupted workflow
sgit dev workflow inspect <work-id>          show step state + timings
sgit dev workflow trace <command>            run with verbose per-step output
sgit dev workflow gc [--older-than <dur>]    clean up old workspaces
```

## What this design leaves to other docs

- The pack-download flow inside `walk_trees` and `download_blobs` (after pack format ships): `design__05__clone-pack-format.md`.
- The CLI integration / context visibility for `dev workflow <…>`: `design__02 / design__03`.
- The actual step list per command: each application brief (B06 for clone, B11 for push/pull/fetch).

## Acceptance for this design

- Step / Workflow / Workspace types agreed.
- `.sg_vault/work/` layout agreed.
- Workspace lifetime resolved.
- Granularity preference resolved.
- Shared step library principle agreed.

Brief B05 implements the framework; brief B06 applies it to clone.
