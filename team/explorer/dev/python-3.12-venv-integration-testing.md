# Python 3.12 Venv + Integration Testing Setup

## Problem

The default Python environment uses Python 3.11, but the `sgraph-ai-app-send` package (which provides the in-memory SG/Send test server) requires Python >= 3.12. This means integration tests that run against a real SG/Send server instance need a separate Python 3.12 virtual environment.

## Solution: Dual-Python Setup

### 1. Create the Python 3.12 venv

```bash
python3.12 -m venv /tmp/sg-send-venv-312
```

### 2. Install dependencies

```bash
/tmp/sg-send-venv-312/bin/pip install -e ".[dev]"
/tmp/sg-send-venv-312/bin/pip install sgraph-ai-app-send
```

The `sgraph-ai-app-send` package includes:
- `setup__send_user_lambda__test_server()` — starts a real HTTP server with in-memory S3 storage
- FastAPI-based SG/Send server with all vault endpoints (read, write, delete, batch, list)
- No external dependencies needed (no real S3, no database)

### 3. Run integration tests

```bash
# Integration tests (require Python 3.12 + sgraph-ai-app-send)
/tmp/sg-send-venv-312/bin/python -m pytest tests/integration/ -v

# Unit tests (work with default Python 3.11)
python -m pytest tests/unit/ -v
```

## How the Test Server Works

The integration test fixtures are defined in `tests/integration/conftest.py`:

```python
@pytest.fixture(scope='session')
def test_server():
    """Start an in-memory SG/Send server for the entire test session."""
    from sgraph_ai_app_send.testing import setup__send_user_lambda__test_server
    server_info = setup__send_user_lambda__test_server()
    yield server_info
    # Server is automatically cleaned up

@pytest.fixture
def vault_api(test_server):
    """Create a Vault__API client pointing at the test server."""
    api = Vault__API()
    api.base_url     = test_server['url']
    api.access_token = test_server['token']
    return api
```

Key details:
- **Session-scoped**: The server starts once and is shared across all tests in the session
- **In-memory S3**: All vault data is stored in memory — no disk I/O, no cleanup needed
- **Real HTTP**: Tests make actual HTTP requests to a real FastAPI server running on localhost
- **All endpoints**: batch, list, read, write, delete — the full vault API surface

## Available Endpoints on Test Server

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/vault/batch/{vault_id}` | Batch operations (write, write-if-match, delete) |
| GET | `/api/vault/list/{vault_id}/{prefix}` | List files with optional prefix |
| GET | `/api/vault/read/{vault_id}/{file_id}` | Read a single file |
| POST | `/api/vault/write/{vault_id}/{file_id}` | Write a single file |
| DELETE | `/api/vault/delete/{vault_id}/{file_id}` | Delete a single file |

## When to Use Each Environment

| Test Type | Python | Command |
|-----------|--------|---------|
| Unit tests (mocked APIs) | 3.11 (default) | `pytest tests/unit/` |
| Integration tests (real server) | 3.12 (venv) | `/tmp/sg-send-venv-312/bin/python -m pytest tests/integration/` |
| All tests | Both | Run unit tests first, then integration tests |

## Troubleshooting

### "python3.12 not found"
Check available Python versions: `ls /usr/bin/python3.*` or `which python3.12`

### "ModuleNotFoundError: sgraph_ai_app_send"
Install in the 3.12 venv: `/tmp/sg-send-venv-312/bin/pip install sgraph-ai-app-send`

### Venv doesn't persist between sessions
The venv is created in `/tmp/` which may be cleared on reboot. Re-run the setup steps above.
