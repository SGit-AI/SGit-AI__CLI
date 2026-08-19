"""READER: real read-only static clone from a 'GitHub Pages' URL.
Real: Vault__Sync.clone_read_only + spike Vault__API__Static (repo code).
Only the hosting (local http.server standing in for Pages CDN) is simulated."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
os.environ.setdefault('NO_PROXY', '127.0.0.1,localhost')
from importlib import import_module
spike = import_module('spike__static_vault_transport')
from sgit_ai.core.Vault__Sync      import Vault__Sync
from sgit_ai.crypto.Vault__Crypto  import Vault__Crypto

base_url, vault_id, read_key, dest = sys.argv[1:5]
crypto = Vault__Crypto()
kind   = crypto.classify_key(read_key)                     # real classifier (67c2ab6)
print(f'key classified as : {kind}')
hexkey = crypto.strip_key_prefix(read_key)
st = spike.Vault__API__Static(base_url=base_url); st.setup()
sync = Vault__Sync(crypto=crypto, api=st)
r = sync.clone_read_only(vault_id, hexkey, dest)
print(f'layout sniffed    : {st._layout}')
print(f'cloned            : {sorted(r.get("files", r.keys()) if isinstance(r, dict) else [])}')
for root, dirs, files in os.walk(dest):
    if '.sg_vault' in root: continue
    dirs[:] = [d for d in dirs if d != '.sg_vault']
    for f in sorted(files):
        print('  file:', os.path.relpath(os.path.join(root, f), dest))
