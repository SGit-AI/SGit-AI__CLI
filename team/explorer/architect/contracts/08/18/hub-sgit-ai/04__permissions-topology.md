# 04 — Permissions as Key Topology

The part most likely to be got wrong, because it inverts an assumption every forge user
holds. In a forge, permissions are **a policy the server enforces**. Here, **possession of a
key is access** — there is no referee, because there is nothing for a referee to withhold
that the key does not already unlock.

```
   FORGE                           VAULT FORGE
   one repository                  one vault, or several
   + an ACL table                  + a key distribution
   server checks each request      the key opens it or it does not
```

A cryptographic boundary has **no bypass** — a misconfigured ACL grants access; a missing
key does not decrypt. It also has to be **designed in advance**, and **revocation is not
retroactive**.

---

## 1. The four positions that exist today

The briefing pack works with two (read key, vault key). There are four, and the third is
shipped but unused.

| Position | Grants | Derivation | Status |
|---|---|---|---|
| **Vault key** | read **and** write | root credential | shipped |
| **Read key** | read everything, write nothing | one-way from the vault key | shipped |
| **Structure key** | **metadata only** — tree shape, paths, history, sizes. **No file contents** | one-way (HKDF) from the read key | **shipped, no consumer** |
| **No key** | custody: hold, mirror, verify, serve — read nothing | — | shipped (needs a manifest) |

The structure key is the interesting one. It answers "let them see the shape of the
repository without seeing the code", which a conventional forge cannot express at all, and
it is **already implemented and tested** (`Vault__Crypto.derive_structure_key`,
`tests/unit/crypto/test_Vault__Crypto__Structure_Key.py`).

Because each derivation is one-way, handing out the weaker key discloses nothing about the
stronger one.

## 2. Worked topologies (the specification asks for these — nobody derives them unaided)

### 2.1 An open-source project

```
project-docs      (vault)   read key PUBLISHED      → anyone reads; the hub indexes it
project-src       (vault)   read key PUBLISHED      → anyone reads, forks by rekey
project-release   (vault)   vault key: 2 maintainers
                            read key PUBLISHED
```

Contributors need **no credential**: clone the public vault, work, emit a serialised diff.
Maintainers hold the write keys. This works **today**, with no missing primitive.

### 2.2 A company with a mostly-private estate

```
acme-hub          (vault)   read key PUBLISHED   → the catalogue: lists everything, reveals nothing
acme-handbook     (vault)   read key → all staff
acme-product      (vault)   vault key → the team;  structure key → the whole company
                                                    ("see what exists, not what it says")
acme-payroll      (vault)   vault key → 2 people;  nothing else issued
```

Note what the hub does here: **it is a useful index of things it cannot read.** Every vault
is listed with a cover — title, description, "request access" — and only the ones with a
published key are readable. That is the shape most organisations actually have.

### 2.3 A contractor, scoped by vault

```
client-brief      (vault)   read key → contractor
client-deliverable(vault)   vault key → contractor      (they write here)
client-internal   (vault)   contractor holds nothing    (not even a structure key)
```

Granularity comes from **which vaults exist**, decided when the work starts.

## 3. The two hard limits (publish them; do not let them be discovered)

**Revocation is not retroactive.** Anybody who held a read key and fetched the objects keeps
a working copy forever. Rotating the key protects future commits and returns nothing already
taken. Worse on a git-hosted publication: the old ciphertext stays in git history, so a
public-repo vault **cannot revoke read access at all**, even with the write key (measured).

**Granularity costs structure.** Five permission levels means five vaults and five keys,
decided in advance. A forge lets you add a rule later; this requires the shape to have been
designed. The honest counterweight: **a shape you can see is easier to audit than a table of
rules nobody has read.**

## 4. The missing primitive — decide this before writing hub architecture

Every brief describes granularity as *"sub-vaults with their own keys, link files"*. **That
primitive does not exist in the CLI** (audit, §2). Everything in §2 above is expressible
only as *separate vaults* plus the key tiers.

Three ways forward:

| Option | What it is | Cost | Risk |
|---|---|---|---|
| **A — Separate vaults + a link convention** | a vault file that names another vault (id + optional key); the client follows it. This is exactly the fractal edge from `01`, applied inside a vault | **small** — a schema and a resolver; no format change | topology is coarse: the unit is a vault |
| **B — Nested sub-vaults with derived keys** | a real sub-tree with its own key derived from the parent | **large** — new wire format, cross-runtime (CLI + web + API), migration | this is a protocol project, not assembly |
| **C — Per-path content keys** | derive a content key per path prefix | very large; also breaks CAS dedup and complicates rekey | not recommended |

**Recommendation: A.** It is the same mechanism the fractal already needs (an entry that
points at another vault), it requires no format change, and it makes the worked topologies
above expressible as *one hub vault linking to several scoped vaults*. B is a real option
later; it should not gate the hub.

**Whichever is chosen, the CI answer changes with it.** "A build runs against a sub-vault
containing only what it needs" becomes, under A, "a build runs against **a separate vault**
containing only what it needs, and somebody has to assemble it" — which is honest, works
today, and names the open question the forge brief already flagged (*who assembles the
scoped build vault?*).

## 5. Continuous integration — the genuine hole

A runner must read to build. Three options, none free:

| Option | Property |
|---|---|
| **Run it locally** | the developer already holds the key; works today; gives up shared visibility |
| **Grant a runner a key** | works, and the runner can then read *everything* in that vault — the over-privileged agent problem with a worse blast radius |
| **Scope it** (recommended) | the build gets a vault/sub-vault containing only what the build needs, and only that key — least authority applied to CI |

The third is the only one consistent with the model, and under option A above it is
buildable today. Its open question is assembly: something must produce the scoped vault, and
that something holds the broader key.

## 6. What the hub must never do

- **Never publish write keys.** Read keys for public vaults may be catalogued; a central
  list of vault keys would be a single artefact whose compromise is unbounded.
- **Never imply revocation.** No "remove access" button that does not remove access.
- **Never accept a vault key in a read surface.** The loader refuses `sgit_private_vault_`.
- **Never let a catalogue entry imply endorsement.** Trust does not compose across hops.
