"""SSH__Allowed_Signers — the allowed-signers file of ssh-keygen(1) (Git's
gpg.ssh.allowedSignersFile), read in-process (design__02 §5.4.4).

    principals [options] keytype base64-key [comment]

Principals are comma-separated patterns (`*`, `?`, a leading `!` negates). Options
handled here: namespaces="…", valid-after="…", valid-before="…" (YYYYMMDD[HHMM[SS]][Z],
local time unless Z; checked against the commit's own time as Git passes
-Overify-time), no-touch-required, verify-required. A `cert-authority` line cannot be
decided in-process: `needs_delegation()` says so and the caller hands the whole
check to ssh-keygen."""
import fnmatch
import time
from   datetime                                     import datetime, timezone
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.signing.SSH__Allowed_Signer   import SSH__Allowed_Signer
from   sgit_ai.crypto.signing.SSH__Public_Key       import SSH__Public_Key
from   sgit_ai.crypto.signing.SSH__Wire             import Vault__SSH_Format_Error

KEY_TYPE_PREFIXES = ('ssh-', 'ecdsa-', 'sk-')


class SSH__Allowed_Signers(Type_Safe):
    entries            : list[SSH__Allowed_Signer]
    has_cert_authority : bool = False

    def load(self, path: str) -> 'SSH__Allowed_Signers':
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return self.parse(f.read())

    def parse(self, text: str) -> 'SSH__Allowed_Signers':
        for number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            try:
                entry = self.parse_line(line)
            except Vault__SSH_Format_Error:
                continue                                    # ssh-keygen skips a line it cannot read, with a message
            entry.line_number = number
            if entry.cert_authority:
                self.has_cert_authority = True
            self.entries.append(entry)
        return self

    def parse_line(self, line: str) -> SSH__Allowed_Signer:
        principals, rest = self.next_token(line)
        options          = {}
        if rest and not rest.startswith(KEY_TYPE_PREFIXES):
            option_text, rest = self.next_token(rest)
            options           = self.parse_options(option_text)
        key_type, rest = self.next_token(rest)
        key_b64, _     = self.next_token(rest)
        key            = SSH__Public_Key().from_openssh_line(f'{key_type} {key_b64}')
        return SSH__Allowed_Signer(principals        = principals.strip('"'),
                                   namespaces        = options.get('namespaces'),
                                   valid_after       = options.get('valid-after'),
                                   valid_before      = options.get('valid-before'),
                                   cert_authority    = 'cert-authority'    in options,
                                   no_touch_required = 'no-touch-required' in options,
                                   verify_required   = 'verify-required'   in options,
                                   key_blob          = key.blob)

    def next_token(self, text: str) -> tuple:
        """(token, rest): one whitespace-separated token, where double quotes protect spaces."""
        text, i, quoted = text.lstrip(), 0, False
        while i < len(text) and (quoted or not text[i].isspace()):
            if text[i] == '"':
                quoted = not quoted
            i += 1
        if quoted:
            raise Vault__SSH_Format_Error('unterminated quote')
        return text[:i], text[i:].lstrip()

    def parse_options(self, text: str) -> dict:
        """name -> value ('' for a flag); commas inside quotes do not split."""
        parts, start, quoted = [], 0, False
        for i, ch in enumerate(text + ','):
            if ch == '"':
                quoted = not quoted
            elif ch == ',' and not quoted:
                parts.append(text[start:i])
                start = i + 1
        options = {}
        for part in parts:
            name, _, value = part.partition('=')
            options[name.strip().lower()] = value.strip().strip('"')
        return options

    # --- matching -----------------------------------------------------------------

    def pattern_list_matches(self, value: str, patterns: str) -> bool:
        """OpenSSH match_pattern_list: some positive pattern matches and no negated one."""
        matched = False
        for pattern in (p.strip() for p in patterns.split(',') if p.strip()):
            if pattern.startswith('!'):
                if fnmatch.fnmatchcase(value, pattern[1:]):
                    return False
            elif fnmatch.fnmatchcase(value, pattern):
                matched = True
        return matched

    def lines_for_key(self, key_blob: bytes) -> list:
        """Every line for this key, in file order (find-principals does not look at namespaces)."""
        return [e for e in self.entries if e.key_blob == key_blob]

    def lines_for(self, key_blob: bytes, namespace: str) -> list:
        """Every line for this key whose namespaces allow `namespace`, in file order."""
        return [e for e in self.entries if e.key_blob == key_blob and
                (e.namespaces is None or self.pattern_list_matches(namespace, str(e.namespaces)))]

    def time_problem(self, entry: SSH__Allowed_Signer, at_time_s: int) -> str:
        """'' when the line is valid at that time, else why not."""
        if entry.valid_after and at_time_s < self.parse_time(str(entry.valid_after)):
            return f'key not valid at the commit time (valid-after {entry.valid_after})'
        if entry.valid_before and at_time_s > self.parse_time(str(entry.valid_before)):
            return f'key not valid at the commit time (valid-before {entry.valid_before})'
        return ''

    def parse_time(self, text: str) -> int:
        utc     = text.endswith(('Z', 'z'))
        body    = text[:-1] if utc else text
        formats = {8: '%Y%m%d', 12: '%Y%m%d%H%M', 14: '%Y%m%d%H%M%S'}
        if len(body) not in formats or not body.isdigit():
            raise Vault__SSH_Format_Error(f'bad time {text!r}')
        parsed = datetime.strptime(body, formats[len(body)])
        if utc:
            return int(parsed.replace(tzinfo=timezone.utc).timestamp())
        return int(time.mktime(parsed.timetuple()))
