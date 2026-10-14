# Brief to the SG/Send team — disk-mode performance, large files without S3, and removing MCP

**From:** the sgit-ai CLI agent, 14 Oct 2026, with Dinis's go-ahead on the MCP point.
**Server read:** `sgraph_ai_app_send` 0.34.0, as installed from PyPI. Line references are to that
package. Each claim is marked **[reproduced]** (run here, or in the 14 Oct benchmark report) or
**[code-read]**.

Four asks, in order of impact. The first two come from a third-party benchmark of 0.34.0 in disk
mode (`sgit issues found on 14 October 2026`, measured for two newsroom articles); the third is
what sgit now does on its side; the fourth is a decision Dinis has taken for the CLI and asks
you to consider for the server.

## 1. Disk mode: every append-lane write scans the whole store

**[reproduced by the benchmark, confirmed by code-read]**

| Load | Disk storage | Memory storage |
|---|---|---|
| 1 writer × 1 entry | 0.38 s | 0.004 s |
| 10 writers × 1 | 2.8 s | 0.03 s |
| 100 writers × 1 | 29.8 s | 0.27 s |
| 50 writers × 10 | 172 s | — |

The cause is in the local patch `lambda__user/storage/Storage_FS__Local_Disk.py`:
`folder__files__all(parent_folder)` iterates **`self.files__paths()`, the entire store**, and
filters by prefix in Python. `Service__Vault__Append.append()` calls it on every write to check
the 1,000-entry cap (`len(files) >= APPEND_MAX_FILES`), and `list_entries()` calls it once per
inbox. So each append walks every file the server holds, ~3,500 in the benchmark, and the cost
grows with the store, not with the inbox.

The file's own comment says the subclass exists because upstream `memory_fs` raised
`NotImplementedError` for these two methods.

**Ask:** make `folder__files__all` walk only `parent_folder` (`os.scandir` / `os.walk` from the
folder's path), and `folder__folders` likewise. The append write then costs one small directory
listing. The benchmark notes memory mode also slows as the store grows, so the same full-scan
shape may exist on that path too.

## 2. Files over 4 MB cannot be pushed to, or fetched on demand from, a server without S3

**[reproduced here against the in-memory test server; the benchmark hit it on disk mode]**

`POST /api/vault/presigned/initiate` and `GET /api/vault/presigned/read-url` answer
`400 {"detail": "S3 storage mode required"}` in memory and disk mode. The CLI sent every blob
over 4 MB through the presigned route (the Lambda base64 limit), so a push with one such file
failed, and a `clone --sparse` + `fetch` of a large file failed the same way.

**What sgit does now (0.21.1):** when the server answers that it has no presigned route, the
CLI falls back to the ordinary batch write and read routes. A server without S3 has no Lambda
body limit either, so those routes carry any size. Tested on the in-memory server with a 4.25 MB
file: push, full clone and sparse fetch all round-trip.

**Ask:** none for correctness now. Two things would help: (a) document the body-size ceiling
of `/api/vault/batch` and `/api/vault/read` in disk and memory mode, if there is one (uvicorn
has none by default; a reverse proxy in front might); (b) if you ever put a limit there,
return a distinct status so the client can say so rather than retry.

## 3. One server process queues full clones

**[benchmark]** Ten concurrent full clones of a 500-file vault took 21 s against 2.2 s for one;
scoped clones barely noticed (0.72 s → 1.9 s). `python -m sgraph_ai_app_send__docker.serve`
runs a single uvicorn process, and full clones are server-bound (batch reads, about 1.2 cores).

**Ask:** document `--workers N` (or the uvicorn env var) for the Docker entry point and the
`sgit serve` image, and make the default follow the CPU count. This is deployment advice, not
a bug. The sgit side already fetches in 16 parallel batches, so a multi-worker server is used
straight away.

## 4. Remove MCP from the server

Dinis has decided to drop MCP on the CLI side (it was never used there: the only trace was a
`mcp<2` pin that 0.34.0 now carries itself). Reading the server, MCP costs three things that
matter for a zero-knowledge vault host:

- **A wider, unauthenticated discovery surface.** Both the user and admin lambdas mount `/mcp`
  (`utils/MCP__Setup.py`); the user lambda exposes the transfers, presigned, early-access, vault
  and vault/presigned routes as tools, and the setup comment says discovery is authless.
- **Content sniffing on uploads.** `Routes__Transfers.unwrap_mcp_payload` base64-decodes any
  upload body that starts with `{` and parses as JSON with a `data` key, because MCP clients
  cannot send bytes. Vault objects are ciphertext and never parse, so sgit is unaffected, but
  the server now stores something different from what some clients sent, decided by content.
- **A token in the query string.** `POST /transfers/create` takes `access_token` as a plain
  parameter "when headers unavailable" (an MCP tool parameter), which FastAPI also accepts as a
  query parameter; tokens in URLs reach access and CDN logs.
- Plus the `fastapi-mcp` and `mcp` dependencies and the mcp-2.x breakage they brought in July.

**Ask:** remove `MCP__Setup`, the `/mcp` mounts, `unwrap_mcp_payload` and the `access_token`
parameter, and drop `fastapi-mcp` and `mcp` from the dependencies. The CLI and the web UI cover
agents and people; if an MCP front is wanted later, it is better as a separate service in front
of the API than as a mount inside the vault host.

## What the CLI side has done on the same report

- **Pull performance** (the agents' complaint on the comms vault, 35k objects): a pull used to
  make one request per blob and one per commit of a linear history. It now batches blobs (50
  per request, 16 in flight) and, when far behind, lists the store once and fetches in bulk,
  as a clone does. Numbers in the 0.21.1 CHANGELOG.
- **`clone-headless` then `fetch`** (benchmark issue 3): fixed; the first sparse command brings
  the branch index, ref and trees down.
- **Large files without S3** (issue 2): as above.

Nothing here needs a CLI change on your side; the fallbacks are in the client.
