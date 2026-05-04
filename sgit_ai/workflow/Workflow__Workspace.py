"""Workflow__Workspace — on-disk state for a single workflow execution."""
import json
import os
import tempfile
import uuid

from osbot_utils.type_safe.Type_Safe           import Type_Safe
from sgit_ai.safe_types.Safe_Str__Workflow_Name import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Work_Id       import Safe_Str__Work_Id
from sgit_ai.safe_types.Safe_Str__File_Path     import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Semver        import Safe_Str__Semver


class Workflow__Workspace(Type_Safe):
    """Manages the on-disk workspace for one workflow run."""

    workflow_name    : Safe_Str__Workflow_Name
    work_id          : Safe_Str__Work_Id
    workspace_dir    : Safe_Str__File_Path
    started_at       : Safe_Str__ISO_Timestamp = None
    workflow_version : Safe_Str__Semver        = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, workflow_name: str, base_dir: str,
               workflow_version: str = '1.0.0') -> 'Workflow__Workspace':
        """Create a new workspace directory and return a Workspace object."""
        from datetime import datetime, timezone
        work_id   = uuid.uuid4().hex[:8]
        ts        = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
        dir_name  = f'{workflow_name}-{ts}-{work_id}'
        wdir      = os.path.join(base_dir, dir_name)
        os.makedirs(wdir, exist_ok=True)
        now_iso   = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        return cls(workflow_name    = Safe_Str__Workflow_Name(workflow_name),
                   work_id          = Safe_Str__Work_Id(work_id),
                   workspace_dir    = Safe_Str__File_Path(wdir),
                   started_at       = Safe_Str__ISO_Timestamp(now_iso),
                   workflow_version = Safe_Str__Semver(workflow_version))

    @classmethod
    def load(cls, workspace_dir: str) -> 'Workflow__Workspace':
        """Load an existing workspace from disk (reads workflow.json)."""
        manifest_path = os.path.join(workspace_dir, 'workflow.json')
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f'No workflow.json in {workspace_dir}')
        with open(manifest_path) as f:
            data = json.load(f)
        return cls(workflow_name    = Safe_Str__Workflow_Name(data.get('workflow_name', '')),
                   work_id          = Safe_Str__Work_Id(data.get('work_id', '')),
                   workspace_dir    = Safe_Str__File_Path(workspace_dir),
                   started_at       = Safe_Str__ISO_Timestamp(data.get('started_at', '')),
                   workflow_version = Safe_Str__Semver(data.get('workflow_version', '1.0.0')))

    # ------------------------------------------------------------------
    # Step I/O
    # ------------------------------------------------------------------

    def _step_path(self, step: 'Step', index: int = None) -> str:
        name = step.step_name()
        if index is not None:
            return os.path.join(str(self.workspace_dir), f'{index:02d}__{name}.json')
        # Find by name glob
        wdir = str(self.workspace_dir)
        for fname in sorted(os.listdir(wdir)):
            if fname.endswith(f'__{name}.json'):
                return os.path.join(wdir, fname)
        return os.path.join(wdir, f'00__{name}.json')

    def has_output_for(self, step: 'Step') -> bool:
        """Return True if this step's output file already exists."""
        wdir = str(self.workspace_dir)
        name = step.step_name()
        for fname in os.listdir(wdir):
            if fname.endswith(f'__{name}.json'):
                return True
        return False

    def persist_output(self, step: 'Step', output: Type_Safe, index: int = 0) -> None:
        """Write step output atomically via temp-file + rename."""
        path = self._step_path(step, index)
        content = json.dumps(output.json()) if hasattr(output, 'json') else json.dumps(output)
        self._atomic_write(path, content)

    def gather_input_for(self, step: 'Step') -> Type_Safe:
        """Load the input for a step from its declared input_schema + prior step outputs."""
        schema = step.input_schema
        if schema is None:
            return None
        # Build an empty input instance — subclasses override for real wiring
        return schema()

    def read_output_for(self, step: 'Step') -> dict:
        """Read the persisted JSON for a step as a plain dict."""
        wdir = str(self.workspace_dir)
        name = step.step_name()
        for fname in sorted(os.listdir(wdir)):
            if fname.endswith(f'__{name}.json'):
                with open(os.path.join(wdir, fname)) as f:
                    return json.load(f)
        raise FileNotFoundError(f'No output found for step {name!r}')

    def final_output(self) -> dict:
        """Return the output of the last completed step as a plain dict."""
        wdir   = str(self.workspace_dir)
        files  = sorted(f for f in os.listdir(wdir) if f.endswith('.json') and f != 'workflow.json')
        if not files:
            return {}
        with open(os.path.join(wdir, files[-1])) as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Manifest (workflow.json)
    # ------------------------------------------------------------------

    def write_manifest(self, manifest_data: dict) -> None:
        path = os.path.join(str(self.workspace_dir), 'workflow.json')
        self._atomic_write(path, json.dumps(manifest_data, indent=2))

    def read_manifest(self) -> dict:
        path = os.path.join(str(self.workspace_dir), 'workflow.json')
        if not os.path.isfile(path):
            return {}
        with open(path) as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove the workspace directory."""
        import shutil
        wdir = str(self.workspace_dir)
        if os.path.isdir(wdir):
            shutil.rmtree(wdir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(path: str, content: str) -> None:
        """Write content atomically: write to a temp file, then os.rename."""
        dir_  = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix='.tmp-')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            os.rename(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
