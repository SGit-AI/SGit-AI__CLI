from osbot_utils.type_safe.Type_Safe               import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str  import Safe_Str
from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from sgit_ai.schemas.Schema__Dump_Object           import Schema__Dump_Object
from sgit_ai.schemas.Schema__Dump_Ref              import Schema__Dump_Ref
from sgit_ai.schemas.Schema__Dump_Commit           import Schema__Dump_Commit
from sgit_ai.schemas.Schema__Dump_Tree             import Schema__Dump_Tree
from sgit_ai.schemas.Schema__Dump_Branch           import Schema__Dump_Branch


class Schema__Dump_Result(Type_Safe):
    """Complete snapshot of a vault's internal state (local or remote)."""

    # Source information
    source          : Safe_Str  = None   # 'local' or 'remote'
    directory       : Safe_Str  = None   # local path or remote URL

    # Traversal path: ordered sequence of object IDs visited (root → leaves)
    traversal_path  : list[Safe_Str]

    # Refs
    refs            : list[Schema__Dump_Ref]

    # Branches (decoded from branch index)
    branches        : list[Schema__Dump_Branch]

    # All commits encountered during traversal
    commits         : list[Schema__Dump_Commit]

    # All trees encountered during traversal
    trees           : list[Schema__Dump_Tree]

    # All objects in bare/data (blobs only — no content, just IDs and sizes)
    objects         : list[Schema__Dump_Object]

    # Dangling object IDs (in bare/data but not referenced by any tree or commit)
    dangling_ids    : list[Safe_Str]

    # Counts
    total_objects   : Safe_UInt
    total_refs      : Safe_UInt
    total_branches  : Safe_UInt
    dangling_count  : Safe_UInt

    # Errors encountered during traversal (non-fatal)
    errors          : list[Safe_Str]
