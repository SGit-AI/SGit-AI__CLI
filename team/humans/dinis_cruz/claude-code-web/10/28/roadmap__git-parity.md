# Roadmap: feature parity with Git, then more on top (28 Oct 2026)

**The message:** sgit does just about everything Git does, and then more on top. Git, the client, is the bar.
GitHub's features (accounts, verified badges, protected branches, review, CI) belong to a future server product
("SGitHub"), not to the CLI.

**Follows:** `review__article-what-sgit-does-that-git-does-not.md` (same folder). That review mixed Git and GitHub
features, and proposed an owner-signed signer registry for TM-R01. Under this scope, that registry moves to
SGitHub (section 4). Signing becomes what Git does: sign with the key you already have, and let each verifier
decide whom to trust.

**Extension rule:** every new feature is off by default and changes nothing for vaults and clients that don't use
it. It is on through a setting, either local or a vault feature (`sgit vault format --feature …`, the mechanism
`packs` and `signatures-required` already use). Only a feature that old clients would get *wrong* sets a minimum
client version.

---

## 1. Already at parity

These Git commands already have an sgit equivalent.

**Working with a clone**

| Git | sgit |
|---|---|
| `clone`, `--depth`, `fetch --unshallow` | `clone`, `--depth N`, `fetch --unshallow` |
| partial clone + `sparse-checkout` | `clone --path` (repeatable), `fetch <folder>` to widen, `clone --sparse` |
| `clone --no-checkout`, `--bare` | `clone --no-checkout`, `checkout <paths>` / `--since-pull` / `--changed-since` / `--all`; `clone --bare` |
| `status`, `commit`, `commit --amend` | `status`, `commit`, `commit --amend` |
| `push`, `pull`, `fetch`, `push --force-with-lease` | the same |
| `remote` | `remote` |
| `.gitignore` | `.gitignore` (read as is) |
| `stash` | `vault stash` |

**Branches, tags and merges**

| Git | sgit |
|---|---|
| `branch`, `switch`, `checkout <commit>` | `branch new/list/switch/rename/checkout` |
| `merge` | `branch merge` (whole-file: see 2.1) |
| `merge --abort` | `merge-abort` |
| conflict resolution | `resolve` |
| `tag -s` (signed), `tag -v` | `vault tag create/list/show/delete` (signed, verified) |

**History**

| Git | sgit |
|---|---|
| `log`, `--grep`, `--since`, `--until`, `--author`, `--stat`, `-p`, `-- <file>`, `--graph`, `--oneline` | `history log` with the same filters |
| `diff`, `show` | `history diff`, `history show` |
| `reflog` | `history reflog` |
| `reset --hard` | `history reset` |
| `revert` | `history revert --as-commit` |
| (no single command) | `history undo` |
| `HEAD~2`, `HEAD^2`, short ids, tag names | the same revision syntax |

**Integrity and plumbing**

| Git | sgit |
|---|---|
| `fsck` | `check fsck` |
| `verify-commit` (one commit) | `check verify` (every commit to HEAD) |
| `commit-graph`, pack indexes | index packs (0.26.0) |
| packs, kept packs (`fetch.unpackLimit`) | pack vaults, `clone --pack-store` |
| `hash-object` / `commit-tree` plumbing | `write --file … --also … --push --json` (atomic commit of named files) |
| `bundle` / `file://` remotes | `--transport local`, `vault backup` / `restore` |
| dumb HTTP | `--transport static` |

---

## 2. Gaps: Git has it, sgit doesn't yet (the CLI roadmap)

All of these run on the client in Git too. None needs a server change.

### Priority 1

| # | Feature | Git | sgit plan | Size | Gate? |
|---|---|---|---|---|---|
| 2.1 | **Line-level three-way merge** | `ort` merge, conflict markers, `merge-file` | One function changes: `Vault__Merge.three_way_merge`. Every merge (pull, `branch merge`, `revert`, the rewind re-apply) goes through it. For a text file both sides changed: decrypt base/ours/theirs, run a three-way line merge, and store the result as a new blob. A clean merge commits as today; rough edges get `<<<<<<<` markers in the file instead of a `.conflict` copy. Binary files (a NUL byte) and files over a size cap stay whole-file. Tests use `git merge-file -p` as the oracle. **Opt-in; whole-file with `.conflict` stays the default** (the web UI works that way). Chosen per command (`--merge lines` / `--merge files` on `pull` and `branch merge`) or per clone (a `merge_style` field in `.sg_vault/local/config.json`, never synced, like Git's `.git/config`). A team-wide per-file rule, if ever wanted, is a committed attributes file (Git's `.gitattributes`), versioned like the `.gitignore` sgit already reads. | 2–3 days | No: a merge result is an ordinary commit |
| 2.2 | **Sign with your own key** (SSH or GPG) **and verify against your allowed-signers file** | `user.signingkey`, `gpg.format`, `commit.gpgSign`, `tag.gpgSign`, `gpg.ssh.allowedSignersFile`, `log --show-signature`, `verify-commit`, `verify-tag` | Section 3 | 3–4 days | No (section 3) |
| 2.3 | **Commit some files, not all** | `commit <paths>`, `add -p` + `commit` | `sgit commit <paths>` reuses `write`'s code (only the named paths' folders are rebuilt). `commit -p` picks hunks over `history diff`. A persistent staging area (`sgit add`) is a separate decision; pathspec plus `-p` covers most use. | 1 day / 2 days | No |

### Priority 2

| # | Feature | Git | sgit plan | Size |
|---|---|---|---|---|
| 2.4 | Rename detection | `diff -M`, `log --follow`, renames in merge | Exact renames: the same plaintext `content_hash` (already in tree entries) on a deleted and an added path. Similar renames: Git's similarity score, within a cap. | 1–2 days |
| 2.5 | `blame` | `blame` | `history blame <path>`: walk the file's commits (the index pack's file → commits member makes it cheap) with a line diff per step. Blobs are fetched on demand; it stops at a shallow boundary. | 2 days |
| 2.6 | `bisect` | `bisect start/good/bad/run` | `history bisect …`. State in `.sg_vault/local/`; the midpoint comes from generation numbers (index packs carry them). | 1–2 days |
| 2.7 | `grep`, pickaxe | `grep`, `log -S` / `-G` | `sgit grep <regex>` over HEAD or `--rev C` (decrypt locally); `history log -S/-G`. | 1–2 days |
| 2.8 | `cherry-pick` | `cherry-pick` | `history cherry-pick <commit>`: a three-way merge of that commit's change onto HEAD (uses 2.1). | 1 day after 2.1 |
| 2.9 | Hooks | `.git/hooks/pre-commit`, `commit-msg`, `pre-push`, `post-merge` | `.sg_vault/local/hooks/`, local only and never synced (as in Git, a hook in a vault must never run on a clone). | 1 day |

### Priority 3

| # | Feature | Git | sgit plan | Size |
|---|---|---|---|---|
| 2.10 | Garbage collection | `gc`, `prune` | `vault prune` with the write key. Compute the set reachable from every branch, clone branch, tag and stash; delete the rest after a grace period (Git's two weeks) so in-flight pushes survive. On pack vaults, delete `archive/` packs older than the grace period. It has to be client-side: the host cannot read trees. | 2–3 days |
| 2.11 | Delta compression | `repack`, delta packs | At push, delta a blob against its previous version before deflate and encryption. The reader rebuilds the blob and verifies it by content address. | 1–2 weeks; old clients can't read deltas, so it needs a vault feature with a gate |
| 2.12 | `rebase` | `rebase`, `rebase -i` | Replay this clone's unpushed commits on the new head (2.8 in a loop). Interactive rebase later. | 2–3 days |
| 2.13 | `worktree` | `worktree add` | Several working copies over one `.sg_vault` store. | 2 days |
| 2.14 | `archive`, `shortlog`, `describe`, aliases | the same | Plaintext export of a commit as zip/tar; summaries; `sgit config alias.*`. | small each |
| 2.15 | Submodules | `submodule` | A vault referencing another vault at a commit. Needs a design; skip until someone asks. | design |

---

## 3. Signing the way Git does it

**How Git does it.** Git never asks who is allowed. It signs with the key the user already has: GPG (`gpg.format
openpgp`), SSH (`gpg.format ssh`, signing through `ssh-keygen -Y sign` and so through ssh-agent and hardware keys)
or X.509. It stores the signature in the commit (`gpgsig`), excluded from the signed bytes. Verification is each
verifier's choice: a GPG keyring, or an `allowed_signers` file of principal → public key. GitHub then adds
"verified" on top by matching keys to accounts. That last part is the SGitHub layer, not the CLI.

**sgit, the same way:**

- **Signing.**
  - Read Git's own settings (`git config user.signingkey`, `gpg.format`, `commit.gpgsign`, `tag.gpgsign`). A user
    whose Git signs their commits gets signed sgit commits with zero sgit setup. `sgit config` can override per vault.
  - Sign the way Git does: run `ssh-keygen -Y sign -n git` (agent and hardware keys work) or `gpg --detach-sign`.
    The output is Git's format, so `ssh-keygen -Y verify` or `gpg --verify` can check an sgit signature outside sgit.
- **Verification.**
  - `check verify`, `history log --show-signature` and `vault tag show` read the same `allowed_signers` file Git
    uses (`gpg.ssh.allowedSignersFile`), or the GPG keyring.
  - Results are Git's: good signature from a listed principal / good signature from an unknown key / bad / none.
  - Verifying SSH signatures in-process uses `cryptography`, which is OpenSSL underneath and already a dependency;
    ed25519, ECDSA and RSA keys are supported. GPG verification runs `gpg`, as Git does.
- **What stays as it is.**
  - The per-clone ECDSA key keeps signing every commit. It is the machine signature that agents get with no setup,
    and `signatures-required` keeps meaning "every commit carries a valid clone signature".
  - The user's signature is a second, optional one. It is what answers "who wrote this", for anyone who keeps an
    allowed-signers file. That closes TM-R01 for that verifier exactly as far as Git closes it, and that is the bar.
- **Compatibility: no gate needed.** Checked on the code today:
  - A commit JSON with a field the client does not know parses fine (`Schema__Object_Commit.from_json` accepts
    unknown keys).
  - Clients check the clone signature over the fields they know (`commit.json()`), so the new field must be
    *excluded* from the clone's signing bytes, as Git excludes `gpgsig`. Then old clients verify the clone signature
    unchanged and simply ignore the user signature.
  - The reserved `author_signature` field cannot carry it: it is validated as base64 of at most 256 characters, and
    an SSH or PGP signature is longer, so a client would reject the commit (tested). The signature goes in a new
    field.
  - Signed tags work the same way.
- **What it does not do** (SGitHub's job later): a list of who may write, carried in the vault; joining and approval;
  revocation records; "verified" decided by a server.

Size: 3–4 days with tests (SSH first, GPG second), plus CHANGELOG and threat-model rows (TM-R01 gains "closed
per verifier with an allowed-signers file").

---

## 4. Moved to SGitHub (server-side, later)

These were in the article's "Git is ahead" list or in yesterday's review. They are GitHub's features, not Git's,
so they are out of scope for the CLI:

- **Accounts and identity:** who pushed, keys attached to people, "verified" badges, verification recorded at push
  time.
- **A list of who may write:** owner-signed signer registry, join requests and approval, revocation (yesterday's
  TM-R01 proposal), per-person write tokens.
- **Protected branches:** required signed pushes, rules enforced by the server.
- **Collaboration:** review / pull requests, the web merge button, CI triggers, issues.
- **The append lane** is already a server feature. Its CLI (`sgit inbox send/read`) belongs in section 5, because
  Git has nothing like it.

Under zero knowledge, an SGitHub server can do the access parts: tokens, ref ACLs keyed by the hashed ref ids,
recording verification. The content parts (review, CI, search) run in the browser or in a runner that holds the
key.

---

## 5. More on top: what sgit does that Git does not

The second half of the message. Already shipped unless marked.

- The host reads nothing: contents, file names, messages and branch names are encrypted on the client.
- A read key is a capability: publish it, and anyone reads from any static host with no account.
- Fetch one folder by byte ranges from plain storage (pack vaults), each object verified by hash.
- Indexes shipped by the writer, signed and encrypted, checked before use.
- Many agents, one folder each: writes outside the scope are refused by name, and two scoped agents never conflict.
- Custody without access: `vault mirror`.
- Policy carried by the vault and enforced by every client: format gate, `signatures-required`.
- Rewind detection on every clone.
- The secret guard (keys and key zips are never committed).
- Key rotation: `vault rekey` / `vault move`.
- A computable cache for fixed-cost reads.
- `serve`, `publish`.
- `pki encrypt` to a person.
- To add: `sgit inbox` for the append lane; `cat --vault-key` (one file with no clone); Phase 4 ranged reads on pack
  vaults.

## Suggested order

1. 2.1 line-level merge.
2. 2.2 signing with your own key.
3. 2.3 `commit <paths>`.
4. Then 2.4–2.9 as a "history tools" release.
5. 2.10–2.15 when a workload asks.

Each is an extension: off or invisible until used, and no version gate except 2.11.
