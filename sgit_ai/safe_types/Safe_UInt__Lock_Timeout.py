from osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt

MAX_LOCK_TIMEOUT = 86400                                                        # 24 hours

class Safe_UInt__Lock_Timeout(Safe_UInt):
    max_value = MAX_LOCK_TIMEOUT
