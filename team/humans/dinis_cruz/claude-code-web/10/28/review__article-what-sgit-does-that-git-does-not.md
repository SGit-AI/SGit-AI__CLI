# Review: "What sgit does that Git does not" (newsroom.sgit.ai, article No. 308, 27 Oct 2026)

**Article:** <https://newsroom.sgit.ai/articles/what-sgit-does-that-git-does-not.html> (`.md` twin read in full).
**Checked against:** this repository at `640069a` (branch `claude/charming-babbage-5hzcxq`, the same code as `dev`):
the source, `sgit --help` for every command group, `CHANGELOG.md`, the threat model
(`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`) and the response and release notes under
`team/humans/dinis_cruz/claude-code-web/10/`. Numbers that come from the newsroom's own briefs or from cli.sgit.ai pages
are not in this repo. They are marked "external": not contradicted, just not checkable from here.

**In one paragraph.** The article is accurate on the whole, and its honesty sections are mostly fair. There is one
headline number we cannot source: "29 minutes to 4.6 seconds" for a one-file commit on a 76,000-file vault. The
"commits signed since 0.19.0" line is wrong the other way: commits were signed long before October, and 0.19.0 added
*verification*. Two claims are too strong, both in sgit's favour:

- "sgit's signatures say which clone wrote a commit" (see TM-R01).
- "every index is verified against a signed commit" (see TM-R42).

The article also undersells sgit. It does not claim we lack shallow clones: it lists them under "Git has it too",
which is right. But it says sgit refuses partial commits (`sgit write` does them), and it puts "read one file with no
clone" wholly in the future (it works today on normal vaults). It also leaves out several things Git has no equivalent
for, listed in section 2.

Almost everything on the "Git is ahead" list can be built client-side, as Git builds it. The things that cannot be
built are the ones that need the host to read content, and one more: taking back data a reader already has.

---

## 1. Claim by claim

✓ = matches the code or our records · ✗ = wrong · ~ = right but needs a qualifier · ext = external, not checkable here.

### Releases and numbers

| # | Article says | Verdict | What the record says |
|---|---|---|---|
| 1 | Ten releases, 0.17.0 on 3 Oct to 0.26.0 at 01:26 UTC on 27 Oct | ✓ | 0.17 → 0.26 is ten minors. PyPI dates match. |
| 2 | **One-file commit on a 76,000-file vault: 29 min (1,739 s) → 4.6 s** (headline, abstract, "In short", 0.25.0 bullet) | ✗ **unsourced** | Not in the CHANGELOG or any note here. The 0.25.0 record has a one-file `commit` going from **4 min** on the newsroom's 79,465-file vault, and from **47 min** for the *first* commit on the 228,000-file synthetic vault, to **9 s**. The 76,000-file synthetic vault was built later, for the 0.26.0 measurements; it has no 29-minute number, and its "first commit" is 50–69 s. Ask the writer for the source. If none exists, use "4 min → 9 s (79,000 files)" or "47 min → 9 s (228,000 files)". |
| 3 | Pull of a 300-file pass on 228,000 files: 566 s → 31.7 s, and 16.9 s with indexes | ✓ ~ | `response__newsroom-first-morning-on-0-25-0.md` and CHANGELOG 0.26.0. Qualifier: 566 → 31.7 was measured **under cProfile**, which inflates absolute times; the ratio stands. 31.7 → 16.9 is a plain run. |
| 4 | One-folder clone of a pack vault: 36 s → 2.8 s; 12.5 MB against the whole 88 MB pack | ✓ | `release-readiness__pack-indexes-branch.md`: `clone --path raw/c09` (1,520 files) on the 76,000-file vault, 0.25.0 against 0.26.0. 5 requests for 88 MB against 24 ranged requests for 12.5 MB. |
| 5 | 0.24.0: listing timed out at 90.8 s → 0.73 s; fresh clone 827 → 95 s; 29,861 files, 1.6 GB | ext | Newsroom brief of 23 Oct. Not contradicted. |
| 6 | 0.26.0 took eighteen hours, five reviews, three fix rounds | ext / plausible | Matches the session history (26 Oct morning to the merge on 27 Oct). |
| 7 | `pack index verify` 1,002 s → 3.5 s on 24,000 files, "planned for 0.26.1" | ✓ number, ~ version | Numbers match `10/27/response__pack-index-verify-field-report.md`. **Version:** since the CI change of 27 Oct, dev publishes it now as the pre-release **0.26.1.dev0** (`pip install --pre sgit-ai` / `sgit update --pre`). The next release from main bumps the minor, so it ships as **0.27.0**. Our own response note says 0.26.1 too; both should say "next release". |
| 8 | Researcher measured ~57 s a pack on 0.26.0 | ext | Field report. Consistent with 1,002 s over 9 packs here. |
| 9 | "The first `status` **after upgrading** to 0.25.0 took 18 min 23 s on the curator's 4.2 GB clone … 0.26.0 fixed it by seeding the cache on every write" | ~ | It was the first `status` **after a fresh clone** (a 4.2 GB pack clone, nearly all of it disk wait), not after an upgrade. The cause and the fix are right: every working-copy write seeds the scan cache, in the 0.26.0 CHANGELOG. |
| 10 | First push and each compaction are 35–50 s slower in 0.26.0 on 76,000 files | ✓ | First push 47 → 82–84 s (+35–37). Compaction 58 → 95–109 s (+37–51). |
| 11 | Memory-FS: keeping the zip directory "turns 1.3 s per read into 5 µs" | ~ | The 5 µs is in `10/26/review__pack-indexes-dev-pack.md:49`. The 1.3 s per read is not in our notes; probably the cli.sgit.ai article. |
| 12 | Type_Safe parsing ~3 ms a tree was the 0.24.0 slowness | ✓ | CHANGELOG 0.25.0. |
| 13 | "the cache needs no invalidation"; `sgit cache` from August | ✓ | CHANGELOG 0.25.0. The cache contract is dated 08/12. |
| 14 | Middle releases: format gate, signed commits checked on every client, rewinds refused, signed tags, undo and amend | ✓ ~ | Gate, verification and rewind guard in 0.19.0; signed tags, `history undo` and `commit --amend` in 0.21.0. "On every client" is too strong: on every **sgit** client, and only when the vault turns on `signatures-required`. The web UI and old clients do not enforce it (TM-R26). |
| 15 | Early releases: keep-alive, each shared sub-tree fetched once, full clone in one parallel sweep | ✓ | 0.18.0. |

### What Git has no equivalent for

| # | Article says | Verdict | What the code says |
|---|---|---|---|
| 16 | Contents, file names, commit messages and branch names are encrypted; host sees sizes, timing, counts and, in pack mode, which commit each push carried | ✓ ~ | Correct, but the leak list is short. The host also sees: <br>• equality of trees through deterministic tree encryption (KI-SEC-02); <br>• with `blob-deflate`, each file's compressibility (TM-R40); <br>• index pack sizes; <br>• in path-ordered packs, which blobs share a folder; <br>• for a scoped clone, which byte ranges it reads, which reveals folder sizes and positions (TM-R42). |
| 17 | A read key is derived from the vault key one way, so it can never become write access; works from any static host with no account | ✓ ~ | Read and write keys are two independent PBKDF2-SHA256 derivations (600k iterations, distinct salts) from the vault key, and neither yields the other. `--transport static` reads from any GET host. **Qualifier:** reading is a capability; **writing is a permission**. The write key is a bearer secret the *host* checks, with no cryptographic role. A read-key holder with store write access (a host that does not check, or a leaked write key) can author history that `check verify` calls *verified* (**TM-R01**, the top accepted risk). |
| 18 | Read access cannot be revoked after the fact; per vault, not per folder; "a partial clone is not an access boundary" | ✓ ~ | TM-R12. Add the remedy we do ship: `sgit vault rekey` / `sgit vault move` rotate the key going forward, and the old vault should be deleted after a rekey. Git and GitHub cannot revoke an existing clone either. |
| 19 | Append lane: write without read, answer `{"ok": true}`, a server feature with no sgit command yet | ✓ | No append-lane code in `sgit_ai/`. |
| 20 | Fetch one folder by byte ranges from plain storage, each object verified by hash | ✓ | Phase 2 ranged scoped clone, 0.26.0. Git uses ranged requests only to resume dumb-HTTP downloads. Its partial clone needs a smart server. |
| 21 | Indexes shipped by the writer, signed and encrypted, checked against the commit and its signature; "a bad one is skipped"; "an index is a plan, never a proof" | ✓ ~ | `Vault__Pack_Index__Reader` order: header → signature *under the vault's policy* → anchor to the local commit → member sha256. **Two qualifiers (TM-R42):** <br>• An unsigned index is accepted unless the vault has `signatures-required`. <br>• The snapshot index's `flat` below the root is not checked by the reader. A *signing teammate* can mislead a fresh clone's working copy, just as a commit from that key could. `sgit pack index verify` catches it. Workflow 4's "every index is verified against a signed commit" should say "anchored to its commit and checked under the vault's signature policy". |
| 22 | `sgit pki encrypt --recipient` seals a file to a public key | ✓ ~ | It writes a sealed file that you then commit. The vault does not hold per-recipient files as a native object type. |

### What Git has too

| # | Article says | Verdict | What the record says |
|---|---|---|---|
| 23 | Git packs are delta-compressed, sgit's are not; keeping packs whole is Git's default above `fetch.unpackLimit` | ✓ | sgit deflates each blob (`blob-deflate`); no deltas. Git keeps a received pack above `fetch.unpackLimit` / `transfer.unpackLimit` (default 100 objects). |
| 24 | `clone --path`: refuses a commit outside the scope by name; two scoped clones never conflict | ✓ | Since 0.18.0. Out-of-scope entries are always the remote's, by id. |
| 25 | `pull --no-checkout` then `checkout --since-pull` | ✓ | 0.26.0. Also `checkout --changed-since COMMIT`, `--all`, and `checkout <paths>`. |
| 26 | "Shallow clones, private branches and signed commits all have Git equivalents" | ✓ | **We do have shallow clones:** `clone --depth N` and `fetch --unshallow` (0.18.0), combinable with `--path`. The article does not say we lack them; it says Git has them too. |

### Where Git is ahead

| # | Article says | Verdict | What the code says |
|---|---|---|---|
| 27 | Merges are whole-file with conflict files; Git merges line by line and detects renames | ✓ | `Vault__Merge.three_way_merge` compares by blob id and writes `<path>.conflict`. No rename detection. |
| 28 | **Staging and partial commits: sgit refuses them by design** | ✗ partly | No staging area and no hunk-level commits, true. But **whole-file partial commits exist:** `sgit write <path> --file F [--also P:F …] [-m …] [--push]` commits the named files straight to HEAD, atomically, without scanning the working copy. Other edits stay uncommitted. The limitations-page quote ("committing three of seven changed files") is out of date for agents. `sgit commit <paths>` would be a small addition (section 3). |
| 29 | Identity: "sgit's signatures say which clone wrote a commit, not who is allowed to write"; GitHub keys can expire and be revoked | ~ too generous | Weaker than stated. A signature proves the signing key's file decrypts under the read key. Any read-key holder can mint such a key (TM-R01). So a signature says "some key holder", not "which clone", until the owner-signed signer registry (TM-R01 design row) exists. No per-key expiry or revocation either; only whole-vault rotation. |
| 30 | Git has delta packs and GC; sgit has no pruning | ✓ ~ | No unreachable-object GC. (`core/actions/gc` drains pending change packs and is not a prune.) `sgit pack compact` moves superseded packs to `archive/`, which is a partial answer for pack vaults. |
| 31 | Git ids 160-bit by default; sgit format 1 is 48-bit, format 2 is 128-bit and opt-in per vault | ✓ | `sgit vault format --set 2` (0.19.0); existing ids stay 48-bit in a mixed vault. |
| 32 | Ecosystem: forges, review, CI, search, blame, bisect, IDEs; "most of it needs a host that can read the content" | ~ | Half right. Blame, bisect, search, IDE support and most of review are **client-side** in Git too, and can be built (section 3). Only host-side features need a host that reads. We already have `history log --grep / --since / --until / --author / --file / --patch / --stat`, `history diff`, `history show` and `history reflog`. |

### Next, not now

| # | Article says | Verdict | What the record says |
|---|---|---|---|
| 33 | On a normal vault a file is four plain GETs of fixed paths | ~ | Four only for a file at the root. The walk is ref, commit, *every tree on the path*, blob, so a file *d* folders deep is 4 + *d* GETs. For paths declared with `sgit cache add`, it is **one batch request** with no walk (shipped, the cache layer). |
| 34 | Reading one file from a pack vault by byte range with no clone is not shipped (Phase 4) | ✓ | The `at` offsets are written into every path-ordered pack; the reader is not built. |
| 35 | The browser library cannot read pack vaults yet | ext | Not this repo. Consistent with what we know. |

### Housekeeping claims

| # | Article says | Verdict | What the record says |
|---|---|---|---|
| 36 | **Limitations page says signing is "planned work", "though commits have been signed since 0.19.0"** | ✗ | Commits were signed (ECDSA P-256, per clone key) **long before October**. The 0.19.0 notes speak of "commits signed before this (`author_key_id` null)". 0.19.0 fixed the canonical signing input (RFC 8785) and added **verification** (`check verify`, fsck) and `signatures-required` on pull. 0.21.0 extended the check to every clone. Correct line: "commits have been signed for months and verified since 0.19.0". The limitations page is still out of date either way. |
| 37 | The 0.26.0 notes sit under "Unreleased" in the changelog | ✓ on main | True of `main` today. Fixed on `dev` in `01d167a`, which dates `[0.26.0] — 2026-10-27`; it reaches main with the next release. |
| 38 | sgit's docs open with "git for encrypted vaults" | ✓ | `README.md` line 1. |

---

## 2. What we have that the article misses or says we lack

**Things the article says we lack, or puts in the future:**

- **Partial commits** (row 28): `sgit write … --also … --push --json`. It commits named files atomically to HEAD
  and, with `--push`, publishes them in one call. That is the agent form of `git commit <paths>`.
- **One file with no clone** (row 33), on a normal vault: the browser reader does it today (four GETs plus one per
  folder level), and `sgit cache add` makes it one batch request. `sgit history log --vault-key …` already runs with
  no clone; `cat` does not yet (section 3).
- **Key rotation:** `sgit vault rekey` and `sgit vault move` (rotation plus an optional move to another server).
  GitHub has nothing to rotate; a leaked Git deploy key is revoked on the server.
- **Search / history tools** (row 32): `history log --grep --since --until --author --file --patch --stat --json`,
  `history diff A..B`, `history show`, `history reflog`, `history undo`, `history revert`, `history reset`,
  `commit --amend`, `vault stash`, signed `vault tag`, `resolve`, `merge-abort`.
- **Shallow and partial clones:** `clone --depth N`, `fetch --unshallow`, `clone --path`, `fetch <folder>` (widen),
  `clone --sparse`, `clone --no-checkout`, `clone --bare`, `clone-branch`, `clone-headless`, `clone-range`. The
  article files these under "Git has too", which is fair; we are not behind there.

**Things Git has no equivalent for that the article leaves out** (candidates for its first list, or for the follow-up
article):

1. **Custody without access:** `sgit vault mirror` copies a published vault you cannot read, keyless, and verifies it.
   A backup service or a second host can hold and check the vault and learn nothing.
2. **Policy carried by the repository and enforced at clone and pull:** the format gate (`min_client`, features) and
   `signatures-required` live in the encrypted branch index, and every sgit client enforces them before writing
   anything. Git's signature checks are each user's local config; a repository cannot require them of its cloners.
3. **Rewind detection on every clone:** a remote head that does not descend from the last accepted one is refused by
   name (`pull --accept-rewind` to take it). Git's default `+` refspec takes a forced update with one line of output.
4. **A secret guard:** commit refuses vault keys, key-bearing zips and in-tree symlinks to secrets (TM-F11,
   TM-F18, TM-F27).
5. **Agent-shaped writes:** `write --push --json` and `checkout --since-pull`. Two scoped agents can never conflict
   (already in the article).
6. **Serving:** `sgit serve` runs the vault UI and API locally in a container; `sgit serve --static` and
   `sgit publish` lay a vault out for any static host. A read-only clone from a published read key needs no account
   and no server code.
7. **A computable cache:** `sgit cache add <path>` puts a fixed-cost read of a hot file at a location only key
   holders can compute, for edge functions. Git has no read path that skips the tree walk.

---

## 3. What we don't have, and how to build it

Git is a client-side program; almost all of the "Git is ahead" list runs on the client in Git too. Each row below
works on plaintext the client already holds, and needs **no new server feature** unless the row says so.

| Feature | How to build it in sgit | Size | Notes |
|---|---|---|---|
| **Line-level three-way merge** | In `Vault__Merge`, when both sides changed a text file (UTF-8, under a size cap), run a diff3 merge of base / ours / theirs (port of xdiff's merge, or a `difflib`-based merge). Write a clean result, or inline `<<<<<<< ======= >>>>>>>` markers, instead of `<path>.conflict`. Whole-file stays the fallback for binary files, and an opt-in strategy for anyone who wants the old behaviour. | M | Biggest user-visible gap. The client has all three plaintexts. |
| **Rename detection** (merge, `history diff`, `log --follow`) | Exact renames: same plaintext `content_hash` in the tree entries on a deleted and an added path. Similar renames: Git's similarity score on plaintext, within a cap. | S–M | Tree entries already carry the plaintext hash, encrypted. |
| **`sgit commit <paths>`, `-p` hunks, a staging area** | `commit <paths>` reuses `write_file`'s path (build only the named paths' spines). `-p`: interactive hunk picker over `history diff`. A real staging area (index) is a design decision; the scan cache is half of it already. | S / M / L | Rule 9: `commit` stays the verb. |
| **blame** | `sgit history blame <path>`: walk the file's commits (the index pack's file → commits member makes this cheap on pack vaults) and run a line diff per step. | M | Fetches each version's blob on demand on shallow or sparse clones; refuses below a shallow boundary. |
| **bisect** | `sgit history bisect start/good/bad/run`: state in `.sg_vault/local/bisect.json`, midpoint by generation number (pack indexes carry them), `branch checkout <commit>` for each step. | S–M | Pure client. |
| **grep over content** | `sgit grep <regex> [--rev C]` over HEAD or a commit, decrypting blobs locally. History grep is `--all`. Optionally a local, encrypted-at-rest search index under `.sg_vault/local/`. | S (HEAD) / M (history) | Needs the blobs: fetch on demand on sparse clones. |
| **Delta compression** | At push, delta a changed blob against its previous version (same path) before deflate and encryption. The pack member is a delta object naming its base id; the reader rebuilds the blob and **verifies it by its content address**, so integrity is unchanged. Bases are restricted to objects in the same pack or the reader's store (thin packs). | L | Leaks only "how big the change was", which ciphertext sizes already show. Needs a format feature flag and a `min_client` gate. |
| **GC / prune** | `sgit vault prune` (write key): compute the set reachable from every named branch, clone branch, tag and stash; delete the rest through the API's delete route after a grace period (Git's `gc.pruneExpire`, default 2 weeks), so objects uploaded by a push still in flight survive. Pack vaults: delete `archive/` packs older than the grace period, since compaction already moves superseded packs there. | M | Must be client-driven: the host cannot read trees to know what is reachable. Same power the write key already has (TM-R39). |
| **One file, no clone, from the CLI** | `sgit cat --vault-key K <path>` (also `--read-key`): ref → commit → trees on the path → blob, or the cache entry when declared. Pack vaults: Phase 4. Read the snapshot index's `flat` member by range, find the blob's `at` offset, read that range, verify by hash. | S (normal) / L (pack) | The `history log --vault-key` path already does the first half. |
| **Append-lane command** | `sgit inbox send <vault> --to <recipient> FILE` seals with `pki encrypt` and calls the append route; `sgit inbox read` for the owner drains it into a commit (the change-pack drain in `core/actions/gc/` is the same shape). | S–M | Server feature exists; this is the client. |
| **Allowed signers, key expiry and revocation** | The owner-signed signer registry already designed for TM-R01: the owner signs the set of trusted signer keys (with expiry and revoked entries) in the branch index; clones pin it on first use; `signatures-required` checks membership, not just "decrypts". | L | Closes the top accepted risk; also gives "who is allowed to write". |
| **Per-folder read access** | A folder key per protected folder, wrapped to each member's public key (pki) in the branch index. That folder's trees and blobs are encrypted under it. Holders of the vault key but not the folder key see the folder as an **opaque entry**, which is exactly what scoped clones already carry. Writers without the key can still commit elsewhere and carry the folder by id (already proven by `clone --path`). Revoking a member means re-encrypting the folder under a new key. | XL, architect first | New crypto, but no new idea: it is the scoped-clone opaque entry plus key wrapping. Folder names on the spine stay visible to vault-key holders. |
| **Per-person protected branches / "who pushed"** | Server: per-member write tokens instead of one shared write key, with an ACL keyed by ref file id (the owner registers which HMAC'd ref ids each token may write). The host enforces it without learning branch names. Client: the signer registry rejects commits on a branch from keys not allowed there. | L (server and client) | Both halves are possible under zero knowledge. |
| **Review, CI, IDEs** | Review: a client-side or browser-side review UI over encrypted review objects in the vault (the vault web UI already decrypts in the browser). CI: a runner that holds the read key (self-hosted, or an Action with the key as a secret), triggered by a ref-change webhook, which the host can send without reading anything. IDEs: an extension driving the CLI, or, for the most leverage, a **`git-remote-sgit` remote helper** so Git, IDEs and Git tooling read and write a vault as a remote. | L each | Zero knowledge holds because the plaintext lives only where the key does. |

---

## 4. What is impossible, or only partly possible, under zero knowledge

These are limits of the model, not of effort. Each one has a client-side substitute.

1. **Anything the host must read to do.** Server-side search, diffs rendered by the server, a "merge" button the host
   executes, code scanning by the host, server-side blame or language statistics. All impossible unless the host is
   given the read key, at which point it is no longer zero-knowledge.
   Substitute: do it in the client or the browser, or in a runner the key holder controls.

2. **Taking back what a reader already has.** No system can revoke data already fetched. GitHub cannot either: a
   removed collaborator keeps their clone. What sgit can do is rotate forward (`rekey`, `move`), delete the old vault
   (TM-R12), and with per-folder keys limit what each reader ever received.

3. **Per-folder permissions enforced by the host inside one key.** The host cannot tell folders apart, and anyone with
   the key can decrypt every object. Per-folder access needs per-folder keys (section 3), not permissions.

4. **Hiding all metadata.** Sizes, timing, counts, which ranges a scoped clone reads, and compressibility with
   `blob-deflate` (TM-R08, R38, R40, R42). Padding to size buckets, fixed-size packs and decoy range reads reduce
   the leak, at a bandwidth cost. They never remove it (that would take an ORAM-style protocol).

5. **Host-side optimisation of the store.** `git gc` and repacking on the server, deltas the host computes, dedupe
   across vaults. The host has only ciphertext. Client-side deltas and prune are possible (section 3). Cross-vault
   dedupe would need convergent encryption, which leaks equality, so we should not want it.

6. **A host that enforces fast-forward-only.** The host cannot read the ref, so it cannot check ancestry. The
   client-side rewind guard (shipped) is the answer. A signed, append-only ref log kept by the host would let clients
   prove a rewind, but not stop a write-key holder from making one.

Everything else in the article's "Git is far ahead" list (merges, staging, blame, bisect, search, identity, GC, deltas,
IDE support, and most of review and CI) is client-side in Git and can be client-side in sgit. "Twenty years of
maturity" is the one item only time fixes.

---

## 5. Suggested edits to the article

1. Replace or source "29 minutes → 4.6 seconds" (abstract, "In short", 0.25.0 bullet, chart).
2. "Signed since 0.19.0" → "signed for months; verified since 0.19.0".
3. "after upgrading to 0.25.0" → "after a fresh clone on 0.25.0".
4. "planned for 0.26.1" → "on dev now as the pre-release 0.26.1.dev0; in the next release".
5. Staging row: add "but `sgit write` commits named files atomically to HEAD".
6. Identity row and the read-key bullet: add TM-R01 in one line: writing is a host-checked permission, and a
   signature today proves a key holder, not a particular clone.
7. Index rows and workflow 4: "anchored to its commit, checked under the vault's signature policy".
8. Four GETs: "four for a file at the root, one more per folder; one batch request for a cached path".
9. Leak list: add tree equality, compressibility under `blob-deflate`, and range positions for scoped clones.
10. Consider adding section 2's list (mirror, repo-carried policy, rewind detection, secret guard, rekey, serve,
    cache) to "What Git has no equivalent for".

## 6. Fixes on our side, found while checking

- `sgit help all` ("full command surface") omits `checkout`, `pack`, `doctor`, `remote` and the `cat` / `ls` / `write`
  shortcuts. All of them are in `TOP_LEVEL_COMMANDS`. Small fix in `CLI__Main` (around line 1491).
- The limitations page on cli.sgit.ai: signing is not "planned work", and partial commits exist through `sgit write`.
  That page is not in this repo.
- `10/27/response__pack-index-verify-field-report.md` says "ships in 0.26.1": it ships as 0.26.1.dev0 on dev and in
  the next release (0.27.0 under the current CI numbering).
- `main`'s CHANGELOG shows 0.26.0 under "Unreleased" until the next merge from dev (already fixed on dev).
