"""Classification of a per-file download failure during pull/fetch.

Distinguishes three failure kinds:
  - TRANSIENT — server load, connection errors, 5xx — retrying may succeed.
  - ABSENT    — HTTP 404 / server 'not_found' — the object is missing on the
    server; retrying will not help.
  - FORBIDDEN — HTTP 403 — the server refuses to serve the object (commonly a
    missing-from-backing-store, cache, or permission issue); retrying will not
    help and the vault operator should investigate.
"""
from enum import Enum


class Enum__Fetch_Failure_Class(Enum):
    ABSENT    = 'absent'      # 404 / server 'not_found' — object missing on server
    FORBIDDEN = 'forbidden'   # 403 — server denies access (missing backing object / cache / permission)
    TRANSIENT = 'transient'   # 5xx / network / unknown — should retry
