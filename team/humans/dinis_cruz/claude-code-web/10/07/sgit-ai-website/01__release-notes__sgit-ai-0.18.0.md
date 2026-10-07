# sgit-ai release notes — 0.18.0

*7 October 2026, on PyPI. Upgrade: `sgit update` (wraps `pip install --upgrade sgit-ai`). Check: `sgit version`.*

This release is about one situation: a team of AI agents sharing one vault that has grown
large. Every number below was measured on such a vault (about 600 commits and 9,400 files,
roughly 170 MB of encrypted objects, worked on by around ten agents in parallel) from one
client in a cloud sandbox whose network path adds latency to every request, so a client on a
plain connection sees at least these gains.

## What changed, in one table

| Area | 0.16 | 0.18.0 | Change |
|---|---|---|---|
| Full clone of the example vault | ~7–8 min at 170 commits; 165–172 s at 600 commits | 73 s at 170 commits; 80 s at 600 commits | tree walk fixed (0.17.0), then one parallel sweep of the store (0.18.0) |
| Clone of one folder of it (`--path`, 365 files) | not available | 14 s, 429 objects, 3.2 MB | new |
| Clone of two small folders | not available | 5 s | new |
| Shallow clone (`--depth 1`) | not available | whole tree, one commit | new |
| `sgit pull` with uncommitted edits | edits to tracked files silently reverted | edits kept, or the pull refused before writing | fixed |
| `sgit status` after someone else pushed | "200 ahead, 1 behind" | "remote has 1 new commit" | fixed |
| API requests | one TLS handshake per request | one connection per host, reused | 0.17.0 |
| `sgit push` after editing a file twice | the first version's content never reached the server | every pushed commit's files are uploaded | fixed |

## New

### Scoped clones: `sgit clone --path <folder>`

Hold only the folders you work in. A vault is a Merkle tree, so a clone needs the
folders on the way down to yours plus your folder; every other folder is carried by its
id and never downloaded. `commit`, `push` and `pull` work normally inside the held
folders, writes outside them are refused with the path named, and two scoped clones in
different folders can never conflict with each other. Repeat `--path` for several
folders; add one later with `sgit fetch <folder>`.

```
$ sgit clone --path mail/crm.example <vault-key> workspace
```

On the example vault: 14 s and 3.2 MB for a 365-file folder, against 80 s and 173 MB for
the whole vault. Guide: *Partial clones*.

### Shallow clones: `sgit clone --depth N`

Fetch only the newest N commits (`--depth 1` is HEAD only). Commit, push, pull and
status work normally; history commands stop at the boundary and say so. `sgit fetch
--unshallow` fetches the rest later. Combine with `--path`.

### `sgit fetch <folder>` widens a scoped clone; `sgit fetch --unshallow` deepens a shallow one

Widening fetches the folder from HEAD and writes its files. It never overwrites a file
already on disk whose bytes differ from the vault: it refuses and names the file.

### Whole-vault commands refuse on a partial clone

`sgit check fsck`, `sgit dev dump`, `sgit publish` and `sgit vault move` need the whole vault.
On a scoped or shallow clone they stop and say how to widen it. Any other command that
meets an object the clone never fetched explains the scope instead of reporting corruption.

## Faster

### Full clones download the store in one parallel sweep (0.18.0)

The three clone phases used to discover objects one dependency level at a time: a commit's
parents are inside its ciphertext, a tree's children inside its, so a 600-commit history
was 300 serial round trips before the first tree was known. A full clone now lists the
store once and downloads everything not yet local in 16 parallel batches, verified before
it is written; the walks then run against a store that already has everything. On the
example vault: 170 s to 80 s. The commit walk went from 57 s to 0.2 s and the file download
from about 48 s to under a second; the tree phase is now 13 s of local decryption instead
of 60 s of download. Sparse clones skip the sweep. A host that cannot list the
store only loses the speed-up.

Parallel reads went from 8 to 16 workers (about twice the throughput on the live API), and
an HTTP 429 from the server is retried with back-off like a 5xx, so a burst of ten agents
cloning at once cannot fail a clone on a throttle.

### The tree walk requests each shared sub-tree once (0.17.0)

Every history shares most of its folders between commits. The walk queued a sub-tree once
per commit that referenced it and fetched 50 ids at a time, serially. On a 170-commit vault
that was 10,098 requests' worth for 2,236 unique trees: 377 s. Now 24 s. Clone and pull
both use the walk.

### One connection per host (0.17.0)

Every API call used to open a new TLS connection. Calls now go through a small connection
pool (standard library only, no new dependency) keyed by host and proxy settings, shared
by the parallel fetchers, honouring `HTTP(S)_PROXY` and `NO_PROXY`. The serial commit walk
roughly halved. Safety rules: a failure mid-response discards the connection; a stale
connection is retried once for reads only, never for a write; redirects are not followed,
so the token headers can never be sent to another host. `SGIT_HTTP_NO_KEEPALIVE=1`
restores one connection per request.

## Fixed

### `sgit pull` no longer discards uncommitted edits

Reported three times by an agent team sharing one vault. A pull wrote the whole incoming
tree over the working copy, so an uncommitted edit to a tracked file was replaced by the
committed version even when the incoming commits never touched that file, and `sgit
status` then said "fully in sync". Pull now follows git's rules, before writing anything:

- a changed file the incoming commits do not touch is kept, and listed as
  `Kept … (yours, uncommitted)`;
- a changed, locally deleted, or untracked colliding file that the incoming commits *do*
  touch refuses the pull, names each file, and changes nothing. Commit it, or
  `sgit vault stash` it, and pull again.

### `sgit status` counts ahead and behind for real

When the remote had moved, status counted every local commit as "ahead" (a fresh clone one
commit behind said `diverged: 200 ahead, 1 behind — push`). It now fetches the missing
commit objects (one small object per new commit, up to 50) and reports real counts. Offline
or past 50, `behind` is shown as a lower bound (`50+`) rather than invented.

### `sgit push` uploads every pushed commit's files

Push uploaded only the files in the final tree, while uploading the trees of every pushed
commit. A file created and then changed before one push left its first version referenced
on the server but never sent (41 such objects on the example vault after four days). Every
pushed commit's files now go up. Objects already missing can only be recovered from the
clones that created them: `sgit check upload-objects` on the agent's clone.

### `sgit push --branch-only` re-sent its whole history each time, and its ref write failed after a commit

It now sends only what the server does not have, and the compare-and-swap on the branch ref
matches the server's copy instead of the local file.

### `sgit clone-branch`, `clone-headless`, `clone-range` could not reach the server

They built an API client with no base URL and failed instantly. They resolve the saved
token, `--base-url` / `--remote` and `--transport` like `sgit clone`.

### Every clone left an empty temporary directory behind

One `sgit-clone-*` directory under the system temp dir per clone, for every clone ever
made. Removed on success and failure.

## Hardening (no vulnerability was found; three checks were tightened)

- A batch read keeps only the objects it asked for. The server's answer names where each
  object is written on disk, so an answer naming an object that was not requested is ignored.
- Downloaded bytes are written only to leaves of the encrypted store, never to the local
  config, the key file, or a working-copy path, whatever name the server gives them.
- A pull lets an untracked local file collide with an incoming one only when the
  *decrypted* incoming file proves the content identical; the commit's own content hash is
  the committer's claim and is not trusted for that decision.

## Unchanged

Full clones are untouched by the partial-clone work: no scope, no boundary, the same object
set (checked on the example vault: the same 18,720 objects and the same `fsck` result
before and after). The pull guard is the only visible behaviour change in an existing
command, and it only acts when a pull would have overwritten your work.
