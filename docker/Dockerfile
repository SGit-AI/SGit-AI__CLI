# sgit Docker image
# CI path: installs from pre-built wheel in docker/dist/ (exact version, no PyPI timing issue)
# Local path: falls back to PyPI (docker/dist/ contains only .gitkeep)
#
# Usage (pull from Docker Hub — no local build needed):
#   docker pull diniscruz/sgit-ai:latest
#   docker run --rm -it -v "$(pwd):/vault" diniscruz/sgit-ai:latest status
#
# Or run setup-sgit-docker.sh once to add a shell function so you can just:
#   sgit status
#   sgit clone mypass:vaultabc123 ./my-vault
#
# To upgrade: docker pull diniscruz/sgit-ai:latest

FROM python:3.12-slim

ARG SGIT_VERSION=latest

COPY dist/ /tmp/dist/
RUN set -e; \
    if ls /tmp/dist/sgit_ai-*.whl 1>/dev/null 2>&1; then \
      pip install --no-cache-dir /tmp/dist/sgit_ai-*.whl; \
    else \
      VERSION_STRIPPED="${SGIT_VERSION#v}"; \
      if [ "$VERSION_STRIPPED" = "latest" ]; then \
        pip install --no-cache-dir sgit-ai; \
      else \
        pip install --no-cache-dir "sgit-ai==${VERSION_STRIPPED}"; \
      fi; \
    fi && rm -rf /tmp/dist

# Work dir mounted from host at runtime
WORKDIR /vault

ENTRYPOINT ["sgit"]
