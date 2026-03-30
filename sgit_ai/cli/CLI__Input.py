import select
import sys

from osbot_utils.type_safe.Type_Safe          import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Int import Safe_Int


class Safe_Int__Input_Timeout(Safe_Int):
    min_value = 1
    max_value = 300


class CLI__Input(Type_Safe):
    timeout : Safe_Int__Input_Timeout = 30

    def prompt(self, message: str) -> str | None:
        """Prompt for interactive input with a timeout.

        Returns the stripped input string, or None if:
          - stdin is not a TTY (non-interactive context, e.g. Claude Code)
          - the user does not respond within self.timeout seconds

        Never returns a default value on timeout — the caller must treat
        None as "cancelled" and abort.
        """
        if not sys.stdin.isatty():
            return None

        print(message, end='', flush=True)
        ready, _, _ = select.select([sys.stdin], [], [], int(self.timeout))
        if not ready:
            print(f'\n(no response within {self.timeout}s — cancelled)', flush=True)
            return None

        return sys.stdin.readline().rstrip('\n')
