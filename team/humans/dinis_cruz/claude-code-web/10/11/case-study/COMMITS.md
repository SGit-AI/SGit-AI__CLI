# Commits to make from this working tree

Written 2026-10-11 by the sgit-ai CLI agent. The session could not commit after its first
pre-fix test run removed `/tmp/code-sign` (the commit-signing helper git is configured to use);
restoring it needs a person's approval. Three commits are already on
`claude/youthful-feynman-bpunv5` (research pack, step 0, step 1 part, step 2, step 3 part);
everything below is uncommitted and verified (full unit + security suites green, every new
attack test shown failing on the pre-fix commit in a clean worktree).

From the repository root, in this order:

```bash
# 1. the four fixes with their tests, register rows and changelog
git add sgit_ai/crypto/pki/PKI__Key_Store.py sgit_ai/crypto/pki/PKI__Keyring.py sgit_ai/cli/CLI__PKI.py \
        sgit_ai/core/actions/push/Vault__Batch.py sgit_ai/core/actions/push/Vault__Sync__Push.py \
        sgit_ai/core/actions/index/Vault__Index_Sync.py sgit_ai/core/Vault__Sync__Base.py \
        sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py sgit_ai/workflow/clone/Step__Clone__Download_Index.py \
        tests/security/test_Security__Fixed__PKI_Paths.py tests/security/test_Security__Fixed__Lying_Host.py \
        tests/security/test_Security__Fixed__Index_Overwrite.py tests/unit/sync/test_Vault__Batch__Coverage.py \
        tests/unit/sync/test_Vault__Sync__Push__Coverage.py tests/unit/workflow/clone/test_Step__Clone__Download_Index__Fallback.py \
        team/explorer/appsec/threat-model/v0.21.0__threat-model.md CHANGELOG.md
git commit -m "fix: five host and local answers no longer taken as control (TM-F32..TM-F36)

- TM-F32 pki stores validate the fingerprint before building a path (sgit pki delete .. emptied ~/.sg-send)
- TM-F33 a push the host acknowledged with an empty body is not pushed (batch and individual-write paths)
- TM-F34 a clone that has synced refuses to resync over an empty listing (host-induced rewind under a legitimate key)
- TM-F35 a branch index that is present but unreadable refuses the clone instead of degrading to no policy
- TM-F36 a server index this build cannot parse is never overwritten by push, tag or vault format
- delete-on-remote forgets the clone's accepted heads so the recreated vault's push is a first push again
- tests: 46 attack cases that fail on the code before the fixes, 11 controls; existing unit tests that
  encoded the old behaviours updated; register rows TM-F32..F36; CHANGELOG [Unreleased]

Found by the round-1 tool-assisted security review (review/findings/)."

# 2. the CI gate (TM-R21) and the skill rule
git add .github/workflows/ci-pipeline.yml tests/security/bandit-baseline.json library/skills/sg-send-cli__SKILL.md
git commit -m "ci: Bandit against a committed baseline and pip-audit --strict in the security job (TM-R21); skill rule: keys never leave the vault"

# 3. the review data: dossiers, findings, ranking, per-file records, refreshed graph
git add review/
git commit -m "Security review steps 1-5: 270 function dossiers, 104 finding records, the ranking, 41 per-file security records, refreshed graph"

# 4. the case study
git add team/humans/dinis_cruz/claude-code-web/10/11/
git commit -m "Security review step 6: case study with per-tool counts, vetting record, commit plan"

git push -u origin claude/youthful-feynman-bpunv5
```

Each commit message should end with the session's attribution lines:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019h8FuSstSk1ANp93DrBbnz
```
