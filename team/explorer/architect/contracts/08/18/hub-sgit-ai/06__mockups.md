# 06 — Interface Mockups

Forge conventions are worth following closely: the argument is that this is **a familiar
thing on unfamiliar foundations**, and every gratuitous difference costs a reader attention
that should go to the substance.

---

## 1. The one screen that matters

The specification is explicit that this should be **designed, not added later as a panel**:
the screen where a visitor can see that the server returned only ciphertext while they were
reading a file.

```
┌───────────────────────────────────────────────────────────────────────────┐
│  hub.sgit.ai › acme › product-docs                    [structure] [raw]   │
├──────────────────────────┬────────────────────────────────────────────────┤
│  src/                    │  # Getting started                             │
│    main.py               │                                                │
│  › docs/                 │  Install the client, then open your first      │
│      getting-started.md  │  vault. Nothing here reached a server in       │
│      architecture.md     │  readable form.                                │
│    README.md             │                                                │
│                          │                                                │
├──────────────────────────┴────────────────────────────────────────────────┤
│ ▼ WHAT THE SERVER SAW  (7 requests · 14.2 KB · all opaque)                 │
│                                                                           │
│   GET bare/refs/ref-pid-muw-1995ccf51fe8         69 B   ▓▒░▓▒░▓▒░▓▒░      │
│   GET bare/data/obj-cas-imm-4ccb5bc28ba1      8,871 B   ░▓▒░▓▒░▓▒░▓▒      │
│   GET bare/data/obj-cas-imm-fd3fb9f0e9d9      1,514 B   ▓░▒▓░▒▓░▒▓░▒      │
│   …                                                                       │
│                                                                           │
│   The hub returned these bytes. It has no key, so it cannot tell a        │
│   file from a folder, a name from its contents, or this vault from        │
│   a private one — the bytes are identical either way.                     │
│                                    [ show me the raw ciphertext ]         │
└───────────────────────────────────────────────────────────────────────────┘
```

The panel is **live, not illustrative** — it lists the actual requests this page made. That
is what makes it an argument rather than a marketing claim, and it is far more persuasive
than a page explaining zero knowledge.

## 2. The hub index — a useful index of things it cannot read

```
┌───────────────────────────────────────────────────────────────────────────┐
│  acme hub                                        13 vaults · 4 readable   │
│  Engineering estate. Most of this is encrypted and stays that way.        │
├───────────────────────────────────────────────────────────────────────────┤
│  🔓 product-docs        Public docs for the product         updated 2d    │
│     read · fork · mirror                                                  │
│                                                                           │
│  🔓 component-starters  12 reusable UI components           updated 5d    │
│     read · fork · mirror                                                  │
│                                                                           │
│  🔒 product-src         The product. Ask #eng for access.   updated 1h    │
│     ▤ structure visible · request access · mirror                         │
│                                                                           │
│  🔒 payroll             Finance only.                       updated 9d    │
│     request access · mirror                                               │
│                                                                           │
│  🜲 team-alpha hub      14 vaults                            updated 3h    │
│     open hub →                                                            │
└───────────────────────────────────────────────────────────────────────────┘
```

Four states, and the affordances differ by what you hold:

- 🔓 **readable** — the owner published a read key
- 🔒 **listed only** — cover renders; content opaque; *request access* is out of band
- ▤ **structure visible** — a structure key was issued: shape and history, no contents
- 🜲 **a hub** — the fractal edge; opening it is the same operation as opening a vault

**mirror** appears on every row, including the ones you cannot read — custody without access
is a capability, not a leftover.

## 3. Structure-key view — the tier nobody knows we have

```
┌───────────────────────────────────────────────────────────────────────────┐
│  acme › product-src            ▤ STRUCTURE ONLY — contents are withheld   │
├───────────────────────────────────────────────────────────────────────────┤
│  src/            34 files    412 KB     last change 1h ago                │
│    api/          11 files    108 KB                                       │
│    ui/           18 files    221 KB                                       │
│  tests/          52 files    303 KB     last change 1h ago                │
│  README.md          1 file     4 KB     last change 6d ago                │
│                                                                           │
│  History (last 5)                                                         │
│    1h   ●  3 files changed                                                │
│    4h   ●  1 file changed                                                 │
│    2d   ●  17 files changed                                               │
│                                                                           │
│  You hold a structure key. You can see the shape, the sizes and when      │
│  things changed. You cannot open a file. Ask #eng for a read key.         │
└───────────────────────────────────────────────────────────────────────────┘
```

This screen is buildable today — the primitive is shipped and tested — and no conventional
forge can express it.

## 4. Opening a private vault — the flow needing the most care

```
┌──────────────────────────────────────────────┐
│  🔒  acme › payroll                          │
│                                              │
│  Finance only. Contents are encrypted; this  │
│  page and the hub cannot read them.          │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ Paste a read key to open…              │  │
│  └────────────────────────────────────────┘  │
│                     [ Open ]                 │
│  ☐ Remember this key on this device          │
│    (off by default — not on a shared machine)│
│                                              │
│  Request access: finance@acme.example        │
└──────────────────────────────────────────────┘
```

And the refusal the key classifier makes possible:

```
⚠  That is a VAULT key (sgit_private_vault_…), which can modify this vault.
   This page only ever needs your read key, and should never receive a write key.
   Get it with:  sgit vault derive-keys <your-vault-key>
```

## 5. Fork = rekey, made visible

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Fork  acme › component-starters                                          │
│                                                                           │
│  Forking re-encrypts the content under a new key of your own. The result  │
│  is an independent vault: your key, your history from here.               │
│                                                                           │
│    • the new vault shares NO identifiers with the original                │
│    • nobody can tell it was derived from this one                         │
│    • updates do not flow — a fork is a copy, not a reference              │
│                                                                           │
│  sgit clone sgit_public_read_c28b…:ivpijuvg ./fork                        │
│  sgit vault rekey ./fork                                                  │
│  sgit publish ./fork-site --visibility public                             │
│                                                     [ copy commands ]     │
└───────────────────────────────────────────────────────────────────────────┘
```

Both properties are measured, not asserted: a rekey turns over **100%** of object ids, and
two vaults holding the same document share **zero** identifiers.

## 6. Design rules for the interface

1. **Sparse by default.** A browsing session fetches the subtree it is viewing. The honest
   claim is "this scales with what you look at, not with the size of the vault" — and only
   if the interface behaves that way.
2. **Never imply a capability that does not exist.** No "revoke access" button (revocation
   is not retroactive). No cross-vault search box that silently searches only what you hold.
3. **Say which tier you are in.** A reader should always know whether they are seeing a
   public vault, one they were trusted with, or only its shape.
4. **Show the head's age.** An intermediary can serve a stale ref; it cannot forge content.
   Freshness is the reader's problem, so surface it.
5. **Follow forge conventions everywhere else.** The novelty budget is spent on the
   ciphertext panel and the tier indicators. Nothing else should be surprising.
