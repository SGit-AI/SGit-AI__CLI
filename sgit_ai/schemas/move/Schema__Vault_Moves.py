from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.schemas.move.Schema__Vault_Move_Record   import Schema__Vault_Move_Record


class Schema__Vault_Moves(Type_Safe):
    moves : list[Schema__Vault_Move_Record]
