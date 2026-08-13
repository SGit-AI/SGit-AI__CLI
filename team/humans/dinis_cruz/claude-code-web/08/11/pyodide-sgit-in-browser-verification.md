# Verified: sgit-ai v0.14.27 runs in the browser under Pyodide

**Date:** 2026-08-11
**Author:** Claude Code (web session), responding to the SGraph-AI__Tools handoff
(`pyodide-sgit-handoff`, 17 Jun 2026)
**Method:** real headless Chromium (Playwright) in the CCW sandbox, Pyodide v0.27.4
(CPython 3.12) vendored locally, wheels from PyPI. Not a thought experiment — the test ran.

## Result

| Check | Outcome |
|---|---|
| `sgit_ai-0.14.27-py3-none-any.whl` installs under Pyodide (micropip, `deps:false`) | ✅ |
| `osbot-utils` 3.75.0 installs (pure Python) | ✅ |
| `cryptography` via Pyodide's built-in WASM package | ✅ |
| `from sgit_ai.crypto.Vault__Crypto import Vault__Crypto` | ✅ |
| PBKDF2-SHA256 600k-iteration key derivation | ✅ ~1,250 ms (vs ~200–300 ms native — fine with a spinner) |
| AES-GCM encrypt→decrypt round trip in-browser | ✅ |
| `Vault__API__In_Memory` write/read (after `.setup()`) | ✅ |
| **Cross-implementation exactness:** ref file id for the live sgit.ai site vault derived in-browser | ✅ `2c32947535f3` — byte-identical to native CPython, and matches the actual `ref-pid-muw-2c32947535f3` object on the server |
| Pyodide boot (local/cached assets) | ~2 s (first-load network cost is the ~20 MB download, per the handoff) |

The handoff's §0 claim ("it's been done and proven" for `sg-send-cli` v0.5.0) now holds for
**today's renamed, 400-module sgit-ai** with zero source changes.

## Deltas vs the handoff recipe (what the next builder needs to know)

1. **Names:** PyPI package is `sgit-ai` (pure-Python wheel `py3-none-any`), imports are
   `sgit_ai.*`. Deps exactly `cryptography>=43` (use Pyodide's built-in 42.0.5 — worked) and
   `osbot-utils>=3.70`.
2. **NEW discovery — load Pyodide's `ssl` package.** `sgit_ai.network.api.Vault__API` imports
   `urllib.request`, which needs the `ssl` module; Pyodide ships it as a loadable package
   (`py.loadPackage(['cryptography','micropip','ssl'])`). Without it: `ModuleNotFoundError: ssl`
   on any `sgit_ai.network` import. (Sockets still don't exist — this only satisfies the import;
   the XHR transport is still required for real network.)
3. **Type_Safe API classes need `.setup()`:** `Vault__API__In_Memory().setup()` — attributes are
   created there, not in `__init__`.
4. **Watch hex-vs-bytes:** `Vault__Crypto.derive_keys*()` dicts return hex strings;
   `derive_ref_file_id()` etc. want the `bytes` from `derive_read_key()`. (Cost me one failed run.)
5. **Still true from the handoff:** `micropip.install.callKwargs(..., {deps:false})` (plain
   `install(pkg, {deps:false})` silently ignores the kwargs); fetch the wheel in JS +
   `py.FS.writeFile` + `emfs://` install.

## CORS — verified live today (curl, `Origin: https://sgit.ai`)

- `tools.sgraph.ai` module assets: `access-control-allow-origin: *` ✅ (handoff §2 confirmed).
- **`dev.send.sgraph.ai`: fully browser-ready.** Preflight `OPTIONS` returns
  `allow-origin: *`, `allow-methods: GET, POST, PUT, DELETE, HEAD, OPTIONS`, and
  `allow-headers` including `x-sgraph-access-token`, `x-sgraph-vault-write-key`,
  `x-vault-read-key`, `x-sgraph-vault-enum-key`. The real-remote clone/push/pull transport is
  not blocked by CORS. (Open question §8 of the handoff: answered.)

## XHR patch surface for real-remote (today's method names)

`sgit_ai/network/api/Vault__API.py` — the urllib usage to reroute through the browser's
XMLHttpRequest (per the handoff §4 recipe): `write`, `read`, `delete`, `batch`, `batch_read`
(+ `_batch_read_chunk`), `_presigned_read_fallback` (direct S3 GET), and the `presigned_*`
trio. All go through `Request`/`urlopen` imported at the top of that file — a single-module
monkey-patch, exactly as the v0.1.2 recipe did for the old CLI.

## What was NOT tested (sandbox limitation, not a design doubt)

The sandbox's egress proxy resets browser TLS to external hosts, so the in-browser
`fetch('https://dev.send.sgraph.ai/…')` leg could not run here (CORS itself verified via curl
above; a real browser on a real network has no such proxy). First thing to smoke-test when
running this from a normal machine: fetch + decrypt one ref object, then the full XHR-patched
`clone`.

## Recommended path (updates handoff §7)

1. **Ship a "Try sgit in your browser" page on sgit.ai** — the in-memory flavour first:
   import `sg-pyodide.js` from tools.sgraph.ai (CORS `*`), install the `sgit-ai` wheel from
   PyPI at runtime, run create→commit→history against `Vault__API__In_Memory`. All verified
   working today; honest loading UX for the ~20 MB first load.
2. **Then the real-remote terminal:** lift the XHR transport from
   `sg-send-cli__v0.1.2__REAL-REMOTE-xhr-recipe.html`, target the method list above,
   point at `dev.send.sgraph.ai` (CORS confirmed). That gives browser-native
   clone/commit/push/pull with all crypto client-side — sgit with zero install.
3. **Extraction request to the tools team** (handoff §7.5): package loader + wheel-install +
   ssl + XHR transport as `core/sg-sgit-browser` so sgit.ai and vaults import one module.
4. **Strategic note for positioning:** combined with SG/Vault, this closes the loop — the
   same Python codebase runs natively and in the browser, joining the JS client as a third
   consumer of the wire format. "pip install sgit-ai — or don't install anything at all."

## Artifacts

Test harness (vendored Pyodide + wheels + Playwright runner) lives in the session scratchpad
(`pyodide-test/`: `test.html`, `run.js`); the working recipe is fully reproduced in this
document. Total runtime of the passing suite: ~8 s with local assets.
