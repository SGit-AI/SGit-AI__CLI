from osbot_utils.type_safe.Type_Safe import Type_Safe
from sgit_ai.schemas.migrations.Schema__Migration_Record import Schema__Migration_Record

class Schema__Migrations_Applied(Type_Safe):
    records : list[Schema__Migration_Record]
