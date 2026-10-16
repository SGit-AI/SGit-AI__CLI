# Response to "Scion and sgit" (newsroom.sgit.ai, article No. 141, v1.0.0)

**Date:** 16 Oct 2026. **Code read:** `dev` at 881d6df (what 0.22.0 ships plus the 14 Oct fixes).
**Vault measured:** the comms / DC collaboration vault (`y8pwtjlw` on `dev.send.sgraph.ai`), read-only:
cloned eight ways from the hosted API, then the same objects served from local disk (static and a
local API server); nothing pushed to the real server. **Also measured:** the vault the article used
(`newsroom-synthetic-users`, `bg1opz3c`, public read key), from the same kind of sandbox.
**Also read:** Anthropic's post in full, every sgit.ai page the article should link, and the eleven
newsroom articles that already describe sgit's architecture and deployment.

## Verdict

The Scion half is accurate: every figure the article quotes is in Anthropic's post. The sgit half is
under-claimed where it should be strong (deployment models, reading files without a clone, the
pull fix, history integrity) and over-claimed in one place (a CDN that caches for a year), and its
measurement is the wrong one: an 83-file vault says nothing about the question the post raises,
which is what happens when the repository is big and the clients are many. We have a vault that
is big by sgit's standards and is used by ten agents every day. Its numbers are below, and they
are the ones the article should carry.

Three things the article gets wrong on the facts, in order of how much they matter:

1. **"no packing on the server" is listed as a gap.** Scion has no packfiles either and says so as
   a feature: "There is no equivalent of packfiles … so no repository maintenance is needed."
   sgit is the same: immutable objects, no maintenance, no GC on the server. This is a point of
   agreement, not a gap.
2. **"its latest releases add scoped, shallow and on-demand clones" / "sgit 0.18 to 0.22 added
   … `--sparse`".** `--path` and `--depth` are 0.18.0 (7 Oct). `--sparse` has been in the CLI
   since v0.11.3 (1 May 2026).
3. **"objects cache for a year at a CDN".** Drop it (see §2, claim 1). The property is that they
   *can* be cached by anyone, for ever, and the evidence for that is what the sgit.ai pages do in
   the browser, not a CDN header.

## 1. What Scion actually says, and the overlaps the article missed

Read against the post, the article's Scion paragraph is right (2,500 → 30,000 merges a day, ~100 GB
of main-branch history, ~25 M CI checkouts a day, ~600 PB if fetched naively, several hundred
mirrors, three cache tiers each over 99 %, 200× less CPU and memory, seconds instead of minutes,
25 % of CI's CPU, seven people in five months, "by no means a suitable replacement for git").
Four things in the post are closer to sgit than the article noticed:

| Scion (from the post) | sgit | Where it is documented |
|---|---|---|
| "Scion's negotiation doesn't tell the server what the client already has; instead, it operates exclusively on trees and blobs the client wants. Starting from a root tree, the client checks its local store for missing trees and requests them recursively, then repeats the process for blobs." | This is sgit's clone and pull walk, word for word: level-by-level over the trees, one batched request per level, then the blobs in batches of 50 with 16 requests in flight. A scoped clone asks only for the spine down to its folders. | `docs/partial-clones`, CHANGELOG 0.18.0; `Step__Clone__Walk_Trees`, `Vault__Scoped_Tree.walk_fetch` |
| "Every request is for a specific object that never changes, so any cache can answer it." | Every object's name is the SHA-256 of its ciphertext; the client checks every object against its name before writing it. The mutable ref is `no-store`. | `api/vault-objects` (the caching contract), `case-studies/live-vault-docs` |
| "There is no equivalent of packfiles … no repository maintenance is needed." | Same. No packing, no GC, no maintenance on the server. For cold starts from a static host, `sgit publish --bundles` emits a head snapshot and per-commit delta zips. | CHANGELOG 0.18.0 (static publishing) |
| "moving [a ref] is a compare-and-swap on a single Spanner row" | Refs move by compare-and-swap; so does the branch index, which every client merges as a shared document. | `docs/history-integrity`, `docs/vault/vault-from-javascript` §5 |

And two differences the article should state, because they are the real ones:

- **A Scion changeset stores the list of files that changed; an sgit commit stores a tree,** like
  git. Scion rebuilds history and blame as "derived data" on the server. sgit's tree snapshot is
  what makes a scoped clone cheap (an unchanged folder keeps its tree id across commits, so it is
  never fetched twice) and what makes a client-side blame possible without the server.
- **Scion protects directories with permissions on the server; sgit protects them with keys.**
  A partial clone is a speed setting, not a boundary (`docs/limitations`); the boundary is one
  vault per trust domain, a read key that cannot be turned into a write key, and append lanes
  that can write but never read. The article says nothing about any of this, and it is the
  strongest contrast with a server that holds plaintext and an IAM system in front of it.

## 2. Claim by claim

| # | The article says | Status | Say instead (evidence) |
|---|---|---|---|
| 1 | "Its object ids are immutable content addresses, so objects cache for a year at a CDN" (title paragraph, abstract) and "the live server already uses it: … `cache-control: public, max-age=31536000, immutable`, through a CDN" | **Half true, and the half that is true is the wrong half.** The header is now sent (verified today on `/api/vault/read/y8pwtjlw/bare/data/obj-cas-imm-…`: `public, max-age=31536000, immutable`; the ref answers `no-store`). But three consecutive reads of the same object all came back `x-cache: Miss from cloudfront`: the CDN in front of the dev API does not serve reads from cache today. | "Objects are named by the hash of their ciphertext, so anything that has fetched one can keep it for ever: a browser's Cache API, a proxy, a CDN, a folder on disk. sgit.ai's own documentation pages read a vault that way: a cold load fetches 18 objects, the next load fetches one 69-byte ref, and a load inside the two-minute freshness window fetches nothing." Link `case-studies/live-vault-docs` and `docs/vault/reading-a-vault-file`. |
| 2 | "measured it on a real vault: a scoped clone in 4 seconds against 59 for the full one" (12 MB, 83 files) | **Wrong vault, and the 59 s was a bug, now fixed.** 83 files answers nothing about Scion's problem. The 59 s reproduced exactly from here (59.0 s, 56.5 s): the vault's 106 objects go up in two batches of 50, each batch's response is over the Lambda's size limit, the client slept 14 s retrying each whole and then read 106 objects one at a time. A refused batch is now split in halves on the first refusal: 8.1 s and 9.9 s for the same clone (§3). The article measured a Lambda limit and a client fallback, not the vault. | Use the comms vault (§3): 35k objects, 1,295 commits, 5,281 files, ten agents writing daily; and say what the 59 s was. |
| 3 | "sgit 0.18 to 0.22 added the same family of options: `--path` …, `--depth` …, and `--sparse`" | **Partly wrong.** `--sparse` is from v0.11.3 (May). 0.18.0 added `--path` and `--depth`; the 14 Oct fixes made `clone-headless` + `fetch`/`cat`/`ls` work. | "sgit has had on-demand (`--sparse`) clones since May; 0.18.0 added a folder scope and a history depth, and they combine." |
| 4 | "writes … go through a batch endpoint, up to 100 operations at a time" | Server cap is 100; the client sends 50 per request with 16 requests in flight on reads. | "batches of 50 objects a request, 16 in flight". |
| 5 | "a vault of 626 commits and 9,404 files" | 9,404 **blobs**; the file count was not recorded then (today's vault: 5,101 files, 16,315 blobs). | "9,404 blobs". |
| 6 | "The CLI team measured a scoped clone of one folder in 14 seconds against 81" | True (6 Oct, 18,720 objects). | Keep, but it is superseded by §3. |
| 7 | "sgit does no packing or compaction on the server" under *Where Scion is ahead* | **Not a gap** (§1). | Move to the overlaps. |
| 8 | "a vault of 35,000 objects still takes about three and a half minutes to clone in full" | True (14 Oct), and it is the honest number for a *whole* vault. What the article leaves out: nobody doing agent work needs the whole vault, and the pull that an agent does every session was the slow path, fixed on 14 Oct (§3). | Keep the 3½ min and put the scoped/depth numbers and the pull fix next to it. |
| 9 | "sgit has a history log on the client but no blame and no bisect" | True. Understated: `history log --file PATH` (path history), `--stat`, `--grep/--since/--until/--author`, `history diff A..B`, `history show`, `history revert --as-commit`, `commit --amend`, `history undo`, reflog, `vault tag` (signed), and `check verify` (which commit was signed by which key). Blame is a client-side fold over path history and nothing in the format prevents it. | "No blame or bisect yet; path history, signed authorship and signed tags, yes." Link `docs/history-integrity`, `docs/update-to-0-21-0`. |
| 10 | "There is no command to read a file from a vault without at least a headless local clone" | True for the CLI, and misleading: reading one file is four GETs by design (ref → commit → trees on the path → blob), which the site's pages do in the browser with a 90-line reader, and `clone-headless` is a config directory, not data. The real edge is in §3: on a long history today's `cat` first walks the commits. | "A file is four GETs away from its read key, and sgit.ai's pages read vaults that way; the CLI needs a headless clone directory first." Link `docs/vault/reading-a-vault-file`, `docs/vault/vault-from-javascript`, `demos/vault-app-embed`. |
| 11 | "Merges happen on the client, three-way and whole-file; Scion does them on the server" | True. Add: two independent clients (the CLI and the browser vault app) speak one wire format, so a merge made in a browser is one the CLI verifies and vice versa (`sgit serve pull`). | Link `docs/what-is-sgit` (three doors), `security/` (two implementations, one wire format). |
| 12 | "Git and sgit also live side by side rather than in sync … no bridge" | True for history. There is `vault attach` (bind a key to a `.sg_vault/bare` that came in through `git clone`), the one-repo pattern, and a pure-Python git reader for vault apps. | Link `docs/vault/git-and-vaults`, `case-studies/one-tree-two-remotes`. |
| 13 | "The server only matters for writes" | Also for the store listing that makes a cold full clone fast (one `list`, then bulk fetch). A static host has no listing, so a cold full clone from one walks the graph; a scoped or depth clone never lists. | Fine as a simplification; say "writes and the branch index". |
| 14 | Side-by-side figure "Scion, sgit 0.22.0 and Git … proven scale and availability" | Add rows: *server holds plaintext* (Scion yes, sgit never), *directory protection* (Scion IAM, sgit keys per vault and read-only / write-only keys), *clients* (Scion one, sgit two implementations), *deployment* (Scion internal fleet; sgit hosted, your container, static host, a folder). | |
| 15 | "What it means … The useful next steps are clear from Scion's list: server-side history queries that do not need the plaintext" | A server that cannot read commits cannot answer history questions; that is the design, not a roadmap item. The sgit answer is a client-side index over a *scoped* clone, which §3 shows is small. | Reword: "history queries over a scoped clone on the client, and a commit-chain object so a partial clone does not walk history one commit at a time". |
| 16 | *Where this comes from*: "the largest vault sgit's team documents has about 35,000 objects" | Make it concrete: it is a live vault with ten agents, 1,295 commits (68 added in the last two days), 5,101 files, 527 MB of ciphertext in a full clone. | |

## 3. The evidence the article should carry

All timings from one client in this cloud sandbox (every request leaves through a proxy; a plain
connection does better), against `dev.send.sgraph.ai` (S3 storage behind CloudFront), sgit at
`dev` 881d6df (0.22.0 plus the 14 Oct fixes), one run each unless stated. The vault: 1,295 commits
on 16 Oct (1,227 on 14 Oct), 16,391 trees, 16,315 blobs, 5,101 files, 35,423 objects / 527 MB in a
full clone on 14 Oct.

**Clones** (the full clone is the 14 Oct run; the vault has grown by 180 files since):

| Clone | Time | Objects | Store on disk | Files checked out |
|---|---|---|---|---|
| everything (full clone) | 3 min 30 s | 35,423 | 527 MB | 5,101 (131 MB) |
| `--depth 1` (whole tree, one commit) | 57 s | 6,248 | 142 MB | 5,281 (139 MB) |
| `--path security --depth 1` | **13 s** | **137** | **3 MB** | 130 (3 MB) |
| `--sparse --depth 1` (structure only, one commit) | 27 s | 967 | 6 MB | 0 |
| `--path docs` (12 files, all history) | 181 s | 2,668 | 17 MB | 12 (1 MB) |
| `--path security` (all history) | 227 s | 3,364 | 64 MB | 130 (3 MB) |
| `--path mail/crm.riskmandate` (all history) | 159 s | 6,109 | 69 MB | 558 (27 MB) |
| `--path mail` (the biggest folder, all history) | 264 s | 25,110 | 274 MB | 3,275 (69 MB) |
| `--sparse` (every commit and tree, no blobs) | 206 s | 18,299 | 117 MB | 0 |
| `clone-headless` (keys and config only) | 0.4 s | | | 0 |

**Working in a partial clone** (each is one CLI invocation, so ~1.5 s of it is process start and
PBKDF2):

| Operation | Time | Network |
|---|---|---|
| `ls docs` in the sparse clone | 1.8 s | none (trees are local) |
| `fetch docs/drafting-guide.md` into the sparse clone | 2.9 s | 1 object |
| `cat` of a held file | 1.7 s | none |
| `cat` of a file not yet held (fetched on demand) | 2.5 s | 1 object |
| `fetch security/` (130 files) into the sparse clone | 5.1 s | 130 objects, batched |
| `fetch security` to widen the `--path docs` clone | 7.8 s | 135 objects |
| `status` in the scoped clone, up to date | 1.5 s | ref + index |
| `pull` in the scoped clone, up to date | 2.5 s | ref + index |
| `cat` of one file from a headless clone (first command: brings every commit and tree down) | **202 s** | 18,300 objects, 116 MB |
| `cat` of a second file from the same headless clone | 2.5 s | 1 object |
| `history log --file <path>` on the full clone (1,227 commits) | **6 min 8 s** | none: CPU, 5½ min of it |

**The article's own vault** (`newsroom-synthetic-users`, 83 files, 12 MB, public read key),
cloned from this sandbox for comparison with its "59 s full / 4 s scoped":

| Clone | Before the fix (0.22.0) | After (`dev`, batch splitting) | Objects / store |
|---|---|---|---|
| full, read-only | 59.0 s, 56.5 s | **8.1 s, 9.9 s** | 106 / 12.4 MB |
| `--depth 1` | 62.1 s | (same path) | 93 / 12.0 MB |
| `--sparse` | 4.0 s | | 18 / 180 KB |
| `--path <first folder>` (5 files) | 3.7 s | | 15 / 412 KB |

The article's numbers reproduce to the second. The full clone's 59 s was two 50-object batches
whose responses exceeded the Lambda's size limit (files of ~150 KB): the client retried each
whole through the 2 + 4 + 8 s back-off and then read 106 objects one per request. Fixed on `dev`
(CHANGELOG, Unreleased): a refused chunk is split in halves on the first refusal.


### What the numbers say

- **A scoped clone of a 35k-object vault is a few MB and a few seconds, when it also carries a
  depth.** `--path security --depth 1` and `--depth 1` are the agent pattern the docs already
  recommend ("an agent clones only its own folder with one commit of history"), and they do not
  grow with the vault's history.
- **Without a depth, a partial clone pays one round trip per commit.** `--path docs` (12 files)
  took 181 s and 2,668 objects because it walked 1,295 commits one request each, then the spine
  trees of every one of them (that is what gives `history log` on a scoped clone); `--sparse`
  without a depth is the same walk (206 s), `clone-headless` + `cat` pays it on the first `cat`
  (202 s, then 2.5 s a file), and `--path mail` with all its history is most of the vault
  (25,110 objects). Whole-vault
  clones and pulls stopped doing this on 6 and 14 Oct (list the store once, fetch in bulk); a
  partial clone cannot list-and-sweep because it must not hold what it does not track. This is the
  one real performance edge today, and it has a clean fix that needs no server change: a small
  encrypted "commit chain" object written on push, so a clone batch-fetches the chain (1,295
  commits is 26 requests, 16 in flight) instead of discovering it. Until then: `--depth`.
- **Once a clone exists, every operation is a few requests.** A file on demand is one object and
  under 3 s including process start; a folder of 130 files is 5 s; a pull that is up to date is
  2.5 s. This is the "fetch only what you need" number, and it does not depend on the vault's size.
- **History queries on the client are the other honest edge.** `history log --file` over 1,227
  commits took 6 min of CPU on the full clone because it flattens every commit's tree; it should
  skip subtrees whose id did not change, the way the clone walk does. The fix is local and needs no
  format change.
- **The pull an agent runs every session was the slow path, and is fixed.** Fetching the whole
  head into an empty store through the pull path: 186 s now, about 53 min before 14 Oct (one request
  per commit and one per blob). Measured on this vault, in the 14 Oct note.
- **A full clone is the worst case and still bounded:** 3½ min for 35,423 objects / 527 MB
  (listing 21 s, bulk sweep ~140 s, local tree decrypt 33 s, checkout 4 s).
- **Server-side numbers already published:** ten scoped clones at once in 1.9 s against ten full
  clones in 21.1 s on a single server process (the single uvicorn worker is the limit, not the
  protocol); a one-folder clone of 0.59 s at 100 files and 0.77 s at 2,000 while the full clone
  went 0.95 → 5.55 s; 100 writers landing 1,000 append-lane entries in 4.9 s with none lost
  (newsroom: *Agent workflows on ephemeral vaults*, *sgit in GitHub Actions, side by side*).

## 4. The argument the article should make

Scion's post names what matters at agent scale: always-online clients, fetch only what a job
needs, immutable objects any cache can serve, cheap incremental commits, a sparse working copy
by design. Point by point, with the mechanism and the number:

1. **Fetch only what you need.** A clone asks for the spine down to its folders and nothing else;
   unchanged folders keep their tree ids across commits, so they are never fetched twice. §3.
2. **One file is four requests, from any host that answers a GET.** Ref → commit → trees on the
   path → blob, computed from the read key; no listing, no index, no account. The site's own pages
   do it; `sgit cat` on a sparse clone does it (and, once a file is held, reads it with no network).
3. **Immutable objects, cached by whoever fetched them.** Browser Cache API on sgit.ai, a CDN,
   `--transport static` from GitHub Pages or S3 or a folder, `sgit vault mirror` for custody
   without access. The server sends `immutable`; the design does not depend on it.
4. **Writes are one batched request and a compare-and-swap.** 50 objects per request; the ref and
   the branch index move by CAS, and every client merges the index as a shared document. A commit
   costs the size of the change: the new blobs, the rebuilt spine, one commit object.
5. **Many clients, a dumb server.** The server computes nothing, so it scales as storage does
   (S3 behind CloudFront is the hosted deployment; `sgit serve` is the same image on a laptop).
   Append lanes let a hundred writers post without reading.
6. **And the thing Scion cannot offer anyone outside Anthropic:** the server never holds plaintext,
   the read key is one-way derived and publishable, and the whole thing is `pip install sgit-ai`.

Said with the gaps: no blame or bisect yet; partial clones walk history per commit until the
commit-chain object exists; one server process queues full clones; proven at 35k objects and ten
agents, not at 100 GB and 30,000 merges a day.

## 5. Deployment models the article should claim (all shipped, all documented)

| Model | What runs | Docs |
|---|---|---|
| Hosted | `dev.send.sgraph.ai`: S3 storage behind CloudFront, access token per account | `/docs/installation`, `/api/` |
| Your own server, one container | `diniscruz/sg-send-vault` with an access token and a folder or an S3 bucket; Docker Compose on a Mac mini; Kubernetes; a cloud VM with no public route; two servers, one vault | `/docs/self-host-for-agents`, `/deploy/`, newsroom *Encrypted memory for agents that run somewhere else* (five patterns) |
| On the laptop, from the clone | `sgit serve`: the vault UI + API in Docker, Podman, Apple `container`, nerdctl, Finch, or `uv` with no container; `serve pull/push` move work between the browser and the clone | CHANGELOG (Unreleased, `sgit serve`) |
| Static host, no server | `sgit publish` + any GET host (GitHub Pages, S3, a CDN, Python's file server); clients use `--transport static`; `sgit serve --static` locally | `/docs/vault/static-hosting`, CHANGELOG 0.18.0, newsroom *The homepage is a vault* (317 ms a request via the API, 44 ms from GitHub Pages) |
| A folder | `--transport local` | CHANGELOG 0.18.0 |
| CI sidecar | the server as a job sidecar; ciphertext in the cache or a branch between runs; a key per job; append lanes per shard | newsroom *sgit in a CI pipeline*, *sgit in GitHub Actions, side by side* (four lanes) |
| In the browser | the vault app, `vault-embed.js`, and pages on sgit.ai and newsroom.sgit.ai that render a vault with a published read key | `/docs/vault/vault-apps`, `/docs/vault/vault-from-javascript`, `/demos/vault-app-embed`, `/case-studies/live-vault-docs`, newsroom *Two agents, one vault*, *No server, by design* |

## 6. Website changes (sgit.ai)

1. **`/api/vault-objects` → "Measured 21 September 2026: the immutable header is not currently
   being sent."** Stale. Measured 16 Oct: `cache-control: public, max-age=31536000, immutable` on
   `obj-cas-imm-*`, `no-store` on `ref-pid-muw-*`. Add: CloudFront still reports a miss on repeated
   reads of the same object (the token header is likely in the cache key), so the CDN is not yet a
   cache for API reads; browser and client caches are.
2. **`/docs/partial-clones` → "Measured".** Add the §3 table, and a sentence under `--depth`:
   on a partial clone the history walk is one request per commit (a scoped clone of a 1,295-commit
   vault: 181 s without a depth, seconds with one); whole-vault clones and pulls list the store and
   fetch in bulk since 0.18 / 0.22.
3. **`/docs/limitations` → "Commit author attribution is not yet recorded … population is planned
   work."** Stale since 0.19.0: commits are signed, `check verify` classifies every commit, `history
   log --author` filters by key id, `vault tag` is signed. Replace with the current edges: no blame
   or bisect, partial clones walk history per commit, no rebase or cherry-pick.
4. **`/llms.txt` quick answer "No for: … tags"** and `/docs/sgit-for-git-users`: tags exist
   (`sgit vault tag create/show/list/delete`, signed). Also add `history undo`, `commit --amend`,
   `history revert --as-commit`, `reflog`.
5. **`/docs/self-host-for-agents` §1:** `pip install sgraph-ai-app-send "mcp<2"` → 0.34.0 caps
   `mcp` itself; image `v0.33.0` → `v0.34.0` in the three places; the troubleshooting row for
   `mcp` 2.x can go once 0.34.0 is the floor.
6. **`/deploy/`:** the `--endpoint` → `--base-url` correction note can be folded into the vault
   pages themselves (they are a vault: push the fix).
7. **A single "deployment models" table** (§5) somewhere under `/deploy/` or `/docs/`: today the
   seven models are spread over six pages and two newsroom articles, which is why the article
   claimed none of them.
8. **`/docs/vault/reading-a-vault-file`:** add the CLI equivalent (`clone-headless` + `cat`, and
   `clone --sparse` + `cat`/`fetch`) next to the browser reader, with the history-walk caveat.

## 7. Links for the newsroom agent

sgit.ai: `/docs/partial-clones`, `/docs/agents-sharing-one-vault`, `/docs/self-host-for-agents`,
`/deploy/`, `/docs/vault/static-hosting`, `/docs/vault/reading-a-vault-file`,
`/docs/vault/vault-from-javascript`, `/docs/vault/vault-apps`, `/demos/vault-app-embed`,
`/case-studies/live-vault-docs`, `/api/vault-objects`, `/docs/history-integrity`,
`/docs/two-branch-model`, `/docs/update-to-0-21-0`, `/docs/limitations`, `/docs/sgit-for-git-users`,
`/security/`, `/docs/vault/git-and-vaults`, `/case-studies/one-tree-two-remotes`,
`/use-cases/ai-agents`, `/docs/surfaces`, `/docs/what-is-sgit`, `/demos/vaults/llms.txt`.
newsroom.sgit.ai articles: *Encrypted memory for agents that run somewhere else*, *sgit in a CI
pipeline*, *sgit in GitHub Actions, side by side*, *Agent workflows on ephemeral vaults*, *No
server, by design*, *The homepage is a vault*, *Two agents, one vault*, *The vault is live*, *Where
the vault keys live*, *From sending a file to sgit*, *Git for things you cannot put on GitHub*.
Repo: `CHANGELOG.md` (0.18.0 partial clones and static publishing; 0.19.0 history integrity;
0.21.0 history commands; Unreleased: `sgit serve`, the 14 Oct pull fix), and the 14 Oct note
`team/humans/dinis_cruz/claude-code-web/10/14/response__sgit-issues-2026-10-14.md`.

## 8. Three paragraphs the article can paste

**Replacing "Immutable identifiers that cache":** Every object in an sgit vault is named by the
SHA-256 of its ciphertext, so a name can never point at different bytes, and the client checks each
object against its name before it is written. That is the property Scion's three cache tiers rest
on, and it means anyone who has fetched an object can keep it for ever: a browser's cache, a
proxy, a CDN, a folder. sgit.ai's own documentation pages are a vault read this way: a cold load
fetches 18 objects, the next load fetches one 69-byte ref, and a load inside the two-minute
freshness window fetches nothing at all. The only mutable object is the ref, and it is never
cached.

**Replacing "Measured on 0.22.0":** The vault this site's agent should have measured is the one ten
agents share every day: 1,295 commits, 5,101 files, 35,000 encrypted objects, 527 MB in a full
clone. [§3 table]. A full clone is the worst case at three and a half minutes. An agent does not
take one: it clones its own folder with one commit of history, in [path-security-depth1] seconds
and [MB], and a pull that is a day behind, which used to be the slow path at nearly an hour, now
takes three minutes for the whole head. One file is four requests from its read key, from any host
that answers a GET.

**Replacing "Where Scion is ahead", first sentences:** Scion does blame, bisect and merges on the
server and builds history indexes as derived data; sgit's server cannot read a commit, so those
run on the client, and today sgit has path history, signed authorship and signed tags but no blame
or bisect. Neither system packs objects on the server, and both treat that as a feature. Where sgit
is behind on its own terms: a partial clone still walks a long history one commit per request
(a depth avoids it), one server process queues concurrent full clones, and the largest vault it has
been proven on is 35,000 objects and ten agents, not 100 GB and 30,000 merges a day.

## 9. Storage is the bottleneck, not sgit

The hosted API is a Lambda in front of S3 behind CloudFront. Every request costs its round trip
(sandbox → proxy → CDN → Lambda → S3) before a byte moves, and the client's work per object (verify
the hash, decrypt) is microseconds. So on the hosted path the numbers are request counts, not
bytes: `--path security --depth 1` is 137 objects and 3 MB, and takes 13 s because it is about a
dozen dependent requests (ref, index, commit, one batch per tree level, the blob batches) plus
0.4 s of PBKDF2. The newsroom measured the same thing from the browser: 317 ms a request through
the vault API, 44 ms for the same object from GitHub Pages (*The homepage is a vault*).

Take the Lambda away and the same objects move at the speed of the storage:

- **ruv.sgit.ai ledger** (local SG/Send server, one process, disk storage, 11 recorded runs): every
  sgit operation, including Python start-up and the 600k-iteration PBKDF2, is 0.4 to 1.5 s; a
  38-file / 4.0 MB vault clones in 0.63 s; a 142-file / 6.9 MB vault clones in 0.74 s and pushes in
  0.87 s. Not one of those numbers is sgit being slow; they are the floor of starting a Python
  process and deriving a key.
- **newsroom, local server:** a one-folder clone 0.59 s at 100 files, 0.77 s at 2,000; ten scoped
  clones at once in 1.9 s.
- **The comms vault from local storage** (same 35k objects, this sandbox): the same sandbox, the
  same CLI, the same 35,423 objects, three transports:

  | Clone / operation | Hosted API (Lambda + S3 + CloudFront, via proxy) | Static: `sgit serve --static` (plain GETs, local disk) | Local API: `sgit serve --runtime uv` (one Python process, disk) |
  |---|---|---|---|
  | full clone | 3 min 30 s | 110.6 s (bulk fetch 71.5 s, tree decrypt ~33 s) | 69.1 s (commits 1.4 s, trees 40.7 s, blobs 18.8 s, checkout 2.7 s) |
  | `--depth 1` | 57.4 s | 25.4 s | 11.7 s |
  | `--path security --depth 1` (120 files) | 13.0 s | 2.3 s | **0.8 s** |
  | `--path docs`, all 1,227 commits | 181 s | | 7.1 s |
  | `--sparse`, all history | 206 s | 67.0 s | 43.3 s |
  | `cat` of one file on demand | 2.5 s | 1.8 s | 1.8 s |
  | `pull`, up to date | 2.5 s | | 0.8 s |

  Read down the columns: the per-commit history walk that costs 181 s against the hosted API is
  7 s against a local server (the same 1,227 requests at ~1 ms each); a one-folder clone is
  0.8 s. What is left when the network is gone is the client's own work, which is decrypting
  16,391 trees (about 33 to 40 s on a full clone) and nothing else of note. (Observation for
  the SG/Send brief: the local disk server answered the store listing with 0 objects, so the
  full clone there went by the graph walk rather than the bulk sweep; the walk found everything.)

The API does two things that storage cannot: it protects writes (the access token, compare-and-swap
on the ref and the branch index) and it shortens reads a little (batches of 50, a listing for cold
full clones). Both are small, and both can be done differently on different storage. Everything
else is a GET of an immutable object. So "how fast is sgit" is the wrong question; the right one
is "where is the storage, and how close": memory, a local disk, an S3 bucket behind a CDN, GitHub
Pages, a folder. The deployment table in §5 is that list.

## 10. sgit is a standard, not a server

The article treats sgit as a product with a server. It is closer to a convention for laying files
out, and the proof is that everything in a vault is reachable from one hash with no help from
anyone:

1. The vault key gives the vault id and, one way, the read key.
2. The read key gives the ref's name: `ref-pid-muw-` + the first 12 hex of
   `HMAC(read_key, "sg-vault-v1:file-id:ref:" + vault_id)`. Nobody told you; you computed it.
3. The ref holds the head commit id; the commit holds the tree id; trees hold blob ids and
   encrypted names. Ref → commit → tree → blob is four GETs for any file, from any host that
   serves the paths.
4. Every object but the ref and the index is named by the hash of its ciphertext, so it is
   immutable, verifiable and cacheable by whoever holds it.
5. Writes are the same objects PUT in batches, plus a compare-and-swap on the ref.

That is the whole wire format, and two independent implementations speak it (the CLI; the browser
vault app, which `vault-embed.js` reduces to about 90 lines). A static host implements the read
half with nothing installed. The **cache layer** (`sgit cache add <path>`, shipped) extends the
same idea to hot records: a declared path gets a client-computable cache object under
`bare/cache/`, maintained by push, so a reader with only `vault_id` + read key does *one* batch
read (the ref plus the candidate ids) and gets the file with no tree walk; a miss or a stale entry
falls back to the walk, so correctness never depends on it. The reference reader is written to run
in an edge function or a Lambda that serves one hot record. Scion's "derived data" is the same
move, computed on a server that can read the plaintext; sgit's is computed by the writer and named
by the key.

## 11. History, blame and merges: where they belong

Correct the article's framing, and then disagree with Scion's. In sgit, history (`log`, `--file`,
`--stat`, `diff`, `show`, `reflog`), undo, revert, tags, signature verification and three-way
merges all run on the client, and that is the design, not a shortfall. Blame is the one Scion
feature sgit does not have as a command today; it is a fold over path history and nothing in the
format prevents it. (The honest edge: on this vault `history log --file` over 1,295 commits took
6 min 8 s (5½ min of CPU), because it flattens every commit's tree; it should skip subtrees whose id did not
change, the way the clone walk does.)

The argument for the client: a merge is a workflow step, not a storage operation. It needs the
context of the change, the history, and the policy that says who may merge what. In ruv.sgit every
worker writes to its own branch and the host merges them per the run's mandate, with a receipt;
in the comms vault ten agents meet on a named branch and resolve on the clone that has the
conflict in front of it. A server that merges for you must be trusted with the plaintext and with
the policy. Scion's own post concedes the point from the other side: it could not keep a merge
queue, so "concurrent changes can conflict, but Claude can typically fix these conflicts" — the
merge went back to the agent.

And keep what made git git. Scion is in the Piper and Sapling line, a centralised system with one
authoritative store, and the post says plainly it "is by no means a suitable replacement for git
for general use". sgit keeps the distributed property: a full clone is still one command and a
complete, verifiable copy of everything, and anyone with the key can rebuild the whole thing from
any host. What changed is that the full clone became optional. `--path`, `--depth`, `--sparse` and
the cache layer mean a repository can hold large files without every client paying for them, which
is the one habit every git team has had to police by hand. The whole-history clone is a backup and
an audit, and it is still there when you want it.

## 12. Encryption as a constraint

The article sells encryption as privacy. The stronger claim is that it is a design constraint that
forbids the shortcut. Because the server cannot read a byte, there is no "just index it on the
server", no "just render it there", no server-side merge, no derived data the client did not
compute. Every feature had to be expressible as objects the client writes and other clients can
derive by key, which is why the results are small: a read is four GETs, a cache is a path-derived
object, a deployment is any storage. The newsroom's *No server, by design* is the same argument
applied to a whole site. Say it as a property, not a scolding: the constraint is what produced the
simple designs.

## 13. ruv.sgit, the integration the article does not mention

ruv.sgit.ai runs a Ruflo hive (rUv / ruvnet; a queen and parallel workers) with one ephemeral sgit
vault per run and an Agent Behaviour Policy compiled into Ruflo's enforce mode. The ledger
(`data/vaults.json`, 11 runs to 15 Oct) records every sgit operation with its milliseconds, the
server-held bytes, a plaintext probe of the server's store (0 hits in every run), a fresh clone
checked identical to what was delivered, and the vault deleted at close. It is the agent-swarm
case Scion's post is about, run on a local server, and it is where the "storage, not sgit" numbers
in §9 come from. Link it as the swarm evidence, next to *Agent workflows on ephemeral vaults*.

## 14. What was not done

- Nothing pushed to the comms vault; nothing changed on the site. The site changes in §6 are a
  list for the site agent.
- The commit-chain object (§3) is a design, not code. It is the one change that would make
  partial clones of long histories as fast as the depth-1 case; it needs a format note and a
  migration-free write path (a mutable, encrypted, per-branch object the client rewrites on push).
