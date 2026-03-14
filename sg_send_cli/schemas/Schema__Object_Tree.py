from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sg_send_cli.schemas.Schema__Object_Tree_Entry                import Schema__Object_Tree_Entry


class Schema__Object_Tree(Type_Safe):
    schema  : Safe_Str__Schema_Version = None                      # v2: e.g. 'tree_v1'
    entries : list[Schema__Object_Tree_Entry]
