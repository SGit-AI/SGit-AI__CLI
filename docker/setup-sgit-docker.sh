#!/usr/bin/env bash
# setup-sgit-docker.sh
# Builds the sgit Docker image and adds a shell function to your rc file
# so that `sgit` transparently runs inside Docker with the current directory
# mounted as the vault working directory.
#
# Usage:
#   bash docker/setup-sgit-docker.sh
#
# After setup, reload your shell (source ~/.bashrc or ~/.zshrc) and use
# sgit exactly as normal — it runs inside Docker automatically.

set -euo pipefail

IMAGE_NAME="sgit-local"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── build image ───────────────────────────────────────────────────────────────
echo "▶ Building Docker image '${IMAGE_NAME}'…"
docker build -t "${IMAGE_NAME}:latest" "${SCRIPT_DIR}"
echo "✔ Image built: ${IMAGE_NAME}:latest"

# ── shell function definition ─────────────────────────────────────────────────
# Mounts the current working directory into /vault inside the container.
# Passes SGIT_TOKEN env var if set (avoids typing --token every time).
FUNC_DEF=$(cat <<'FUNC'
sgit() {
  docker run --rm -it \
    -v "$(pwd):/vault" \
    -e SGIT_TOKEN="${SGIT_TOKEN:-}" \
    sgit-local:latest "$@"
}
FUNC
)

# ── detect rc file ────────────────────────────────────────────────────────────
if [[ "${SHELL}" == *"zsh"* ]]; then
  RC_FILE="${HOME}/.zshrc"
else
  RC_FILE="${HOME}/.bashrc"
fi

# ── inject function (idempotent) ──────────────────────────────────────────────
MARKER="# >>> sgit-docker function <<<"
if grep -q "${MARKER}" "${RC_FILE}" 2>/dev/null; then
  echo "✔ Function already present in ${RC_FILE} — skipping."
else
  {
    echo ""
    echo "${MARKER}"
    echo "${FUNC_DEF}"
    echo "# <<< sgit-docker function <<<"
  } >> "${RC_FILE}"
  echo "✔ Function written to ${RC_FILE}"
fi

echo ""
echo "Done! Reload your shell or run:"
echo "  source ${RC_FILE}"
echo ""
echo "Then use sgit exactly as normal — it runs inside Docker:"
echo "  sgit status"
echo "  sgit clone mypass:vaultabc123 ./my-vault"
echo "  sgit push"
echo ""
echo "Tip: export SGIT_TOKEN=your-token in your environment to avoid"
echo "     passing --token on every command."
