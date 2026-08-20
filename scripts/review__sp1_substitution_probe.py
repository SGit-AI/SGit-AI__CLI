"""Review probe: does the SP-1 GCM fallback let a hostile host SWAP two valid
objects (each authentic under the read key) between ids, on a vault that was
never moved? Runs the real clone path against a real HTTP host.
"""
import functools, os, shutil, tempfile, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.core.actions.publish.Vault__Publish import Vault__Publish
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.network.api.Vault__API__Static    import Vault__API__Static
from sgit_ai.safe_types.Enum__Visibility       import Enum__Visibility


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve(d):
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=d))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


tmp    = tempfile.mkdtemp(prefix='sg_review_')
crypto = Vault__Crypto()
api    = Vault__API__In_Memory().setup()
sync   = Vault__Sync(crypto=crypto, api=api)
vault  = os.path.join(tmp, 'vault')
res    = sync.init(vault)

with open(os.path.join(vault, 'allowlist.txt'), 'w') as f:
    f.write('ALLOW: alice\n')
with open(os.path.join(vault, 'denylist.txt'), 'w') as f:
    f.write('DENY: mallory-was-here\n')
sync.commit(vault, 'initial')
sync.push(vault)
Vault__Publish(crypto=crypto, api=api).publish(vault, visibility=Enum__Visibility.PUBLIC)

site = os.path.join(tmp, 'site')
os.makedirs(site)
shutil.copytree(os.path.join(vault, '.sg_vault', 'bare'), os.path.join(site, 'bare'))
for n in os.listdir(os.path.join(vault, '.sg_vault', 'publish')):
    s = os.path.join(vault, '.sg_vault', 'publish', n)
    if os.path.isfile(s):
        shutil.copy(s, os.path.join(site, n))

# --- honest clone, for the baseline -------------------------------------------
httpd, url = serve(site)
honest = os.path.join(tmp, 'clone_honest')
t = Vault__API__Static(base_url=url); t.setup()
Vault__Sync(crypto=crypto, api=t).clone(res['vault_key'], honest)
httpd.shutdown()
print('honest clone   :', sorted(os.listdir(honest)))
for n in ('allowlist.txt', 'denylist.txt'):
    p = os.path.join(honest, n)
    if os.path.isfile(p):
        print(f'   {n}: {open(p).read()!r}')

# --- hostile host: swap the two blobs' BYTES between their ids ----------------
data_dir = os.path.join(site, 'bare', 'data')
blobs    = {}
for n in os.listdir(data_dir):
    with open(os.path.join(data_dir, n), 'rb') as f:
        raw = f.read()
    try:
        blobs[n] = crypto.decrypt(crypto.derive_keys_from_vault_key(res['vault_key'])['read_key_bytes'], raw)
    except Exception:
        pass
targets = [n for n, pt in blobs.items() if b'ALLOW' in pt or b'DENY' in pt]
print('\nswappable blobs:', len(targets))
if len(targets) >= 2:
    a, b = targets[0], targets[1]
    pa   = os.path.join(data_dir, a)
    pb   = os.path.join(data_dir, b)
    da   = open(pa, 'rb').read()
    db   = open(pb, 'rb').read()
    open(pa, 'wb').write(db)          # object A now serves B's authentic ciphertext
    open(pb, 'wb').write(da)
    print(f'swapped {a} <-> {b}')

httpd, url = serve(site)
eviljob = os.path.join(tmp, 'clone_hostile')
t2 = Vault__API__Static(base_url=url); t2.setup()
try:
    Vault__Sync(crypto=crypto, api=t2).clone(res['vault_key'], eviljob)
except Exception as e:
    print('clone raised:', type(e).__name__, e)
httpd.shutdown()

print('\nhostile clone  :', sorted(os.listdir(eviljob)) if os.path.isdir(eviljob) else 'MISSING')
for n in ('allowlist.txt', 'denylist.txt'):
    p = os.path.join(eviljob, n)
    if os.path.isfile(p):
        print(f'   {n}: {open(p).read()!r}')
    else:
        print(f'   {n}: NOT WRITTEN (refused)')
shutil.rmtree(tmp, ignore_errors=True)
