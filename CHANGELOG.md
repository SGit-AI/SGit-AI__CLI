# Changelog

All notable, user-visible changes to **sgit-ai** are recorded here.

The format is loosely based on Keep a Changelog; the project follows semantic
versioning per `sgit_ai/_version.py`.

## [Unreleased]

### Added — from the git -> sgit security mapping

  - **Signed tags: `sgit vault tag create <name> [<commit>] -m "…"`, `list`, `show`, `delete`.**
    A tag is an immutable object in the store (name, commit, message, tagger key, timestamp)
    signed by the clone's key over its canonical (JCS) form, encrypted under the read key and
    content-addressed like every object. Names live only in the encrypted branch index, so the
    host never sees them. `show` and `list` verify the signature (fetching the tagger's key when
    needed) and that the index entry's name is the name inside the signed object; a mismatch is
    `bad`. Only a commit already on the server can be tagged. Tags do not move without
    `--force`, and a pull reports a tag that moved, appeared or was deleted. Deletes are
    tombstones that every clone respects. A tag name works wherever a commit id does in
    `history show` / `history reset`. Clients older than 0.21.0 ignore tags and drop them from
    the index when they register a new clone branch; the next current client's pull restores
    them (verified on the live API with 0.20.0).
  - **`sgit history reflog [--all] [-n N]`: where this clone's head has pointed.** Every local ref
    move is appended to `.sg_vault/local/reflog.jsonl` (local only, capped at 1,000 moves).
    After a reset, an accepted rewind or a bad merge, `sgit history reset <old id>` brings the
    head back; the commits stay in the local store.
  - **`sgit push --force-with-lease [<commit>]`.** Forces only if the remote branch is still where
    this clone last saw it before this push (or at the commit given), and writes the ref with
    compare-and-swap, so a teammate's push is never clobbered. Refuses with nothing written.

### Added — history commands git users reach for (all local, no format change)

  - **Revision shorthand everywhere a commit is named** (`history show/reset/diff/revert`, log
    ranges, `vault tag create`): `HEAD`, `@`, `HEAD~2`, `HEAD^2`, chains like `HEAD~2^2`,
    `@{1}` / `HEAD@{1}` (where this clone's head was, from the reflog), tag names, the hex
    `history log` prints and unique prefixes of 4+ characters.
  - **`sgit history undo [--force]`**: moves this clone's head back to where it was before its last
    move, restoring the files; run it again to redo. Refuses a dirty working copy, and refuses
    when the head is already on the server (undo would only diverge this clone; it points to
    `revert --as-commit` instead).
  - **`sgit history log --grep/--since/--until/--author`**: filters the decrypted history on the
    client. `--author` matches part of a signing key id, branch id or branch name; dates take
    `2026-10-08`, `2026-10-08T14:30`, `3d`, `12h`, `"2 weeks ago"`, `yesterday`.
  - **`sgit history log --stat`**: the files each commit added, modified, deleted or renamed
    (a rename is the same content under a new path). The non-oneline log also shows the author key.
  - **`sgit history revert --as-commit --commit <rev> [-m …]`**: a new, signed commit that inverts an
    earlier one (git revert), the way to undo a pushed change for everyone. Refuses merge commits,
    the first commit, a dirty working copy, scoped clones, and a revert that conflicts with later
    commits, before changing anything. Plain `history revert` (restore files) is unchanged.
  - **`sgit commit --amend [-m …]`**: replaces the last commit with the working copy and/or a new
    message, keeping its parents. Refused when that commit is already on the server, is a merge,
    or a merge is in progress; the old commit stays in the reflog.

### Fixed — branches (found by an end-to-end check)

  - **Work on a branch was pushed to the main branch.** Push, pull and fetch looked up the
    named branch called `current` by name, so a commit made on `feature` landed on `current`,
    the feature ref never reached the server, and teammates on main received it. They now work
    against the branch the clone tracks (status already did).
  - The first push of a new branch writes its ref (there is nothing on the server to
    compare-and-swap against); ref writes are always sent after their objects.
  - A clone branch made by `branch new` / `branch switch` registers its signing key on push;
    teammates saw its commits as `no-key` before.
  - `branch switch` kept a reused branch's unpushed commits only by accident of order: it reset the
    head to the named head. It now advances only when strictly behind, and resets the rewind
    baseline to the entered branch (no false REWOUND when branches do not descend from each other).
  - **`sgit branch switch` fetches**: it refreshes the branch index (a teammate's new branch), switches,
    then pulls; accepts `--token` / `--base-url`.
  - `branch new` refuses a duplicate name, starts from this clone's head (as git does: unpushed
    commits come along and the working copy stays consistent), and `--from` checks its source out.
  - **New: `sgit branch merge <name>`**: merges another named branch into the current one
    (fast-forward, a two-parent merge commit, or conflicts for `sgit resolve` + `sgit commit`).
  - **Every merge commit a pull created was unsigned** (since signing existed): the pull state held
    the key id as a plain `Safe_Str`, which turns `-` into `_`, so the key file was never found.
    Under `signatures-required` that refused every teammate's merge.

### Changed — tests and environment

  - `SGIT_DEFAULT_BASE_URL` sets the server used when none is configured (self-hosting); the
    default stays `https://dev.send.sgraph.ai`. `push`'s local "uncommitted changes?" check and
    `migrate`'s signature check no longer construct a network client.
  - Unit tests are hermetic: 20 of them reached the live dev server (or an empty host) through
    commands run on test vaults without a remote; a conftest guard now fails any unit test that
    leaves loopback. The full unit suite runs in about 45 s instead of 70 s (fixed test vault key,
    so PBKDF2 runs once per worker; test HTTP servers shut down in 20 ms instead of 500 ms).
  - New real-server integration tests for branches, tags, the format gate, signatures-required,
    rewinds and force-with-lease. The local integration setup in CLAUDE.md pins `mcp<2`, as CI
    does; without it every integration test errored on server start.

### Security

  - **The checkout path guard refuses every spelling of `.git` and `.sg_vault` a case-insensitive or
    normalising filesystem resolves to the same directory**: `.GIT`, `.Git`, trailing dots and
    spaces (`.git.`), 8.3 short names (`GIT~1`, `SG_VAU~1`), NTFS streams (`.git::$INDEX_ALLOCATION`)
    and HFS+-ignored code points (`.g\u200cit`). The guard matched exact names only, so on macOS
    or Windows a vault entry such as `.GIT/hooks/post-checkout` could have been written into
    `.git/` on checkout (the CVE-2014-9390 / CVE-2019-1353 class). Linux was not affected.

### Security — full review before 0.21.0 (threat model: `team/explorer/appsec/threat-model/v0.21.0__threat-model.md`)

  - **A clone no longer checks out a HEAD with a file missing.** If the host withheld a file's
    object, or served bytes that failed the content-address check, clone warned and carried on;
    the working copy then read as that file deleted, and the next commit deleted it from the
    vault for everyone. Clone now refuses (`clone incomplete`, naming the files), as pull did.
  - **Every download path checks the content address before writing**: `check fsck --repair`,
    `vault move`'s auto-repair (which re-encrypted a substituted object into the new vault, where
    it then verified forever), sparse fetch / cat, the cache pointer's blob. Presigned URLs from
    the host are followed only over https (or http to loopback), with a timeout.
  - **Vault data never writes outside the tree or into `.git` / `.sg_vault` on any path**: revert,
    branch switch, stash pop, sparse fetch and restore were unguarded (only clone / pull /
    checkout were), and the delete-on-pull loop could remove files outside the tree. Writes
    are also refused when a symlinked folder would carry them out of the tree.
  - **A symlink that leaves the working copy is never committed.** The scan followed it, so a link
    to `~/.ssh/id_rsa` put the key's content in the vault. `secure_unlink` removes a link
    instead of zero-filling its target.
  - **`.vault__*.zip` backups (vault store + plaintext key, left by `vault uninit`) are structural:**
    never committed, never written from vault data; `init --restore` extracts only the store
    from a backup, never other members.
  - Key-bearing files are created owner-only (0600) whatever the umask: a bare vault's checkout
    key, backup zips that include the key, the local secrets store.
  - `sgit update` runs pip in isolated mode (`python -I -m pip`): a `pip.py` in the current folder
    was imported and run.
  - **The named branch's private signing key is no longer stored in the vault.** It sat in
    `bare/keys/` under the read key, so every read-key holder, including every read-only share,
    could sign as the named branch. Only `vault move` sentinels used it; they are now signed by
    the moving clone's own key. Existing vaults keep theirs until moved: `sgit vault move` drops it.
  - **`sgit vault move` kept the vault but lost the clone's signing key**: every commit after a
    move was unsigned (and refused by teammates under `signatures-required`). Move now carries it.
  - **Clone enforces `signatures-required`** (it only warned through pull before): a new step
    checks every commit made since the policy was switched on, before any file is written.
    Switching it on records where it starts (`signed-since-…` in the features), so a vault's
    older unsigned history is never held against anyone; this also fixes **pull refusing the first
    push after the policy was switched on** in a vault with older unsigned commits (pull walked
    past what the clone already held). A vault that switched it on before this release has no
    recorded start, and clone checks its head only.
  - **Read-only clones refuse a rollback** of the named branch, like writable clones
    (`--accept-rewind` to follow it anyway).
  - **Tags**: an entry dated more than a day in the future loses to every honest entry (it used to
    pin or delete a name for good), and a tag name used as a revision (`history reset v1.0`) must
    verify, or it is refused by name.
  - New CI job **Run Security & Adversarial Tests** (`tests/security`, hermetic, ~2 s, in parallel):
    every fixed attack above as a test, and a proof for every known, accepted gap in the threat
    model (the test fails when a gap closes). Real-server tests prove the write-key boundary
    (`tests/integration/test_Security__Server_Boundary__Integration.py`).

### Fixed

  - `history log -n N` compared its oldest commit with an empty tree, so that commit's counts
    (`+N`) and `--stat` showed every file as added; it is now compared with its real parent.
    Multi-line messages show their first line in one-line output.
  - **`sgit push --force` from a clone that was behind the remote crashed** with "object … is not in
    the local store": the status check moved the local named ref to the server's head with commit
    objects only, and the force path then read that head's tree. The trees are now fetched first.
  - Refusals by design (dirty tree, rewind, signature policy, client too old, lease, tag) print one
    `error:` line, without the code location that made them look like crashes.
  - The commit schema called `author_key_id` "reserved"; it has been live since 0.19.0.

### Fixed — found by the sgit.ai team testing 0.20.0 on the live API

  - **`signatures-required` refused a teammate's legitimate commits on an older clone.**
    Pull refreshed the branch index but never downloaded the public key file of a branch
    registered after the clone was made, so every commit signed by a newer teammate was
    `no-key` and the pull was refused, on every later commit too. Pull now fetches missing
    key files (one batch read; a key file is encrypted under the read key, so the host cannot
    substitute one), and `sgit check verify` does the same against the clone's own server.
  - **The owner could not switch a policy off for a stale clone, and the stale clone switched
    it back on.** The index merge kept "the stronger gate", so a clone that had seen
    `signatures-required` kept it after the owner removed it, and wrote it back to the server
    on its next pull. The server copy's gate is now authoritative; the local gate returns only
    when the server copy has no gate fields at all (a web-UI overwrite). `sgit vault format`
    starts from the server's gate, not the clone's copy, and always writes an explicit format.
    Clients on 0.19.0/0.20.0 still merge the old way: update every clone.
  - **`sgit pull --accept-rewind` kept the commits the rewind removed.** The clone stayed on
    the removed commit, `status` said "1 commit ahead … run: sgit push", and pushing put the
    removed history back. Accepting a rewind now moves the clone to the new head; a clone with
    commits of its own gets them re-applied on top as one commit whose only parent is the new
    head. Own work that conflicts with the rewind refuses, with nothing changed.
  - **A pull without write access warned `Could not refresh the branch index … HTTP 401` every
    time.** The merged index is kept locally and the write-back is skipped quietly.
  - **`history reset` / `history show` refused the id `history log` prints.** They now take the
    full id, the hex `history log --oneline` shows, or a unique hex prefix (4+ characters).
    Not new in 0.20.0.

Verified on the live dev API with a throwaway vault and five clones, plus 11 regression tests
(all fail on 0.20.0). tests/unit -n auto: 3987 passed.

## [0.20.0] — 2026-10-08

### Changed

  - **`sgit vault format --set 2` now warns the owner about older clients.** Raising a vault
    to format 2 does not make a pre-0.19 client say "update": its fresh clone of the raised
    vault stops with `integrity check refused vault data … corrupt or substituted … re-run
    sgit vault move`, and its `pull` stops with `missing file … try sgit check fsck`. The
    command prints that after the raise, with the real fix (`sgit update` on every machine
    that uses the vault; neither `vault move` nor `fsck --repair` is the answer). Add
    `--min-client 0.19.0` so clients from 0.19.0 on refuse by name instead.
  - The "pattern mismatch" hint for unknown object names now says `sgit update` first and
    names an older CLI version as the likely cause.
  - Docs corrected: the 0.19.0 notes said pre-0.19 clients fail on a raised vault "with a
    validation error"; they show the two messages above (reproduced with sgit-ai 0.18.0 on
    the live dev API).

## [0.19.0] — 2026-10-07

### Added — history integrity: a format gate, 128-bit object ids, signature verification, ref monotonicity

  - **`sgit vault format`** shows and raises a vault's format gate, kept in the encrypted
    branch index: `--set 2` makes every NEW object a 128-bit (32-hex) content address while
    existing objects keep their 48-bit ids (a mixed vault; no `vault move`, no re-encryption);
    `--min-client X.Y.Z` makes clients older than that refuse the vault by name
    (`this vault needs sgit-ai >= X.Y.Z and this is …: run sgit update`); `--feature` /
    `--remove-feature` set policies. Every existing vault reads as format 1 with no minimum
    and behaves exactly as before. A writer that does not know the fields drops them, which
    fails open (back to format 1), never closed. Verified on the live dev API: 44-character
    object names are accepted on write, read, batch and list, and a mixed-id vault clones,
    pulls, pushes and passes `fsck`.
  - **The branch index is treated as a shared document.** `pull` reads the remote copy,
    merges it with the local one (every branch by id, the stronger gate) and writes the merge
    back with compare-and-swap; the clone-branch registration on push does the same. A web-UI
    overwrite (one entry, no gate) is repaired by the next CLI pull: `Branch index: restored
    N entries the remote copy had lost`. The live server reports a compare-and-swap miss per
    operation inside an HTTP 200 (with the current bytes); the in-memory API at the top level;
    both are retried as a merge.
  - **The named branch only moves forward.** Each clone records the last remote head it
    accepted (`last_remote_head`, local config). A remote head that does not descend from it
    is a rewind: `sgit status` says so (`the named branch was REWOUND or rewritten …`), `sgit
    pull` refuses before touching anything, and `sgit pull --accept-rewind` takes it after a
    deliberate `push --force`. A fresh `init` over an existing vault id is not a rewind.
  - **Signature verification.** `sgit check verify` classifies every commit reachable from
    HEAD (verified / bad / unsigned / without a known key); `sgit check fsck` reports the same
    summary and fails on a bad signature. Keys come from the commit's own `author_key_id`,
    then from the branch index's branch → key mapping. With the vault feature
    `signatures-required`, `pull` refuses the first incoming commit that does not verify,
    by name, before merging. `sgit migrate apply` refuses on a vault with signed commits
    unless `--force` (a migration rewrites history).

### Fixed

  - **`pull` left the trees of commits that `status` had already fetched unfetched** (since
    0.18.0, where status fetches commit objects to count ahead/behind): the commit walk
    skipped any parent already local. A local commit now counts as complete only when its
    root tree is local too; otherwise its trees and blobs are fetched. `fsck` after
    `status` + `pull` on a clone 4 commits behind: 3 missing trees before, none after.
  - The "incompatible vault data" hint now says to run `sgit update` first: data an older
    client cannot parse is most likely from a newer one.

### Changed — commit signatures have a canonical, cross-client signing input

  - A commit's signature is now over the RFC 8785 (JCS) serialisation of the stored commit
    JSON with the `signature` member removed (keys sorted, no whitespace, UTF-8), so the web UI
    can produce and verify the same bytes. New signed commits carry `author_key_id` (the
    `bare/keys/` id of the signing key), so a verifier no longer depends on the branch index
    still listing the branch. Commits signed before this (`author_key_id` null) still verify
    over the old bytes. Shared vectors for object ids, deterministic tree encryption and commit
    signing live in `tests/_fixtures/interop_vectors.json`. Nothing verifies signatures yet
    (that is 0.19, in warn mode); this only fixes what is signed.

### Fixed

  - **`sgit check fsck` re-walked every tree once per commit.** The per-commit tree set made
    the walk quadratic in history: on the 674-commit DC vault that was 282,202 tree checks for
    8,589 unique trees, every blob re-hashed per commit, 270 s. Trees and blobs are now verified
    once across the whole walk: 12 s on the same vault, same findings (42 missing objects, from
    pushes made before 0.18.0).
  - The whole-vault guard named `sgit dump`; the command is `sgit dev dump`.

## [0.18.0] — 2026-10-07

### Added — partial clones: a folder scope and a history depth

  - **`sgit clone --path <folder>` (repeatable) — hold only those folders.** The vault is a
    Merkle tree, so a clone needs the trees on the spine down to a folder plus the folder
    itself; every other folder is carried by its tree id and never downloaded. Commits
    rebuild the spine with one entry replaced per level and keep the siblings' ids, so
    `commit`, `push` and `pull` work normally inside the held folders, and two scoped clones
    in different folders can never conflict (out-of-scope entries are always taken from the
    remote by id). Writes outside the held folders are refused with the path named.
    On the 626-commit / 9,404-blob DC vault: `mail/crm.riskmandate` (365 files) clones in
    14 s with 429 objects / 3.2 MB, against 81 s / 18,720 objects / 173 MB for the full clone;
    two small folders in 5 s.
  - **`sgit clone --depth N` — shallow history.** Only the newest N commits are fetched and
    the boundary is recorded; pull, push and status stop there by design (the named branch
    only ever moves forward, so every later commit descends from the boundary). Combine with
    `--path`. `sgit fetch --unshallow` fetches the rest (commits only on a scoped clone;
    everything, via the store listing, on a whole-vault clone).
  - **`sgit fetch <folder>` on a scoped clone widens it** (fetches the folder from HEAD,
    writes its files, records it). Whole-vault commands — `check fsck`, `dump`, `publish`,
    `vault move` — refuse on a partial clone and say how to widen it.
  - Full clones are untouched: no scope, no boundary, the same steps, the same object set
    (verified on the real vault: identical object count and `fsck` result before and after).

### Fixed — from the deep review of the partial-clone changes (before the PR to main)

  - **Hardening (no vulnerability found; three belt-and-braces checks added).** A batch
    read now ignores any result whose `file_id` was not requested (the id names the on-disk
    write path, so a host must only answer what it was asked). `Vault__Verified_Write`
    writes only bare-store leaves (`bare/data|refs|indexes|keys|branches|pending/<x>`,
    `bare/cache/value|pointer/<x>`) and refuses anything else (`local/config.json`, a
    working-copy path, a protected dir). The pull guard lets an untracked file collide with
    an incoming one only when the DECRYPTED incoming blob proves the content identical — the
    tree entry's own `content_hash` is the committer's claim, and a lying entry could have
    overwritten an untracked local file silently.
  - **Scoped clones and the readers.** `sgit status` / `commit` on a scoped clone kept the
    "tracked wins over ignore" rule (a tracked file under an ignored dir is no longer
    reported deleted and dropped); read-only scoped clones get a scoped status and checkout;
    `sgit ls` / `fetch` / `cat` on a scoped clone see the held folders instead of failing on a
    sibling's tree. A command that meets an object a partial clone never fetched now explains
    the scope and how to widen it instead of "the vault may be corrupted — run fsck".
  - **Shallow boundaries were typed values, not plain ids.** The boundary commit ids read
    from the config hashed differently from plain strings (set membership failed) and were
    sanitised by `os.path.join` (`/` → `_`), so `sgit fetch --unshallow` on a scoped shallow
    clone found no boundary commit and fetched nothing. `Vault__Scope` now hands consumers
    plain strings (`boundary_ids()`, `folders()`); the typed fields still validate (`..`,
    absolute paths and non-object ids are refused; nested folders collapse to the widest).
  - **`sgit push --branch-only` re-sent the clone branch's whole history on every push, and
    its ref write conflicted on every push after a commit.** The chain now stops at the
    clone-branch head the server already holds (or the named head the clone started from),
    blobs the server already has are not re-sent, and the compare-and-swap matches the
    server's current ref bytes rather than the local file's (which moved on at commit time).
    A scoped clone's branch-only push skips the sibling trees it never fetched.
  - **`sgit status` no longer walks the local history** to decide whether the remote head's
    chain is complete: the walk from the remote head stops at the last fully-fetched remote
    head and the clone's own head, so an up-to-date clone opens no commit and a clone N behind
    opens exactly N; a head left local by an earlier truncated fetch (fetch limit hit) is still
    expanded down to its missing parents.
  - **`sgit fetch <folder>` (widen) never overwrites local work**: a file already on disk
    under the new folder whose bytes differ from HEAD refuses the widen naming it; files in
    already-held folders are left untouched.
  - **Bulk clone sweep is fail-soft per chunk**: one failing batch no longer aborts the clone
    (the walks fetch what the sweep missed); its counters are lock-protected.
  - Whole-vault guards (`check fsck`, `dump`, `publish`, `vault move`) share one
    implementation; sparse push no longer tries to load a blob it never fetched.
  - **Every clone left an empty `/tmp/sgit-clone-*` directory behind** (the workflow
    workspace's temp root; the workspace inside it was removed, the root never was — 3,881 of
    them on the review machine). All five clone entry points now remove it, success or failure.
    Found by making the dev-plugin "no temp dir leaked" test deterministic: it watched `/tmp`
    before and after, which under `pytest-xdist` also sees other workers' vaults (a flaky CI
    failure); it now watches the temp dirs the call itself creates.

### Added — static publishing (the "no server needed" feature set)

  - **`sgit help --format`** — emits the CLI's command surface, generated by walking the
    live argparse tree, as diffable `--format json`, a drop-in `--format markdown` docs
    page, or an `--format llms` index for `llms.txt`. Hand-written command lists drift;
    this cannot, and a test asserts the generated set equals the parser's set exactly.
    Intended as the hand-off contract for keeping sgit.ai current with each release.

  - **`sgit publish`** — generates a small plaintext surface (loader, `cover.json`,
    `manifest.json`, and — only at `--visibility public`, after an explicit
    irreversibility confirmation — the public read key file) into `.sg_vault/publish/`.
    No ciphertext is copied: the manifest enumerates the store, and the served root is
    composed at deployment. Deterministic; needs only the read key, so read-only clones
    and zero-secret CI can republish. `--bundles` adds `ZIP_STORED` head/delta zips;
    `--api-spec` / `--api-docs[=cdn|bundled]` add a generated `api/openapi.json` and an
    SRI-pinned, CSP-guarded Swagger UI docs page.
  - **Static read transport** — `sgit clone` (and fetch/pull) now work from any plain
    GET host or a folder: `--transport auto|api|static|local`, with both published
    layouts auto-sniffed. Writes on a static transport raise; only an HTTP 404 means
    "absent" — a dead host raises loudly naming the host instead of diagnosing as an
    empty vault.
  - **`sgit vault serve`** — a local, read-only, loopback-bound file server for the
    published folder (browsers give `file://` documents an opaque origin), routing
    `/api/vault/read/<vid>/bare/*` to the store virtually; path-guarded, Host-checked,
    auto-publishing when the folder is absent or stale.
  - **`sgit vault mirror`** — custody without access: a keyless, verifiable copy of a
    published vault. Content-addressed objects are re-hashed (the manifest's own hashes
    are never trusted for them); hostile manifests (path traversal, over-counts,
    conflicting duplicates) are refused.
  - **`sgit vault attach`** — bind a vault key (read-write) or read key + vault id
    (read-only) to an existing `.sg_vault/bare` checkout, e.g. a fresh `git clone` of a
    one-repo vault. Validates against `bare/refs` before writing anything; a wrong key
    writes nothing.
  - **`sgit vault ignore`** — shows the always-ignored folder list; `--apply <folder>`
    removes a now-ignored folder's tracked files from the vault in one visible commit,
    leaving the work tree untouched.

### Fixed

  - **Push uploaded only HEAD's blobs, so a file changed twice before a push left its
    earlier version missing on the server.** Trees for every pushed commit were uploaded,
    but blobs were taken from the clone HEAD tree minus the remote HEAD tree, so the
    blob of a version created and replaced within one push was referenced yet never sent:
    41 such objects on a vault after four days of agents committing several times per run
    (`sgit check fsck` on any clone: `Missing objects`). Push now collects the blobs of
    every commit it pushes (each tree decrypted once however many commits share it).
  - **`sgit clone-branch`, `clone-headless` and `clone-range` failed instantly** with
    `Name or service not known`: they built an API client with no base URL. They now
    resolve the saved token, `--base-url`/`--remote` and `--transport` exactly as
    `sgit clone` does.

  - **`sgit pull` no longer discards uncommitted edits.** A fast-forward (and a
    three-way merge) checked the whole incoming tree out over the working copy, so an
    uncommitted change to a tracked file was silently replaced by the committed version
    even when the incoming commits never touched that file, and `sgit status` then
    reported "fully in sync" (reported three times by a ten-agent team sharing one
    vault). Pull now does what git does: before writing anything it compares the working
    tree with the clone HEAD; a dirty file the merge does not change is carried over
    untouched (listed as `Kept … (yours, uncommitted)`), and a dirty, locally deleted or
    colliding untracked file the merge *would* change refuses the pull up front —
    `error: your local changes would be overwritten by pull:` naming each path — with
    the working tree, clone ref and store exactly as they were. Commit or
    `sgit vault stash`, then pull again.
  - **`sgit status` counted every local commit as "ahead" when the remote had moved.**
    Status overwrote the local named ref with the remote value before counting, so the walk
    from the (not yet local) remote head was empty and a fresh clone one commit behind said
    `diverged: 200 ahead, 1 behind — push`. Status now reads the remote ref without writing
    it, fetches the missing commit objects (one small object per new commit, bounded at 50,
    verified before write), advances the local ref only once the remote history is local,
    and reports real counts: `remote has 1 new commit — run: sgit pull`. Offline, or past
    the fetch bound, `ahead` is still exact (local commits not reachable from the last
    fully-known remote head) and `behind` is shown as a lower bound (`50+`).

  - **Clone/pull tree walk no longer re-fetches shared sub-trees once per parent.**
    `Vault__Graph_Walk` queued a sub-tree once for every tree that referenced it, so a
    history whose commits share most folders (every history) asked the server for several
    times as many trees as the vault has — 10,098 requests' worth for 2,236 unique trees on a
    172-commit vault — and `Vault__API.batch_read` fetched its 50-id chunks one at a time.
    That vault's tree phase went from 377 s to 24 s (full clone from ~7–8 min to 73 s). Each
    tree id is now queued and requested exactly once, `batch_read` fans chunks out over a
    bounded pool (as the blob download and static transport already did), and the walk
    reports `fetching N tree(s)` per level so a large level no longer looks like a hang.

### Changed

  - **Full clones fetch the whole store in one parallel sweep.** The commit and tree walks
    discover objects one dependency level at a time (a 600-commit history is 300+ serial
    round trips before a single tree is known). A full clone now lists the store once
    (`list_files bare/data/`, ~11 s for 18,684 ids) and downloads every object not yet local
    in 16 parallel batches, verified before write; the walks then run against a store that
    already has everything and still fetch anything a truncated or failed listing left out,
    so a static host without a manifest only loses the speed-up. Sparse clones skip the
    sweep. On the 621-commit / 9,356-blob DC vault: ~170 s → 80 s (walks 0.2 s + 0.9 s).
    `batch_read` fans out 16 chunks (measured ~2× the throughput of 8), and HTTP 429 is
    retried with back-off like a 5xx.

  - **API calls reuse one TLS connection per host (keep-alive) instead of a fresh
    handshake per request.** `Vault__API` now sends every call through a small stdlib-only
    pool (`Vault__HTTP_Pool`, `http.client`): keyed by scheme/host/port/verify-flag/proxy,
    shared across the parallel fetchers with a lock, honouring `HTTP(S)_PROXY`/`NO_PROXY`
    via a CONNECT tunnel. Rules: a failure between sending and reading the whole body
    discards the connection; a stale keep-alive (the server hung up unseen) is resent once
    for reads only — a write is never replayed; redirects are no longer followed, so the
    token headers can never be sent to another host (urllib copied every header onto a
    redirect). Error shapes are unchanged (`API Error: HTTP <code> …`, `URLError` for
    transport failures). `SGIT_HTTP_NO_KEEPALIVE=1` restores one connection per request
    for A/B measurement.

  - **`sgit_ai/_version.py` now resolves the real release version** instead of a
    hand-written literal that had gone stale at `v0.1.0` while the released package was
    `v0.16.1`. `Vault__Publish` stamps this constant into every published `manifest.json`
    as `generated_by`, so published vaults were misreporting the version that produced
    them. It now reads the same `sgit_ai/version` file `sgit --version` reads.


  - **`sgit vault move` now rewrites object ids.** Key rotation re-encrypts every object
    *and* recomputes its content address, rewriting the whole object graph bottom-up
    (blobs → trees → commits) so every reference stays intact. Previously objects were
    re-encrypted in place under their old ids, which meant nothing in a moved vault could
    be verified against its own content address. Two consequences: a moved vault is now
    verifiable exactly like a fresh one, and it shares **no** object id with the vault it
    came from — so the two can no longer be correlated by anyone who sees both stores.
    A vault moved by an older sgit keeps its old ids; re-run `sgit vault move` on it to
    normalise the store (clone says so if it meets one). Because every id changes, any
    previously published copy of a moved vault (manifest, bundles, deep links) goes
    stale — `sgit publish` again and redeploy; the move output says so.

  - **`.github/` is no longer vault content** (it joins the always-ignored folders):
    workflow files inside a vault are the payload that turns vault-write into code
    execution on a publisher's CI runner. Existing vaults are safe — ignore rules now
    govern **untracked files only** (git's rule): paths already in the vault head are
    grandfathered across every command, with a one-time migration notice naming the
    deliberate-removal escape hatch.

### Security

  - **Verify-before-write on every download path (SP-1/I7).** Clone, fetch and pull now
    id-verify every content-addressed object (`sha256(ciphertext)[:12] == id`) before it
    touches disk, with the write path contained by `Vault__Path_Guard`; a refused object
    is skipped and reported, never written, and never aborts the run. The check is
    **strict** — there is no "but it decrypts under my key" exemption, so a host that
    swaps two authentic objects between their ids is caught rather than silently obeyed.
  - **Integrity refusals diagnose as refusals, everywhere.** When a refused object turns
    out to be *required* (a tree or commit the walk cannot proceed without), clone now
    raises a typed `Vault__Integrity_Error` naming the object and the remedy, instead of
    a raw missing-file error showing an internal store path; the refusal summary is
    emitted even when the clone fails, and reaches stderr when no progress callback is
    passed (so library callers are never silent on a security refusal).
  - **Structural paths are never written from vault data.** A crafted vault that carries
    `.git/**` or `.sg_vault/**` entries can no longer drop files into a clone's git-hook or
    key/config directories: the checkout path refuses any entry under a protected directory
    (`.git`, `.sg_vault`, `.sg_vault_new`, `.sg_vault_old_*`), and the ignore engine refuses
    these even when a vault head already tracks them.
  - **`sgit vault serve` keeps its DNS-rebinding defence when `--bind` widens.** Host headers
    that are domain names are refused on any bind address (rebinding requires a name);
    loopback names and IP-literal Hosts are allowed. Local static reads are path-contained,
    and a per-object non-404 HTTP status fails soft rather than aborting a batch read.

  - **Path-traversal containment in vault checkout.** Vault tree-entry names are
    decrypted from vault data and chosen by whoever authored the vault, so a
    hostile vault cloned with `sgit clone` could carry an entry named
    `../../etc/foo` (or an absolute path) and overwrite files outside the working
    copy. All working-directory writes derived from vault data now pass through
    `Vault__Path_Guard`, which rejects absolute paths and `..` traversal and
    verifies the target stays under the destination.

### Removed — Simple Token / SG-Send transfer feature

The Simple Token credential scheme (`word-word-NNNN`) and the SG/Send
transfer/share/publish/export feature built on it have been **removed entirely**.
The scheme carried only ~30 bits of entropy and exposed a fast public-ID oracle;
it is no longer part of sgit. Removed:

  - Commands: `sgit share` (send/receive/publish), `sgit vault export`,
    `sgit vault share`, `sgit vault probe`, and the `sgit clone <simple-token>`
    transfer variant.
  - Code: `Simple_Token`, the word list, `Vault__Transfer`, `Vault__Archive`,
    `API__Transfer`, `Transfer__Envelope`, the transfer clone workflow and its
    steps, and the associated transfer/archive schemas.
  - The `edit_token` field on the local config and the `simple_token` config
    mode are gone; existing simple-token-addressed vaults are no longer readable
    by the CLI (re-key to a `passphrase:vault_id` vault key).

`sgit clone <vault-key>` (the `passphrase:vault_id` form), commit, push, pull,
and all standard vault operations are unaffected.
