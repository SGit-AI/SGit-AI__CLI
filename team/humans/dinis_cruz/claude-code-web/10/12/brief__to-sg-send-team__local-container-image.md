# To the SG/Send team: running `sg-send-vault` locally from sgit — eight asks

**From:** the sgit-ai CLI agent · **Date:** 2026-10-12 · **Context:** sgit is adding
`sgit serve`, which runs your `diniscruz/sg-send-vault` image on the user's machine (Docker,
Podman, Apple `container`, or your server code under `uv` when there is no container
runtime). Clone a vault, `sgit serve`, edit it in the vault UI on `localhost`. Background:
`team/humans/dinis_cruz/claude-code-web/10/12/options__sgit-serve-container-and-static.md` in
the SGit-AI__CLI repo.

## What works today

I ran image `latest` (server v0.34.0, UI v0.2.3) in a Linux container on 2026-10-12.

- **sgit:** `init`, `push`, `clone` and `pull` against `http://127.0.0.1:8080`, with data on a
  host folder.
- **The UI:** headless Chromium opened `http://localhost:8080/en-gb/vault/`, the vault key was
  typed into the form, and the vault decrypted and listed its files.
- **Without the Docker API:** the image also runs under containerd alone.
- **Without a container:** `sgraph_ai_app_send__docker.app` runs in a plain Python 3.12 venv,
  with the UI folder copied out of the image.

## Asks, most important first

1. **Ship the UI's external scripts inside the image.**
   - `/en-gb/vault/` and `/en-gb/app/` load `sg-layout.js`, `sg-layout-events.js` and
     `sg-llm-events.js` from `https://dev.tools.sgraph.ai/...` at runtime.
   - Ten files under `/app/static_vault` reference that host.
   - Offline or air-gapped, the UI does not render. The README says "no CDN dependency" and
     "air-gapped".
   - Please build these scripts into `static_vault`, and fail the image build if a
     `dev.tools.sgraph.ai` reference remains.
2. **Allow Chrome's private-network preflight.**
   - A preflight from `Origin: https://vault.sgraph.ai` gets 200 with
     `Access-Control-Allow-Origin: *`.
   - With `Access-Control-Request-Private-Network: true` added, it gets **400 "Disallowed
     CORS private-network"**.
   - The cause is Starlette's `CORSMiddleware`, whose `allow_private_network` defaults to off.
   - Please set `allow_private_network=True`, in both the lambda and the container's
     re-added middleware. Without it, the hosted UI cannot reach a server on the user's own
     machine in Chrome, even before Chrome's Local Network Access permission prompt.
3. **No stack traces in error responses.**
   - A write error returned the full Python traceback in the JSON body.
   - Example: `"error":"[Errno 13] Permission denied: '/data/vault'","stack_trace":"Traceback …`.
   - Please send it only behind a debug flag. The container is meant for VPS and EC2 use too.
4. **The image runs as uid 10001, but the README says `root`.**
   - The documented `-v "$(pwd)/_sg-send_data:/data"` fails on Linux unless the host folder
     is writable by 10001: `PermissionError: '/data/vault'` on the first write.
   - Please document `--user "$(id -u):$(id -g)"` (or `chown 10001`) next to the run
     commands.
   - sgit always passes `--user`.
5. **Publish the image to a second registry too** (GHCR or ECR Public).
   - An anonymous pull from Docker Hub got **429 Too Many Requests**; the anonymous limit is
     100 pulls per 6 h per IP.
   - CI and shared offices hit that limit. sgit will fall back to the second registry.
6. **Publish the built vault UI as a versioned release asset.**
   - That is `/app/static_vault`, as a zip with a SHA-256.
   - sgit's no-container engine needs it; today it can only be copied out of the image.
7. **The list endpoint returns nothing in disk mode.**
   - `GET /api/vault/list/{id}?prefix=bare/` (and with no prefix) answered `{"files":[]}`, while 26
     `payload` files were on disk under `/data/vault/{id[:2]}/{id}/bare/…`. Seen on image `latest`
     (v0.34.0) with the default flat layout.
   - sgit's bulk-fetch clone uses this listing (it falls back to walking), and `sgit serve` now
     keeps its own record instead. Probably the disk backend's `folder__files__all` with an empty
     storage prefix.
8. **Optional: let the vault open from the URL.**
   - `http://localhost:8080/en-gb/vault/#<vault-key>` did not open the vault in our run
     (the form did).
   - If `#<key>` (or a one-time `?open=` handoff) opened `/en-gb/vault/` directly,
     `sgit serve --open` could land the user inside their vault.
   - The hash never reaches the server.

## Also useful to know

- **Read-only until an access key:** the UI shows "Read-only" until an access key is entered,
  even when the container has no auth. Fine, but `sgit serve` will tell users what to type.
  If the UI could detect a server with no auth (for example from `/api/info/server`) and skip
  the access key, local use would be smoother.
- **Version reporting:** `/api/info/versions` reports `sgraph_ai_app_send` v0.34.0, and the
  UI footer shows `UI v0.2.3 (IFD)`. sgit records the image digest it ran and shows both.
- **Stable interfaces we rely on:**
  - the `SEND__*` and `FAST_API__TLS__*` environment variables;
  - the `/data` layout `vault/{id[:2]}/{id}/{file_id}/payload`;
  - `/api/info/health`.

  Please treat these as a stable interface, or tell us when they change.

Thank you. Item 1 is what users would notice first.
