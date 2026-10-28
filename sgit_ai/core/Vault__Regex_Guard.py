"""Vault__Regex_Guard — one check for every user-supplied regular expression that sgit runs
over vault content: `history log --grep`, `sgit grep`, the pickaxe (design__04 §5.9).

A valid pattern of at most MAX_PATTERN_CHARS characters, with no repetition that holds
another repetition inside it (catastrophic backtracking: `(a+)+$` took 7 s on one commit
message). Moved from Vault__Log_Filter, which delegates; its rules are unchanged."""
import re
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   sgit_ai.core.Vault__Errors                      import Vault__Revision_Error

OUTER_REPEAT_MAX  = 3                                  # (ab*){2} is fine; (a+){10} is not
MAX_PATTERN_CHARS = 1000


class Vault__Regex_Guard(Type_Safe):

    def check(self, pattern: str, what: str = '--grep', flags: int = re.IGNORECASE):
        """The compiled pattern, or Vault__Revision_Error naming `what` and the reason."""
        if len(pattern) > MAX_PATTERN_CHARS:
            raise Vault__Revision_Error(f'{what} pattern is {len(pattern)} characters; the limit is {MAX_PATTERN_CHARS}')
        try:
            compiled = re.compile(pattern, flags)
        except re.error as error:
            raise Vault__Revision_Error(f'{what} {pattern!r} is not a valid regular expression: {error}')
        if self.nested_repeat(pattern):
            raise Vault__Revision_Error(f'{what} {pattern!r} repeats a repetition (like (a+)+), which can take '
                                        f'exponential time; write it without the outer repeat')
        return compiled

    def nested_repeat(self, pattern: str) -> bool:
        """True when a repetition that can run more than OUTER_REPEAT_MAX times holds another
        repetition anywhere inside it: (a+)+, (a+|b)+, ((a+))+, (a{2,})*, (a+){10}. Read from
        the parsed pattern, not its text: a text match missed `(a+|b)+$` (46 s) and
        `((a+))+$` (30 s), and refused the harmless `(ab*){2}` (review eed8084 F4).
        A repetition whose every round starts with a character none of the repetitions
        inside it can match is allowed: each round then has one way to split, as in
        `[a-z]+(-[a-z]+)*` or `(/[^/]+)+`."""
        try:
            import re._parser as sre_parse                     # Python 3.11+
        except ImportError:                                    # pragma: no cover
            import sre_parse
        return self._has_nested(sre_parse.parse(pattern), sre_parse, outer=False)

    def _has_nested(self, sub, sre_parse, outer: bool) -> bool:
        repeats = {sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT, getattr(sre_parse, 'POSSESSIVE_REPEAT', None)}
        for op, av in sub:
            if op in repeats:
                low, high, body = av
                many = high == sre_parse.MAXREPEAT or high > OUTER_REPEAT_MAX
                if outer and high > 1:
                    return True                                # a repetition inside a repetition
                if many and not outer and self._separated(body, sre_parse):
                    continue
                if self._has_nested(body, sre_parse, outer or many):
                    return True
            else:
                for child in self._children(av, sre_parse):
                    if self._has_nested(child, sre_parse, outer):
                        return True
        return False

    def _separated(self, body, sre_parse) -> bool:
        """The body starts with a literal character, and every repetition inside it repeats
        one item that cannot match that character."""
        body = self._unwrap(body, sre_parse)
        if not len(body) or body[0][0] != sre_parse.LITERAL:
            return False
        sep     = body[0][1]
        repeats = {sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT, getattr(sre_parse, 'POSSESSIVE_REPEAT', None)}
        for op, av in list(body)[1:]:
            if op in repeats:
                inner = self._unwrap(av[2], sre_parse)
                cases = {sep, ord(chr(sep).lower()[0]), ord(chr(sep).upper()[0])}     # --grep is case-insensitive
                if len(inner) != 1 or any(self._item_matches(inner[0], c, sre_parse) for c in cases):
                    return False
            elif op not in (sre_parse.LITERAL, sre_parse.NOT_LITERAL, sre_parse.IN, sre_parse.ANY, sre_parse.AT):
                return False                                   # groups, branches …: not judged, refused as before
        return True

    def _unwrap(self, sub, sre_parse):
        while len(sub) == 1 and sub[0][0] == sre_parse.SUBPATTERN:
            sub = sub[0][1][-1]
        return sub

    def _item_matches(self, item, char: int, sre_parse) -> bool:
        """Can one regex item match chr(char)? True when unsure."""
        op, av = item
        if op == sre_parse.LITERAL:
            return av == char
        if op == sre_parse.NOT_LITERAL:
            return av != char
        if op == sre_parse.ANY:
            return True
        if op != sre_parse.IN:
            return True
        negate, hit = False, False
        for kind, value in av:
            if kind == sre_parse.NEGATE:
                negate = True
            elif kind == sre_parse.LITERAL:
                hit = hit or value == char
            elif kind == sre_parse.RANGE:
                hit = hit or value[0] <= char <= value[1]
            elif kind == sre_parse.CATEGORY:
                probe = {sre_parse.CATEGORY_DIGIT: r'\d', sre_parse.CATEGORY_NOT_DIGIT: r'\D',
                         sre_parse.CATEGORY_WORD:  r'\w', sre_parse.CATEGORY_NOT_WORD:  r'\W',
                         sre_parse.CATEGORY_SPACE: r'\s', sre_parse.CATEGORY_NOT_SPACE: r'\S'}.get(value)
                hit = hit or probe is None or re.match(probe, chr(char)) is not None
            else:
                return True
        return hit != negate

    def _children(self, av, sre_parse) -> list:
        if isinstance(av, sre_parse.SubPattern):
            return [av]
        if isinstance(av, (list, tuple)):
            return [c for item in av for c in self._children(item, sre_parse)]
        return []
