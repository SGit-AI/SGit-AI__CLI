# sgit-ai release notes — 0.19.0

*7 October 2026, on PyPI. Upgrade: `sgit update`. Check: `sgit version`.*

0.18.0 made a large shared vault fast to clone and safe to pull. 0.19.0 makes its history
verifiable: a vault can say which client may touch it, new objects can get 128-bit content
addresses, the branch index survives being overwritten, a rolled-back branch is refused rather
than silently taken, and commit signatures can be checked and required. **Nothing changes for an
existing vault until its owner raises it**; every default is the 0.18.0 behaviour.

## What changed, in one table

| Area | 0.18.0 | 0.19.0 |
|---|---|---|
| Object ids | 48-bit content addresses | 48-bit by default; **128-bit for new objects on a vault raised to format 2**, old objects untouched, no `vault move` |
| Which client may open a vault | any | the vault can set a minimum; older clients are refused by name: `this vault needs sgit-ai >= 0.19.0 and this is 0.18.0: run sgit update` |
| The branch index when the web UI pushes | its other entries were lost | the next CLI `pull` restores them, and CLI writes use compare-and-swap |
| A rolled-back or rewritten branch on the server | taken silently | `status` says `REWOUND`; `pull` refuses; `pull --accept-rewind` takes it after a deliberate `push --force` |
| Commit signatures | written, never checked | `sgit check verify`; a summary in `fsck`; per-vault `signatures-required` refuses unverified incoming commits |
| `sgit check fsck` on a 674-commit vault | 270 s | 12 s, same findings |
| `pull` after `status` on a clone several commits behind | left intermediate trees unfetched | fetches them |

## New

### `sgit vault format`: the format gate

```
$ sgit vault format
  Format:      1  (new objects get 12-hex ids)
  Min client:  none   (this client: v0.19.0)
  Features:    none

$ sgit vault format --set 2 --min-client 0.19.0
Vault format updated and written to the server.
  Format:      2  (new objects get 32-hex ids)
  Min client:  0.19.0   (this client: v0.19.0)
  Features:    ids-128
```

The gate lives in the vault's encrypted branch index and is read by every command. Absent, it
means format 1 and no minimum: every vault that exists today. A format can only go up; a
minimum you do not meet yourself is refused ("you would lock yourself out"). Raising to format
2 changes nothing already stored: new commits, trees and files get 128-bit ids, existing ones
keep theirs, both verify, and a clone of the vault holds both. Measured cost on the 674-commit
example vault: +1.5 % of bytes, no extra compute.

### `sgit check verify`: signatures

```
$ sgit check verify
Checked 674 commit(s): 247 verified, 0 bad, 112 unsigned, 315 without a known key, 0 missing
```

Every CLI commit since the first release carries an ECDSA signature; 0.19.0 is the first
release that checks it. New commits also carry the id of their signing key, so verification no
longer depends on the branch index still listing the branch that made them. On a vault that
predates 0.19.0 expect "without a known key" for commits whose branch left the index, and
"unsigned" for commits made by the web UI or by a clone without a local key. `fsck` prints the
same summary and fails on a *bad* signature. `sgit vault format --feature signatures-required`
makes `pull` refuse, by name and before merging, any incoming commit that does not verify.

### Rewinds

```
$ sgit status
  Remote: the named branch was REWOUND or rewritten on the server (it no longer descends from obj-cas-imm-…)
          if that was a deliberate `sgit push --force`, run: sgit pull --accept-rewind
          otherwise treat it as tampering and check with the vault owner
```

Each clone remembers the last remote head it accepted. A remote head that does not descend
from it is a rewind: a rollback, a rewritten history, or a host replaying an old ref. `pull`
refuses with the same message and changes nothing; `pull --accept-rewind` takes it. A vault
created fresh over an existing id, or any normal forward move, is never a rewind.

## Fixed

- **`pull` after `status`** left the trees of commits that `status` had already fetched
  unfetched (since 0.18.0): `fsck` showed missing trees on a clone four commits behind. Fixed.
- **`sgit check fsck` re-walked every tree once per commit.** 282,202 tree checks for 8,589
  trees, 270 s on the example vault; now 12 s with identical findings.
- **Every clone left an empty temp directory behind** (`sgit-clone-*`): removed.
- The "incompatible vault data" hint now says to run `sgit update` first.
- Commit signatures use a canonical, cross-client signing input (RFC 8785 over the stored
  commit JSON minus `signature`); older signatures still verify. Shared test vectors ship in
  the repo for the web UI.

## Compatibility, in two lines

A vault nobody raises behaves exactly as in 0.18.0 for every client, including older CLIs and
the web UI. A vault raised to format 2 refuses CLIs that know the gate and are too old by
name, and crashes CLIs older than 0.19.0 with a validation error, so raise a vault only once
its agents are on 0.19.0. The web UI reads raised vaults; writing 32-hex ids, signing commits
and keeping the branch index are queued on its side.

## Verified against the live service

On a throwaway vault on the dev API: the gate written with compare-and-swap; 44-character ids
accepted on write, read, batch read and list; a mixed-id vault cloned in 2.7 s with a clean
`fsck`; a server-side rollback reported, refused, then accepted; a web-UI-style index
overwrite repaired by the next pull. The 674-commit example vault clones scoped and shallow in
15 s, unchanged.
