# One vault, ten agents, 35,000 objects: what sgit does when the repository is big and the clients are many

*Draft for the newsroom, 16 Oct 2026. Companion to "Scion and sgit" (No. 141). Numbers from the
response note in this folder; every one was measured on the live vault from a cloud sandbox, so a
plain connection does better. Placeholders in [brackets] are filled from the measurement table.*

Anthropic's post on Scion makes one observation that survives contact with any version control
system: when the clients are agents, they are always online, there are a great many of them, and
the expensive thing is moving bytes nobody needs. Scion answers with a server that does the work
and three tiers of cache in front of it. This is what sgit does with the opposite constraint, a
server that cannot read a byte, on the one vault we have that is big by our standards and busy
every day.

## The vault

The comms vault is where ten agents and one human keep their mail, briefs, runs and analysis. On
16 October it had 1,295 commits, 68 of them from the last two days, 5,101 files, 16,315 blobs and
16,391 trees: about 35,000 encrypted objects, 527 MB when every one of them is on disk. Its
biggest folder is `mail` (3,200 files, 68 MB); `docs` has twelve files. It lives on the hosted
server, S3 behind CloudFront, and the agents reach it through the CLI.

## What an agent fetches

Nobody working in this vault needs all of it, and the point of the design is that they do not
have to take it.

| What was asked for | Time | Objects | On disk |
|---|---|---|---|
| Everything (full clone, 14 Oct) | 3½ min | 35,423 | 527 MB |
| The whole tree, one commit of history (`--depth 1`) | [depth1] | | |
| One folder, one commit (`--path security --depth 1`, 130 files) | [path-security-depth1] | | |
| One folder, all its history (`--path security`) | 227 s | 3,364 | 64 MB |
| The biggest folder (`--path mail`, 3,200 files) | [path-mail] | | |
| Structure only (`--sparse`), then one file | [sparse] + [sparse-fetch] | | |
| A headless clone, then one file (`clone-headless` + `cat`) | [headless] + [headless-cat] | | |
| Widening a scoped clone by a folder (`fetch security`) | [widen] | | |
| A pull when nothing changed | [pull] | | |

Two things stand out. A clone that carries a depth costs seconds and megabytes however large the
vault is, because it asks for the spine of trees down to its folder and the blobs under it, and
nothing else; this is the pattern the documentation gives agents, and the one the agents use. And
a clone that carries the whole history of a folder pays for the history, not the folder: 227
seconds for 130 files, almost all of it walking 1,295 commits one request at a time, because a
partial clone cannot do what a full clone does (list the store once and fetch everything in bulk)
without holding objects it must not hold. That is the one real edge in the numbers, and the fix
is a small encrypted object that records the commit chain, so a clone can fetch the chain in 26
batched requests instead of discovering it. Until it ships, the depth flag is the answer.

## What an agent does every session

The command an agent runs most is not clone but pull: come back to the vault, take what changed,
go on. Until 14 October that was the slow path on this vault, one request per commit and one per
blob, and an agent a day behind was waiting most of an hour. It now fetches the whole head into an
empty store in 186 seconds, blobs in batches of fifty with sixteen requests in flight, and a pull
that is a few commits behind takes the few requests it needs. The agents reported the slowness;
the vault they reported it on is the one it was fixed and measured on.

## One file, four requests

The question Scion's API answers for jobs that never check out is "give me this file at this
commit". In sgit that is four GETs computed from the read key: the ref, the commit, the trees on
the path, the blob. No listing, no index, no account; the server could be GitHub Pages, and on
sgit.ai it sometimes is. The site's documentation pages are a vault read exactly this way in the
browser: a cold load fetches 18 objects, the next load fetches one 69-byte ref, and a load inside
the two-minute freshness window fetches nothing, because every object but the ref is named by the
hash of its ciphertext and can be kept for ever by whoever fetched it. The CLI does the same from
a sparse or headless clone, with one caveat the table shows: on a long history it walks the
commits first, which is the same edge as above with the same fix.

## Where the server is, and what it is

The hosted server is S3 behind a CDN and a small API that accepts batches of fifty objects, moves
refs by compare-and-swap, and can read none of what it stores. The same image runs on a laptop
(`sgit serve`, in Docker, Podman, Apple's container runtime, or as a plain Python process), in a
CI job as a sidecar, on a Mac mini next to the agents, in Kubernetes, or not at all: a published
vault is plain files on any host that answers a GET. Ten scoped clones at once took 1.9 seconds on
a single server process; ten full clones queued to 21 seconds, which is the single process, not
the protocol, and the deployment note says so.

## What this does not claim

- Not proven at Scion's scale. 35,000 objects, 1,295 commits and ten agents is the largest vault we
  run; Scion's monorepo has 100 GB of history and 30,000 merges a day.
- No blame or bisect. Path history, signed commits, signed tags and verification exist; blame is a
  fold over path history that nobody has written yet.
- A partial clone of a long history is slow without a depth, today. The fix is designed, not
  shipped.
- One run each, from a sandbox whose every request goes through a proxy.
