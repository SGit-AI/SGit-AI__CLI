"""Tests for B08 — workflow runtime polish (5 polishes).

Polish 1: Workflow auto-discovery in sgit dev workflow list
Polish 2: Workflow__Runner.resume_from(step_name)
Polish 3: SGIT_TRACE=1 writes .sg_vault/local/trace.jsonl
Polish 4: Plugin manifest round-trip via from_json
Polish 5: Per-plugin settings field in Schema__Plugin_Manifest
"""
import json
import os
import tempfile

import pytest

from sgit_ai.workflow.Workflow__Runner    import Workflow__Runner
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace
from sgit_ai.plugins._base.Plugin__Loader     import Plugin__Loader
from sgit_ai.plugins._base.Schema__Plugin_Manifest import Schema__Plugin_Manifest


# ---------------------------------------------------------------------------
# Minimal stub workflow for runner tests
# ---------------------------------------------------------------------------

from osbot_utils.type_safe.Type_Safe        import Type_Safe
from sgit_ai.workflow.Workflow              import Workflow
from sgit_ai.workflow.Step                 import Step
from sgit_ai.safe_types.Safe_Str__Step_Name     import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_Str__Workflow_Name import Safe_Str__Workflow_Name

class _State(Type_Safe):
    value : int = 0

class _StepA(Step):
    name          = Safe_Str__Step_Name('step-a')
    input_schema  = _State
    output_schema = _State
    def execute(self, input, workspace):
        return _State(value=input.value + 1)

class _StepB(Step):
    name          = Safe_Str__Step_Name('step-b')
    input_schema  = _State
    output_schema = _State
    def execute(self, input, workspace):
        return _State(value=input.value + 10)

class _StepC(Step):
    name          = Safe_Str__Step_Name('step-c')
    input_schema  = _State
    output_schema = _State
    def execute(self, input, workspace):
        return _State(value=input.value + 100)

class _Workflow(Workflow):
    name    = Safe_Str__Workflow_Name('test-b08')
    steps   = [_StepA, _StepB, _StepC]


def _make_runner(tmp_path):
    ws = Workflow__Workspace.create('test-b08', str(tmp_path))
    wf = _Workflow()
    return Workflow__Runner(workflow=wf, workspace=ws, keep_work=True)


# ---------------------------------------------------------------------------
# Polish 1 — auto-discovery
# ---------------------------------------------------------------------------

class Test_B08__Polish1__Auto_Discovery:

    def test_known_workflows_returns_dict(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        known = CLI__Dev__Workflow._known_workflows()
        assert isinstance(known, dict)

    def test_known_workflows_discovers_clone_workflow(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        known = CLI__Dev__Workflow._known_workflows()
        assert 'clone' in known

    def test_known_workflows_discovers_pull_workflow(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        known = CLI__Dev__Workflow._known_workflows()
        assert 'pull' in known

    def test_auto_discover_idempotent(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        known1 = CLI__Dev__Workflow._known_workflows()
        known2 = CLI__Dev__Workflow._known_workflows()
        assert set(known1.keys()) == set(known2.keys())


# ---------------------------------------------------------------------------
# Polish 2 — resume_from
# ---------------------------------------------------------------------------

class Test_B08__Polish2__Resume_From:

    def test_resume_from_reruns_step_c(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.run(_State(value=0))
        # run() succeeded; reload workspace and re-run from step-c
        ws2     = Workflow__Workspace.load(str(runner.workspace.workspace_dir))
        runner2 = Workflow__Runner(workflow=_Workflow(), workspace=ws2, keep_work=True)
        result  = runner2.resume_from('step-c')
        assert result.get('value') == 111

    def test_resume_from_unknown_step_raises(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.run(_State(value=0))
        ws2     = Workflow__Workspace.load(str(runner.workspace.workspace_dir))
        runner2 = Workflow__Runner(workflow=_Workflow(), workspace=ws2, keep_work=True)
        with pytest.raises(ValueError, match='Unknown step'):
            runner2.resume_from('no-such-step')

    def test_resume_from_step_b_reruns_b_and_c(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.run(_State(value=0))
        ws2     = Workflow__Workspace.load(str(runner.workspace.workspace_dir))
        runner2 = Workflow__Runner(workflow=_Workflow(), workspace=ws2, keep_work=True)
        result  = runner2.resume_from('step-b')
        assert result.get('value') == 111


# ---------------------------------------------------------------------------
# Polish 3 — SGIT_TRACE=1
# ---------------------------------------------------------------------------

class Test_B08__Polish3__Trace_Log:

    def setup_method(self):
        self._orig_trace = os.environ.pop('SGIT_TRACE', None)

    def teardown_method(self):
        if self._orig_trace is None:
            os.environ.pop('SGIT_TRACE', None)
        else:
            os.environ['SGIT_TRACE'] = self._orig_trace

    def test_trace_not_written_by_default(self, tmp_path):
        (tmp_path / '.sg_vault' / 'local').mkdir(parents=True)
        runner = _make_runner(tmp_path)
        runner.run(_State(value=0))
        trace_path = tmp_path / '.sg_vault' / 'local' / 'trace.jsonl'
        assert not trace_path.exists()

    def test_trace_written_when_env_set(self, tmp_path):
        os.environ['SGIT_TRACE'] = '1'
        (tmp_path / '.sg_vault' / 'local').mkdir(parents=True)
        runner = _make_runner(tmp_path)
        runner.run(_State(value=0))
        trace_path = tmp_path / '.sg_vault' / 'local' / 'trace.jsonl'
        assert trace_path.exists()
        lines = [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        step_names = [r['step'] for r in lines]
        assert step_names == ['step-a', 'step-b', 'step-c']

    def test_trace_record_has_expected_fields(self, tmp_path):
        os.environ['SGIT_TRACE'] = '1'
        (tmp_path / '.sg_vault' / 'local').mkdir(parents=True)
        runner = _make_runner(tmp_path)
        runner.run(_State(value=0))
        trace_path = tmp_path / '.sg_vault' / 'local' / 'trace.jsonl'
        rec = json.loads(trace_path.read_text().splitlines()[0])
        assert 'at' in rec
        assert 'workflow' in rec
        assert 'step' in rec
        assert 'duration_ms' in rec


# ---------------------------------------------------------------------------
# Polish 4 — Plugin manifest round-trip
# ---------------------------------------------------------------------------

class Test_B08__Polish4__Manifest_Round_Trip:

    def test_from_json_produces_correct_manifest(self):
        data = {'name': 'history', 'version': '0.1.0', 'stability': 'stable',
                'commands': ['log', 'diff'], 'enabled': True}
        m = Schema__Plugin_Manifest.from_json(data)
        assert str(m.name) == 'history'
        assert str(m.version) == '0.1.0'
        assert m.enabled is True
        assert len(m.commands) == 2

    def test_round_trip_invariant(self):
        data = {'name': 'history', 'version': '0.1.0', 'stability': 'stable',
                'commands': ['log', 'diff'], 'enabled': True}
        obj = Schema__Plugin_Manifest.from_json(data)
        assert Schema__Plugin_Manifest.from_json(obj.json()).json() == obj.json()

    def test_load_manifest_uses_from_json(self, tmp_path):
        manifest = {'name': 'testplugin', 'version': '1.2.3', 'stability': 'experimental',
                    'commands': ['run'], 'enabled': False}
        path = tmp_path / 'plugin.json'
        path.write_text(json.dumps(manifest))
        loader = Plugin__Loader()
        m = loader.load_manifest(str(path))
        assert isinstance(m, Schema__Plugin_Manifest)
        assert str(m.name) == 'testplugin'
        assert str(m.version) == '1.2.3'
        assert m.enabled is False

    def test_load_manifest_catches_malformed_at_load_time(self, tmp_path):
        # name strips to '' which violates allow_empty=False → raises at load time
        bad = {'name': '', 'version': '1.0.0', 'stability': 'stable',
               'commands': [], 'enabled': True}
        path = tmp_path / 'plugin.json'
        path.write_text(json.dumps(bad))
        loader = Plugin__Loader()
        with pytest.raises(Exception):
            loader.load_manifest(str(path))


# ---------------------------------------------------------------------------
# Polish 5 — Per-plugin settings field
# ---------------------------------------------------------------------------

class Test_B08__Polish5__Plugin_Settings:

    def test_schema_has_settings_field(self):
        m = Schema__Plugin_Manifest()
        assert hasattr(m, 'settings')

    def test_settings_defaults_to_none(self):
        m = Schema__Plugin_Manifest()
        assert m.settings is None

    def test_settings_can_hold_arbitrary_dict(self):
        m = Schema__Plugin_Manifest.from_json({
            'name': 'history', 'version': '0.1.0', 'stability': 'stable',
            'commands': [], 'enabled': True,
            'settings': {'max_commits_shown': '50', 'color': 'auto'},
        })
        assert m.settings == {'max_commits_shown': '50', 'color': 'auto'}

    def test_settings_survives_round_trip(self):
        data = {'name': 'history', 'version': '0.1.0', 'stability': 'stable',
                'commands': [], 'enabled': True,
                'settings': {'key': 'value'}}
        obj  = Schema__Plugin_Manifest.from_json(data)
        copy = Schema__Plugin_Manifest.from_json(obj.json())
        assert copy.settings == {'key': 'value'}

    def test_load_manifest_reads_settings(self, tmp_path):
        manifest = {'name': 'history', 'version': '0.1.0', 'stability': 'stable',
                    'commands': ['log'], 'enabled': True,
                    'settings': {'max_commits_shown': '100'}}
        path = tmp_path / 'plugin.json'
        path.write_text(json.dumps(manifest))
        loader = Plugin__Loader()
        m = loader.load_manifest(str(path))
        assert m.settings == {'max_commits_shown': '100'}
