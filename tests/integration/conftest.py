import os
import tempfile
import shutil

import pytest

from sg_send_cli.api.Vault__API       import Vault__API
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto

try:
    from sgraph_ai_app_send.lambda__user.testing.Send__User_Lambda__Test_Server import setup__send_user_lambda__test_server
    HAS_SEND_LAMBDA = True
except ImportError:
    HAS_SEND_LAMBDA = False


@pytest.fixture(scope='session')
def send_server():
    """Start a real HTTP server running the SG/Send User Lambda (in-memory storage).

    Returns the test_objs with server_url, access_token, write_key.
    The server starts once per test session and shuts down at the end.
    """
    if not HAS_SEND_LAMBDA:
        pytest.skip('sgraph-ai-app-send not installed — run: pip install sgraph-ai-app-send')
    with setup__send_user_lambda__test_server() as test_objs:
        yield test_objs


@pytest.fixture()
def vault_api(send_server):
    """A Vault__API instance pointed at the local test server."""
    api = Vault__API(base_url=send_server.server_url, access_token=send_server.access_token)
    api.setup()
    return api


@pytest.fixture()
def crypto():
    return Vault__Crypto()


@pytest.fixture()
def temp_dir():
    d = tempfile.mkdtemp(prefix='sg_vault_test_')
    yield d
    shutil.rmtree(d, ignore_errors=True)
