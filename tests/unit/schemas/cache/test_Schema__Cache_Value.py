from sgit_ai.schemas.cache.Schema__Cache_Value import Schema__Cache_Value
from sgit_ai.safe_types.Enum__Cache_Kind       import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability import Enum__Cache_Mutability


class Test_Schema__Cache_Value:

    def test_defaults(self):
        s = Schema__Cache_Value()
        assert s.kind       == Enum__Cache_Kind.VALUE
        assert s.mutability == Enum__Cache_Mutability.SNW
        assert int(s.size)  == 0

    def test_round_trip__defaults(self):
        s = Schema__Cache_Value()
        assert Schema__Cache_Value.from_json(s.json()).json() == s.json()

    def test_round_trip__populated(self):
        s = Schema__Cache_Value(schema       = 'cache_value_v1',
                                path         = 'pages/home.md',
                                commit_id    = 'obj-cas-imm-aaaaaaaaaaaa',
                                content_type = 'text/markdown',
                                size         = 7,
                                content_hash = 'c8e5a6f1b2d3',
                                value_b64    = 'IyBIb21lCg==')
        assert Schema__Cache_Value.from_json(s.json()).json() == s.json()

    def test_json_shape(self):
        s = Schema__Cache_Value(schema='cache_value_v1', path='pages/home.md', size=7)
        j = s.json()
        assert j['schema'] == 'cache_value_v1'
        assert j['kind']   == 'value'                    # enum serialises to its value
        assert j['mutability'] == 'snw'

    def test_from_json_drops_unknown_fields(self):
        # forward-compat: a v2 producer may add fields a v1 reader ignores
        s = Schema__Cache_Value.from_json({'schema': 'cache_value_v1', 'path': 'a.txt',
                                           'size': 1, 'future_field': 'ignored'})
        assert 'future_field' not in s.json()

    def test_muw_round_trips(self):
        s = Schema__Cache_Value(schema='cache_value_v1', path='k.json', size=3,
                                mutability=Enum__Cache_Mutability.MUW)
        r = Schema__Cache_Value.from_json(s.json())
        assert r.mutability == Enum__Cache_Mutability.MUW
        assert r.json() == s.json()
