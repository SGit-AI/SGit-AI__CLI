from sgit_ai.schemas.Schema__Dump_Result  import Schema__Dump_Result
from sgit_ai.schemas.Schema__Dump_Ref     import Schema__Dump_Ref
from sgit_ai.schemas.Schema__Dump_Branch  import Schema__Dump_Branch
from sgit_ai.schemas.Schema__Dump_Commit  import Schema__Dump_Commit
from sgit_ai.schemas.Schema__Dump_Tree    import Schema__Dump_Tree
from sgit_ai.schemas.Schema__Dump_Object  import Schema__Dump_Object


class Test_Schema__Dump_Result:

    def test_defaults(self):
        result = Schema__Dump_Result()
        assert str(result.source)    == 'None'  or result.source is None
        assert result.traversal_path == []
        assert result.refs           == []
        assert result.branches       == []
        assert result.commits        == []
        assert result.trees          == []
        assert result.objects        == []
        assert result.dangling_ids   == []
        assert result.errors         == []
        assert int(result.total_objects)   == 0
        assert int(result.total_refs)      == 0
        assert int(result.total_branches)  == 0
        assert int(result.dangling_count)  == 0

    def test_create_with_source(self):
        result = Schema__Dump_Result(source='local', directory='/tmp/vault')
        assert str(result.source)    == 'local'
        assert str(result.directory) == '/tmp/vault'

    def test_round_trip(self):
        ref     = Schema__Dump_Ref(ref_id='ref-pid-muw-aabbccdd1122',
                                   commit_id='obj-cas-imm-abcdef012345')
        commit  = Schema__Dump_Commit(commit_id='obj-cas-imm-abcdef012345',
                                      tree_id  ='obj-cas-imm-fedcba543210',
                                      timestamp_ms=1710412800000)
        tree    = Schema__Dump_Tree(tree_id='obj-cas-imm-fedcba543210',
                                    entry_count=2)
        obj     = Schema__Dump_Object(object_id='obj-cas-imm-abcdef012345',
                                      size_bytes=128)
        branch  = Schema__Dump_Branch(branch_id='branch-named-aabb1122',
                                      name='current',
                                      created_at=1710412800000)
        result = Schema__Dump_Result(
            source         = 'local',
            directory      = '/tmp/vault',
            traversal_path = ['obj-cas-imm-abcdef012345'],
            refs           = [ref],
            branches       = [branch],
            commits        = [commit],
            trees          = [tree],
            objects        = [obj],
            dangling_ids   = [],
            total_objects  = 1,
            total_refs     = 1,
            total_branches = 1,
            dangling_count = 0,
        )
        restored = Schema__Dump_Result.from_json(result.json())
        assert restored.json() == result.json()

    def test_dump_ref_round_trip(self):
        ref      = Schema__Dump_Ref(ref_id='ref-pid-muw-aabbccdd1122',
                                    commit_id='obj-cas-imm-abcdef012345')
        restored = Schema__Dump_Ref.from_json(ref.json())
        assert restored.json() == ref.json()

    def test_dump_branch_round_trip(self):
        branch   = Schema__Dump_Branch(branch_id='branch-named-aabb1122',
                                       name='current',
                                       branch_type='named',
                                       head_ref_id='ref-pid-muw-aabbccdd1122',
                                       head_commit='obj-cas-imm-abcdef012345',
                                       created_at=1710412800000)
        restored = Schema__Dump_Branch.from_json(branch.json())
        assert restored.json() == branch.json()

    def test_dump_commit_round_trip(self):
        commit   = Schema__Dump_Commit(commit_id='obj-cas-imm-abcdef012345',
                                       tree_id  ='obj-cas-imm-fedcba543210',
                                       parents  =['obj-cas-imm-111111111111'],
                                       timestamp_ms=1710412800000,
                                       message  ='initial commit',
                                       branch_id='branch-named-aabb1122')
        restored = Schema__Dump_Commit.from_json(commit.json())
        assert restored.json() == commit.json()

    def test_dump_tree_round_trip(self):
        tree     = Schema__Dump_Tree(tree_id='obj-cas-imm-fedcba543210',
                                     entry_count=2,
                                     blob_ids=['obj-cas-imm-bbbbbbbbbbbb'],
                                     sub_tree_ids=['obj-cas-imm-cccccccccccc'])
        restored = Schema__Dump_Tree.from_json(tree.json())
        assert restored.json() == tree.json()

    def test_dump_object_round_trip(self):
        obj      = Schema__Dump_Object(object_id='obj-cas-imm-abcdef012345',
                                       size_bytes=256, is_dangling=True,
                                       integrity=True)
        restored = Schema__Dump_Object.from_json(obj.json())
        assert restored.json() == obj.json()
