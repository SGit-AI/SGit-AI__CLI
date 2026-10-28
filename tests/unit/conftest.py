"""Unit tests are hermetic: they never reach the internet.

The default server is a closed local port and any connection to a non-loopback
host fails the test by name (tests/_helpers/hermetic_network.py, shared with
tests/security). Integration tests (tests/integration) are where real servers belong.
"""
from tests._helpers.hermetic_network import install, _no_network      # noqa: F401 — autouse fixture

install()
