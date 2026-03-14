from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Ref_Id                      import Safe_Str__Ref_Id
from sg_send_cli.safe_types.Safe_Str__Object_Id                   import Safe_Str__Object_Id


class Schema__Tracking_Entry(Type_Safe):
    ref_id    : Safe_Str__Ref_Id    = None                 # the ref being tracked
    commit_id : Safe_Str__Object_Id = None                 # last-known commit ID for this ref


class Schema__Tracking_State(Type_Safe):
    entries : list[Schema__Tracking_Entry]
