"""Legacy ISO-load tests for the timestamp migration.

When Schema__* fields move from Safe_Str__ISO_Timestamp to Timestamp_Now,
old on-disk JSON files (written with ISO strings) must still load cleanly.
Timestamp_Now.parse_string_value handles ISO -> int ms conversion.

These tests pin the contract: legacy data continues to deserialise.
"""
from sgit_ai.schemas.Schema__PKI_Key_Pair                       import Schema__PKI_Key_Pair
from sgit_ai.schemas.Schema__Secret_Entry                       import Schema__Secret_Entry
from sgit_ai.schemas.merge.Schema__Merge_State                  import Schema__Merge_State
from sgit_ai.schemas.migrations.Schema__Migration_Record        import Schema__Migration_Record
from sgit_ai.schemas.move.Schema__Vault_Move_Record             import Schema__Vault_Move_Record
from sgit_ai.schemas.workflow.Schema__Transaction_Record        import Schema__Transaction_Record
from sgit_ai.schemas.workflow.Schema__Workflow_Manifest         import Schema__Workflow_Manifest
from sgit_ai.schemas.workflow.Schema__Workflow_Step_Entry       import Schema__Workflow_Step_Entry
from sgit_ai.schemas.workflow.move.Schema__Move__State          import Schema__Move__State


ISO_EXAMPLE          = '2026-03-10T12:00:00Z'
ISO_EXAMPLE_MS       = 1773144000000
ISO_FRACTIONAL       = '2026-03-12T10:00:00.000Z'
ISO_FRACTIONAL_MS    = 1773309600000


class Test_Timestamp_Migration__Legacy_ISO_Load:

    def test_pki_key_pair_legacy_iso(self):
        s = Schema__PKI_Key_Pair.from_json({'created_at': ISO_FRACTIONAL})
        assert int(s.created_at) == ISO_FRACTIONAL_MS

    def test_secret_entry_legacy_iso(self):
        s = Schema__Secret_Entry.from_json({'key': 'k', 'created_at': ISO_EXAMPLE})
        assert int(s.created_at) == ISO_EXAMPLE_MS

    def test_merge_state_legacy_iso(self):
        s = Schema__Merge_State.from_json({'started_at': ISO_EXAMPLE})
        assert int(s.started_at) == ISO_EXAMPLE_MS

    def test_migration_record_legacy_iso(self):
        s = Schema__Migration_Record.from_json({'name': 'mig', 'applied_at': ISO_EXAMPLE})
        assert int(s.applied_at) == ISO_EXAMPLE_MS

    def test_vault_move_record_legacy_iso(self):
        s = Schema__Vault_Move_Record.from_json({'rotated_at': ISO_EXAMPLE})
        assert int(s.rotated_at) == ISO_EXAMPLE_MS

    def test_transaction_record_legacy_iso(self):
        s = Schema__Transaction_Record.from_json({'started_at': ISO_EXAMPLE,
                                                  'completed_at': ISO_EXAMPLE})
        assert int(s.started_at)   == ISO_EXAMPLE_MS
        assert int(s.completed_at) == ISO_EXAMPLE_MS

    def test_workflow_manifest_legacy_iso(self):
        s = Schema__Workflow_Manifest.from_json({'started_at':   ISO_EXAMPLE,
                                                 'completed_at': ISO_EXAMPLE})
        assert int(s.started_at)   == ISO_EXAMPLE_MS
        assert int(s.completed_at) == ISO_EXAMPLE_MS

    def test_workflow_step_entry_legacy_iso(self):
        s = Schema__Workflow_Step_Entry.from_json({'started_at':   ISO_EXAMPLE,
                                                   'completed_at': ISO_EXAMPLE})
        assert int(s.started_at)   == ISO_EXAMPLE_MS
        assert int(s.completed_at) == ISO_EXAMPLE_MS

    def test_move_state_legacy_iso(self):
        s = Schema__Move__State.from_json({'renamed_at': ISO_EXAMPLE})
        assert int(s.renamed_at) == ISO_EXAMPLE_MS

    def test_int_input_passes_through(self):
        # Post-migration disk files store ints; they must also load cleanly.
        s = Schema__Secret_Entry.from_json({'key': 'k', 'created_at': ISO_EXAMPLE_MS})
        assert int(s.created_at) == ISO_EXAMPLE_MS

    def test_none_input_stays_none(self):
        s = Schema__Secret_Entry.from_json({'key': 'k', 'created_at': None})
        assert s.created_at is None
