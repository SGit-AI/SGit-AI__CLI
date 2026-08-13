"""Tests for Schema__Fetch_Failure — per-object pull/fetch failure record."""
from sgit_ai.safe_types.Enum__Fetch_Failure_Class       import Enum__Fetch_Failure_Class
from sgit_ai.safe_types.Safe_Str__Error_Message         import Safe_Str__Error_Message
from sgit_ai.safe_types.Safe_Str__Object_Id             import Safe_Str__Object_Id
from sgit_ai.schemas.Schema__Fetch_Failure              import Schema__Fetch_Failure


OBJ_ID = 'obj-cas-imm-14d8663015d8'


class Test_Schema__Fetch_Failure:

    def test_default_construction(self):
        f = Schema__Fetch_Failure()
        assert f.file_id        is None
        assert f.classification is None
        assert f.error_message  is None

    def test_construction_absent(self):
        f = Schema__Fetch_Failure(
            file_id        = Safe_Str__Object_Id(OBJ_ID),
            classification = Enum__Fetch_Failure_Class.ABSENT,
            error_message  = Safe_Str__Error_Message('not_found'),
        )
        assert str(f.file_id)              == OBJ_ID
        assert f.classification            == Enum__Fetch_Failure_Class.ABSENT
        assert str(f.error_message)        == 'not_found'

    def test_construction_transient(self):
        f = Schema__Fetch_Failure(
            file_id        = Safe_Str__Object_Id(OBJ_ID),
            classification = Enum__Fetch_Failure_Class.TRANSIENT,
            error_message  = Safe_Str__Error_Message('HTTP 502 Bad Gateway'),
        )
        assert f.classification == Enum__Fetch_Failure_Class.TRANSIENT

    def test_round_trip_invariant(self):
        f = Schema__Fetch_Failure(
            file_id        = Safe_Str__Object_Id(OBJ_ID),
            classification = Enum__Fetch_Failure_Class.ABSENT,
            error_message  = Safe_Str__Error_Message('object missing'),
        )
        assert Schema__Fetch_Failure.from_json(f.json()).json() == f.json()

    def test_round_trip_empty(self):
        f = Schema__Fetch_Failure()
        assert Schema__Fetch_Failure.from_json(f.json()).json() == f.json()

    def test_enum_values(self):
        assert Enum__Fetch_Failure_Class.ABSENT.value    == 'absent'
        assert Enum__Fetch_Failure_Class.TRANSIENT.value == 'transient'
