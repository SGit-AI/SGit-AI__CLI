"""VERSION — resolved from the `version` file release automation maintains.

This used to be a hand-written literal, which went stale: it still said v0.1.0
while the released package was v0.16.1, and `Vault__Publish` stamps it into
every published `manifest.json` as `generated_by`. So every published vault
misreported the version that produced it. Read the same file `sgit --version`
reads, and keep the literal only as the fallback for a source tree where the
file is absent.
"""
import os

VERSION_FILE    = os.path.join(os.path.dirname(__file__), 'version')
FALLBACK_VERSION = 'v0.0.0-dev'


def _resolve_version() -> str:                     # noqa: module-level by necessity —
    try:                                           # this must run at import time, before
        with open(VERSION_FILE) as f:              # any class is available to hold it
            found = f.read().strip()
            return found or FALLBACK_VERSION
    except OSError:
        return FALLBACK_VERSION


VERSION = _resolve_version()
