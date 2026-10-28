"""Vault__Commit_Message — how long a commit message may be in a vault.

740 bytes of UTF-8 by default: what a commit's encrypted message field held before
0.26.4 (1,024 base64 characters, less the IV and the tag); older clients reject a
longer one when they read the commit. A vault with the `long-messages` feature takes
64 KiB, and adding the feature raises its min_client to 0.26.4, so an older client is
told to update instead of failing on the first long message. Git has no limit; 64 KiB
is far above any real commit message and keeps every commit object small.
"""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe

SHORT_MESSAGE_BYTES = 740
LONG_MESSAGE_BYTES  = 64 * 1024


class Vault__Commit_Message_Too_Long_Error(Exception):
    """A commit message over the vault's limit, refused before anything is written.
    Counted in UTF-8 bytes, so non-ASCII text reaches it sooner."""
    def __init__(self, size: int, limit: int, can_raise: bool):
        self.size  = size
        self.limit = limit
        hint = (' Shorten it, or let this vault take messages up to 64 KB: sgit vault format --feature long-messages '
                '(clients older than 0.26.4 cannot read longer messages; the vault then asks them to update).'
                if can_raise else ' Shorten it.')
        super().__init__(f'the commit message is {size:,} bytes (UTF-8) and this vault takes up to {limit:,}.{hint}')


class Vault__Commit_Message(Type_Safe):

    def limit_for(self, branch_index) -> int:
        from sgit_ai.storage.Vault__Format import Vault__Format, FEATURE_LONG_MESSAGES
        long_ok = branch_index is not None and Vault__Format().has_feature(branch_index, FEATURE_LONG_MESSAGES)
        return LONG_MESSAGE_BYTES if long_ok else SHORT_MESSAGE_BYTES

    def check(self, message: str, limit: int) -> None:
        size = len((message or '').encode('utf-8'))
        if size > limit:
            raise Vault__Commit_Message_Too_Long_Error(size, limit, can_raise=limit < LONG_MESSAGE_BYTES)
