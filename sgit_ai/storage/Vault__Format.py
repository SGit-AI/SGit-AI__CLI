"""Vault__Format — the per-vault format gate, read from the branch index.

A vault says which client may touch it (`min_client`), which object-id width new
objects get (`format`: 1 = 12 hex, 2 = 32 hex) and which policies apply
(`features`). Every existing vault has none of these fields and reads as
format 1 with no minimum. The gate fails open: a writer that drops the fields
leaves the vault at format 1, which every client understands.
"""
import re
from osbot_utils.type_safe.Type_Safe                 import Type_Safe
from sgit_ai.schemas.Schema__Branch_Index            import Schema__Branch_Index

FORMAT_1            = 1
FORMAT_2            = 2
ID_HEX_LEN          = {FORMAT_1: 12, FORMAT_2: 32}
FEATURE_IDS_128     = 'ids-128'
FEATURE_SIG_REQUIRED = 'signatures-required'
SIG_SINCE_PREFIX     = 'signed-since-'                       # + the first 24 hex of the head when the policy was switched on
SIG_SINCE_HEX        = 24
VERSION_RE          = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)')


class Vault__Client_Too_Old_Error(Exception):
    """This client is below the vault's min_client; the message names both versions."""


class Vault__Format(Type_Safe):

    def client_version(self) -> str:
        """The installed version, read from the package's `version` file (the storage
        layer may not import sgit_ai._version); 'v0.0.0-dev' when absent, which the
        comparison treats as 'never refuse'."""
        import os
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'version')) as f:
                return f.read().strip() or 'v0.0.0-dev'
        except OSError:
            return 'v0.0.0-dev'

    def parse_version(self, text) -> tuple:
        """(major, minor, patch) from 'v0.20.1', '0.20.1rc1', '0.20.1.dev3'; None when unparseable."""
        m = VERSION_RE.match(str(text or '').strip())
        if not m:
            return None
        v = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None if v == (0, 0, 0) else v                 # 0.0.0 is a dev checkout, not a version

    def format_of(self, index: Schema__Branch_Index) -> int:
        try:
            value = int(index.format) if index is not None and index.format is not None else FORMAT_1
        except Exception:
            value = FORMAT_1
        return value if value in ID_HEX_LEN else FORMAT_1

    def id_hex_len(self, index: Schema__Branch_Index) -> int:
        return ID_HEX_LEN[self.format_of(index)]

    def features_of(self, index: Schema__Branch_Index) -> list:
        return [str(f) for f in (getattr(index, 'features', None) or [])]

    def has_feature(self, index: Schema__Branch_Index, name: str) -> bool:
        return name in self.features_of(index)

    def sig_anchor_feature(self, commit_id: str) -> str:
        """The feature string that records where `signatures-required` starts: commits
        after this one must verify; this one and its history are what the vault had
        before the policy (a clone of an older vault must not be refused for them).
        An unknown feature to older clients, which ignore it."""
        hex_part = str(commit_id or '').rsplit('-', 1)[-1][:SIG_SINCE_HEX]
        return SIG_SINCE_PREFIX + hex_part if hex_part else ''

    def sig_anchor_of(self, index: Schema__Branch_Index) -> str:
        """The hex prefix recorded by sig_anchor_feature, or ''."""
        for f in self.features_of(index):
            if f.startswith(SIG_SINCE_PREFIX):
                value = f[len(SIG_SINCE_PREFIX):]
                return value if re.fullmatch(r'[0-9a-f]{12,%d}' % SIG_SINCE_HEX, value) else ''   # 'signed-since-0' names
        return ''                                                                              # no commit: ignored

    def min_client_of(self, index: Schema__Branch_Index) -> str:
        return str(index.min_client) if index is not None and index.min_client else ''

    def check_client(self, index: Schema__Branch_Index, client_version: str = None) -> None:
        """Raise Vault__Client_Too_Old_Error when the vault needs a newer client. An
        unparseable min_client is treated as no minimum (a typo must never lock a vault);
        an unparseable client version (a dev checkout) is never refused either."""
        needed = self.parse_version(self.min_client_of(index))
        if needed is None:
            return
        have_text = client_version or self.client_version()
        have      = self.parse_version(have_text)
        if have is None or have >= needed:
            return
        raise Vault__Client_Too_Old_Error(
            f'this vault needs sgit-ai >= {".".join(map(str, needed))} and this is '
            f'{".".join(map(str, have))}: run `sgit update`, then try again')

    def describe(self, index: Schema__Branch_Index) -> str:
        parts = [f'format {self.format_of(index)} ({self.id_hex_len(index)}-hex object ids)']
        if self.min_client_of(index):
            parts.append(f'min client {self.min_client_of(index)}')
        if self.features_of(index):
            parts.append('features: ' + ', '.join(self.features_of(index)))
        return '; '.join(parts)
