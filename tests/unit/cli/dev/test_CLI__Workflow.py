"""Tests for `sgit dev workflow` CLI commands."""
import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.cli.CLI__Main import CLI__Main


def _parser():
    return CLI__Main().build_parser()


class Test_CLI__Dev__Workflow_Parser:

    def test_workflow_list_parser_exists(self):
        args = _parser().parse_args(['dev', 'workflow', 'list'])
        assert args.dev_command      == 'workflow'
        assert args.workflow_command == 'list'

    def test_workflow_show_parser_exists(self):
        args = _parser().parse_args(['dev', 'workflow', 'show', 'clone'])
        assert args.workflow_command == 'show'
        assert args.workflow         == 'clone'

    def test_workflow_inspect_parser_exists(self):
        args = _parser().parse_args(['dev', 'workflow', 'inspect', 'abc12345'])
        assert args.workflow_command == 'inspect'
        assert args.work_id          == 'abc12345'

    def test_workflow_resume_parser_exists(self):
        args = _parser().parse_args(['dev', 'workflow', 'resume', 'abc12345'])
        assert args.workflow_command == 'resume'
        assert args.work_id          == 'abc12345'

    def test_workflow_gc_parser_exists(self):
        args = _parser().parse_args(['dev', 'workflow', 'gc', '--older-than', '14'])
        assert args.workflow_command == 'gc'
        assert args.older_than       == 14

    def test_workflow_log_parser_exists(self):
        args = _parser().parse_args(['dev', 'workflow', 'log'])
        assert args.workflow_command == 'log'

    def test_workflow_log_filter_flag(self):
        args = _parser().parse_args(['dev', 'workflow', 'log', '--filter', 'clone'])
        assert args.filter == 'clone'

    def test_workflow_inspect_vault_dir_flag(self):
        args = _parser().parse_args(['dev', 'workflow', 'inspect', 'abc', '--vault-dir', '/tmp/v'])
        assert args.vault_dir == '/tmp/v'


class Test_CLI__Dev__Workflow_List:

    def test_list_no_registered_workflows(self, capsys):
        from sgit_ai.cli.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow, _WORKFLOW_REGISTRY
        cli = CLI__Dev__Workflow()
        old = dict(_WORKFLOW_REGISTRY)
        _WORKFLOW_REGISTRY.clear()
        try:
            cli.cmd_list(type('A', (), {})())
            out = capsys.readouterr().out
            assert 'No registered workflows' in out
        finally:
            _WORKFLOW_REGISTRY.update(old)

    def test_list_shows_registered_workflow(self, capsys):
        from sgit_ai.cli.dev.workflow.CLI__Dev__Workflow import (
            CLI__Dev__Workflow, _WORKFLOW_REGISTRY, register_workflow)
        from sgit_ai.workflow.Workflow               import Workflow
        from sgit_ai.safe_types.Safe_Str__Workflow_Name import Safe_Str__Workflow_Name
        from sgit_ai.safe_types.Safe_Str__Semver        import Safe_Str__Semver

        @register_workflow
        class _TestWf(Workflow):
            name    = Safe_Str__Workflow_Name('test-list-wf')
            version = Safe_Str__Semver('1.0.0')
            steps   = []

        try:
            cli = CLI__Dev__Workflow()
            cli.cmd_list(type('A', (), {})())
            out = capsys.readouterr().out
            assert 'test-list-wf' in out
        finally:
            _WORKFLOW_REGISTRY.pop('test-list-wf', None)


class Test_CLI__Dev__Workflow_GC:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.vault_dir = os.path.join(self.tmp, 'myvault')
        self.work_root = os.path.join(self.vault_dir, '.sg_vault', 'work')
        os.makedirs(self.work_root, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gc_removes_old_workspaces(self, capsys):
        import time
        old_dir = os.path.join(self.work_root, 'old-workspace')
        os.makedirs(old_dir)
        # Make it look old by modifying mtime
        old_time = time.time() - 10 * 86400  # 10 days ago
        os.utime(old_dir, (old_time, old_time))

        from sgit_ai.cli.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        cli = CLI__Dev__Workflow()

        class FakeArgs:
            vault_dir  = self.vault_dir
            older_than = 7

        cli.cmd_gc(FakeArgs())
        assert not os.path.isdir(old_dir)
        out = capsys.readouterr().out
        assert 'Removed 1' in out

    def test_gc_skips_new_workspaces(self, capsys):
        new_dir = os.path.join(self.work_root, 'new-workspace')
        os.makedirs(new_dir)

        from sgit_ai.cli.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        cli = CLI__Dev__Workflow()

        class FakeArgs:
            vault_dir  = self.vault_dir
            older_than = 7

        cli.cmd_gc(FakeArgs())
        assert os.path.isdir(new_dir)


class Test_CLI__Dev__Workflow_Inspect:

    def setup_method(self):
        self.tmp       = tempfile.mkdtemp()
        self.vault_dir = os.path.join(self.tmp, 'myvault')
        self.work_root = os.path.join(self.vault_dir, '.sg_vault', 'work')
        os.makedirs(self.work_root, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inspect_prints_manifest(self, capsys):
        wdir = os.path.join(self.work_root, 'clone-abc12345-def')
        os.makedirs(wdir)
        manifest = {'workflow_name': 'clone', 'workflow_version': '1.0.0',
                    'work_id': 'abc12345', 'status': 'success',
                    'started_at': '2026-05-04T10:00:00Z',
                    'completed_at': '2026-05-04T10:01:00Z',
                    'steps': [{'step_index': 1, 'name': 'derive-keys',
                                'status': 'completed', 'duration_ms': 50}],
                    'error': None}
        with open(os.path.join(wdir, 'workflow.json'), 'w') as f:
            json.dump(manifest, f)

        from sgit_ai.cli.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        cli = CLI__Dev__Workflow()

        class FakeArgs:
            work_id   = 'abc12345'
            vault_dir = self.vault_dir

        cli.cmd_inspect(FakeArgs())
        out = capsys.readouterr().out
        assert 'clone' in out
        assert 'success' in out
        assert 'derive-keys' in out
