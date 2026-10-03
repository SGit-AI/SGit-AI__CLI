from enum import Enum


class Enum__Api_Docs_Mode(Enum):
    """How the Swagger UI docs page gets its assets (08 §4).

    CDN (default): a ~4 KB HTML page loading swagger-ui-dist from jsdelivr,
    exact-version-pinned with SRI — mismatched bytes do not execute.
    BUNDLED: the pinned files are fetched once, verified against the same SRI
    hashes, cached under ~/.sgit/assets/, and vendored into the output
    (+1.53 MB — offline / no-third-parties deployments).
    A CDN reference without SRI, or a floating tag, is not offered at all.
    """
    CDN     = 'cdn'
    BUNDLED = 'bundled'
