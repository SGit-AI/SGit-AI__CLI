from sgit_ai.schemas.Schema__Archive_Provenance import Schema__Archive_Provenance


class Test_Schema__Archive_Provenance:

    def test_create_with_defaults(self):
        p = Schema__Archive_Provenance()
        assert p.branch_id  is None
        assert p.commit_id  is None
        assert p.author_key is None

    def test_create_with_values(self):
        p = Schema__Archive_Provenance(
            branch_id  = 'branch-clone-abcd1234ef56',
            commit_id  = 'obj-cas-imm-abcdef012345',
            author_key = 'a' * 64,
        )
        assert p.branch_id  == 'branch-clone-abcd1234ef56'
        assert p.commit_id  == 'obj-cas-imm-abcdef012345'
        assert p.author_key == 'a' * 64

    def test_round_trip_empty(self):
        p = Schema__Archive_Provenance()
        assert Schema__Archive_Provenance.from_json(p.json()).json() == p.json()

    def test_round_trip_with_values(self):
        p = Schema__Archive_Provenance(
            branch_id = 'branch-clone-abcd1234ef56',
            commit_id = 'obj-cas-imm-abcdef012345',
        )
        assert Schema__Archive_Provenance.from_json(p.json()).json() == p.json()
