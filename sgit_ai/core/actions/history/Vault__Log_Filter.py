"""Vault__Log_Filter — `sgit history log --grep/--since/--until/--author`.

Filtering happens on the client, after the commits are decrypted (the host can
never search them). --author matches, case-insensitively, the commit's branch name
exactly, or its signing key id / branch id: whole, by 4+ hex at the start or end of the
random part, or by a prefix that reaches 4+ hex into it (`key-1` no longer matches
`key-12…`: review nit). Dates: 2026-10-08, 2026-10-08T14:30, ISO with `Z` or an
offset, or relative: 30m, 12h, 3d, 2w, 6mo, 1y, "3 days ago", "yesterday", "today".
--until is inclusive: an exact time includes a commit made at that moment.
"""
import datetime
import re
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from   sgit_ai.core.Vault__Errors                      import Vault__Revision_Error
from   sgit_ai.safe_types.Safe_Str__Tag_Message        import Safe_Str__Tag_Message

_UNITS    = {'m': 60, 'min': 60, 'minute': 60, 'h': 3600, 'hour': 3600, 'd': 86400, 'day': 86400,
             'w': 604800, 'week': 604800, 'mo': 2592000, 'month': 2592000, 'y': 31536000, 'year': 31536000}
_RELATIVE = re.compile(r'^(\d+)\s*(mo|months?|y|years?|m|min|minutes?|h|hours?|d|days?|w|weeks?)(\s+ago)?$',
                       re.IGNORECASE)
_NESTED   = re.compile(r'\((?:[^()\\]|\\.)*[+*}]\)\s*[+*{]')           # (a+)+, (x*)*, (a{2,})+ ...


class Vault__Log_Filter(Type_Safe):
    grep     : Safe_Str__Tag_Message = None          # a case-insensitive regular expression on the message
    author   : Safe_Str__Tag_Message = None
    since_ms : Safe_UInt
    until_ms : Safe_UInt

    def setup(self, grep: str = None, since: str = None, until: str = None, author: str = None, now_ms: int = None):
        now = int(now_ms if now_ms is not None else datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        if grep:
            try:
                re.compile(grep)
            except re.error as error:
                raise Vault__Revision_Error(f'--grep {grep!r} is not a valid regular expression: {error}')
            if _NESTED.search(grep):                                 # `(a+)+$` took 7 s on one message (review nit)
                raise Vault__Revision_Error(f'--grep {grep!r} repeats a repetition (like (a+)+), which can take '
                                            f'exponential time; write it without the outer repeat')
            self.grep = grep
        if author:
            self.author = author
        if since:
            self.since_ms = self.parse_when(since, now)
        if until:
            self.until_ms = self.parse_when(until, now, end_of_day=True)
        return self

    def active(self) -> bool:
        return bool(self.grep or self.author or int(self.since_ms) or int(self.until_ms))

    def parse_when(self, text: str, now_ms: int, end_of_day: bool = False) -> int:
        t = str(text).strip().lower()
        if t in ('today', 'yesterday'):
            day = datetime.datetime.fromtimestamp(now_ms / 1000, tz=datetime.timezone.utc).date()
            if t == 'yesterday':
                day -= datetime.timedelta(days=1)
            start = datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc)
            return int((start + (datetime.timedelta(days=1) if end_of_day else datetime.timedelta(0))).timestamp() * 1000)
        m = _RELATIVE.match(t)
        if m:
            unit = m.group(2).lower()
            unit = unit[:-1] if unit.endswith('s') and unit not in ('s',) else unit
            return now_ms - int(m.group(1)) * _UNITS[unit] * 1000
        raw = str(text).strip()
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):                    # a day: --until includes all of it
            day  = datetime.datetime.strptime(raw, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            when = day + datetime.timedelta(days=1) - datetime.timedelta(milliseconds=1) if end_of_day else day
            return int(when.timestamp() * 1000)
        try:                                                           # ISO times, with Z or an offset
            when = datetime.datetime.fromisoformat(raw.replace('Z', '+00:00').replace(' ', 'T', 1))
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime.timezone.utc)
            return int(when.timestamp() * 1000)
        except ValueError:
            pass
        raise Vault__Revision_Error(f'{text!r} is not a date this CLI understands '
                                    f'(2026-10-08, 2026-10-08T14:30Z, 3d, 12h, 2w, 6mo, 1y, "3 days ago", yesterday)')

    def _author_matches(self, needle: str, value: str) -> bool:
        """The whole value (a branch name or a full id); 4+ hex at the start or the end of an
        id's random part (what people copy from `history log`); or a prefix of the full id
        that reaches 4+ hex into it. A substring anywhere over-matched: `key-1` matched
        `key-12…` (review nit)."""
        if value == needle:
            return True
        if not re.fullmatch(r'(key|branch)-[a-z]+-[a-z0-9-]*[0-9a-f]{8,}', value):
            return False                                                   # a branch name: exact only
        hex_part = value.rsplit('-', 1)[-1]
        if re.fullmatch(r'[0-9a-f]{4,}', needle):
            return hex_part.startswith(needle) or hex_part.endswith(needle)
        return value.startswith(needle) and len(needle) - (len(value) - len(hex_part)) >= 4

    def matches(self, entry: dict, branch_names: dict = None) -> bool:
        if 'error' in entry:
            return False
        ts = int(entry.get('timestamp_ms') or 0)
        if int(self.since_ms) and ts < int(self.since_ms):
            return False
        if int(self.until_ms) and ts > int(self.until_ms):              # inclusive (review nit)
            return False
        if self.grep and not re.search(str(self.grep), entry.get('message') or '', re.IGNORECASE):
            return False
        if self.author:
            needle = str(self.author).lower()
            bid    = entry.get('branch_id') or ''
            hay    = [entry.get('author_key_id') or '', bid, (branch_names or {}).get(bid, '')]
            if not any(self._author_matches(needle, h.lower()) for h in hay if h):
                return False
        return True
