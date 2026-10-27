from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt        import Safe_UInt


class Schema__Pack_Index__Totals(Type_Safe):
    files   : Safe_UInt
    bytes   : Safe_UInt
    folders : Safe_UInt
