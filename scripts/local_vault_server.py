#!/usr/bin/env python3
"""Start a local SG/Send vault server (in-memory mode) on a given port.

Requires: sgraph-ai-app-send (Python >=3.12)
Usage:    python3.12 scripts/local_vault_server.py [PORT]

The server runs vault pointer endpoints only:
  PUT    /api/vault/write/{vault_id}/{file_id}
  GET    /api/vault/read/{vault_id}/{file_id}
  DELETE /api/vault/delete/{vault_id}/{file_id}

No AWS credentials, no external dependencies — pure in-memory storage.
"""
import sys
import uvicorn
from fastapi import FastAPI
from sgraph_ai_app_send.lambda__user.fast_api.routes.Routes__Vault__Pointer import Routes__Vault__Pointer

def create_app():
    app = FastAPI(title='SG/Send Vault (local)')
    Routes__Vault__Pointer(app=app).setup()
    return app

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18321
    app  = create_app()
    print(f'VAULT_SERVER_READY port={port}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
