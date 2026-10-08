"""Vault__Log_Filter — `sgit history log --grep/--since/--until/--author`.

Filtering happens on the client, after the commits are decrypted (the host can
never search them). --author matches, case-insensitively and as a substring,
the commit's signing key id, its branch id or that branch's name in the index.
Dates: 2026-10-08, 2026-10-08T14:30, or relative: 3d, 12h, 2w, 30m,
"3 days ago", "yesterday", "today".
"""
import datetime
import re
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from   sgit_ai.core.Vault__Errors                      import Vault__Revision_Error
from   sgit_ai.safe_types.Safe_Str__Tag_Message        import Safe_Str__Tag_Message

_UNITS    = {'m': 60, 'min': 60, 'minute': 60, 'h': 3600, 'hour': 3600, 'd': 86400, 'day': 86400,
             'w': 604800, 'week': 604800}
_RELATIVE = re.compile(r'^(\d+)\s*(m|min|minutes?|h|hours?|d|days?|w|weeks?)(\s+ago)?$', re.IGNORECASE)


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
            unit = m.group(2).lower().rstrip('s')
            unit = {'minute': 'minute', 'min': 'min', 'hour': 'hour', 'day': 'day', 'week': 'week'}.get(unit, unit)
            return now_ms - int(m.group(1)) * _UNITS[unit] * 1000
        for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                when = datetime.datetime.strptime(str(text).strip(), fmt).replace(tzinfo=datetime.timezone.utc)
                if end_of_day and fmt == '%Y-%m-%d':
                    when += datetime.timedelta(days=1)
                return int(when.timestamp() * 1000)
            except ValueError:
                continue
        raise Vault__Revision_Error(f'{text!r} is not a date this CLI understands '
                                    f'(2026-10-08, 2026-10-08T14:30, 3d, 12h, 2w, "3 days ago", yesterday)')

    def matches(self, entry: dict, branch_names: dict = None) -> bool:
        if 'error' in entry:
            return False
        ts = int(entry.get('timestamp_ms') or 0)
        if int(self.since_ms) and ts < int(self.since_ms):
            return False
        if int(self.until_ms) and ts >= int(self.until_ms):
            return False
        if self.grep and not re.search(str(self.grep), entry.get('message') or '', re.IGNORECASE):
            return False
        if self.author:
            needle = str(self.author).lower()
            bid    = entry.get('branch_id') or ''
            hay    = [entry.get('author_key_id') or '', bid, (branch_names or {}).get(bid, '')]
            if not any(needle in h.lower() for h in hay if h):
                return False
        return True
