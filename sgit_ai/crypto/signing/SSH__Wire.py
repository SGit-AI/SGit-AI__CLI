"""SSH__Wire — RFC 4251 wire encoding over a bytes buffer, every read bounds-checked.

Reads raise Vault__SSH_Format_Error (a ValueError) on a length past the end, so a
hostile blob from the vault can never index outside its own bytes."""
from   osbot_utils.type_safe.Type_Safe                  import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt


class Vault__SSH_Format_Error(ValueError):
    pass


class SSH__Wire(Type_Safe):
    data : bytes
    pos  : Safe_UInt

    def remaining(self) -> int:
        return len(self.data) - int(self.pos)

    def at_end(self) -> bool:
        return self.remaining() == 0

    def read_bytes(self, n: int) -> bytes:
        if n < 0 or n > self.remaining():
            raise Vault__SSH_Format_Error(f'truncated: {n} byte(s) wanted, {self.remaining()} left')
        start    = int(self.pos)
        self.pos = start + n
        return self.data[start:start + n]

    def read_byte(self) -> int:
        return self.read_bytes(1)[0]

    def read_uint32(self) -> int:
        return int.from_bytes(self.read_bytes(4), 'big')

    def read_string(self) -> bytes:
        return self.read_bytes(self.read_uint32())

    def read_mpint(self) -> int:
        """A non-negative mpint (RFC 4251 §5); a negative one is refused (r, s, e, n)."""
        raw = self.read_string()
        if raw and raw[0] & 0x80:
            raise Vault__SSH_Format_Error('negative mpint')
        return int.from_bytes(raw, 'big')

    def expect_end(self, what: str) -> None:
        if not self.at_end():
            raise Vault__SSH_Format_Error(f'{self.remaining()} trailing byte(s) after the {what}')

    # --- writing ------------------------------------------------------------------

    def uint32(self, value: int) -> bytes:
        return int(value).to_bytes(4, 'big')

    def string(self, value: bytes) -> bytes:
        return self.uint32(len(value)) + value

    def mpint(self, value: int) -> bytes:
        if value == 0:
            return self.string(b'')
        raw = value.to_bytes((value.bit_length() + 7) // 8, 'big')
        if raw[0] & 0x80:
            raw = b'\x00' + raw
        return self.string(raw)
