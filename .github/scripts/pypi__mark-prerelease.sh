#!/usr/bin/env bash
# Mark the checked-out build as a PEP 440 pre-release before it is built for PyPI (the dev pipeline).
#
# The dev pipeline has just tagged vX.Y.Z (a patch bump of the last tag); this build is published as
# X.Y.Z.dev0. That sorts above the last release and below the next one (main bumps the minor: X.(Y+1).0),
# and a plain `pip install sgit-ai` never selects it: only `pip install --pre sgit-ai`, an exact
# `sgit-ai==X.Y.Z.dev0`, or `sgit update` from a pre-release install does. Only the files in this
# checkout change (pyproject.toml and the package's version file); nothing is committed.
#
# The guard: the result must be a pre-release by PEP 440's own rule (the `packaging` library, or the
# copy pip vendors), else the script exits 1 and nothing is built, so dev can never publish a release.
#
# usage: pypi__mark-prerelease.sh <package dir> [repo root]
set -euo pipefail
PACKAGE="${1:?usage: pypi__mark-prerelease.sh <package dir> [repo root]}"
ROOT="${2:-.}"
VERSION_FILE="$ROOT/$PACKAGE/version"
TAG=$(tr -d '[:space:]' < "$VERSION_FILE")
BASE="${TAG#v}"
if ! [[ "$BASE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "error: expected the dev pipeline's vX.Y.Z in $VERSION_FILE, found '$TAG'; nothing was changed" >&2
    exit 1
fi
PRE="${BASE}.dev0"
python3 -I - "$ROOT/pyproject.toml" "$PRE" <<'PY'
import re, sys
path, pre = sys.argv[1], sys.argv[2]
try:
    from packaging.version import Version
except ImportError:
    from pip._vendor.packaging.version import Version
if not Version(pre).is_prerelease:
    sys.exit(f'error: {pre} is not a PEP 440 pre-release; refusing to build it from dev')
with open(path) as f:
    text = f.read()
new, n = re.subn(r'(?m)^(version\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{pre}"', text, count=1)
if n != 1:
    sys.exit(f'error: no `version = "..."` line in {path}')
with open(path, 'w') as f:
    f.write(new)
PY
echo "v$PRE" > "$VERSION_FILE"
echo "Marked this build as the pre-release $PRE (tag $TAG): pip install --pre sgit-ai"
