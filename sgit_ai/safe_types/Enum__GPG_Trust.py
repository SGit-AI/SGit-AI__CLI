from enum import Enum

TRUST_ORDER = ('undefined', 'never', 'marginal', 'fully', 'ultimate')


class Enum__GPG_Trust(str, Enum):
    """gpg's key validity on a TRUST_* status line, and Git's gpg.minTrustLevel values."""
    UNDEFINED = 'undefined'
    NEVER     = 'never'
    MARGINAL  = 'marginal'
    FULLY     = 'fully'
    ULTIMATE  = 'ultimate'

    def rank(self) -> int:
        return TRUST_ORDER.index(self.value)
