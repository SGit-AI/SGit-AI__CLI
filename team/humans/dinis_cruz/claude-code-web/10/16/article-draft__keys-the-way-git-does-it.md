# Keys the way git does them, and the way a vault could: what SSH actually checks, what a read key actually prevents, and a door per member

*Draft for the newsroom, 16 Oct 2026. From a voice memo of Dinis's; facts checked against the CLI at
`dev` 37218af, the sgit.ai pages linked, RFC 0001 and the passkey article. Nothing here is built
beyond what is named as built.*

## In short

- **Git authenticates you once and then checks nothing.** An SSH key or an HTTPS token gets you
  to the server; after that a push is file copying. Who wrote a commit is a string in the commit
  unless it is signed. A clone is unrestricted by design.
- **sgit is the same shape with the names changed.** The write key is the push credential, the
  read key is a deploy key, the access token is the account, and the server compares hashes the
  way GitHub checks an SSH fingerprint. A read-only clone cannot push, and it cannot stop you
  editing files locally, exactly like a git clone.
- **Where sgit already goes further:** every commit is signed by the clone's own key, a vault can
  require signatures, and the named branch can only move forward. Where it does not yet: the
  server cannot tell one writer from another, because every writer presents the same key.
- **The "GitHub" version of sgit is RFC 0001's Design 1.** A write key pair per writer, a writer
  set the server trusts, signed heads. That is what it would take to copy git's model properly.
- **The PKI version is a door per member.** One small object per member, holding the vault's data
  key sealed to that member's public key. Join by adding one, leave by deleting one, and never
  write the key to disk. The pieces exist (sealing, the door, `bare/keys`); the one new thing is
  objects that have no history.
- **Revocation is bounded, as in git.** Deleting a door stops the next open; it does not take
  back what was fetched. For that, rotate, as every sgit page already says.

## What git actually checks

Git over SSH is two systems glued together. SSH authenticates: your private key proves you hold
the key the server lists in `authorized_keys`, and on GitHub that key is tied to an account.
Then `git-receive-pack` runs on the server with whatever rights that account has on the
repository, and the push is a transfer of objects plus an update of refs. Nothing in that
transfer says who made the commits. A commit's author and committer are strings you typed into
your config; git will happily push a commit that says it was written by anyone. The only thing
that binds a commit to a person is a signature (GPG, S/MIME, or since git 2.34 an SSH key), and
the only thing that makes signatures matter is a server rule that requires them.

A clone is a complete copy, and git does nothing to restrict what you do with it. "Read-only
access" in git means the server will not accept your push; it never meant the files on your
disk were protected. A deploy key is an SSH key tied to one repository, read-only by default:
it gets you the clone and nothing else.

So git's model, written out: **authentication at the door, authorisation by account on the
server, nothing on the objects themselves unless signed, and a local copy that is yours.**

## sgit, with the names changed

sgit arrives at the same place from the encryption side. A vault key is `passphrase:vault_id`,
and from the passphrase two keys are derived: a **read key**, which encrypts every object,
and a **write key**, which the server stores as a SHA-256 hash and compares on every write
(`x-sgraph-vault-write-key`). A third thing, the **access token**, is the account: on the shared
host it gates writes; on a single-key self-hosted server it gates everything.

| git + GitHub | sgit | Where it is checked |
|---|---|---|
| SSH key / HTTPS token | access token | server, hash comparison |
| push permission on the repo | write key | server, hash comparison |
| deploy key (read-only) | read key | nowhere: the ciphertext is the protection, and reads on the shared host are open |
| `git clone` | `sgit clone` with the read key or the vault key | a clone is yours; the read key does not stop local edits, and it cannot |
| `git push` | `sgit push`: batch write + compare-and-swap on the ref | server: write-key hash, then CAS |
| commit author string | commit author key id | client: every commit is signed by the clone's ECDSA key; `sgit check verify` classifies each one |
| branch protection "require signed commits" | vault feature `signatures-required` | client, on pull: the first unsigned incoming commit is refused |
| branch protection "no force push" | the named branch only moves forward (`last_remote_head`) | client: a rewind is refused unless `--accept-rewind` |
| `git filter-repo` + force push | `history reset` + `push --force`; old objects stay until deleted | the host keeps what it was given; readers keep what they fetched |

Read the table down the last column and the difference with git is visible: **git checks on the
server, sgit checks on the client, and the server can only ever check a shared hash.** Every
writer of a vault presents the same write key, so the server cannot tell them apart, and a reader
cannot tell whether a head was written by a writer or by the host. RFC 0001 calls this the honest
problem, and it is the one thing git's server has that sgit's does not.

The read-key-does-not-prevent-local-changes observation is therefore not a gap. It is git's
rule. What stops a reader's edits from going anywhere is the push, which needs the write key,
and what will stop a *writer* from pretending to be another writer is a signature the server can
check, which is the next section.

## The GitHub version: a key per writer

To copy git's model properly, a vault needs what GitHub has and the shared write key cannot
give: a per-writer identity the server verifies. RFC 0001's Design 1 is that, already designed:

- two key pairs, neither derivable from the other: a **read pair** (X25519) that the data key is
  sealed to, and a **write pair** (Ed25519) that signs the refs and the branch index;
- the server accepts a write only when the head it moves is signed by a key in the vault's
  **writer set**, instead of comparing a hash;
- a reader holds the read private key and the write public key, so it can read and verify and
  cannot write; a writer holds both private halves; a host holds ciphertext and the write public
  key and can refuse unsigned writes but not forge one;
- a **write-only depositor** becomes possible, which git cannot express at all: a key that can
  add to an inbox branch and read nothing.

In git terms: the writer set is `authorized_keys`, a signed head is a signed push, and the
depositor is a contributor who can open a pull request into a repository they cannot clone. The
RFC's effort estimate for the first three phases, the ones that give "a reader cannot write and a
host cannot forge", is about three weeks of client work plus the server accepting signed writes.

An SSH key fits this directly. An Ed25519 SSH key signs; it converts to X25519 for sealing; an
RSA SSH key seals with RSA-OAEP, which `sgit pki encrypt` already does. The RFC lists "an ssh
key" as one of the places a private key can live. Nothing stops `sgit` reading
`~/.ssh/id_ed25519` or asking an SSH agent to sign, the way git does for signed commits today.
That is the smallest version of "the public key becomes the write key": not a read key, a
**write identity**, which is what SSH keys are in git too.

## The PKI version: a door per member

The second thing in the memo is not git at all. It is: let a vault's members get in with their
own key pairs, and let membership be a file. Three published pieces say how, and nobody has yet
put them together:

1. **Sealing.** `sgit pki encrypt --recipient` wraps an AES key to an RSA-4096 public key; RFC
   0001 Design 2 seals a file key to named recipients (age-style). Either seals a 32-byte data
   key to a member.
2. **The door.** The passkey article (11 Oct) built and tested exactly this shape on a real
   vault server: a vault whose address and key are derived from something only the member has
   (there, the passkey's PRF bytes), holding **one file**, the master's key encrypted under the
   door's key; "a door is retired by deleting its one file, never by destroying its address".
3. **Where public keys live.** `bare/keys/key-rnd-imm-*` already holds public keys as immutable
   objects, "public by construction".

Put together, membership is a folder of doors inside the vault:

```
members/
  <fingerprint-of-alice-pub>   = data key, sealed to alice's public key
  <fingerprint-of-agent-7-pub> = data key, sealed to agent 7's public key
```

- **Open:** fetch your door by your fingerprint, unwrap the data key with your private key, hold
  it in memory. Nothing under `.sg_vault/local/` ever holds the key: that is the "never stored
  locally" the memo asks for, and it is what the passkey page already does in the browser
  ("Where is the door key stored? Nowhere.").
- **Join:** a writer adds a door. Sealing needs only the public key, so a writer can admit a
  member it has never met, from a key in a directory or a signed registry (the registry handover
  in *Where the vault keys live* is already PKI in daily use).
- **Leave:** delete the door. From the next open, that member finds nothing.
- **Write access:** a member's door can hold the write identity too, which under Design 1 is a
  place in the writer set rather than a shared secret.

This is also the "messages for you" idea in the memo: a folder per public key, with things only
that key can open, is a door that holds a message instead of a key. The vault-messaging page's
append lanes are the write-only half of the same thing.

## The catch is history, and the three ways out

Everything above has one problem, and the passkey article states it plainly: "Vaults keep their
versions, so an entry deleted from A is still in A's past for anyone who can open A." A door
deleted in a commit is a door that every later clone still carries in history. The memo's
question is the right one: can some files exist only at the current version?

Three ways to get that, from least to most new:

1. **Doors as mutable objects outside the tree.** sgit already has a class of objects with no
   history by construction: refs (`ref-pid-muw-*`), the branch index, and the cache layer's value
   and pointer objects, which are written directly to a path-derived id, never through the
   content-addressed store, with a random IV, and deleted with the ordinary delete route. A door
   is exactly that: a mutable object at an id derived from the member's fingerprint, outside the
   Merkle tree, so no commit ever points at it and deleting it leaves nothing behind on the
   server. The code pattern exists (contract 08/12, rule D10); what is missing is the member
   object kind and the open command.
2. **A branch with a `no-history` feature.** The branch index already carries features
   (`signatures-required`). A branch flagged `no-history` would move its ref without keeping
   parents, and the client would delete the superseded objects on push. Easier to explain,
   harder to make safe: every client has to honour it, and an old client would keep the parents.
3. **A separate tiny vault per membership**, the way the passkey design keeps doors apart from
   the master. Works today with no new code; costs a vault id per door and a second key to
   manage.

The first is the one to take: it is the primitive the code already has, and it keeps the vault's
own history intact and signed, which the memo also wants. A membership *log* can still be kept,
signed, in the tree, as long as it holds fingerprints and dates and never a key.

## What revocation can and cannot do

The same as git, and every sgit page already says it: deleting a door, or a deploy key, stops
the next access. It does not take back a copy. A member who already fetched the objects keeps
them (TM-R12, `docs/credentials`: "revocation is not retroactive"). A member removed for cause
therefore means the RFC's rotation step: a new data key, sealed to the remaining members, and
the content re-encrypted for future commits; today `sgit vault rekey` does that at the cost of a
new vault id. A door deleted from a server that runs on a copy-on-write filesystem or keeps
backups can also survive in those, which is the same caution the secure-unlink work recorded.
None of that is a reason not to have doors. It is the reason the door is the *authorisation*
layer and rotation stays the *confidentiality* layer, which is also how the memo describes it.

## What this does not claim

- Nothing in the member-door pattern is built. Sealing, signing, `bare/keys`, mutable objects
  and the door test exist; the member object kind, the open command and signed writes do not.
- SSH keys are not accepted by `sgit` today; `sgit pki` makes its own RSA-4096 and ECDSA P-256
  pairs.
- A vault cannot yet tell its writers apart on the server. That is RFC 0001's Design 1, estimated,
  not scheduled.
