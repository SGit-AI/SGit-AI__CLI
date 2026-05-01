#!/usr/bin/env bash
# setup-sgit-docker.sh
# Pulls the sgit Docker image from Docker Hub and adds shell functions to
# your rc file so that sgit transparently runs inside a container with the
# current directory mounted as the vault working directory.
#
# Usage:
#   bash docker/setup-sgit-docker.sh          # sets up sgit (Docker)
#   bash docker/setup-sgit-docker.sh podman   # sets up sgit_podman
#   bash docker/setup-sgit-docker.sh applec   # sets up sgit_applec (macOS 26)
#
# After setup, reload your shell (source ~/.bashrc or ~/.zshrc) and use
# sgit exactly as normal — it runs inside a container automatically.
#
# To upgrade to a new version at any time:
#   docker pull diniscruz/sgit-ai:latest   # or podman/container pull

set -euo pipefail

IMAGE="diniscruz/sgit-ai:latest"
MODE="${1:-docker}"

# ── detect rc file ────────────────────────────────────────────────────────────
if [[ "${SHELL}" == *"zsh"* ]]; then
  RC_FILE="${HOME}/.zshrc"
else
  RC_FILE="${HOME}/.bashrc"
fi

# ── pull image + write function ───────────────────────────────────────────────
case "${MODE}" in

  docker)
    echo "▶ Pulling ${IMAGE} via Docker…"
    docker pull "${IMAGE}"
    echo "✔ Image ready: ${IMAGE}"

    FUNC_NAME="sgit"
    RUNTIME="docker"
    MARKER="# >>> sgit-docker function <<<"
    END_MARKER="# <<< sgit-docker function <<<"
    ;;

  podman)
    echo "▶ Pulling ${IMAGE} via Podman…"
    echo "  (ensure 'podman machine start' has been run first)"
    podman pull "${IMAGE}"
    echo "✔ Image ready: ${IMAGE}"

    FUNC_NAME="sgit_podman"
    RUNTIME="podman"
    MARKER="# >>> sgit-podman function <<<"
    END_MARKER="# <<< sgit-podman function <<<"
    ;;

  applec)
    echo "▶ Pulling ${IMAGE} via Apple Containers…"
    echo "  (requires macOS 26 / Tahoe)"
    container pull "${IMAGE}"
    echo "✔ Image ready: ${IMAGE}"

    FUNC_NAME="sgit_applec"
    RUNTIME="container"
    MARKER="# >>> sgit-applec function <<<"
    END_MARKER="# <<< sgit-applec function <<<"
    ;;

  *)
    echo "Unknown mode '${MODE}'. Use: docker | podman | applec"
    exit 1
    ;;
esac

# ── shell function definition ─────────────────────────────────────────────────
FUNC_DEF="${FUNC_NAME}() {
  ${RUNTIME} run --rm -it \\
    -v \"\$(pwd):/vault\" \\
    -e SGIT_TOKEN=\"\${SGIT_TOKEN:-}\" \\
    ${IMAGE} \"\$@\"
}"

# ── inject function (idempotent) ──────────────────────────────────────────────
if grep -q "${MARKER}" "${RC_FILE}" 2>/dev/null; then
  echo "✔ Function '${FUNC_NAME}' already present in ${RC_FILE} — skipping."
else
  {
    echo ""
    echo "${MARKER}"
    echo "${FUNC_DEF}"
    echo "${END_MARKER}"
  } >> "${RC_FILE}"
  echo "✔ Function '${FUNC_NAME}' written to ${RC_FILE}"
fi

echo ""
echo "Done! Reload your shell or run:"
echo "  source ${RC_FILE}"
echo ""
echo "Then use ${FUNC_NAME} exactly as normal — it runs inside a container:"
echo "  ${FUNC_NAME} status"
echo "  ${FUNC_NAME} clone mypass:vaultabc123 ./my-vault"
echo "  ${FUNC_NAME} push"
echo ""
echo "To upgrade to a new version:"
echo "  ${RUNTIME} pull ${IMAGE}"
echo ""
echo "Tip: export SGIT_TOKEN=your-token in your environment to avoid"
echo "     passing --token on every command."
