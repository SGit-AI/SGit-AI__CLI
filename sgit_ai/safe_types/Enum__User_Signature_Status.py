from enum import Enum

STATUS_CODES = {'good': 'G', 'untrusted': 'U', 'bad': 'B', 'expired-signature': 'X', 'expired-key': 'Y',
                'revoked': 'R', 'cannot-check': 'E', 'none': 'N'}


class Enum__User_Signature_Status(str, Enum):
    """A user signature's verdict, Git's %G? letters as words (design__02 §5.2)."""
    GOOD              = 'good'
    UNTRUSTED         = 'untrusted'
    BAD               = 'bad'
    EXPIRED_SIGNATURE = 'expired-signature'
    EXPIRED_KEY       = 'expired-key'
    REVOKED           = 'revoked'
    CANNOT_CHECK      = 'cannot-check'
    NONE              = 'none'

    def code(self) -> str:
        return STATUS_CODES[self.value]
