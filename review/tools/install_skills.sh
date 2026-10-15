#!/usr/bin/env bash
# Installs the third-party review skills used by the security review, pinned to the
# commits vetted on 2026-10-11 (team/humans/dinis_cruz/claude-code-web/10/11/case-study/00__vetting.md).
#
# Usage:  review/tools/install_skills.sh [<skills dir>]      default: ~/.claude/skills
#
# Every skill is copied from a shallow clone at the pinned commit, and the sha256 of each
# SKILL.md is checked against review/tools/skills.lock.json. A mismatch stops the install:
# re-vet before moving a pin. Nothing here runs a skill; it only puts the files in place.
set -euo pipefail

DEST="${1:-$HOME/.claude/skills}"
WORK="$(mktemp -d)"
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCK="$HERE/skills.lock.json"
trap 'rm -rf "$WORK"' EXIT

# repo                       pinned commit
PINS="trailofbits/skills       442fc9d6c89b1e937e6f7a477e7071ea75fcbea4
getsentry/skills              d18b7aa8ba878354e5c348310230e652f7690f9c
mrwadams/mcp-stride-gpt       44c58711881e78665112e655f2aa23ee9c3d4745
mrwadams/threat-led-triage    0b67cb1716958001a084d550a4e28194c33c9e13"

# skill name (as installed)   source path inside the repo
# insecure-defaults is a command + workflow plugin with no SKILL.md; its reference corpora
# (references/*.md, *.json) and commands/audit.md are what the review follows by hand.
SKILLS="audit-context-building      trailofbits/skills       plugins/audit-context-building/skills/audit-context-building
insecure-defaults            trailofbits/skills       plugins/insecure-defaults
sharp-edges                  trailofbits/skills       plugins/sharp-edges/skills/sharp-edges
differential-review          trailofbits/skills       plugins/differential-review/skills/differential-review
post-patch-validation        trailofbits/skills       plugins/post-patch-validation/skills/post-patch-validation
fp-check                     trailofbits/skills       plugins/fp-check/skills/fp-check
semgrep                      trailofbits/skills       plugins/static-analysis/skills/semgrep
sarif-parsing                trailofbits/skills       plugins/static-analysis/skills/sarif-parsing
supply-chain-risk-auditor    trailofbits/skills       plugins/supply-chain-risk-auditor/skills/supply-chain-risk-auditor
sentry-security-review       getsentry/skills         skills/security-review
sentry-secret-serialization  getsentry/skills         skills/secret-serialization
sentry-gha-security-review   getsentry/skills         skills/gha-security-review
stride-threat-modelling      mrwadams/mcp-stride-gpt  skills/stride-threat-modelling
threat-led-triage            mrwadams/threat-led-triage skills/threat-led-triage"

clone_at() {                       # $1 repo  $2 commit  -> $WORK/<repo with / as _>
  local repo="$1" commit="$2" dir="$WORK/${1//\//_}"
  git init -q "$dir"
  git -C "$dir" remote add origin "https://github.com/$repo"
  git -C "$dir" fetch -q --depth 1 origin "$commit"
  git -C "$dir" checkout -q FETCH_HEAD
}

echo "$PINS" | while read -r repo commit; do
  echo "clone  $repo @ ${commit:0:12}"
  clone_at "$repo" "$commit"
done

mkdir -p "$DEST"
echo "$SKILLS" | while read -r name repo path; do
  src="$WORK/${repo//\//_}/$path"
  manifest="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['skills'][sys.argv[2]]['manifest'])" "$LOCK" "$name")"
  [ -f "$src/$manifest" ] || { echo "missing: $src/$manifest" >&2; exit 1; }
  actual="$(sha256sum "$src/$manifest" | cut -d' ' -f1)"
  expected="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['skills'][sys.argv[2]]['manifest_sha256'])" "$LOCK" "$name")"
  if [ "$actual" != "$expected" ]; then
    echo "sha256 mismatch for $name: expected $expected, got $actual (re-vet before moving the pin)" >&2
    exit 1
  fi
  rm -rf "${DEST:?}/${name:?}"
  cp -r "$src" "$DEST/$name"
  echo "install $name  ($(echo "$actual" | cut -c1-16))"
done

echo "done: $(echo "$SKILLS" | wc -l) skills in $DEST"
