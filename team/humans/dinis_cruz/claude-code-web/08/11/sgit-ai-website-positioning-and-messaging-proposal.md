# sgit.ai — Website Positioning, Messaging & Content Proposal

**Date:** 2026-08-11
**Author:** Claude Code (web session), for Dinis Cruz
**Inputs:** deep teardown of dolthub.com / dolt (research notes with sources in Appendix B); full inventory of this repository at v0.14.27 (CLI surface, crypto, docs, team paper trail — Appendix A)
**Deliverable:** the structure, messaging, and content plan for **sgit.ai**, deployed as GitHub Pages, with a features/use-cases marketing section and a technical docs section.

---

## Executive Summary

Dolt spent six years building the "Git for Data" category with a developer-led playbook — literal git analogies, terminal demos as the product explanation, radical benchmark honesty, comparison-page SEO, and a lean site (Product · Docs · Blog · Pricing) — then in 2025-26 re-aimed the *same* story at AI agents: "Agents need branches. Dolt is the only SQL database with branches. Dolt is the database for agents." Crucially, they layered rather than replaced: the agent hook is the hero; "Git for Data" still anchors the page below it.

sgit can run the same playbook from a stronger *differentiated* position: Dolt gives agents branches; **sgit gives agents (and humans) branches *and* privacy**. Nobody else occupies "git workflows over zero-knowledge encrypted storage." The proposal below:

1. **Positioning:** lead with the agent story ("Agents need shared state. Shared state needs versioning — and privacy."), anchor on the durable identity ("sgit is git for encrypted vaults"), and keep the Ambassador's approved line "Encrypted vaults. Git workflows. Zero knowledge." as the brand triplet.
2. **Site structure:** a single static site (landing + `/use-cases/` + `/docs/`) on GitHub Pages at sgit.ai, with the CLI reference **generated from the argparse tree in CI** so docs can never go stale (the #1 problem with the repo's existing guides).
3. **Trust strategy:** copy Dolt's honesty plays, which work *better* for a small project than for a funded one — publish the AppSec findings, the "what the server can see" table, a "When NOT to use sgit" page, the Alpha status, and the currently-disabled commands, prominently.
4. **Content engine:** a small "So you want an encrypted git?" comparison franchise, three agent-workflow stories that are already true (the multi-agent vault paper trail in this repo), and an `AGENTS.md`-in-every-vault feature that is both product and marketing.

Everything proposed as a *claim* below is backed by code or docs in this repo; where the repo says something is stubbed, disabled, or Alpha, the site must say so too. That constraint is the strategy, not a limitation of it.

---

# Part 1 — What Dolt/DoltHub Actually Do (Teardown)

## 1.1 The pitch stack: one analogy, three altitudes

Dolt's positioning is a ladder of three sentences that appear verbatim everywhere (homepage meta, README, docs intro):

1. **Category one-liner:** "Dolt is Git for Data!"
2. **Mechanism sentence:** "Dolt is a SQL database that you can fork, clone, branch, merge, push and pull just like a Git repository."
3. **The joke that makes it stick:** "It's like Git and MySQL had a baby."

Three properties worth noting: it's **literal, not metaphorical** (the CLI verbs *are* git's verbs — "All the commands you know for Git work exactly the same for Dolt"), it **survives being quoted out of context**, and the **command list itself is the demo** — a git user who sees `dolt init/branch/diff/merge/clone/push` understands the product before reading a paragraph.

## 1.2 The 2025-26 agent pivot — layered, not replaced

The current homepage hero:

> Eyebrow: **AGENTS NEED VERSION CONTROL**
> H1: **Dolt is the Database for Agents**
> Sub: *The only version-controlled SQL database*

The agent narrative was built deliberately over 18 months of blog posts:

- *"Dolt for Agentic Workflows"* (2025-03): "Could version control also allow thousands of AI and human agents to collaborate asynchronously on large, complicated systems?" Without it, agent workflows are "limited to very simple tasks that must be overseen by human review."
- *"AGENT.md"* (2025-08): every Dolt database now ships an AGENT.md that teaches coding agents how to use Dolt — a product feature that *is* marketing. Contains the mantra: "Agents need branches. Dolt is the only SQL database with branches. Dolt is the database for agents."
- *"So you want an AI Database?"* (2025-12): "Code is stored in files. The rest of our data is stored in databases. AI requires version-controlled databases." And the honest kicker: "Dolt wasn't built for AI… It just so happens that AI needs Dolt's features to reach its full potential."
- *"Agentic Memory"* (2026-01) and *"Multi-Agent Persistence"* (2026-03): memory as "a graph of context with branches and merges," and "to get many agents to work together, they all need to cooperate on some shared state."
- *"BranchBench"* (2026-06): they invented a benchmark for agentic branching — "Future agents will create thousands of branches — forking a candidate state, mutating it, evaluating the result against other branches, and pruning irrelevant states."

The mechanics of the pivot: same product story, re-aimed. "Human PR review for data" became "human-in-the-loop review of agent writes." "Branch to experiment" became "a branch per agent." And they **kept "Git for Data" on the page** — it moved down from the hero to the product grid. The layering is the copyable part.

## 1.3 Homepage anatomy

Section order on dolthub.com: agent hero → humans-and-agents video → featured **blog cards** (the blog is a first-class homepage citizen) → "Marry Git and SQL" feature bullets → **4-tab interactive terminal demo** (branch → change → diff → merge, with real colored terminal output) → social proof (live GitHub star count + founder pedigree bios) → the "DOLT YOUR WAY" product grid.

Navigation is radically lean: **Databases · Pricing · Documentation · Blog**, plus Discord and a GitHub button with a live star count. No "Solutions" megamenu, no "Resources." Docs, blog, and stars do all the work.

## 1.4 The product grid — analogies as pricing

Each product card carries a "Think of it as:" tag that does the explanatory work of a pricing page:

| Product | Analogy tag |
|---|---|
| Dolt | "Git for Data" (open source, free) |
| DoltHub | "GitHub for Dolt" (hosting, free public + paid private) |
| DoltLab | "GitLab for Dolt" (self-hosted enterprise, $5k/mo) |
| Hosted | "AWS for Dolt" (managed, from $50/mo) |
| Workbench | "DataGrip for Dolt" |

The free/paid boundary needs zero prose: **the database is entirely free; you pay for hosting, collaboration, or managed infrastructure** — exactly the Git/GitHub/GitLab split the audience already understands.

## 1.5 Trust through radical honesty

This is Dolt's most distinctive move and the most transferable one:

- **Correctness benchmarks in the docs**, updated every release: sqllogictest at 5.9M queries, currently 100%, *including* honest sub-metrics (73% MySQL function coverage, a "Skipped Engine Tests" confession).
- **Unflattering latency numbers published for years**: "Dolt is 2X slower than MySQL" was their published goalpost; today's page still discloses "about 40% of the transactional throughput on TPC-C than MySQL."
- **A whole anti-pitch page**: *"When NOT to Use Dolt"* — "If you are looking for a simple solution to a small versioning problem, Dolt is probably not the database for you"; no horizontal scaling; "Your DBA Says No."
- **The "So you want X?" comparison franchise**: one evergreen page per search intent (Git for Data / Database Version Control / Data Version Control / AI Database…), each surveying the *whole* market generously ("we like what we see" about lakeFS) before making a measured claim. Owning the query while praising competitors reads as confidence.

## 1.6 README shape

Pitch in the first 17 lines → the full CLI command list as the first runnable output (the demo) → one-command install with candor ("Dolt is a single ~103 megabyte program", literal `du -h` output) → a long, casual, founder-voiced tutorial inline in the README.

## 1.7 What NOT to copy (scale-dependent moves)

- **Daily blog cadence** — powered by a funded ~15-person team with blogging written into the culture. Copy the formats, not the volume; monthly is fine.
- **Founder-pedigree social proof** ("led the effort to move all of Amazon to Git") — substitute concrete artifacts: real workflows, test counts, open security reviews.
- **A seven-product grid** — from a small project this reads as vaporware. Three cells maximum.
- **"World's first and only" superlatives** — Dolt can defend them with six years of published evidence. An unsupported superlative from a new project invites debunking.
- The **contrast case** (lakeFS/DVC post-merger) shows the sales-led alternative: persona-split homepages, Book-a-Demo CTAs, Fortune-500 badges. For a CLI-first open-source project, Dolt's self-serve, terminal-demo, engineering-blog end of the spectrum is the one to emulate.

---

# Part 2 — What Transfers to sgit (and What's Different)

## 2.1 The structural rhyme

sgit is already, accidentally, a very close structural match to Dolt's playbook:

| Dolt move | sgit equivalent (already true today) |
|---|---|
| Git verbs as the product | `sgit init / clone / commit / push / pull / status / diff / log / branch / merge / stash / revert / reset / fsck` — the command list is the demo |
| "Git and MySQL had a baby" | "git and a password vault had a baby" (see §3.2) |
| Agents need branches | Agents need **private, versioned shared state** — and sgit's `write`, `--json`, sparse clones, and the Claude Skill already exist for exactly this |
| AGENT.md in every database | The `sgit` Claude Skill already exists; propose `AGENTS.md` in every vault (§5.4) |
| DoltHub / Hosted / DoltLab grid | sgit (CLI) · SG/Vault (browser) · SG/Send (API) — a natural three-cell grid (§4.2, section 8) |
| sqllogictest correctness page | Cross-implementation **crypto interop test vectors** (CLI ↔ Web Crypto, byte-for-byte) — mandated by CLAUDE.md, verifiable by anyone (§5.3) |
| "When NOT to Use Dolt" | "When NOT to use sgit" — Alpha status, disabled sharing commands, not-a-secrets-manager (§5.2) |
| Two implementations, one engine | **Two independent implementations of one wire format** (sgit CLI and the SG/Vault web client), negotiated through a formal contract with test vectors — a *stronger* story than "powered by" (§3.4) |

## 2.2 The differentiator Dolt doesn't have

Dolt's agent pitch is *branches*. sgit's is **branches + zero knowledge**. Every agent-workflow argument Dolt makes ("isolation until review and merge," "every change auditable," "shared state for multi-agent cooperation") applies to sgit — and then sgit adds the claim Dolt cannot make: *the storage provider never sees the plaintext*. For agent workflows involving personal data, client documents, security findings, or anything an organisation won't put in a third-party database, that's not a feature, it's the qualifying criterion.

This also resolves the "why not just use git + encryption?" objection cleanly (and honestly — the Ambassador's competitor table already covers git-crypt/age/SOPS): git-crypt encrypts *contents* but leaks filenames, history structure, and commit messages; sgit's server sees only opaque HMAC-derived IDs, ciphertext, sizes, and timestamps. That's the comparison-page franchise (§5.2).

## 2.3 The constraint Dolt doesn't have

sgit is **Alpha** (its own classifier says so), token-based sharing is **currently disabled** pending a security rework, and `clone --bare` is stubbed. The Ambassador's messaging decisions log already bans overclaiming ("Acknowledge alpha maturity honestly… Do not overclaim stability"; no "military-grade"). Dolt's lesson is that this constraint is an *asset* if published deliberately: a project that discloses "we disabled our own sharing feature because the token scheme lacked expiry and revocation" earns more trust with security-minded early adopters than one that ships it quietly. Lead with the paper trail (12 public AppSec findings, mutation tests, 4,000+ tests) — that *is* the social proof at this stage.

---

# Part 3 — Positioning & Messaging for sgit.ai

## 3.1 The pitch stack (three altitudes, use verbatim everywhere)

1. **Category one-liner:** **"sgit is git for encrypted vaults."**
2. **Mechanism sentence:** **"Clone, commit, branch, diff, and merge folders of files that are encrypted with AES-256-GCM before they leave your machine. The server stores ciphertext under opaque IDs — it never sees your filenames, your contents, or your commit messages."**
3. **The sticky line:** **"It's like git and a password vault had a baby."**

Plus the **agent mantra**, mirroring Dolt's three-line cadence:

> **Agents need shared state.
> Shared state needs versioning — and privacy.
> sgit is the encrypted, versioned workspace for humans and AI agents.**

And the durable **brand triplet** (already approved in the Ambassador review, keep it): **"Encrypted vaults. Git workflows. Zero knowledge."**

## 3.2 Hero — layered, Dolt-style

**Recommended (agent-forward hero, durable identity below the fold):**

> Eyebrow: `AGENTS NEED PRIVATE, VERSIONED STATE`
> **H1: The encrypted git for humans and AI agents**
> Sub: *Version, branch, and share vaults of files that are encrypted before they leave your machine. Zero knowledge: the server stores ciphertext, not your data.*
> Primary CTA: `pip install sgit-ai` (copy button) · Secondary CTA: **Get started in 5 minutes →**

Then, further down the page, the durable section heading: **"Git workflows. Encrypted vaults. Zero knowledge."** — so that if/when the agent zeitgeist moves on, the hero swaps and nothing else changes.

**Conservative alternative** (if leading with agents feels premature): hero = the brand triplet, agents as section 5 of the page. The page structure in Part 4 works for either ordering; only the hero and section 5 swap.

## 3.3 Audience value propositions

Keep the Ambassador's three audiences, add the fourth that has emerged since:

- **Developers & git users:** "You already know how to use it. `sgit clone`, edit, `sgit commit`, `sgit push` — same muscle memory, but every byte is encrypted client-side. No staging area, no new mental model beyond one: your vault key is the URL, the auth, and the encryption key in one string."
- **AI-agent builders (new, primary for launch):** "Give your agents a shared, durable, *private* workspace. `sgit write` commits a file to a vault in one call with `--json` output; sparse clones keep agent startup fast; every agent works on its own branch and a human reviews the merge — in the browser, via SG/Vault."
- **Security teams:** "Zero-knowledge by construction, and auditable: open source (Apache-2.0), byte-for-byte Web Crypto interop test vectors, a published threat model that tells you exactly what the server *can* see (sizes, timing, vault ID), and our AppSec review findings in the open."
- **Teams handling sensitive documents:** "A shared folder with history, where the hosting provider cannot read the contents. Clone it, work offline, push when ready; restore any prior version."

## 3.4 Proof points (all verifiable from the repo — the site should link to each)

- **~4,000 tests** (3,816 unit / 139 QA scenario / 79 integration), plus **mutation testing in CI** — integration tests run against a *real* in-memory SG/Send server, not mocks (a project rule: "No mocks. Write real tests against real objects").
- **Byte-for-byte browser interop:** every crypto operation must match Web Crypto output given the same inputs; test vectors are mandatory, per project law (CLAUDE.md).
- **Two independent implementations, one wire contract:** the sgit CLI and the SG/Vault web client interoperate on the same vaults through a formal, versioned wire-format contract with test vectors — with real interop bugs found on both sides and fixed. Say this *instead of* "SG/Vault is powered by sgit"; it's more precise and more impressive.
- **Real multi-agent usage:** agent teams have collaborated through live vaults, filed structured bug reports about *reading each other's commits*, and driven shipped features (read-only `history show`/`diff` on-demand fetch; 3-way `resolve --show` with a genuine/one-sided verdict). This is the battle-hardened story — tell it as a case study (§5.1).
- **Open security posture:** 12 AppSec findings (F01–F12) worked through with individual public debriefs; secrets-safety by default (`.env*`, `.netrc`, `id_rsa`, etc. are *always* ignored so they can't be swept into a vault); 600k-iteration PBKDF2; KDF cache clearing; 0600 perms on sensitive files.
- **Tiny dependency surface:** two runtime dependencies (`osbot-utils`, `cryptography`). For a security tool this is a headline feature — put it on the security page.

## 3.5 Messaging guardrails (non-negotiable, several already ruled)

1. **No "military-grade," no unsupported superlatives, no "world's first."** (Ambassador decisions log; Dolt's superlatives are defensible only because of six years of published evidence.)
2. **"Zero knowledge" must always be immediately qualified** by the honest disclosure: the server does see the vault ID, encrypted object sizes, and modification timing. The precision is the credibility.
3. **Alpha status stated plainly** on the landing page footer and the install page — "sgit is in alpha; the vault format is versioned and migrations are provided (`sgit migrate`), but expect rough edges."
4. **Disabled commands disclosed on the site**, with the reason: `share send`/`publish`/`export` and Simple-Token vault creation are switched off while the token scheme gains expiry, revocation, and scoping. Frame as the security process working, link the CHANGELOG entry.
5. **sgit is not a secrets manager.** It refuses to commit `.env` and key files by design. Say so; it pre-empts the wrong comparison (Vault/1Password) and strengthens the right one (git-crypt/age/SOPS/Syncthing-with-history).
6. **Fix before launch:** the stale `_version.py` (v0.1.0 vs the real v0.14.27) — trivial, but the kind of thing a security-curious visitor finds in the first five minutes.

---

# Part 4 — Site Structure

## 4.1 Sitemap

```
sgit.ai/                          # landing (Part 4.2)
├── use-cases/
│   ├── ai-agents/                # persistent private memory for agents
│   ├── multi-agent/              # branch-per-agent collaboration + human merge review
│   ├── human-ai-collaboration/   # human in SG/Vault browser ↔ agent in CLI
│   ├── encrypted-backup/         # versioned encrypted folder sync
│   └── secure-file-exchange/     # PKI sign/verify/encrypt/decrypt
├── security/                     # threat model, what the server sees, AppSec findings, interop vectors
├── compare/                      # "So you want an encrypted git?" franchise (§5.2)
├── blog/                         # (phase 2 — can start as links to dinis's existing channels)
├── docs/                         # (Part 4.3)
└── community/                    # GitHub, issues, the Claude Skill, contributing
```

Navigation, Dolt-lean: **Use Cases · Docs · Security · Blog** + GitHub button (live star count) — four items, nothing else. Footer: Apache-2.0, alpha notice, CHANGELOG, sgraph.ai ecosystem links, privacy.

## 4.2 Landing page — section by section (with draft copy)

**1. Hero** — as §3.2, with `pip install sgit-ai` copy-button. (Candor detail worth stealing from Dolt's "~103 MB program": *"Two runtime dependencies. Pure Python. `pip install sgit-ai` and you have `sgit`."*)

**2. The terminal demo — a 5-tab interactive walkthrough.** This is the single highest-value asset on the page; Dolt's 4-tab version is their best product explanation. Static HTML/CSS tabs with real (colored) captured output — no JS framework needed:

1. **Create** — `sgit create my-vault` → vault key printed, "keep this safe — it's the address, the auth, and the encryption key."
2. **Work like git** — edit files; `sgit status`; `sgit commit -m "first draft"`.
3. **See history & diffs** — `sgit history log --oneline`; `sgit history diff` (colored).
4. **Sync** — `sgit push`; on another machine `sgit clone <vault-key>`; `sgit pull`.
5. **Agent mode** — `sgit write notes/finding.md --file result.md --message "agent A: analysis" --push --json` → one call, machine-readable output, no working-directory scan. Caption: *"This is the command your AI agent uses."*

**3. "Git workflows. Encrypted vaults. Zero knowledge."** — the durable-identity section. Six feature bullets (mirroring Dolt's "Marry Git and SQL" list, every one shipped today):

- **Git-like version control** — commit, branch, merge, diff, log, stash, revert your encrypted files
- **Client-side encryption** — AES-256-GCM before upload; keys derived from your vault key, never sent
- **Real three-way merge** — with conflict files and a base/ours/theirs `resolve --show` view
- **The two-branch model** — a private clone branch per machine/agent, shared named branches for collaboration
- **Sparse & partial clones** — structure now, content on demand; thin clones for agents on a time budget
- **Browser interop** — open the same vault at vault.sgraph.ai; CLI and web speak one wire format

**4. "What the server sees" — the signature visual.** A two-column diagram, *your machine* vs *the server*. Left: filenames, contents, commit messages, branch names, file counts. Right: opaque IDs (`obj-cas-imm-3f9c…`), ciphertext blobs, sizes, timestamps. One caption: *"That's the whole list. We publish the threat model, including what the server* can *see."* → links to `/security/`. No other project in the git-for-X space can draw this diagram; it should become sgit's most-shared image.

**5. "Built for agents" section.** The agent mantra (§3.1) as the heading, then three concrete columns:

- **Persistent memory** — "A vault is just a folder. An agent clones it, reads and writes files normally, commits, pushes. The next session pulls and continues. State survives the context window." → the Claude Skill.
- **Multi-agent, human-merged** — "Each agent gets its own private clone branch; work meets on named branches; a human reviews the merge — in the terminal or in the SG/Vault browser."
- **Agent-grade plumbing** — "`sgit write` for surgical single-call commits, `--json` on every read path, `cat --id` with zero network calls, sparse clones for fast cold starts."

**6. Use-case cards** — five cards linking to `/use-cases/*` (list in §4.1), each with one screenshot/terminal capture and a "used in the wild" line where true.

**7. Trust & proof strip** — the §3.4 numbers as a horizontal band: `~4,000 tests · mutation testing in CI · 2 runtime deps · Apache-2.0 · security reviews published · alpha and honest about it`. Each links to evidence. This replaces Dolt's founder-bio section (the pedigree play doesn't transfer; the artifact play does).

**8. Ecosystem grid — three cells, analogy-tagged** (Dolt's "Think of it as" pattern):

| | Think of it as | |
|---|---|---|
| **sgit** | *git, for encrypted vaults* | Open source CLI. Free. `pip install sgit-ai` |
| **SG/Vault** | *the web app for your vaults* | Browse, edit, and review the same vaults at vault.sgraph.ai — an independent implementation of the same wire format |
| **SG/Send** | *the transfer API underneath* | The zero-knowledge storage service both clients speak to. Self-hosting story: the same in-memory server our integration tests run against |

**9. Closer** — install command again + "Star on GitHub" + link to the 5-minute quickstart. (Community CTA: GitHub Discussions/Issues initially; add Discord only when there's someone to answer it.)

## 4.3 Docs section — information architecture

Dolt's skeleton (Introduction → Concepts → Reference → Guides), adapted. The Concepts section is the Rosetta stone — Dolt's docs are explicitly organised as a Git-to-Dolt mapping, and sgit already has the perfect seed document (`sgit-for-git-users.md`, needs refresh).

```
docs/
├── introduction/
│   ├── what-is-sgit            # pitch stack + architecture diagram + honest maturity note
│   ├── installation            # pip, pipx, Docker; Python >=3.11; sgit doctor for verification
│   ├── quickstart              # 5 minutes: create → commit → push → clone elsewhere → pull
│   └── use-cases               # mirror of /use-cases/ in doc form
├── concepts/
│   ├── sgit-for-git-users      # the Rosetta stone: equivalence table + the 3 deliberate differences
│   │                           #   (no staging area; vault key = URL+auth+key; two-branch model)
│   ├── vaults-and-vault-keys   # {passphrase}:{vault_id}; why IDs are opaque; key hygiene
│   ├── the-two-branch-model    # clone branches vs named branches; what `status --explain` shows
│   ├── what-the-server-sees    # the threat model page (also the /security/ centrepiece)
│   └── objects-and-ids         # commits/trees/blobs; self-describing ID scheme; CAS dedup
├── guides/
│   ├── working-with-ai-agents  # the Skill, `sgit write`, --json patterns, sparse/headless clones
│   ├── multi-agent-collaboration # branch-per-agent; reading peers' commits read-only
│   │                           #   (history show/diff); resolve --show; merge review
│   ├── branching-and-merging   # branch new/switch/checkout; three-way merge; conflicts
│   ├── sparse-and-thin-clones  # --sparse, fetch, clone-branch, clone-range, clone-headless
│   ├── backup-restore-move     # vault backup/restore; vault move (key rotation); uninit
│   ├── pki                     # keygen, sign/verify, encrypt/decrypt, contacts keyring
│   └── troubleshooting         # sgit doctor; the SSL per-OS fixes; friendly-error catalogue
├── reference/
│   ├── cli/                    # ⚠ GENERATED from the argparse tree in CI — one page per
│   │                           #   command/namespace incl. plugins (history, inspect, file, check)
│   ├── crypto                  # constants table, key-derivation chain diagram, wire layout,
│   │                           #   deterministic-IV rationale, published test vectors
│   ├── wire-format             # the branch-index contract (adapted from the architect contract doc)
│   ├── transfer-api            # endpoints, batch semantics, CAS via write-if-match, limits
│   └── json-output             # schemas for every --json flag (agents' reference page)
└── project/
    ├── security                # AppSec findings F01–F12 index; disclosure policy; report a vuln
    ├── limitations             # "When NOT to use sgit" (§5.2) — linked from the landing footer
    ├── roadmap                 # incl. honest "disabled pending rework" items (Simple Tokens,
    │                           #   author attribution, merge drivers, bare clones)
    ├── changelog               # rendered from CHANGELOG.md
    └── contributing            # Type_Safe rules digest; how the agent teams work (a curiosity draw)
```

**Critical implementation rule:** every existing prose guide in the repo predates the namespace restructure, the plugin system, three-way merge, and the token disablement. **Command tables must be generated from `CLI__Main.py` + plugin parsers, never hand-written** (see §6.3); crypto details must come from `Vault__Crypto.py`, not the stale architecture doc. The seed documents and their specific staleness are catalogued in Appendix A.

---

# Part 5 — Content Plan

## 5.1 Launch content (write once, evergreen)

1. **"sgit: git for encrypted vaults"** — the manifesto post; the pitch stack, the server-sees diagram, the honest maturity statement. This is the Show-HN / lobste.rs artifact.
2. **Case study: "Two implementations, one wire format"** — how the CLI and the SG/Vault web client interoperate through a versioned contract with test vectors, including the real interop bugs (`bare/idx` vs `bare/indexes`; the `current` lookup key) found and fixed on both sides. Engineering-blog catnip, and it *is* the battle-hardened story.
3. **Case study: "When your collaborator is another agent"** — the multi-agent vault legibility story, straight from the repo's paper trail: two agent teams sharing a vault, the read-only inspection problem (`pull` merges, so agents couldn't safely *look* at peers' commits), and the shipped fixes (`history show/diff` on-demand read-only fetch; `resolve --show` verdicts). No one else has this story with receipts.
4. **"Persistent, private memory for Claude sessions"** — the Skill walkthrough: install → clone/receive → work → commit+push → next session pulls. Ends with the AGENTS.md feature (§5.4).

## 5.2 The comparison franchise — "So you want an encrypted git?"

One page per search intent, Dolt-format (survey the whole field generously, close with a measured claim):

- **"So you want to encrypt a git repo?"** — git-crypt, git-remote-gcrypt, age+git, transcrypt. Honest about each; the sgit claim: those encrypt *contents* inside a structure the host still reads (filenames, history, messages) — sgit's host sees only opaque IDs and ciphertext.
- **"So you want encrypted file sync with history?"** — Syncthing, restic/borg (backup ≠ collaboration), Cryptomator+Dropbox, Keybase (encrypted git, discontinued momentum — its existence proves demand). sgit claim: sync tools have no branches; backup tools have no merge; sgit is the workflow tool.
- **"So you want a private workspace for AI agents?"** — the direct Dolt conversation: Dolt gives agents branches in a SQL database; sgit gives agents branches over *files*, end-to-end encrypted. Be generous to Dolt (structured data → Dolt is right); claim the private-files territory.
- **"When NOT to use sgit"** — the anti-pitch, published early: not a secrets manager (it refuses `.env` by design); alpha, expect migrations; token sharing disabled mid-rework; no horizontal-scale ambitions; large-binary behavior (4 MB blob threshold → S3 path) documented honestly.

## 5.3 The published-metric play (sqllogictest analog)

Pick one objective, third-party-verifiable metric and publish it every release, ugly or not. For sgit: the **cross-implementation interop suite** — N crypto test vectors (PBKDF2/HKDF/AES-GCM byte-for-byte vs Web Crypto) and M wire-format contract vectors, with pass counts per release, plus the test-suite totals (4,034 today) and mutation-testing status. A `/security/interop` page that a reviewer can reproduce in five minutes is worth more than any badge.

## 5.4 AGENTS.md in every vault (product feature as marketing)

Copy Dolt's AGENT.md move, which fits sgit even better: **`sgit init`/`create` writes an `AGENTS.md` into every new vault** — the file every coding agent reads by convention in 2026 — teaching any agent that lands in the folder: what this folder is, the five commands that matter (`status`, `commit`, `push`, `pull`, `write --json`), the two-branch model in three lines, and "never commit secrets; sgit refuses `.env` anyway." Ship it, then blog it. Pair with publishing the refreshed Claude Skill on the site as a first-class download. (The current skill file still says `sg-send-cli` and pre-restructure command names — refresh is a launch blocker for §5.1 item 4.)

## 5.5 Cadence

Monthly, not daily (Dolt's daily cadence is a funded-team artifact). Order: the four launch pieces (§5.1) → the four comparison pages (§5.2) over the following months → then feature-release notes as they happen. Every post ends with the same closer block: install command + GitHub link.

---

# Part 6 — Implementation on GitHub Pages

## 6.1 Repo & deployment

- **New repo `SGit-AI/sgit.ai`** (keeps the CLI repo's history/issues clean; the site has its own cadence). GitHub Pages via Actions, `CNAME` → `sgit.ai`, HTTPS enforced.
- The Designer/Ambassador/Sherpa v0.8.17 website documents (site map, six feature cards, design tokens, copy deck, MVP scoping) are the starting inputs for the Website Squad — this proposal supersedes their *structure* (they predate the agent positioning and the namespace restructure) but their design tokens and copy-deck fragments remain reusable.

## 6.2 Stack recommendation

**Astro + Starlight.** One static build serving both a fully-custom landing page and a proper docs site (sidebar, search, dark mode, mobile) from plain Markdown/MDX — agents on the team can edit content without touching layout. Deploys to Pages with the stock Astro action. *Alternative:* MkDocs Material (more native to a Python team) — excellent for `/docs/` but awkward for a custom landing page; choose it only if the landing is hand-rolled HTML deployed alongside. Either way: **no client-side rendering of content** (Dolt's SPA homepage ships a spinner as its HTML — one of the few things to explicitly not copy; a content site should be static HTML for SEO and for the agents that will read it).

## 6.3 The generated CLI reference (the anti-staleness machine)

The single most important engineering task for the docs. A small `CLI__Docs_Generator` class (Type_Safe, per house rules) in the CLI repo that walks the argparse tree (`CLI__Main` + `CLI__Branch` + `CLI__Merge` + the five plugin parsers) and emits one Markdown page per command: usage, flags, context (inside-vault/outside-vault/universal — the CLI already knows this), and disabled-status banners sourced from `CLI__Disabled_Command`. Run in the CLI repo's CI on every release; publish the output as an artifact the sgit.ai repo pulls on build. Result: the docs *cannot* drift from the shipped CLI — the failure mode of every existing guide in the repo becomes structurally impossible.

## 6.4 Milestones

- **M1 — Credible landing (1–2 weeks of Website-Squad effort):** landing page (all 9 sections, static tabs for the terminal demo), quickstart, installation, `what-is-sgit`, `sgit-for-git-users` (refreshed), the security/threat-model page, limitations page. Fix `_version.py`; refresh the Skill.
- **M2 — Docs complete:** generated CLI reference wired into CI; concepts section done; guides for agents/branching/backup; JSON-output reference.
- **M3 — Launch:** the four §5.1 posts; AGENTS.md feature shipped and blogged; Show HN with the manifesto post.
- **M4 — Compounding:** comparison pages monthly; interop-metric page auto-updating per release; use-case pages fleshed out with real captures.

---

## Appendix A — Repo Source Material (what to reuse, what's stale)

**Version truth:** v0.14.27 (`pyproject.toml`, `sgit_ai/version`); `sgit_ai/_version.py` is stale at v0.1.0 — fix before launch.

**Tier 1 — reuse with refresh:**
- `README.md` — pitch is good; reshape to Dolt pattern (pitch → command list → install candor → inline tutorial).
- `team/humans/dinis_cruz/claude-code-web/03/27/sgit-user-guide.md` (523 lines, incl. an Agentic Workflows section) — best prose seed; **stale on command names** (predates namespaces/plugins).
- `.../03/27/sgit-for-git-users.md` — the Rosetta stone; **stale**: says no 3-way merge / no log / .gitignore planned — all shipped since.
- `.../03/27/sgit-technical-architecture.md` — **stale on crypto specifics** (says HKDF where code uses PBKDF2-with-salts; says `bare/objects/` where code uses `bare/data/`). Regenerate details from `sgit_ai/crypto/Vault__Crypto.py` and `sgit_ai/storage/Vault__Storage.py`.
- `library/skills/sg-send-cli__SKILL.md` — the agent skill; **needs rename + command refresh** before publication.

**Tier 2 — structure donors:** `library/sgit-ai/briefing-packs/03/20/` (12-doc skeleton: overview → architecture → data model → crypto → sync → CLI → API → types → tests → known issues → dev guide; written at v0.8.10, "what works" lists outdated).

**Tier 3 — website work already done (v0.8.17):** Ambassador messaging review (hero triplet, per-audience props, competitor table, decisions log), Designer site map + tokens, Sherpa sprint plan — `team/explorer/{ambassador,designer,sherpa}/reviews/`.

**Tier 4 — evidence to link from the site:** architect wire-format contract (`team/explorer/architect/contracts/06/08/`), AppSec F01–F12 + consolidated report (`team/villager/appsec/v0.10.30/`), multi-agent legibility thread (`team/humans/dinis_cruz/claude-code-web/06/08/cli-response__multi-agent-legibility.md` and siblings), mutation-test matrix, QA scenario tests.

**Honest-caveat register (site must reflect):** Alpha classifier; `share send`/`publish`/`export` + Simple-Token clone disabled (CHANGELOG, exit code 2) pending token expiry/revocation/scoping; `clone --bare` stubbed ("full implementation in B09"); commit author attribution reserved but unpopulated (A1); union/structured merge drivers not yet implemented (A5); `sgit incoming` planned (A2).

## Appendix B — Dolt Research Sources

Homepage copy extracted verbatim from dolthub.com's Next.js bundles (the site is client-rendered); README from github.com/dolthub/dolt (~24k stars); docs from dolthub.com/docs. Key URLs: use-cases (`/docs/introduction/use-cases/`), correctness & latency benchmark pages (`/docs/sql-reference/benchmarks/`), the agent-narrative arc (`/blog/2025-03-17-dolt-agentic-workflows/`, `/blog/2025-08-05-agent-dot-md/`, `/blog/2025-12-09-ai-database/`, `/blog/2026-01-22-agentic-memory/`, `/blog/2026-03-13-multi-agent-persistence/`, `/blog/2026-06-03-branch-bench-database-benchmarking-for-agentic-workflows/`), the comparison franchise (`/blog/2020-03-06-so-you-want-git-for-data/` et seq.), the anti-pitch (`/blog/2025-12-30-why-not-dolt/`), and the customer-anchored use-case roundup (`/blog/2024-10-15-dolt-use-cases/`). Contrast points: dvc.org and lakefs.io (persona-split, sales-led motion — the pattern *not* to follow).
