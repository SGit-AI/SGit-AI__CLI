"""Vault__Path_Quote — a vault path printed as Git prints it (core.quotePath, on by
default): a path holding a control character, a double quote, a backslash or a byte
over 0x7F is shown in double quotes with C escapes, other bytes as three-digit octal
(`"jos\\303\\251.md"`). A name from the vault can therefore never forge an output line
(`a\\nb` cannot start a new grep match). quote_non_ascii=False is core.quotePath=false."""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe

C_ESCAPES = {0x07: 'a', 0x08: 'b', 0x09: 't', 0x0a: 'n', 0x0b: 'v', 0x0c: 'f', 0x0d: 'r', 0x22: '"', 0x5c: '\\'}


class Vault__Path_Quote(Type_Safe):
    quote_non_ascii : bool = True

    def needs_quoting(self, path: str) -> bool:
        return any(ord(ch) < 0x20 or ch in '"\\' or ord(ch) == 0x7f or (self.quote_non_ascii and ord(ch) > 0x7f)
                   for ch in path)

    def quote(self, path: str) -> str:
        if not self.needs_quoting(path):
            return path
        out = []
        for ch in path:
            if ord(ch) > 0x7f and not self.quote_non_ascii:
                out.append(ch)
                continue
            for byte in ch.encode('utf-8', 'surrogateescape'):
                if byte in C_ESCAPES:
                    out.append('\\' + C_ESCAPES[byte])
                elif byte < 0x20 or byte >= 0x7f:
                    out.append(f'\\{byte:03o}')
                else:
                    out.append(chr(byte))
        return '"' + ''.join(out) + '"'
