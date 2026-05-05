"""Workflow__Runner — orchestrates a Workflow execution with manifest tracking."""
import json
import os
from datetime import datetime, timezone

from osbot_utils.type_safe.Type_Safe                               import Type_Safe
from sgit_ai.safe_types.Enum__Step_Status                          import Enum__Step_Status
from sgit_ai.safe_types.Enum__Workflow_Status                      import Enum__Workflow_Status
from sgit_ai.safe_types.Enum__Transaction_Log_Mode                 import Enum__Transaction_Log_Mode
from sgit_ai.workflow.Workflow                                      import Workflow
from sgit_ai.workflow.Workflow__Workspace                           import Workflow__Workspace


class Workflow__Runner(Type_Safe):
    """Runs a Workflow instance against a Workspace, writing a manifest + transaction log."""

    workflow        : Workflow         = None
    workspace       : Workflow__Workspace = None
    keep_work       : bool             = False
    log_mode        : Enum__Transaction_Log_Mode = Enum__Transaction_Log_Mode.OFF

    def run(self, input: Type_Safe = None) -> dict:
        """Execute the workflow and return its final output."""
        ws = self.workspace
        wf = self.workflow

        # --- version check for resume safety ---
        manifest = ws.read_manifest()
        if manifest:
            existing_ver = manifest.get('workflow_version', '1.0.0')
            current_ver  = wf.workflow_version()
            if existing_ver.split('.')[0] != current_ver.split('.')[0]:
                raise RuntimeError(
                    f'Cannot resume: workspace was created with workflow version '
                    f'{existing_ver}; current version is {current_ver}. '
                    f'Please re-run from scratch (workspace preserved at {ws.workspace_dir} for inspection).'
                )

        # --- build step entries ---
        step_entries = []
        for idx, sc in enumerate(wf.step_classes(), start=1):
            step = sc()
            step_entries.append({'step_index': idx, 'name': step.step_name(),
                                  'status': Enum__Step_Status.PENDING.value,
                                  'started_at': None, 'completed_at': None, 'duration_ms': 0})

        started_at = self._now_iso()
        manifest_data = {
            'workflow_name':    wf.workflow_name(),
            'workflow_version': wf.workflow_version(),
            'work_id':          str(ws.work_id),
            'started_at':       started_at,
            'completed_at':     None,
            'status':           Enum__Workflow_Status.RUNNING.value,
            'keep_work':        self.keep_work,
            'steps':            step_entries,
            'error':            None,
        }
        ws.write_manifest(manifest_data)

        # --- execute steps ---
        error_msg  = None
        _exc       = None
        status     = Enum__Workflow_Status.SUCCESS
        final_out  = {}
        step_times = {}

        try:
            current_input = input
            for idx, step_class in enumerate(wf.step_classes(), start=1):
                step      = step_class()
                sname     = step.step_name()
                entry_idx = idx - 1

                if step.is_done(ws):
                    manifest_data['steps'][entry_idx]['status'] = Enum__Step_Status.COMPLETED.value
                    ws.write_manifest(manifest_data)
                    current_input = ws.load_output_schema_for(step)
                    continue

                t0 = self._now_ms()
                manifest_data['steps'][entry_idx]['status']     = Enum__Step_Status.RUNNING.value
                manifest_data['steps'][entry_idx]['started_at'] = self._now_iso()
                ws.write_manifest(manifest_data)

                step.validate_input(current_input)
                output = step.execute(current_input, ws)
                step.validate_output(output)
                ws.persist_output(step, output, index=idx)
                current_input = output

                dur = self._now_ms() - t0
                step_times[sname] = dur
                manifest_data['steps'][entry_idx]['status']       = Enum__Step_Status.COMPLETED.value
                manifest_data['steps'][entry_idx]['completed_at'] = self._now_iso()
                manifest_data['steps'][entry_idx]['duration_ms']  = dur
                ws.write_manifest(manifest_data)
                self._emit_trace_step(wf.workflow_name(), sname, dur)

            final_out = ws.final_output()

        except Exception as exc:
            status    = Enum__Workflow_Status.FAILED
            error_msg = str(exc)
            _exc      = exc
            # Mark the currently-running step as FAILED
            for entry in manifest_data['steps']:
                if entry['status'] == Enum__Step_Status.RUNNING.value:
                    entry['status'] = Enum__Step_Status.FAILED.value
                    break

        # --- finalise manifest ---
        manifest_data['status']       = status.value
        manifest_data['completed_at'] = self._now_iso()
        manifest_data['error']        = error_msg
        ws.write_manifest(manifest_data)

        # --- transaction log ---
        self._emit_transaction(manifest_data, step_times)

        # --- workspace cleanup (on success, unless keep_work) ---
        if status == Enum__Workflow_Status.SUCCESS and not self.keep_work:
            ws.cleanup()

        if status != Enum__Workflow_Status.SUCCESS:
            if _exc is not None:
                try:
                    raise type(_exc)(error_msg) from _exc
                except TypeError:
                    raise RuntimeError(error_msg) from _exc
            raise RuntimeError(error_msg or 'Workflow failed')

        return final_out

    def resume_from(self, step_name: str) -> dict:
        """Re-run from step_name; prior step outputs are kept, later ones are deleted."""
        ws  = self.workspace
        wf  = self.workflow
        wdir = str(ws.workspace_dir)

        step_classes = list(wf.step_classes())
        names        = [sc().step_name() for sc in step_classes]
        if step_name not in names:
            raise ValueError(f'Unknown step {step_name!r}. Known steps: {names}')

        start_idx = names.index(step_name)

        for fname in os.listdir(wdir):
            if fname == 'workflow.json' or not fname.endswith('.json'):
                continue
            for i in range(start_idx, len(names)):
                if fname.endswith(f'__{names[i]}.json'):
                    os.remove(os.path.join(wdir, fname))
                    break

        return self.run()

    # ------------------------------------------------------------------
    # Transaction log
    # ------------------------------------------------------------------

    def _emit_trace_step(self, workflow_name: str, step_name: str, duration_ms: int) -> None:
        """Append one step record to .sg_vault/local/trace.jsonl when SGIT_TRACE=1."""
        if not os.environ.get('SGIT_TRACE'):
            return
        trace_path = self._trace_path()
        if not trace_path:
            return
        record = {'at': self._now_iso(), 'workflow': workflow_name,
                  'step': step_name, 'duration_ms': duration_ms}
        with open(trace_path, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def _trace_path(self) -> str:
        """Return .sg_vault/local/trace.jsonl path by walking up from workspace."""
        path = str(self.workspace.workspace_dir)
        while True:
            candidate = os.path.join(path, '.sg_vault', 'local')
            if os.path.isdir(candidate):
                return os.path.join(candidate, 'trace.jsonl')
            parent = os.path.dirname(path)
            if parent == path:
                return ''
            path = parent

    def _emit_transaction(self, manifest: dict, step_times: dict) -> None:
        if self.log_mode == Enum__Transaction_Log_Mode.OFF:
            return
        # Build record (always; only write to disk if mode says so)
        from sgit_ai.schemas.workflow.Schema__Transaction_Record import Schema__Transaction_Record
        from sgit_ai.schemas.workflow.Schema__Step_Summary       import Schema__Step_Summary
        from sgit_ai.safe_types.Safe_Str__Semver                 import Safe_Str__Semver
        from sgit_ai.safe_types.Safe_Str__Work_Id                import Safe_Str__Work_Id
        from sgit_ai.safe_types.Safe_UInt__Timestamp             import Safe_UInt__Timestamp
        from sgit_ai.safe_types.Enum__Workflow_Status            import Enum__Workflow_Status as WS
        from sgit_ai.safe_types.Enum__Step_Status                import Enum__Step_Status    as SS
        from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
        from sgit_ai.safe_types.Safe_Str__Workflow_Name          import Safe_Str__Workflow_Name
        from sgit_ai.safe_types.Safe_Str__ISO_Timestamp          import Safe_Str__ISO_Timestamp
        from sgit_ai.safe_types.Safe_Str__Error_Message          import Safe_Str__Error_Message

        steps_summary = []
        for entry in manifest.get('steps', []):
            sname  = entry.get('name', '')
            sstatus_str = entry.get('status', 'pending')
            try:
                sstatus = SS(sstatus_str)
            except ValueError:
                sstatus = SS.PENDING
            steps_summary.append(Schema__Step_Summary(
                name        = Safe_Str__Step_Name(sname),
                status      = sstatus,
                duration_ms = Safe_UInt__Timestamp(step_times.get(sname, 0)),
            ))

        status_str = manifest.get('status', 'pending')
        try:
            wstatus = WS(status_str)
        except ValueError:
            wstatus = WS.PENDING

        started   = manifest.get('started_at', '') or ''
        completed = manifest.get('completed_at', '') or ''
        dur_ms    = 0
        if started and completed:
            try:
                from datetime import datetime
                t0 = datetime.fromisoformat(started.replace('Z', '+00:00'))
                t1 = datetime.fromisoformat(completed.replace('Z', '+00:00'))
                dur_ms = int((t1 - t0).total_seconds() * 1000)
            except Exception:
                pass

        record = Schema__Transaction_Record(
            record_version   = Safe_Str__Semver('1.0.0'),
            workflow_name    = Safe_Str__Workflow_Name(manifest.get('workflow_name', '')),
            workflow_version = Safe_Str__Semver(manifest.get('workflow_version', '1.0.0')),
            work_id          = Safe_Str__Work_Id(manifest.get('work_id', 'unknown')),
            started_at       = Safe_Str__ISO_Timestamp(started) if started else None,
            completed_at     = Safe_Str__ISO_Timestamp(completed) if completed else None,
            duration_ms      = Safe_UInt__Timestamp(dur_ms),
            status           = wstatus,
            steps_summary    = steps_summary,
            error            = Safe_Str__Error_Message(manifest.get('error', '') or '') if manifest.get('error') else None,
        )

        # Write to disk only if mode is non-off
        self._write_transaction(record)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def _now_ms(self) -> int:
        import time
        return int(time.monotonic() * 1000)

    def _write_transaction(self, record) -> None:
        """Append one JSONL line to the per-pid transaction log."""
        ws = self.workspace
        vault_dir = str(ws.workspace_dir)
        # Walk up to find .sg_vault/local/
        path = vault_dir
        while True:
            candidate = os.path.join(path, '.sg_vault', 'local')
            if os.path.isdir(candidate):
                break
            parent = os.path.dirname(path)
            if parent == path:
                return  # no vault found — skip
            path = parent

        from datetime import datetime, timezone
        month     = datetime.now(timezone.utc).strftime('%Y-%m')
        tx_dir    = os.path.join(candidate, 'transactions')
        os.makedirs(tx_dir, exist_ok=True)
        pid       = os.getpid()
        log_path  = os.path.join(tx_dir, f'transactions__{month}__{pid}.log')
        line      = json.dumps(record.json()) + '\n'
        with open(log_path, 'a') as f:
            f.write(line)
        try:
            import stat
            os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


