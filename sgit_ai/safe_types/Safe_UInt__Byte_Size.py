from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt

MAX_BYTE_SIZE = 100 * 1024 * 1024 * 1024  # 100 GB

class Safe_UInt__Byte_Size(Safe_UInt):
    max_value = MAX_BYTE_SIZE
