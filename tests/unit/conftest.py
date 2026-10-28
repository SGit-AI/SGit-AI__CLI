"""Unit tests are hermetic: they never reach the internet.

The default server is a closed local port and any connection to a non-loopback
host fails the test by name (tests/_helpers/hermetic_network.py, shared with
tests/security). Integration tests (tests/integration) are where real servers belong.
"""
from tests._helpers.hermetic_network import install, _no_network      # noqa: F401 — autouse fixture

install()

# User signing reads the user's Git config (sgit.gpgSign, user.signingKey, gpg.*). Unit tests
# never see the machine's own ~/.gitconfig or /etc/gitconfig: an empty global file, no system
# file. A test that needs a config points GIT_CONFIG_GLOBAL at its own (monkeypatch).
import os as _os
import tempfile as _tempfile
_EMPTY_GIT_CONFIG = _os.path.join(_tempfile.mkdtemp(prefix='sgit-unit-gitconfig-'), 'gitconfig')
open(_EMPTY_GIT_CONFIG, 'w').close()
_os.environ['GIT_CONFIG_GLOBAL']   = _EMPTY_GIT_CONFIG
_os.environ['GIT_CONFIG_NOSYSTEM'] = '1'
