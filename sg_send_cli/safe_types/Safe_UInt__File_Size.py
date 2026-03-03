from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt

MAX_FILE_SIZE = 100 * 1024 * 1024

class Safe_UInt__File_Size(Safe_UInt):
    max_value = MAX_FILE_SIZE
