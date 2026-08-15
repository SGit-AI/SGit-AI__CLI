# Brief: serial transfer mode (Pyodide/WASM support) for sgit

**Date:** 2026-08-11
**From:** the sgit.ai website session (Claude Code), relaying a request from Dinis Cruz
**Context:** sgit now runs in the browser under Pyodide (see
`pyodide-sgit-in-browser-verification.md`). The sgit.ai /try page ships a working
terminal where `sgit clone` from the live SG/Send servers **succeeds end-to-end** —
but only because the page monkey-patches `concurrent.futures.ThreadPoolExecutor`.
This brief proposes making sgit threadless-safe natively.

## The failure

Under WebAssembly, Python cannot spawn OS threads. Any transfer that reaches a
`ThreadPoolExecutor` dies with `can't start new thread` — surfaced live during the
first in-browser clone attempt at the blob-download stage (index, branch metadata,
commits and trees had already downloaded and decrypted fine, since those paths are
sequential).

## Current thread usage (v0.14.27)

All call sites import the executor *at call time* (which is what makes the
browser-side global patch work):

- `core/actions/clone/Vault__Sync__Clone.py` — 4 sites (blob-chunk fan-out ×2,
  large-blob fan-out ×2; `max_workers` = chunks/8 or large_blobs/4)
- `core/actions/push/Vault__Batch.py` — 2 sites (parallel part upload,
  parallel chunk push)

## Proposal

1. **Auto-detect, no flag needed for the common case:**
   ```python
   SERIAL_TRANSFERS = (sys.platform == 'emscripten') or bool(os.environ.get('SGIT_SERIAL_TRANSFERS'))
   ```
   `sys.platform == 'emscripten'` is true under Pyodide and false everywhere else.
2. **One helper, six call sites.** A small `Transfer__Executor` (Type_Safe, per house
   rules) that returns either a real `ThreadPoolExecutor` or a trivial serial
   executor with the same surface (`submit` returning a completed `Future`, `map`,
   context-manager). The env var doubles as an escape hatch for debugging native
   parallelism issues.
3. **Optionally** expose `--serial` on transfer commands for symmetry, but the
   auto-detect is the part that matters.

## Evidence the serial path is correct

Validated natively against the live dev server with **thread creation disabled**
(`threading.Thread.start` raising, executor swapped for a serial one): full clone of
the sgit.ai site vault — 13 commits, 59 trees, **225 blobs** — byte-correct working
copy. Timing: commits 5.8s, trees 3.7s, blobs 12.5s serial. The browser (sync XHR on
the main thread) is naturally serial anyway, so nothing is lost there.

## Also worth recording (browser-transport findings from the same session)

- The servers' CORS allow-list accepts `x-sgraph-access-token` but not `x-api-key`;
  sgit sends both, and one disallowed header fails the whole browser preflight
  (Starlette returns `400 Disallowed CORS headers`). Either add `x-api-key` to the
  API's CORSMiddleware `allow_headers`, or treat the second header as native-only.
  The sgit.ai browser transport currently drops `X-API-Key` client-side.
- The presigned-S3 fallback path (`_presigned_read_fallback`, large blobs) uses a
  function-local `urlopen` import — invisible to transport monkey-patching and
  untested under CORS from a browser origin. Worth a look when large-blob vaults
  meet the browser.

## Where the working shim lives

`SGit-AI/SGit-AI__Website` → `assets/try-setup.py` (section 0) — deployed and live
on https://sgit.ai/try/ since site v0.1.12.
