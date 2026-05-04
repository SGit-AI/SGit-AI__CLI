"""CLI__Dev__Workflow — `sgit dev workflow <…>` subcommands."""
import argparse
import json
import os
import sys

from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__Dev__Workflow(Type_Safe):
    """Container for all `sgit dev workflow` sub-tools."""

    _registry = {}   # class-level workflow registry; not a Type_Safe field

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    @classmethod
    def register_workflow(cls, wf_cls):
        """Decorator to register a Workflow subclass by name."""
        instance = wf_cls()
        cls._registry[instance.workflow_name()] = wf_cls
        return wf_cls

    @classmethod
    def _known_workflows(cls) -> dict:
        return dict(cls._registry)

    def _find_workspace(self, work_id: str, vault_dir: str = '.') -> str:
        """Find a workspace directory by work-id prefix; returns path or empty string."""
        work_root = os.path.join(vault_dir, '.sg_vault', 'work')
        if not os.path.isdir(work_root):
            return ''
        for name in os.listdir(work_root):
            if work_id in name:
                return os.path.join(work_root, name)
        return ''

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def cmd_list(self, args):
        """sgit dev workflow list — discover registered workflows."""
        known = self._known_workflows()
        if not known:
            print('No registered workflows found.')
            return
        print('Registered workflows:')
        for name, cls in sorted(known.items()):
            ver = getattr(cls, 'version', None)
            ver_str = f' (v{ver})' if ver else ''
            print(f'  {name}{ver_str}')

    def cmd_show(self, args):
        """sgit dev workflow show <command> — list steps + I/O schemas."""
        wf_name = getattr(args, 'workflow', None)
        known   = self._known_workflows()
        if wf_name not in known:
            print(f'Unknown workflow: {wf_name!r}. Run `sgit dev workflow list` to see available workflows.', file=sys.stderr)
            sys.exit(1)
        cls = known[wf_name]
        instance = cls()
        print(f'Workflow: {instance.workflow_name()}  (version {instance.workflow_version()})')
        print('Steps:')
        for idx, sc in enumerate(instance.step_classes(), start=1):
            s = sc()
            in_name  = sc.input_schema.__name__  if sc.input_schema  else 'None'
            out_name = sc.output_schema.__name__ if sc.output_schema else 'None'
            print(f'  {idx:02d}. {s.step_name():<30}  in={in_name}  out={out_name}')

    def cmd_inspect(self, args):
        """sgit dev workflow inspect <work-id> — show manifest + step timings."""
        work_id = getattr(args, 'work_id', None)
        wdir    = self._find_workspace(work_id, getattr(args, 'vault_dir', '.'))
        if not wdir:
            print(f'Workspace not found for work-id {work_id!r}', file=sys.stderr)
            sys.exit(1)
        manifest_path = os.path.join(wdir, 'workflow.json')
        if not os.path.isfile(manifest_path):
            print(f'No workflow.json in {wdir}', file=sys.stderr)
            sys.exit(1)
        with open(manifest_path) as f:
            data = json.load(f)
        print(f'Workflow:  {data.get("workflow_name", "?")}  v{data.get("workflow_version", "?")}')
        print(f'Work ID:   {data.get("work_id", "?")}')
        print(f'Status:    {data.get("status", "?")}')
        print(f'Started:   {data.get("started_at", "?")}')
        print(f'Completed: {data.get("completed_at", "?")}')
        if data.get('error'):
            print(f'Error:     {data["error"]}')
        print()
        print('Steps:')
        for entry in data.get('steps', []):
            status = entry.get('status', 'pending')
            dur    = entry.get('duration_ms', 0)
            name   = entry.get('name', '?')
            print(f'  {entry.get("step_index", 0):02d}. {name:<30} {status:<10} {dur}ms')

    def cmd_resume(self, args):
        """sgit dev workflow resume <work-id> — load workspace and continue."""
        work_id  = getattr(args, 'work_id', None)
        wdir     = self._find_workspace(work_id, getattr(args, 'vault_dir', '.'))
        if not wdir:
            print(f'Workspace not found for work-id {work_id!r}', file=sys.stderr)
            sys.exit(1)
        from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace
        from sgit_ai.workflow.Workflow__Runner    import Workflow__Runner
        ws      = Workflow__Workspace.load(wdir)
        known   = self._known_workflows()
        wf_name = str(ws.workflow_name)
        if wf_name not in known:
            print(f'Cannot resume: workflow {wf_name!r} is not registered.', file=sys.stderr)
            sys.exit(1)
        wf      = known[wf_name]()
        runner  = Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)
        try:
            result = runner.run()
            print(f'Resumed workflow {wf_name!r} — completed.')
        except RuntimeError as e:
            print(f'Resume failed: {e}', file=sys.stderr)
            sys.exit(1)

    def cmd_gc(self, args):
        """sgit dev workflow gc [--older-than <days>] — clean up old workspaces."""
        import shutil
        import time
        vault_dir   = getattr(args, 'vault_dir', '.')
        older_than  = getattr(args, 'older_than', 7)
        work_root   = os.path.join(vault_dir, '.sg_vault', 'work')
        if not os.path.isdir(work_root):
            print('No workflow workspaces found.')
            return
        cutoff = time.time() - older_than * 86400
        removed = 0
        for name in os.listdir(work_root):
            wdir = os.path.join(work_root, name)
            if os.path.isdir(wdir) and os.path.getmtime(wdir) < cutoff:
                shutil.rmtree(wdir)
                removed += 1
        print(f'Removed {removed} workspace(s) older than {older_than} day(s).')

    def cmd_log(self, args):
        """sgit dev workflow log — show recent transaction records."""
        vault_dir = getattr(args, 'vault_dir', '.')
        tx_dir    = os.path.join(vault_dir, '.sg_vault', 'local', 'transactions')
        if not os.path.isdir(tx_dir):
            print('No transaction log found.')
            return
        wf_filter = getattr(args, 'filter', None)
        records   = []
        for fname in sorted(os.listdir(tx_dir)):
            if not fname.endswith('.log'):
                continue
            with open(os.path.join(tx_dir, fname)) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if wf_filter and rec.get('workflow_name') != wf_filter:
                            continue
                        records.append(rec)
                    except json.JSONDecodeError:
                        pass
        if not records:
            print('No transaction records found.')
            return
        for rec in records[-20:]:   # show last 20
            print(f'{rec.get("completed_at", "?")[:19]}  {rec.get("workflow_name", "?")}  '
                  f'{rec.get("status", "?")}  {rec.get("duration_ms", 0)}ms')

    # ------------------------------------------------------------------
    # Argparse registration
    # ------------------------------------------------------------------

    def register(self, dev_subparsers: argparse._SubParsersAction):
        """Add `dev workflow` sub-parser tree."""
        wf_p = dev_subparsers.add_parser('workflow', help='Workflow framework tools (sgit dev workflow <cmd>)')
        wf_s = wf_p.add_subparsers(dest='workflow_command', help='Workflow subcommands')
        wf_p.set_defaults(func=lambda a: wf_p.print_help())

        # list
        lp = wf_s.add_parser('list', help='List registered workflows')
        lp.set_defaults(func=self.cmd_list)

        # show <workflow>
        sp = wf_s.add_parser('show', help='Show steps + I/O schemas for a workflow')
        sp.add_argument('workflow', help='Workflow name (e.g. clone)')
        sp.set_defaults(func=self.cmd_show)

        # inspect <work-id>
        ip = wf_s.add_parser('inspect', help='Inspect a workflow workspace by work-id')
        ip.add_argument('work_id',              help='Work ID (or prefix)')
        ip.add_argument('--vault-dir', '-d',    default='.', dest='vault_dir',
                        help='Vault directory (default: .)')
        ip.set_defaults(func=self.cmd_inspect)

        # resume <work-id>
        rp = wf_s.add_parser('resume', help='Resume an interrupted workflow')
        rp.add_argument('work_id',              help='Work ID to resume')
        rp.add_argument('--vault-dir', '-d',    default='.', dest='vault_dir',
                        help='Vault directory (default: .)')
        rp.set_defaults(func=self.cmd_resume)

        # gc
        gp = wf_s.add_parser('gc', help='Clean up old workflow workspaces')
        gp.add_argument('--older-than', type=int, default=7, dest='older_than',
                        metavar='DAYS', help='Remove workspaces older than N days (default: 7)')
        gp.add_argument('--vault-dir', '-d', default='.', dest='vault_dir',
                        help='Vault directory (default: .)')
        gp.set_defaults(func=self.cmd_gc)

        # log
        logp = wf_s.add_parser('log', help='Show recent transaction log records')
        logp.add_argument('--vault-dir', '-d', default='.', dest='vault_dir',
                          help='Vault directory (default: .)')
        logp.add_argument('--filter', default=None, metavar='WORKFLOW',
                          help='Filter by workflow name')
        logp.set_defaults(func=self.cmd_log)

        return wf_p


# Module-level aliases so existing imports like `from … import register_workflow` keep working.
register_workflow   = CLI__Dev__Workflow.register_workflow
_WORKFLOW_REGISTRY  = CLI__Dev__Workflow._registry
