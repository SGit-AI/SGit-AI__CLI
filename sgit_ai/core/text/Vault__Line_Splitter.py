"""Vault__Line_Splitter — bytes to lines, and lines to comparable ids.

A line is the bytes up to and including `\\n`; the last line may lack it. `\\r` stays
part of the line, so `a\\r\\n` and `a\\n` differ, as in Git without whitespace options.
Lines are interned to small ints shared across every side being compared, so the
differ compares ints, not bytes (design__01 §5.3, shared with design__04 by F1).
"""
import re
from   osbot_utils.type_safe.Type_Safe import Type_Safe

BINARY_PROBE_BYTES = 8000                      # Git's buffer_is_binary: a NUL in the first 8000 bytes
WHITESPACE         = re.compile(rb'[ \t\r\n\f\v]+')


class Vault__Line_Splitter(Type_Safe):
    ignore_whitespace : bool = False           # `-w`: lines compare equal when they differ only in whitespace

    def split(self, data: bytes) -> list:
        """The lines of `data`, each keeping its line ending. Only `\n` ends a line
        (bytes.splitlines also breaks on \r, \x0b, \x0c, \x1c-\x1e and \x85; Git does not)."""
        if not data:
            return []
        lines = data.split(b'\n')
        out   = [line + b'\n' for line in lines[:-1]]
        if lines[-1]:
            out.append(lines[-1])
        return out

    def is_binary(self, data: bytes) -> bool:
        return b'\x00' in data[:BINARY_PROBE_BYTES]

    def intern(self, *sides) -> list:
        """One list of int ids per side (each side a list of lines): equal ids for lines
        that compare equal, with one table shared by all sides."""
        table = {}
        ids   = []
        for lines in sides:
            ids.append([table.setdefault(self.key(line), len(table)) for line in lines])
        return ids

    def key(self, line: bytes) -> bytes:
        return WHITESPACE.sub(b'', line) if self.ignore_whitespace else line
