"""Tests for the honest user-facing pull-incomplete message.

Covers ``Step__Pull__Fetch_Missing._build_missing_message`` for all four
classification cases (absent / forbidden / transient / mixed) and asserts the
exact wording:

  - all-absent:    NO "server may be under load", reports server-side absence
  - all-forbidden: NO "server may be under load", reports HTTP 403 + operator
  - all-transient: KEEPS "server may be under load — retry with: sgit pull"
  - mixed:         per-category counts + lists + guidance
"""
from sgit_ai.safe_types.Enum__Fetch_Failure_Class       import Enum__Fetch_Failure_Class
from sgit_ai.safe_types.Safe_Str__Error_Message         import Safe_Str__Error_Message
from sgit_ai.safe_types.Safe_Str__Object_Id             import Safe_Str__Object_Id
from sgit_ai.schemas.Schema__Fetch_Failure              import Schema__Fetch_Failure
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing    import Step__Pull__Fetch_Missing


OID_1 = 'obj-cas-imm-14d8663015d8'
OID_2 = 'obj-cas-imm-6b1a1ef275e4'
OID_3 = 'obj-cas-imm-aabbccdd1122'


def _failure(oid, klass, msg='err'):
    return Schema__Fetch_Failure(
        file_id        = Safe_Str__Object_Id(oid),
        classification = klass,
        error_message  = Safe_Str__Error_Message(msg),
    )


class Test_Step__Pull__Fetch_Missing__Message:

    def setup_method(self):
        self.step = Step__Pull__Fetch_Missing()

    # -- All absent (the user's real bug) -----------------------------------

    def test_all_absent__no_under_load_text(self):
        missing  = [OID_1, OID_2]
        failures = {
            OID_1: _failure(OID_1, Enum__Fetch_Failure_Class.ABSENT, 'not_found'),
            OID_2: _failure(OID_2, Enum__Fetch_Failure_Class.ABSENT, 'not_found'),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert 'server may be under load' not in msg
        assert 'were not found on the server' in msg
        assert 'storage corruption or incomplete propagation' in msg
        assert OID_1 in msg
        assert OID_2 in msg

    def test_all_absent__failures_keyed_by_bare_data_prefix(self):
        """_find_missing_blobs returns short oids, failures dict may be keyed
        by 'bare/data/<oid>' from the batch_read path. The lookup falls back
        to the prefixed key — both should resolve to ABSENT."""
        missing  = [OID_1]
        failures = {
            f'bare/data/{OID_1}': _failure(OID_1, Enum__Fetch_Failure_Class.ABSENT),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert 'were not found on the server' in msg
        assert 'server may be under load' not in msg

    # -- All transient (legitimate retry path — preserve it) ----------------

    def test_all_transient__keeps_under_load_text(self):
        missing  = [OID_1, OID_2]
        failures = {
            OID_1: _failure(OID_1, Enum__Fetch_Failure_Class.TRANSIENT, 'HTTP 503'),
            OID_2: _failure(OID_2, Enum__Fetch_Failure_Class.TRANSIENT, 'timeout'),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert 'server may be under load' in msg
        assert 'retry with: sgit pull' in msg
        assert 'were not found on the server' not in msg

    def test_no_classification_defaults_to_transient(self):
        """If a blob is missing on disk but the failures dict has no entry
        for it (e.g. the fetch path swallowed somewhere we did not instrument),
        the safe default is TRANSIENT — we never claim 'absent' without
        a positive signal from the server."""
        missing  = [OID_1]
        failures = {}
        msg = self.step._build_missing_message(missing, failures)
        assert 'server may be under load' in msg

    # -- All forbidden (the user's real bug — server returns HTTP 403) -------

    def test_all_forbidden__no_under_load_text(self):
        missing  = [OID_1, OID_2]
        failures = {
            OID_1: _failure(OID_1, Enum__Fetch_Failure_Class.FORBIDDEN, 'HTTP 403 Forbidden'),
            OID_2: _failure(OID_2, Enum__Fetch_Failure_Class.FORBIDDEN, 'HTTP 403 Forbidden'),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert 'server may be under load' not in msg
        assert 'were not found on the server' not in msg
        assert 'HTTP 403 Forbidden' in msg
        assert 'refused by the server' in msg
        assert 'vault operator' in msg
        assert OID_1 in msg
        assert OID_2 in msg

    def test_mixed_with_forbidden__reports_all_three(self):
        missing  = [OID_1, OID_2, OID_3]
        failures = {
            OID_1: _failure(OID_1, Enum__Fetch_Failure_Class.ABSENT),
            OID_2: _failure(OID_2, Enum__Fetch_Failure_Class.FORBIDDEN),
            OID_3: _failure(OID_3, Enum__Fetch_Failure_Class.TRANSIENT, 'HTTP 503'),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert '1 absent on server' in msg
        assert '1 forbidden (HTTP 403)' in msg
        assert '1 transient error' in msg
        assert 'Forbidden:' in msg
        assert OID_1 in msg and OID_2 in msg and OID_3 in msg

    # -- Mixed --------------------------------------------------------------

    def test_mixed__reports_both_counts(self):
        missing  = [OID_1, OID_2, OID_3]
        failures = {
            OID_1: _failure(OID_1, Enum__Fetch_Failure_Class.ABSENT),
            OID_2: _failure(OID_2, Enum__Fetch_Failure_Class.ABSENT),
            OID_3: _failure(OID_3, Enum__Fetch_Failure_Class.TRANSIENT, 'HTTP 503'),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert '2 absent on server' in msg
        assert '1 transient error' in msg
        assert 'report to the vault operator' in msg
        assert OID_1 in msg
        assert OID_2 in msg
        assert OID_3 in msg

    def test_mixed__one_each(self):
        missing  = [OID_1, OID_2]
        failures = {
            OID_1: _failure(OID_1, Enum__Fetch_Failure_Class.ABSENT),
            OID_2: _failure(OID_2, Enum__Fetch_Failure_Class.TRANSIENT),
        }
        msg = self.step._build_missing_message(missing, failures)
        assert '1 absent on server' in msg
        assert '1 transient error' in msg

    # -- Truncation -- (3 examples max) -------------------------------------

    def test_examples_truncated_at_three(self):
        missing = ['obj-cas-imm-aabb00000001',
                   'obj-cas-imm-aabb00000002',
                   'obj-cas-imm-aabb00000003',
                   'obj-cas-imm-aabb00000004']
        failures = {oid: _failure(oid, Enum__Fetch_Failure_Class.ABSENT) for oid in missing}
        msg = self.step._build_missing_message(missing, failures)
        assert '...' in msg
        assert 'obj-cas-imm-aabb00000001' in msg
        assert 'obj-cas-imm-aabb00000002' in msg
        assert 'obj-cas-imm-aabb00000003' in msg
