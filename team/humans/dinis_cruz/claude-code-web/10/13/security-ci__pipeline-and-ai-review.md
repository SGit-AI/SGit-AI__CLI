# Security CI: a dedicated pipeline, and an AI review that can break the build

**Your questions (13 Oct):**
1. Is a dedicated security pipeline worth it?
2. Can some of the checks and AI security reviews run in CI and break the build on anything new?
3. What would that cost, on a cheaper model?
4. How do you create a Claude key for it?

**Short answers:**
1. Yes. It is now `.github/workflows/security.yml`.
2. Yes. The AI review is built, tested without spending anything, and switched **off** until you
   connect it. It is keyless: GitHub's OIDC token through workload identity federation.
3. About **$0.20–0.65 per reviewed PR on Sonnet 5.5**, or **1–16 cents on Haiku 5.5**. Changes
   that touch none of the 45 security-slice files cost nothing.
4. No key is needed: workload identity federation, steps in §6.

## 1. Why a dedicated pipeline

Three reasons:
- **Nothing ran on a pull request.** `ci-pipeline.yml` runs on push to `dev` and `main` only, so
  every gate, including the security job, could only fail after the merge. `security.yml` runs on
  every PR into `dev` or `main`, so a red result blocks the merge rather than reporting it,
  and on every push to `dev`, since that is where changes land here (updated 13 Oct).
- **New advisories and rules arrive without code changes.** A weekly run (Mondays 05:17 UTC) on
  `dev` catches a new CVE in `cryptography` or a new Semgrep rule even when nobody pushes.
- **The workflows themselves had findings.** zizmor found 4 high and 13 medium issues in our
  Actions. They are fixed or recorded (§3).

The release pipeline keeps its own security-tests job, since that job gates publishing. The new
workflow does not replace it.

## 2. The gates (each fails only on what is new)

| Job | What it runs | Fails when |
|---|---|---|
| Security & adversarial tests | `pytest tests/security` | a `Fixed__*` attack works again, or a `Known_Gaps` gap moved |
| Bandit (baseline) | `bandit -r sgit_ai -b tests/security/bandit-baseline.json` (1.9.4) | a finding not in the committed baseline |
| Semgrep (new lines) | `p/python`, `p/security-audit`, `p/secrets`, `r/python.cryptography` (1.178.0) on `sgit_ai` and `review/tools`, `--baseline-commit` = the PR's base | a finding on a line the PR adds or moves. The weekly run reports everything as SARIF and does not fail |
| pip-audit | `--strict` on the runtime dependencies, now **read from `pyproject.toml`** (the release job hardcodes them) | any known advisory |
| zizmor | the workflows and the composite action, `--min-severity medium`, ignores in `.github/zizmor.yml` | a new medium or high finding |
| actionlint | `actionlint` (1.7.12) on the workflows | a workflow GitHub would reject. Added after the first `dev` run of this change failed at load: a duplicated `with:` in the mutation job passed every YAML parser and zizmor |
| review/ graph current | `review/tools/derive.py --check` | never fails: a warning, because a stale graph is a docs debt, not a defect |
| AI security review | `review/tools/ai_review.py` (§4) | a new, confident, medium-or-worse finding that survives a second opinion |

Calibrated here:
- **Semgrep's PR mode** run against the merge I pushed today flagged the three `urlopen` lines in
  the `serve` code. Bandit already had reviewed `nosec` reasons for those lines; they now carry
  `# nosemgrep` as well.
- **Bandit, zizmor and pip-audit** are clean on the branch.

## 3. What zizmor found in our workflows, and what changed

- **template-injection (high, 4).** The composite test action pasted `${{ inputs.* }}` into
  shell text. The values are our own constants today, but the pattern is the classic Actions
  injection.
  - Fix: the inputs now reach the shell as environment variables, with `set -f`.
  - Side effect: the integration jobs' `'mcp<2'` lost its quotes (`mcp<2`). A variable expansion
    never parses `<` as a redirection; I checked the word-splitting in bash.
- **artipacked (medium).** Every read-only job now sets `persist-credentials: false`.
  - The tag job and the two publish jobs keep their credentials, because they push the tag and
    run `git__update_branch`. Each has an inline ignore with that reason.
- **secrets-inherit, excessive-permissions (medium).** The `dev` and `main` callers pass every
  secret and run with default token permissions. Narrowing them changes the publishing path, so
  they are ignored with reasons and left for a release check (follow-up under TM-R21).

**Risk:** these edits touch the release pipeline's test action. They parse, zizmor is clean, and
the word-splitting is checked. The first `dev` run after the merge is the real check, so watch
it.

## 4. The AI review (`review/tools/ai_review.py`)

### Flow

1. **Scope.** Take the PR's changed files that are in the security slice (`review/slice.json`,
   45 files: crypto, host and local boundaries, verify-then-accept, key stores, supply chain).
   If there are none, stop: it costs nothing.
2. **Request.** One request to Claude:
   - *System part (cached):* the rules, `review/intent/*.json`, and the threat model.
   - *User part:* the diff (15 lines of context), each touched file whole, and the function
     dossiers for those files from `review/context/functions/`.
   - Settings: adaptive thinking; effort `medium`; output forced to a JSON schema; server-side
     fallback on (`fallbacks: "default"`), so a safety-classifier decline is retried on another
     model instead of failing. Haiku has no fallback.
3. **Findings.** Each finding has a file and line, a function, a category, a severity, a
   confidence, and **`register`**: the threat-model row it is (TM-F/TM-R), or `new`.
4. **The gate.**
   - It counts only findings that are `new`, at least medium severity and at least 0.8 confidence.
   - If any remain, a **second call tries to refute them**: is the input reachable, is it handled
     elsewhere, did it exist before the diff? Only what survives fails the build.
   - Clean PRs never pay for that second call.
5. **Waivers.** You accept a finding by adding its id (12 hex: file, function and category, not
   the wording) with a reason to `review/findings/ai-waivers.json`. Exit codes:

   | Code | Meaning |
   |---|---|
   | 0 | pass |
   | 1 | new findings |
   | 2 | error |
   | 3 | inconclusive: the model declined or ran out of tokens; nothing was reviewed, which is not a pass |

### What it is not

The diff is attacker-controlled text and the model reads it. A hostile change can argue its way
past the reviewer. So the AI review catches mistakes by honest contributors and agents; the
deterministic gates are the controls. The model gets no tools, so injected text can only change
the verdict. The prompt also asks it to report steering text as a finding.

The job runs only:
- on pushes to `dev`, and on PRs from branches of this repository (a fork's PR never gets an
  OIDC token);
- when the repository variable `SECURITY_AI_REVIEW` is `true` and a federation rule id is set
  for that event.

Never move it to `pull_request_target`.

### Tested without spending anything

- **Wire shape.** A loopback server stood in for the API. It confirmed that the request carries
  the `server-side-fallback-2026-07-01` beta, `fallbacks: "default"`, adaptive thinking, the
  JSON-schema output and the cached system prompt.
- **Paths.** I ran it through the four outcomes:
  - confirmed finding → exit 1 (only the high, new one gates; a low one does not);
  - refuted finding → pass;
  - waived finding → pass, one call only;
  - refusal → exit 3.
- **Unit tests.** `tests/unit/review/test_Review__AI_Review.py` covers the gate rules, waivers,
  the fingerprint, the Haiku price tier, the skip, and a dry run that calls nothing.

### The off-the-shelf alternative

[`anthropics/claude-code-security-review`](https://github.com/anthropics/claude-code-security-review)
runs Claude Code as an agent over the PR (up to 20 minutes) and comments on it.
- It does not fail the build itself. It outputs `findings-count`, so you would add your own
  step to fail on it.
- Its default model is an older Opus. Its README says it is *"not hardened against prompt
  injection attacks and should only be used to review trusted PRs"*.

It is good for PR comments. As a gate, ours is cheaper and predictable, because it is one call
with no tools and known inputs. It also knows our threat model and register, so it can tell new
from known. Both can run if you want PR comments as well.

## 5. Cost (measured inputs, list prices as of 2026-10)

Dry runs (`--dry-run`: counts what would be sent, sends nothing) on five real commits:

| Commit | Slice files | Input tokens (~) | Sonnet 5.5 clean / with findings | Haiku 5.5 clean / with findings | Opus 5.5 clean / with findings |
|---|---|---|---|---|---|
| `b32a6ba` sgit serve | 2 | 61k | $0.19 / $0.32 | $0.01 / $0.02 | $0.38 / $0.64 |
| `9362a25` TM-F32..36 | 4 | 75k | $0.22 / $0.38 | $0.01 / $0.02 | $0.44 / $0.76 |
| `fbd550f` pull guard | 4 | 75k | $0.22 / $0.38 | $0.01 / $0.02 | $0.44 / $0.76 |
| `eb7941c` bulk fetch | 4 | 109k | $0.29 / $0.51 | $0.07 / $0.13 | $0.57 / $1.03 |
| `a5e6043` partial clones | 7 | 144k | $0.36 / $0.65 | $0.09 / $0.16 | $0.71 / $1.30 |

**How the numbers are built:**
- Input is about 16k tokens of system (design plus threat model) plus the change.
- Output is assumed at 6k tokens per review and 4k per verification, including thinking. The
  real figure is printed in the job summary once it runs.
- Prices per million tokens (input / output):
  - Sonnet 5.5: $2 / $10.
  - Haiku 5.5: $0.10 / $0.50, or $0.50 / $2.50 past 100k input tokens, which is why the larger
    commits jump.
  - Opus 5.5: $4 / $20.

**Per month**, at 60 PRs that touch the slice:

| Model | Per month | Before your first top-up | Spend limit to set |
|---|---|---|---|
| Sonnet | about $15–40 | a $10 credit covers about 30 reviews | $25 |
| Haiku | about $1–5 | | |

**Which model.**
- Start with **Sonnet 5.5**, the default (`SECURITY_AI_REVIEW_MODEL` changes it with no code
  edit). Haiku 5.5 is about 20 times cheaper per token, but finding security bugs is reasoning
  work, and a gate that misses or invents findings costs more in attention than it saves.
- **Measure before you choose.** Your branch gives a ready-made test with known answers: review
  the five fixes *backwards*, so the "change" re-introduces TM-F32..F36. Commands are in §6. A
  model that does not flag them is not worth its price at any price. That is under $1 on Sonnet
  and a few cents on Haiku.
- Batch pricing (50% off) does not suit a PR gate, which needs the answer in minutes. It would
  suit a later weekly sweep of the whole slice: about 150k tokens of code, roughly $1.30 on
  Sonnet, $0.65 batched.

## 6. Switching it on: keyless, with workload identity federation

*Updated 13 Oct. This replaces the API-key setup first written here.*

The CI job holds **no API key**. It asks GitHub for a short-lived OIDC token (about 5 minutes)
for the audience `https://api.anthropic.com`, and the SDK exchanges that token once for an
Anthropic token bound to a service account. Billing goes to the organization that owns the
service account (the one with the credits), attributed to the rule's workspace.

The job runs on every **push to `dev`**, since that is where changes land here. It can also run
on PRs. It reviews `before..after` of the push. A push that touches no security-slice file
(release-badge commits, docs) is skipped at no cost.

### In the Claude Console (organization admin)

1. **Settings → Workspaces → Create workspace** `sgit-ci`. Click the workspace, then
   **Spend limits**, and set the monthly cap, for example $25 with an alert at 50%.
2. **Settings → Workload identity → Connect workload → GitHub Actions.** The wizard creates
   the issuer, the service account and the rule together. It is better than the bare
   *Register issuer* dialog.
   - **Issuer:** name `github-actions`, issuer URL `https://token.actions.githubusercontent.com`,
     JWKS source *OIDC discovery*. Leave the discovery URL and CA certificate empty.
   - **Service account:** for example `sgit-ci-security-review`, member of workspace `sgit-ci`.
   - **Rule for pushes to dev** (the one the job needs):
     - subject: `repo:SGit-AI/SGit-AI__CLI:ref:refs/heads/dev` (exact, no `*`);
     - audience: `https://api.anthropic.com`;
     - claims: `repository_id` = `1187093532`, `repository_owner_id` = `269696930`,
       `ref` = `refs/heads/dev` (numeric ids survive a rename);
     - workspace `sgit-ci`, scope `workspace:developer`, token lifetime 600 s.
   - **Optional second rule for PRs:** subject `repo:SGit-AI/SGit-AI__CLI:pull_request`, same
     audience and id claims, no `ref`.
3. Note the ids: rule `fdrl_…`, service account `svac_…`, workspace `wrkspc_…`, and the
   organization id (Settings → Organization).

### In GitHub (Settings → Secrets and variables → Actions → *Variables* tab)

None of these values is a secret: without a GitHub token that matches the rule, they mint
nothing.

| Variable | Value |
|---|---|
| `SECURITY_AI_REVIEW` | `true` |
| `ANTHROPIC_ORGANIZATION_ID` | the organization id |
| `ANTHROPIC_SERVICE_ACCOUNT_ID` | `svac_…` |
| `ANTHROPIC_WORKSPACE_ID` | `wrkspc_…` |
| `ANTHROPIC_FEDERATION_RULE_ID` | the dev-push rule, `fdrl_…` |
| `ANTHROPIC_FEDERATION_RULE_ID_PR` | optional: the PR rule |
| `SECURITY_AI_REVIEW_MODEL` | optional: `claude-haiku-5-5` (the default is Sonnet 5.5) |

Do **not** add an `ANTHROPIC_API_KEY` secret. A set key, even an empty one, takes precedence
over federation; the job unsets it anyway.

**Who can spend.** Anyone who can push to `dev` can run a workflow that mints a token.
Forks cannot: a fork's PR gets no OIDC token. The workspace spend limit is the backstop.

**Tested here without spending anything.** I ran the job's exact shell step against a local
stand-in for both GitHub's token endpoint and Anthropic's token exchange:
- the GitHub token is requested with the right audience;
- it is exchanged **once**, with the rule, organization, service-account and workspace ids;
- API calls carry the federated bearer token;
- an empty API key is unset;
- an all-zero push base falls back to the parent commit;
- the token file is deleted afterwards;
- a gating finding gives two API calls on one exchange, and the step exits 1.

`ai_review.py` now makes one SDK client per run. Before this fix, the second call created a new
client, which would have re-presented the single-use GitHub token and been refused
(`jti_reused`).

**Locally**, with your own key and never in a repo file, the commands in §5 still work:
`export ANTHROPIC_API_KEY=…` and `python3 review/tools/ai_review.py --base 9362a25 --head 9362a25^`.

## 7. Next steps (not done here)

- A weekly whole-slice AI sweep through the Batch API, with findings written as records under
  `review/findings/`.
- Narrowing `secrets: inherit` and the default token permissions in the dev and main callers,
  with a release check.
- A committed lockfile, so pip-audit checks what is installed, not what could be (TM-R21).
- `review/tools/derive.py` running in CI and committing the graph, rather than warning.
