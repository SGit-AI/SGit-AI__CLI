from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.schemas.Schema__Batch_Operation                  import Schema__Batch_Operation


class Schema__Batch_Request(Type_Safe):
    operations : list[Schema__Batch_Operation]
