# `sgit serve`: container first. Options map and spike results

**Date:** 2026-10-12 · **Status:** options and plan, no sgit code yet · **Supersedes** the
"native server" plan in `research__sgit-serve-local-vault-server.md` (same folder). The API
inventory and browser notes there still apply.

**Decision (Dinis):** run a working vault locally from the SG/Send container image. It has
the vault UI and the API in one image and always tracks the latest SG/Send. sgit gets native
support for it:
- it abstracts the container runtime;
- it supports several runtimes, including Apple's `container`;
- it can install one when none is present;
- it should also work without Docker where possible.

The current read-only server stays as a separate, clearly named mode.

## 1. Two modes

| Mode | Command | What it is | Writes | Needs |
|---|---|---|---|---|
| **container** (default) | `sgit serve` | The SG/Send image (`diniscruz/sg-send-vault`): vault UI + full API + disk store, on `localhost` | yes. A real local vault server: the UI edits, sgit pushes and pulls | a container runtime, or the Python engine (§4) |
| **static** | `sgit serve --static` (today's `sgit vault serve`) | A stdlib read-only file server for a **published** vault: the static loader plus the encrypted store, no API | no | nothing |

- Static mode still has a job: it previews what `sgit publish` produces, or serves an unpacked
  published zip, with zero dependencies.
- It is not "run a vault". Rename it, and make `sgit vault serve` print its new place
  (the rule-9 moved-word behaviour).

## 2. What I verified today (spike in this cloud container)

All of it was run here, x86_64 Linux, Docker 29.6 / containerd 2.2. The screenshot
`spike__local-container-ui-open-vault.png` is next to this file.

| # | Check | Result |
|---|---|---|
| 1 | `docker pull diniscruz/sg-send-vault:latest` | about 10 s; **400 MB**; a multi-arch index (amd64 + arm64); server **v0.34.0**, UI v0.2.3; 31 tags (`v0.27.70` … `v0.34.0`) |
| 2 | `docker run -p 8080:8080 -v <dir>:/data` | `/api/info/health` ok; UI `/` 200 |
| 3 | `sgit init` / `commit` / `push` / `clone --base-url http://127.0.0.1:8080` (repo code) | works: 12 objects on disk at `<dir>/vault/iv/ivh5cbkj/{manifest.json,bare/…}`; the fresh clone has the files |
| 4 | **The image runs as uid 10001** (its README still says root) | a host folder owned by the user is **not writable**: `Permission denied: '/data/vault'`. **Fix: `--user $(id -u):$(id -g)`**, which sgit must always pass |
| 5 | sgit refuses to push with no token ("no access token configured") even though the server has no auth | passing any `--token` works. **sgit fix:** a server that needs no token is a normal case |
| 6 | Headless Chromium → `http://localhost:8080/en-gb/vault/`, key typed into the form | **the vault opens and decrypts**: `docs/`, `a.md` ("hello local"). Same origin, plain http on localhost, Web Crypto fine |
| 7 | `#<vault-key>` in the URL | did not auto-open (the form did) |
| 8 | The UI loads `sg-layout.js` and `sg-llm-events.js` **from `dev.tools.sgraph.ai` at runtime** | not self-contained, despite "no CDN dependency" in its README: offline or air-gapped use will break |
| 9 | The UI shows "Read-only" until an access key is entered | expected; `sgit serve` should print the access-key hint, or configure the container so the UI is writable |
| 10 | **containerd only** (`ctr run`, no Docker API) | works (image imported, push lands on disk) |
| 11 | Anonymous `ctr pull` from Docker Hub | **429 Too Many Requests**; Docker Hub's anonymous limit is 100 pulls per 6 h per IP |
| 12 | **No container at all:** the image's own server code (`sgraph_ai_app_send__docker.app`) under a Python 3.12 venv, with the UI folder copied out of the image | works: health, UI, and an sgit push to a disk store |
| 13 | CORS for the hosted UI (`Origin: https://vault.sgraph.ai`) | preflight 200 with `Access-Control-Allow-Origin: *` … **but with `Access-Control-Request-Private-Network: true` → 400 "Disallowed CORS private-network"**. Starlette's `allow_private_network` is off, so Chrome's private-network preflight from vault.sgraph.ai to localhost fails |
| 14 | A server error response | **contains the full Python stack trace** (an information leak; fine on a laptop, not on a shared host) |

## 3. Runtimes: what exists and how sgit would drive each

"docker-compatible" means it accepts `run -d --name -p -v --user -e`, `ps`, `stop`, `logs`
and `pull` with the same flags, so one adapter covers all of them. Rows marked † come from my
knowledge rather than today's run; check each against its current docs when building the
adapter.

| Runtime | OS | CLI | Install (what `sgit serve install` would do or print) | Notes |
|---|---|---|---|---|
| **Docker Engine** | Linux | `docker` | distro package / get.docker.com | the reference; verified here |
| **Docker Desktop** | macOS, Windows | `docker` | the vendor installer | Linux VM under the hood; **paid licence for larger companies**† |
| **Podman** | Linux, macOS, Windows | `podman` (docker-compatible) | `brew install podman` + `podman machine init/start` on mac/Windows; distro package on Linux | daemonless, **rootless by default**†; with `--userns=keep-id` the uid problem (#4) goes away; no Docker licence |
| **Apple `container`** | macOS 26 on **Apple silicon** (macOS 15 runs with reduced networking) | `container` (its own CLI, docker-like) | signed `.pkg` from GitHub `apple/container` releases, then `container system start` | one lightweight VM per container, runs OCI images, no Docker. **Its own adapter**; flags to confirm against `container run --help` (ports, mounts) |
| **Colima** | macOS, Linux | gives a `docker` (or `nerdctl`) context | `brew install colima docker && colima start` | free, Lima VM; then the docker adapter† |
| **OrbStack** | macOS | `docker` | vendor app | fast; commercial licence for business use† |
| **Rancher Desktop** | macOS, Windows, Linux | `docker` or `nerdctl` | vendor installer | free (SUSE)† |
| **Finch** | macOS, Windows, Linux | `finch` (nerdctl-based, docker-like) | AWS installer / brew | free (AWS)† |
| **containerd + nerdctl** | Linux | `nerdctl` (docker-compatible) | distro or release tarball | lean Linux servers; raw `ctr` works too (verified, #10) |
| **WSL2** | Windows | any of the above inside WSL | `wsl --install` + one of the above | Windows without Docker Desktop |
| **Python engine** (no container) | anywhere with **`uv`** | `uv run --python 3.12 --with sgraph-ai-app-send …` | `uv` (one static binary); uv fetches Python 3.12 itself | the same server code as the image, verified (#12); needs the built UI folder (§5) |

**Detection order:** a runtime already running wins. Otherwise the order is:
1. `docker` (context answers)
2. `podman`
3. `container` (Apple)
4. `nerdctl`
5. `finch`
6. the Python engine if `uv` is found
7. `--static` as the last resort, with a message saying what the user is missing

`sgit serve --runtime <name>` overrides the choice. `sgit serve runtimes` lists what it found,
and for anything missing, the one install command per OS.

**Installing:**
- `sgit serve install [<runtime>]` prints the command and runs it **only after a yes**, because
  it is a system change.
- On macOS with Apple silicon it suggests Apple `container`, or Podman.
- On Linux it suggests Podman or Docker Engine.
- On Windows it suggests WSL2 + Podman.
- Without any runtime, it suggests `uv` and the Python engine.

## 4. What `sgit serve` does (container mode)

```
sgit serve                     # inside a clone
  1. pick a runtime (§3); pull the image, pinned by digest and recorded (latest by default; --tag vX.Y.Z)
  2. data dir: <clone>/.sg_vault/serve/ (or --data DIR, interchangeable with any sg-send-vault /data)
  3. run: --name sgit-serve-<vault_id> --user <uid>:<gid> -p 127.0.0.1:<port>:8080 -v <data>:/data
          (-p on 127.0.0.1 only: a plain `-p 8080:8080` publishes on every interface)
  4. wait for /api/info/health
  5. seed: push this clone into it as a remote, `local` → http://127.0.0.1:<port>
           (the existing push code: no coupling to the server's disk layout)
  6. print the UI URL, the vault-key and access-key hints; --open launches the browser
sgit serve status | logs | stop | update     # update = pull the newer image, restart, same data dir
sgit serve --static                          # today's read-only published-folder server
```

Then:
- `sgit pull --remote local` brings edits made in the browser into the clone, with full
  verify-then-accept;
- `sgit push` sends them to the real server.

The server owns its own store. The clone's `.sg_vault/bare/` is never mounted, because the
UI writing the clone's accepted refs would undo what 0.21 fixed.

**Python engine:** steps 1 and 3 become
`uv run --python 3.12 --with sgraph-ai-app-send==<v> python -m … --port <p>`, with
`SEND__STORAGE_MODE=disk`, `SEND__DISK_PATH=<data>` and `SEND__VAULT_STATIC_DIR=<ui dir>`.
Everything else is the same.

**TLS:** only for the LAN or Safari cases (see the research note §5–6).
- sgit generates a cert with `cryptography`;
- it mounts the cert and key at `/certs`;
- it sets `FAST_API__TLS__ENABLED=true`, which the image already supports.

## 5. Asks of the SG/Send team (from the spike)

1. **Vendor the `dev.tools.sgraph.ai` scripts into the image** (#8). Today the "self-contained"
   UI needs the internet.
2. **`allow_private_network=True`** in the CORS middleware (#13). Without it, the hosted UI
   cannot reach a local server from Chrome.
3. **No stack traces in error responses** (#14), or only behind a debug flag.
4. **README:** the image runs as uid 10001, so document `--user` or `chown` (#4).
5. **Also publish to GHCR or ECR Public** (#11). sgit can then fall back when Docker Hub
   rate-limits.
6. **Publish the built vault UI** (`/app/static_vault`) as a versioned release asset. That is
   what the Python engine needs; today it can only be copied out of the image.
7. Optionally, let `#<vault-key>` (or a `?key=` handoff) auto-open on `/en-gb/vault/` (#7), so
   `sgit serve --open` lands inside the vault.

## 6. Changes in sgit

| Change | Size |
|---|---|
| `Container__Runtime` (detect, pull, run, ps, stop, logs, health wait) with adapters: docker-compatible (docker, podman, nerdctl, finch), Apple `container`, Python engine (uv) | ~350 lines |
| `CLI__Serve`: container mode (seed via push to a `local` remote, banner, `--open`), `status/logs/stop/update/runtimes/install`, `--static` = today's server; `sgit vault serve` points to it | ~250 lines |
| A token is optional when the server has no auth (#5) | small |
| TLS cert generation + mount | ~100 lines |
| **Tests:**<br>• unit: each adapter's command lines, against a fake runtime binary on `PATH`;<br>• integration: **real Docker in CI** (the daemon starts in this kind of environment, as shown today); clone, push and pull against the image; a Playwright check that the UI opens the vault | ~1 day |

**Estimate:**

| Phase | Work | Estimate |
|---|---|---|
| 1 | Docker-compatible adapter + serve, stop, status, logs + seeding | 2 days |
| 2 | Apple `container` adapter + Python engine | 1–1.5 days; the Apple adapter needs a Mac to test on |
| 3 | `runtimes`/`install` + TLS | 1 day |
| 4 | Docs, threat model rows | ½ day |

Total: about **5 days**. Phase 1 alone gives you "clone a vault, `sgit serve`, edit it in the
browser".

## 7. Decisions for you

1. **Image tag:** default to `latest` (always current, as you suggested) and record the
   digest in use, or pin per sgit release for reproducibility? My suggestion: `latest`, plus
   `--tag` and a recorded digest.
2. **Installing runtimes:** print the command only, or run it after confirmation?
3. **Apple `container` vs Podman** as the macOS recommendation: Apple's needs macOS 26 on
   Apple silicon; Podman runs everywhere.
4. **`--static` naming:** keep `sgit vault serve` as an alias, or move it fully?
5. Should I send the §5 asks to the SG/Send team as a brief?

## Sources

- Apple `container`: <https://tessl.io/registry/skills/github/sanjay3290/ai-skills/apple-container>
  (community summary of `apple/container`: Apple silicon only, macOS 26 supported, macOS 15
  with reduced networking, signed .pkg + `container system start`)
- Docker Hub pull limits: <https://docs.docker.com/docker-hub/download-rate-limit/>,
  <https://oneuptime.com/blog/post/2026-03-20-portainer-docker-hub-anonymous-auth/view>
- Chrome Local Network Access and Safari localhost blocking: the sources in
  `research__sgit-serve-local-vault-server.md`.
