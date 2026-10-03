from enum import Enum


class Enum__Visibility(Enum):
    """How much a published folder discloses (decision 5; fully used in P4).

    BARE   — unlisted, NOT access-controlled: no key file published; readers
             need the read key from another channel. manifest.json still
             discloses estate shape (object count/sizes/cadence) — required
             for keyless custody, disclosed on purpose (SP-12).
    NAMED  — as BARE plus a human-facing cover.
    PUBLIC — the read key is published in the folder; anyone with the URL can
             read every file, now and in every future publish. Irreversible:
             copies cannot be recalled.
    """
    BARE   = 'bare'
    NAMED  = 'named'
    PUBLIC = 'public'
