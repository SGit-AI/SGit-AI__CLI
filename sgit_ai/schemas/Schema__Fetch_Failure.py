"""A single per-object download failure recorded by the pull/fetch path.

Used to plumb honest classification from the API layer up to the user-facing
message in Step__Pull__Fetch_Missing — distinguishing "object truly absent on
the server" (404 / server 'not_found') from "transient error, please retry"
(5xx / network).
"""
from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Enum__Fetch_Failure_Class       import Enum__Fetch_Failure_Class
from sgit_ai.safe_types.Safe_Str__Object_Id             import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Error_Message         import Safe_Str__Error_Message


class Schema__Fetch_Failure(Type_Safe):
    file_id        : Safe_Str__Object_Id        = None        # blob/commit/tree object id (without bare/data/ prefix)
    classification : Enum__Fetch_Failure_Class  = None        # absent vs transient
    error_message  : Safe_Str__Error_Message    = None        # verbatim error text from server/exception
