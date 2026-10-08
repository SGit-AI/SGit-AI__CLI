# History integrity: the format gate, verifying signatures, and rewinds

*For sgit-ai 0.19.0 or newer. `sgit version` to check, `sgit update` to upgrade.*

A vault is a Merkle tree of encrypted objects: every file, folder and commit is stored under
the hash of its ciphertext, every commit names its parents and its root folder by those hashes,
and every object and ref is AES-256-GCM encrypted under a key the server never holds. So the
server cannot alter a byte of history without it failing to decrypt, and `sgit check fsck`
finds anything missing or corrupt. 0.19.0 adds what that model did not give you: who may open
a vault, 128-bit addresses, a branch pointer that only moves forward, and signatures you can
check. All of it is per vault and off by default.

## The format gate: `sgit vault format`

Every vault has a gate in its branch index. A vault that has never been touched by this
command reads as format 1 with no minimum client, which is exactly the 0.18.0 behaviour.

```
$ sgit vault format
  Format:      1  (new objects get 12-hex ids)
  Min client:  none   (this client: v0.19.0)
  Features:    none
```

The owner raises it, from any clone with the vault key:

```
$ sgit vault format --set 2 --min-client 0.19.0
Vault format updated and written to the server.
  Format:      2  (new objects get 32-hex ids)
  Min client:  0.19.0   (this client: v0.19.0)
  Features:    ids-128
```

- **`--set 2`**: from now on, every new object this vault stores gets a 128-bit content address
  (`obj-cas-imm-` plus 32 hex characters) instead of 48 bits. Existing objects keep their ids
  and still verify; a clone holds both. Nothing is re-encrypted and no `vault move` is needed.
  A format cannot go back down.
- **`--min-client X.Y.Z`**: a client older than this refuses the vault and says so:
  `this vault needs sgit-ai >= 0.19.0 and this is 0.18.0: run sgit update, then try again`.
  You cannot set a minimum you do not meet yourself. Compared on the three numbers; a dev
  build is never refused.
- **`--feature NAME` / `--remove-feature NAME`**: policies. `signatures-required` is the one
  that exists today (below).

**Why 128 bits.** A 48-bit address is plenty against the server, which cannot produce
decryptable bytes at all. It is not plenty against someone who holds the vault key and wants
to swap an object for another with the same address: that is 2⁴⁸ hashes, hours on a GPU. On a
raised vault it is 2¹²⁸. Cost on a 674-commit, 19,780-object vault: 1.5 % more bytes, no more
compute.

**The one thing to plan.** A CLI older than 0.19.0 does not know the gate exists. On an
un-raised vault it works as always. On a vault raised to format 2 it fails on the first 32-hex
id it meets, and because it cannot know why, it blames the data, not itself:

```
$ sgit clone <vault-key> work          # 0.18.0, fresh clone
error: integrity check refused vault data — clone needs object obj-cas-imm-…, which was refused
by the content-address check … the host served corrupt or substituted content: do not trust
this source.

$ sgit pull                            # 0.18.0, existing clone
error: missing file — object obj-cas-imm-… is not in the local store
  hint: try "sgit check fsck ." to check and repair
```

Both hints are wrong for this case: do not run `vault move`, do not run `fsck --repair`. The
fix is `sgit update`. So: upgrade the agents first, raise the vault second; `sgit vault format
--set 2` prints this warning. The web UI reads raised vaults today; writing 32-hex ids is
queued on its side, and until then its new objects get 48-bit ids, which the vault accepts.

## The branch index is shared, and now repaired

The branch index lists every clone branch, maps each to its signing key, and carries the
gate. The web UI currently overwrites it with a single entry on every push, which used to lose
the other entries for good. From 0.19.0 the CLI treats the index as a shared document: `pull`
reads the remote copy, merges it with the local one (every branch, the stronger gate) and
writes the merge back with compare-and-swap; `push` registers a clone branch the same way.

```
$ sgit pull
  ▸ Branch index: restored 2 entr(y/ies) the remote copy had lost
```

You do not have to do anything; it is the reason a raised gate survives a web push.

## Rewinds: the named branch only moves forward

The named branch is a pointer. The server, or anyone with the key running `sgit push
--force`, can point it at an older or unrelated commit. Each clone now remembers the last
remote head it accepted, and a new head that does not descend from it is a **rewind**.

```
$ sgit status
  Remote: the named branch was REWOUND or rewritten on the server (it no longer descends from obj-cas-imm-…)
          if that was a deliberate `sgit push --force`, run: sgit pull --accept-rewind
          otherwise treat it as tampering and check with the vault owner

$ sgit pull
error: the remote named branch was rewound or rewritten: it pointed at obj-cas-imm-… the last
time this clone saw it and now points at obj-cas-imm-…, which does not descend from it. If this
was a deliberate `sgit push --force`, run `sgit pull --accept-rewind`; otherwise treat it as
tampering and check with the vault owner. Nothing was changed.
```

What to do:

- **You, or a teammate, force-pushed on purpose** (after `sgit history reset`, say): every other
  clone runs `sgit pull --accept-rewind` once. The clone that pushed needs nothing.
- **Nobody did**: do not accept it. Your clone still holds the newer history; `sgit push` would
  put it back. Tell the vault owner.
- **The web UI pushed**: today the web UI's push does not compare before writing, so two people
  saving at the same moment can drop one person's commits. The CLI will report that as a rewind,
  and it is right to. The web UI team is moving to compare-and-swap.

Normal forward moves, a clone's first pull, and a fresh `sgit init` over an existing vault id are
never rewinds.

## Signatures: `sgit check verify`

Every CLI commit is signed with the clone branch's ECDSA P-256 key. 0.19.0 checks them.

```
$ sgit check verify
Checked 674 commit(s): 247 verified, 0 bad, 112 unsigned, 315 without a known key, 0 missing
```

| Status | Meaning |
|---|---|
| verified | the signature checks under the key the commit names, or the key the branch index maps its branch to |
| bad | the signature does not check: the commit was altered after signing. `fsck` fails on this |
| unsigned | written without a key: the web UI, or a clone with no local signing key |
| without a known key | signed, but neither the commit nor the index says by which key. Commits from before 0.19.0 whose branch has left the index |

New commits carry their key id, so from 0.19.0 on "without a known key" stops growing. `sgit
check fsck` prints the same summary.

**Requiring signatures.** `sgit vault format --feature signatures-required` makes every
`pull` refuse the first incoming commit that is not *verified*, by name, before merging:

```
error: this vault requires signed commits and incoming commit obj-cas-imm-… is unsigned; the
pull was refused before anything was merged. Ask the vault owner, or relax the policy with
`sgit vault format --remove-feature signatures-required`.
```

Turn it on only for vaults written by 0.19.0 CLIs with their keys: today's web UI does not sign,
and history from before 0.19.0 is not retroactively verifiable. `sgit migrate apply` refuses on
a vault with signed commits (a migration rewrites history) unless `--force`.

## A checklist for raising a vault

1. Every agent that writes to it is on 0.19.0 (`sgit version`).
2. `sgit check fsck` is clean and `sgit check verify` shows no *bad* commits.
3. `sgit vault format --set 2 --min-client 0.19.0`.
4. Each agent's next `sgit pull` picks the gate up; nothing else to do.
5. `signatures-required` only once no web-UI writes are expected on the vault.
