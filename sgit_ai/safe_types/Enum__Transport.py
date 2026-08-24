from enum import Enum


class Enum__Transport(Enum):
    """How a command reaches a vault's objects.

    AUTO resolves at the CLI boundary: a non-http(s) base_url is unambiguously
    LOCAL; an http(s) one is API when the batch endpoint answers, STATIC when
    it does not (404/405/501). The resolved transport is always reported —
    visible, never silent — so auto-detection cannot hide a deployment mistake.
    """
    AUTO   = 'auto'      # resolve at the boundary, report the result
    API    = 'api'       # live SG/API — batch, writes, auth
    STATIC = 'static'    # any GET host — read-only fan-out
    LOCAL  = 'local'     # a folder — open(), no network
