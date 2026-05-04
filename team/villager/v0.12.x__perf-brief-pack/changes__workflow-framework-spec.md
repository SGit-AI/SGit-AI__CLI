# Architect Freeze — Workflow Framework Spec (B05)

**Produced by:** Explorer Architect (B05 closeout)
**Status:** Frozen — implementation complete, reviewed, merged to dev
**Implemented in:** `sgit_ai/workflow/`, `sgit_ai/schemas/workflow/`
**Verified by:** All unit + integration tests passing; B06 (`Workflow__Clone`) validates consumability

---

## 1. Base class APIs

### `Step` (`sgit_ai/workflow/Step.py`)

```python
class Step(Type_Safe):
    name          : Safe_Str__Step_Name = None
    input_schema  : type = None    # Type_Safe subclass (class, not instance)
    output_schema : type = None    # Type_Safe subclass (class, not instance)

    def execute(self, input: Type_Safe, workspace: Workflow__Workspace) -> Type_Safe: ...
    def is_done(self, workspace: Workflow__Workspace) -> bool: ...
    def validate_input(self, input: Type_Safe) -> None: ...   # default: pass
    def validate_output(self, output: Type_Safe) -> None: ...  # default: pass
    def step_name(self) -> str: ...
```

Subclasses implement `execute()`. `is_done()` delegates to `workspace.has_output_for(self)` — no override needed.

### `Workflow` (`sgit_ai/workflow/Workflow.py`)

```python
class Workflow(Type_Safe):
    name    : Safe_Str__Workflow_Name = None
    version : Safe_Str__Semver        = None
    steps   = None   # plain class attr (list[type[Step]]); no annotation — Type_Safe rejects mutable list

    def workflow_name() -> str: ...
    def workflow_version() -> str: ...     # default '1.0.0'
    def step_classes() -> list: ...        # returns self.steps or []
    def execute(input, workspace) -> dict: ...
```

**Key decision:** `steps` is a plain class attribute (no type annotation). Type_Safe rejects `list` as a mutable default; `list[Step]` is also rejected. Subclasses set it as a class-level list literal.

### `Workflow__Workspace` (`sgit_ai/workflow/Workflow__Workspace.py`)

```python
class Workflow__Workspace(Type_Safe):
    work_id       : Safe_Str__Work_Id
    workspace_dir : Safe_Str__File_Path

    @classmethod
    def create(cls, workflow_name, base_dir, work_dir_base=None) -> Workflow__Workspace: ...
    @classmethod
    def load(cls, workspace_dir) -> Workflow__Workspace: ...

    def has_output_for(self, step) -> bool: ...
    def persist_output(self, step, output, index=0) -> None: ...
    def load_output_schema_for(self, step) -> Type_Safe | None: ...
    def read_output_for(self, step) -> dict: ...
    def final_output(self) -> dict: ...
    def write_manifest(self, manifest_data) -> None: ...
    def read_manifest(self) -> dict: ...
    def cleanup(self) -> None: ...
```

### `Workflow__Runner` (`sgit_ai/workflow/Workflow__Runner.py`)

```python
class Workflow__Runner(Type_Safe):
    workflow   : Workflow
    workspace  : Workflow__Workspace
    keep_work  : bool = False
    log_mode   : Enum__Transaction_Log_Mode = OFF

    def run(self, input: Type_Safe = None) -> dict: ...
```

`run()` chains step outputs: each step's output becomes the next step's input. On success and `keep_work=False`, `workspace.cleanup()` is called. On failure, workspace is preserved for inspection.

---

## 2. Workspace filename convention

Workspace directories are created under a `base_dir` passed to `Workflow__Workspace.create()`. Callers choose the base dir (typically `tempfile.mkdtemp()`).

**Directory name format:** `{workflow_name}-{YYYYMMDD_HHMMSS}-{work_id_8hex}`

Example: `clone-20260504_142301-a3f9c72b`

**Step output filename format:** `{index:02d}__{step_name}.json`

Example: `01__derive-keys.json`, `05__walk-commits.json`

**Manifest filename:** `workflow.json` at the workspace root.

---

## 3. Workspace lifetime

- **Default:** clean on success (`keep_work=False`). Workspace directory is `shutil.rmtree`'d after a successful run.
- **On failure:** workspace is preserved at `workspace_dir` for inspection; `RuntimeError` is raised with the error message.
- **Override:** set `Workflow__Runner(keep_work=True)` to preserve on success (used for debugging and integration tests).
- **Resume:** `Workflow__Runner.run()` checks each step's output file via `is_done()`; already-complete steps are skipped and their output reloaded. Cross-major-version resume is refused with a clear error.

---

## 4. Granularity policy

- **Target:** 5–15 steps per command. `Workflow__Clone` uses 10 steps.
- **Step boundary criteria:** a step boundary is appropriate when the work at that point is independently checkpointable, IO-distinct (network vs disk), or represents a meaningful resumable unit.
- **Single shared state schema:** `Workflow__Clone` uses one accumulating `Schema__Clone__State` for all 10 steps rather than per-step input/output schemas. This simplifies resume (one JSON file per step, same shape) and avoids schema explosion.

---

## 5. Step-output schema versioning

- `Workflow` declares `version : Safe_Str__Semver` (default `'1.0.0'`).
- The runner compares major version on resume: if existing workspace was written by a different major version, the run is refused with a descriptive `RuntimeError`.
- Minor/patch bumps: resumable (runner proceeds; schema must be backward-compatible).
- Format: semver string `MAJOR.MINOR.PATCH`.

---

## 6. Shared step library policy

- **No shared cross-workflow steps in B05/B06.** Each workflow owns its step classes under `sgit_ai/workflow/<workflow-name>/`.
- **Future:** if pull/fetch reuse walk_commits or walk_trees patterns, extract to `sgit_ai/workflow/shared/` at that point (brief B15).
- Step classes are not registered globally; `Workflow.step_classes()` returns the list declared on the class.

---

## 7. Atomic-write protocol

All file writes go through `Workflow__Workspace._atomic_write(path, content)`:

1. `tempfile.mkstemp(dir=os.path.dirname(path), prefix='.tmp-')` — temp file in same directory (same filesystem, guarantees rename atomicity).
2. Write `content` to the temp file.
3. `os.rename(tmp_path, path)` — atomic on POSIX.

Applies to: step output files, `workflow.json` manifest. Does NOT apply to bare-vault object files written by clone steps (those use direct `open('wb')` since object content is content-addressed and immutable once written).

---

## 8. Transaction log

- Controlled by `Workflow__Runner(log_mode=Enum__Transaction_Log_Mode.OFF)`.
- Default is `OFF` everywhere until B14 (plugin/config) wires the activation flag.
- When enabled, appends one JSONL `Schema__Transaction_Record` line to `.sg_vault/local/transactions/transactions__{YYYY-MM}__{pid}.log`, walking up from the workspace dir to find the vault root.
- Schema: `sgit_ai/schemas/workflow/Schema__Transaction_Record.py`.

---

## 9. Implementation notes / deviations from B05 brief

| Item | Brief said | Actual |
|---|---|---|
| Per-step schemas | Separate `Schema__Step__Clone__N__Input/Output` | Single `Schema__Clone__State` accumulates all fields — simpler, fewer files |
| `Workflow__Manifest` schema | Separate `Schema__Workflow__Manifest` class | Manifest is a plain `dict` written by the runner; no separate schema class needed |
| `gather_input_for` | Described in brief | Implemented; also added `load_output_schema_for` for resume path |
| `steps: list[type[Step]]` annotation | Brief suggested typed annotation | Must be plain `steps = None` — Type_Safe rejects `list` as mutable default |

All deviations are conservative simplifications, not capability losses. Escalation: none required.
