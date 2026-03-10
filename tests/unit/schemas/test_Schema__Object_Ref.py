from sg_send_cli.schemas.Schema__Object_Ref import Schema__Object_Ref


class Test_Schema__Object_Ref:

    def test_create_with_defaults(self):
        ref = Schema__Object_Ref()
        assert ref.commit_id is None
        assert ref.version   == 0

    def test_create_with_values(self):
        ref = Schema__Object_Ref(commit_id='a1b2c3d4e5f6', version=5)
        assert ref.commit_id == 'a1b2c3d4e5f6'
        assert ref.version   == 5

    def test_round_trip(self):
        ref      = Schema__Object_Ref(commit_id='a1b2c3d4e5f6', version=5)
        restored = Schema__Object_Ref.from_json(ref.json())
        assert restored.json() == ref.json()

    def test_round_trip_empty(self):
        ref      = Schema__Object_Ref()
        restored = Schema__Object_Ref.from_json(ref.json())
        assert restored.json() == ref.json()

    def test_field_types_preserved(self):
        ref = Schema__Object_Ref(commit_id='a1b2c3d4e5f6')
        assert type(ref.commit_id).__name__ == 'Safe_Str__Object_Id'

    def test_null_commit_id_for_empty_vault(self):
        ref = Schema__Object_Ref(version=0)
        assert ref.commit_id is None
