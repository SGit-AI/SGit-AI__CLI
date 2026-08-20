from sgit_ai.schemas.cache.Schema__Cache_Pointer import Schema__Cache_Pointer
from sgit_ai.safe_types.Enum__Cache_Kind          import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability    import Enum__Cache_Mutability
from sgit_ai.safe_types.Enum__Cache_Target_Kind   import Enum__Cache_Target_Kind


class Test_Schema__Cache_Pointer:

    def test_defaults(self):
        s = Schema__Cache_Pointer()
        assert s.kind        == Enum__Cache_Kind.POINTER
        assert s.mutability  == Enum__Cache_Mutability.SNW
        assert s.target_kind == Enum__Cache_Target_Kind.BLOB

    def test_round_trip__defaults(self):
        s = Schema__Cache_Pointer()
        assert Schema__Cache_Pointer.from_json(s.json()).json() == s.json()

    def test_round_trip__blob_target(self):
        s = Schema__Cache_Pointer(schema       = 'cache_pointer_v1',
                                  path         = 'keys/api.json',
                                  commit_id    = 'obj-cas-imm-aaaaaaaaaaaa',
                                  content_type = 'application/json',
                                  size         = 128,
                                  target_kind  = Enum__Cache_Target_Kind.BLOB,
                                  target_id    = 'obj-cas-imm-bbbbbbbbbbbb',
                                  content_hash = 'c8e5a6f1b2d3')
        assert Schema__Cache_Pointer.from_json(s.json()).json() == s.json()

    def test_round_trip__tree_target(self):
        s = Schema__Cache_Pointer(schema       = 'cache_pointer_v1',
                                  path         = 'media/photos',
                                  commit_id    = 'obj-cas-imm-aaaaaaaaaaaa',
                                  content_type = 'application/x-directory',
                                  size         = 0,
                                  target_kind  = Enum__Cache_Target_Kind.TREE,
                                  target_id    = 'obj-cas-imm-cccccccccccc')
        assert Schema__Cache_Pointer.from_json(s.json()).json() == s.json()

    def test_json_shape(self):
        s = Schema__Cache_Pointer(schema='cache_pointer_v1', path='media/photos',
                                  target_kind=Enum__Cache_Target_Kind.TREE)
        j = s.json()
        assert j['schema']      == 'cache_pointer_v1'
        assert j['kind']        == 'pointer'
        assert j['target_kind'] == 'tree'
