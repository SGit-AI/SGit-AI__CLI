from enum import Enum


class Enum__Sign_Choice(str, Enum):
    """A command's signing flag: -S / --gpg-sign (on) or --no-gpg-sign (off); None = config decides."""
    ON  = 'on'
    OFF = 'off'
