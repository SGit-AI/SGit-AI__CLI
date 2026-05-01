# sgit Docker image
# Installs the latest sgit-ai release and sets sgit as the entrypoint
# so the container behaves like the sgit binary itself.
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
RUN pip install --no-cache-dir "sgit-ai${SGIT_VERSION:+=}${SGIT_VERSION}"

# Work dir mounted from host at runtime
WORKDIR /vault

ENTRYPOINT ["sgit"]
