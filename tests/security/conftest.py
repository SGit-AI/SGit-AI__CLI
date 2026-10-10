"""Security and adversarial tests are hermetic, like unit tests: the adversary is
the in-memory host (Vault__API__In_Memory) or local files, never a real server."""
from tests._helpers.hermetic_network import install, _no_network      # noqa: F401 — autouse fixture

install()
