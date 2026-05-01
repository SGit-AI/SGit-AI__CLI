# Docker: Running sgit from Docker + Docker Hub Publishing Plan

**Date:** May 1, 2026  
**Files:** `docker/Dockerfile`, `docker/setup-sgit-docker.sh`

---

## Part 1: Running sgit from Docker (Local Setup)

### Why Docker

Running sgit inside Docker is useful when:
- You want a clean, pinned Python environment without touching system Python
- You're using a machine where `pip install` is restricted or undesirable
- You want the same binary experience across macOS, Linux, and Windows (WSL)
- You're running sgit inside CI jobs or other containers

### Files

```
docker/
├── Dockerfile              # builds the sgit image
└── setup-sgit-docker.sh    # one-time local setup script
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir sgit-ai

WORKDIR /vault

ENTRYPOINT ["sgit"]
```

The container has no state — `WORKDIR /vault` is always the mount point for the host directory. The container exits after each command (`--rm`).

### One-time Setup

```bash
bash docker/setup-sgit-docker.sh
source ~/.bashrc   # or ~/.zshrc
```

This does two things:
1. Pulls `diniscruz/sgit-ai:latest` from Docker Hub
2. Writes a shell function to your rc file so `sgit` transparently runs in Docker

### Shell Function (written to `~/.bashrc` / `~/.zshrc`)

```bash
# >>> sgit-docker function <<<
sgit() {
  docker run --rm -it \
    -v "$(pwd):/vault" \
    -e SGIT_TOKEN="${SGIT_TOKEN:-}" \
    diniscruz/sgit-ai:latest "$@"
}
# <<< sgit-docker function <<<
```

Key design points:
- `--rm` — container is destroyed after each command (stateless)
- `-it` — preserves TTY for interactive prompts (e.g., rekey confirmation)
- `-v "$(pwd):/vault"` — mounts the current working directory as `/vault` inside the container, so all file paths work as expected
- `-e SGIT_TOKEN` — forwards the `SGIT_TOKEN` env var if set
- Idempotent: the script checks for the marker before writing, so running it twice is safe

### Usage After Setup

After `source ~/.bashrc`, sgit works exactly as if installed natively:

```bash
sgit status
sgit clone mypass:vaultabc123 ./my-vault
sgit commit -m "update docs"
sgit push
sgit pull
sgit log
```

The working directory is automatically the vault root. If you're in a subdirectory of a vault, vault root discovery still works because the entire working directory tree is mounted at `/vault`.

### Environment Variable: `SGIT_TOKEN`

```bash
export SGIT_TOKEN="coral-equal-1234"
sgit status          # token passed automatically
sgit push            # no --token flag needed
```

### Pinning a Specific Version

To pin to a specific sgit-ai release instead of `latest`:

```dockerfile
RUN pip install --no-cache-dir sgit-ai==v0.10.22
```

Rebuild after changing: `docker build -t sgit-local:latest docker/`

### Updating the Image

When a new sgit-ai version is released, just pull:

```bash
docker pull diniscruz/sgit-ai:latest
```

No rebuild needed. The shell function already points to `diniscruz/sgit-ai:latest`
so the next `sgit` command automatically uses the updated image.

---

## Part 3: Alternative Runtimes (Podman, Apple Containers)

The image is published as a multi-arch manifest (`linux/amd64` + `linux/arm64`),
so it runs natively on Apple Silicon with any OCI-compatible runtime.

### Runtime comparison on macOS

| | Docker Desktop | Podman | Apple Containers |
|---|---|---|---|
| Daemon required | Yes (dockerd) | No daemon, but needs `podman machine` VM | No — per-container VM on demand |
| macOS 26 required | No | No | Yes |
| Apple Silicon native | Yes (arm64) | Yes (arm64) | Yes (arm64) |
| CLI | `docker` | `podman` | `container` |

**Podman note:** Podman is truly daemonless on Linux (rootless, no socket). On macOS
it still needs `podman machine` — a lightweight Linux VM — because macOS has no Linux
kernel. It's lighter than Docker Desktop but not fully stateless on Mac.

**Apple Containers note:** Each container gets its own tiny per-container VM via
Apple's Virtualization.framework. No persistent daemon, no `machine` command — the
closest to truly on-demand on macOS. Requires macOS 26 (Tahoe).

---

### `sgit-pod` — Podman variant

**Setup (one-time):**
```bash
brew install podman
podman machine init
podman machine start
podman pull diniscruz/sgit-ai:latest
```

**Shell function** (add to `~/.zshrc`):
```bash
sgit-pod() {
  podman run --rm -it \
    -v "$(pwd):/vault" \
    -e SGIT_TOKEN="${SGIT_TOKEN:-}" \
    diniscruz/sgit-ai:latest "$@"
}
```

**Upgrade:**
```bash
podman pull diniscruz/sgit-ai:latest
```

---

### `sgit-ac` — Apple Containers variant

**Requirements:** Mac with Apple Silicon + macOS 26 (Tahoe).

**Setup (one-time):**
```bash
# 1. Download the signed .pkg from:
#    https://github.com/apple/container/releases
# 2. Double-click the .pkg and follow the prompts (installs to /usr/local)
# 3. Start the service:
container system start

# 4. Pull the sgit image:
container pull diniscruz/sgit-ai:latest
```

**Shell function** (add to `~/.zshrc`):
```bash
sgit-ac() {
  container run --rm -it \
    -v "$(pwd):/vault" \
    -e SGIT_TOKEN="${SGIT_TOKEN:-}" \
    diniscruz/sgit-ai:latest "$@"
}
```

**Upgrade:**
```bash
container pull diniscruz/sgit-ai:latest
```

---

### Pinning to a specific version (all runtimes)

Replace `latest` with the version tag:

```bash
# Docker
docker run --rm -it -v "$(pwd):/vault" diniscruz/sgit-ai:v0.10.34 status

# Podman
podman run --rm -it -v "$(pwd):/vault" diniscruz/sgit-ai:v0.10.34 status

# Apple Containers
container run --rm -it -v "$(pwd):/vault" diniscruz/sgit-ai:v0.10.34 status
```

---

## Part 2: Docker Hub Publishing Plan

### Goal

Publish `sgitai/sgit-ai` to Docker Hub on every main branch release, mirroring the existing `publish-to-pypi` step in the CI pipeline. The image should be available as:

```
diniscruz/sgit-ai:latest          # always the most recent release
diniscruz/sgit-ai:v0.10.22        # pinned version tag
```

### Prerequisites

1. **Docker Hub account**: `sgitai` namespace (you have this)
2. **Docker Hub access token**: create at hub.docker.com → Account Settings → Security → New Access Token. Set permissions to `Read & Write`.
3. **GitHub Secrets**: add to the repo:
   - `DOCKERHUB_USERNAME` = `sgitai`
   - `DOCKERHUB_TOKEN` = the access token from step 2

### Step 1: Add `should_publish_dockerhub` input to `ci-pipeline.yml`

In `.github/workflows/ci-pipeline.yml`, add the input alongside `should_publish_pypi`:

```yaml
on:
  workflow_call:
    inputs:
      # ... existing inputs ...
      should_publish_dockerhub:
        required: false
        type: boolean
        default: false
```

### Step 2: Add `publish-to-dockerhub` job to `ci-pipeline.yml`

After the existing `publish-to-pypi` job, add:

```yaml
  publish-to-dockerhub:
    if: inputs.should_publish_dockerhub && needs.increment-tag.result == 'success'
    name: "Publish to: Docker Hub"
    runs-on: ubuntu-latest
    needs: [increment-tag]
    steps:
      - uses: actions/checkout@v4

      - name: Git Update Current Branch
        uses: owasp-sbot/OSBot-GitHub-Actions/.github/actions/git__update_branch@dev

      - name: Read version
        id: version
        run: echo "tag=$(cat sgit_ai/_version.py | grep VERSION | cut -d\"'\" -f2)" >> $GITHUB_OUTPUT

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./docker
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            diniscruz/sgit-ai:latest
            diniscruz/sgit-ai:${{ steps.version.outputs.tag }}
```

Key choices:
- **`platforms: linux/amd64,linux/arm64`** — multi-arch build covers Intel/AMD servers and Apple Silicon / AWS Graviton. No extra cost, GitHub Actions runners support `buildx` natively.
- **Two tags**: `latest` for pull-and-go, version tag for pinning
- **`context: ./docker`** — builds from the `docker/` folder where the Dockerfile lives
- Runs only after `increment-tag` succeeds (same as PyPI publish), so the version in the image matches the released tag

### Step 3: Enable in `ci-pipeline__main.yml`

```yaml
jobs:
  deploy-main:
    uses: ./.github/workflows/ci-pipeline.yml
    with:
      git_branch            : 'main'
      release_type          : 'major'
      should_increment_tag  : true
      should_publish_pypi   : true
      should_publish_dockerhub: true   # ← add this
    secrets: inherit
```

### Step 4: Update the Dockerfile for Production Use

The current `Dockerfile` uses `pip install --no-cache-dir sgit-ai` which always installs the latest PyPI release. Since the CI build runs after `increment-tag` (which bumps the version and publishes to PyPI), the build order is:

```
increment-tag → publish-to-pypi → publish-to-dockerhub
```

Wait — there's a dependency: `publish-to-dockerhub` should run *after* `publish-to-pypi` so the new version is available on PyPI when Docker builds. Update `needs`:

```yaml
  publish-to-dockerhub:
    needs: [publish-to-pypi]          # ← wait for PyPI publish first
    if: inputs.should_publish_dockerhub && needs.publish-to-pypi.result == 'success'
```

For pinning the exact version in the image (optional, better for reproducibility):

```dockerfile
ARG SGIT_VERSION=latest
RUN pip install --no-cache-dir sgit-ai${SGIT_VERSION:+=}${SGIT_VERSION}
```

Then in the build step:
```yaml
build-args: |
  SGIT_VERSION=${{ steps.version.outputs.tag }}
```

This makes the image layer cache-friendly (version change = new layer) and the version explicit in the image metadata.

### Step 5: Add Docker Hub README (optional)

Docker Hub shows the repo's description and a README. You can push the README automatically:

```yaml
      - name: Update Docker Hub description
        uses: peter-evans/dockerhub-description@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
          repository: sgitai/sgit-ai
          short-description: "sgit — encrypted vault CLI. Runs as a drop-in binary."
          readme-filepath: ./docker/DOCKERHUB_README.md
```

---

## Summary of Changes Needed

| Step | File | Change |
|------|------|--------|
| 1 | `.github/workflows/ci-pipeline.yml` | Add `should_publish_dockerhub` input |
| 2 | `.github/workflows/ci-pipeline.yml` | Add `publish-to-dockerhub` job |
| 3 | `.github/workflows/ci-pipeline__main.yml` | Pass `should_publish_dockerhub: true` |
| 4 | GitHub repo settings | Add `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` secrets |
| 5 | `docker/Dockerfile` | Optionally pin version via `ARG SGIT_VERSION` |

Steps 1–3 are pure YAML changes. Step 4 requires access to the GitHub repo settings. No code changes to sgit itself are needed.

### End State

After this is set up, every merge to `main` will:
1. Run tests (unit + integration + QA)
2. Increment the version tag
3. Publish `sgit-ai` to PyPI
4. Build a multi-arch Docker image and push to Docker Hub as `diniscruz/sgit-ai:latest` and `diniscruz/sgit-ai:v{version}`

Users can then use sgit from Docker Hub without building locally:

```bash
# Pull and run directly — no local build needed
docker run --rm -it -v "$(pwd):/vault" diniscruz/sgit-ai:latest status

# Or update the shell function to use the published image
sgit() {
  docker run --rm -it \
    -v "$(pwd):/vault" \
    -e SGIT_TOKEN="${SGIT_TOKEN:-}" \
    diniscruz/sgit-ai:latest "$@"
}
```
