from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt

MAX_LINE_NUMBER = 100_000_000                       # far above the merge and blame caps


class Safe_UInt__Line_Number(Safe_UInt):
    max_value = MAX_LINE_NUMBER
