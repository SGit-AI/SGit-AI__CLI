"""Tests for Schema__Transaction_Record and Schema__Step_Summary — round-trip invariant."""
from sgit_ai.schemas.workflow.Schema__Transaction_Record import Schema__Transaction_Record
from sgit_ai.schemas.workflow.Schema__Step_Summary       import Schema__Step_Summary
from sgit_ai.safe_types.Safe_Str__Semver                 import Safe_Str__Semver
from sgit_ai.safe_types.Safe_Str__Workflow_Name          import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Work_Id                import Safe_Str__Work_Id
from sgit_ai.safe_types.Safe_Str__Step_Name              import Safe_Str__Step_Name
from sgit_ai.safe_types.Safe_UInt__Timestamp             import Safe_UInt__Timestamp
from sgit_ai.safe_types.Enum__Workflow_Status            import Enum__Workflow_Status
from sgit_ai.safe_types.Enum__Step_Status                import Enum__Step_Status


class Test_Schema__Step_Summary:

    def test_default_construction(self):
        s = Schema__Step_Summary()
        assert s.name        is not None  # Safe_Str__Step_Name default
        assert s.status      == Enum__Step_Status.PENDING
        assert s.duration_ms is not None

    def test_with_values(self):
        s = Schema__Step_Summary(
            name        = Safe_Str__Step_Name('derive-keys'),
            status      = Enum__Step_Status.COMPLETED,
            duration_ms = Safe_UInt__Timestamp(123),
        )
        assert str(s.name) == 'derive-keys'
        assert s.status    == Enum__Step_Status.COMPLETED

    def test_round_trip(self):
        s = Schema__Step_Summary(
            name        = Safe_Str__Step_Name('walk-trees'),
            status      = Enum__Step_Status.COMPLETED,
            duration_ms = Safe_UInt__Timestamp(456),
        )
        assert Schema__Step_Summary.from_json(s.json()).json() == s.json()


class Test_Schema__Transaction_Record:

    def _make_record(self):
        step = Schema__Step_Summary(
            name        = Safe_Str__Step_Name('step1'),
            status      = Enum__Step_Status.COMPLETED,
            duration_ms = Safe_UInt__Timestamp(100),
        )
        return Schema__Transaction_Record(
            record_version   = Safe_Str__Semver('1.0.0'),
            workflow_name    = Safe_Str__Workflow_Name('clone'),
            workflow_version = Safe_Str__Semver('1.0.0'),
            work_id          = Safe_Str__Work_Id('abc12345'),
            duration_ms      = Safe_UInt__Timestamp(1234),
            status           = Enum__Workflow_Status.SUCCESS,
            steps_summary    = [step],
        )

    def test_default_construction(self):
        r = Schema__Transaction_Record()
        assert r.status       == Enum__Workflow_Status.PENDING
        assert r.steps_summary == []

    def test_with_values(self):
        r = self._make_record()
        assert str(r.workflow_name) == 'clone'
        assert r.status             == Enum__Workflow_Status.SUCCESS
        assert len(r.steps_summary) == 1

    def test_round_trip(self):
        r = self._make_record()
        assert Schema__Transaction_Record.from_json(r.json()).json() == r.json()

    def test_vault_id_optional(self):
        r = Schema__Transaction_Record()
        assert r.vault_id is None

    def test_error_optional(self):
        r = Schema__Transaction_Record()
        assert r.error is None


class Test_Schema__Workflow_Manifest:

    def test_round_trip(self):
        from sgit_ai.schemas.workflow.Schema__Workflow_Manifest    import Schema__Workflow_Manifest
        from sgit_ai.schemas.workflow.Schema__Workflow_Step_Entry  import Schema__Workflow_Step_Entry
        from sgit_ai.safe_types.Safe_UInt__Timestamp               import Safe_UInt__Timestamp

        entry = Schema__Workflow_Step_Entry(
            step_index  = Safe_UInt__Timestamp(1),
            name        = Safe_Str__Step_Name('derive-keys'),
            status      = Enum__Step_Status.COMPLETED,
            duration_ms = Safe_UInt__Timestamp(50),
        )
        m = Schema__Workflow_Manifest(
            workflow_name    = Safe_Str__Workflow_Name('clone'),
            workflow_version = Safe_Str__Semver('1.0.0'),
            work_id          = Safe_Str__Work_Id('abc12345'),
            status           = Enum__Workflow_Status.SUCCESS,
            steps            = [entry],
        )
        assert Schema__Workflow_Manifest.from_json(m.json()).json() == m.json()
