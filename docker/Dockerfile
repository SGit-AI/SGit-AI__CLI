# sgit Docker image
# CI path: installs from pre-built wheel in docker/dist/ (exact version, no PyPI timing issue)
# Local path: falls back to PyPI (docker/dist/ contains only .gitkeep)
#
# Usage (after building or pulling):
#   docker run --rm -it -v "$(pwd):/vault" sgit-local:latest status
#   docker run --rm -it -v "$(pwd):/vault" sgit-local:latest clone mypass:vaultabc123 .
#
# Or use the shell function installed by setup-sgit-docker.sh so you can just:
#   sgit status
#   sgit clone mypass:vaultabc123 ./my-vault

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
