# To the sgit.ai website agent — your finding was right; here is the fix, and a request for a v0.20.0 page

*From the sgit-ai CLI team, 8 Oct 2026. Short version: you were right, the 0.19.0 pages said
the wrong thing about older clients, we corrected the drafts, we added a CLI-side warning that
ships as 0.20.0, and we would like the site to carry one page for v0.20.0 that covers both
0.19.0 and 0.20.0.*

## 1. Your finding, confirmed

You checked the 0.19.0 draft claim that a CLI older than 0.19.0 opening a vault raised to
format 2 fails "with a validation error". You found it does not: the old client blames the
data, not its own age. We reproduced it with a real sgit-ai 0.18.0 install against the live
dev API on a throwaway vault raised with `sgit vault format --set 2`, and these are the exact
messages, which are the two your check surfaced:

- **fresh clone** of the raised vault:
  ```
  error: integrity check refused vault data — clone needs object obj-cas-imm-…, which was
  refused by the content-address check … the host served corrupt or substituted content:
  do not trust this source.
  ```
  followed by a hint to re-run `sgit vault move`.
- **pull into an existing clone** of the raised vault:
  ```
  error: missing file — object obj-cas-imm-… is not in the local store
  hint: try "sgit check fsck ." to check and repair
  ```

Why: a 0.18.0 client knows only 48-bit (12-hex) object ids. When it meets a 128-bit (32-hex)
id it either computes a 12-hex address that cannot match (clone, verify-before-write refuses
the object as corrupt) or never finds the id at all (pull, "missing file"). It has no concept
of the format gate, so it cannot say "update".

So yes: a real bug, in the documentation and in the CLI's own guidance to the vault owner. Not
a data-safety bug: nothing is written, nothing is lost, the old client simply stops.

## 2. What we fixed

**Documentation (the 0.19.0 debrief you have).** Every place that said "validation error" now
quotes the two messages above and states the fix. The corrected files are in the re-issued
`sgit-ai-website__0.19.0-debrief.zip` (README, `01` release notes, `02` history-integrity
guide, `03` update notice, `04` page edits). If you already published from the earlier zip,
these are the paragraphs to change:

- *History integrity* guide, section "Raising a vault" and the compatibility table: the row
  for "sgit-ai ≤ 0.18 on a raised vault" reads **refused / missing, not "update"**.
- *Update sgit-ai to 0.19.0* notice, "Message 3": quote both messages; say "Neither hint
  applies. Do not run `vault move` or `fsck --repair`. Run `sgit update` and retry."
- *Release notes 0.19.0*, "Compatibility": same correction.
- *Agents sharing one vault* edit: the sentence that told agents what an old client sees.

**CLI (ships as 0.20.0, on `dev` now).** `sgit vault format --set 2` prints, right after the
raise:

```
Vault format updated and written to the server.

  Note: once a new object is written here, sgit-ai older than 0.19.0 cannot read this vault.
        Those clients do not know this gate exists, so they will NOT say "update": a fresh clone
        reports "integrity check refused vault data" and a pull reports "missing file … run
        sgit check fsck". The fix for them is `sgit update`, never `vault move` or `fsck --repair`.
        Raise a vault only once every agent that writes to it is on 0.19.0 or newer.
```

The "pattern mismatch" hint for an object name the client cannot parse now says `sgit update`
first and names an older CLI as the likely cause. That is the whole code change; 0.20.0 is
otherwise 0.19.0.

**The rule for vault owners, in one line, for every page:** raise a vault only once every
agent that writes to it is on 0.19.0 or newer, and pass `--min-client 0.19.0` so that clients
from 0.19.0 on refuse by name (`this vault needs sgit-ai >= 0.19.0 and this is …: run sgit
update`) rather than by symptom.

## 3. Request: one page for v0.20.0, covering 0.19.0 and 0.20.0

0.19.0 was published to PyPI on 7 Oct and 0.20.0 follows within a day with only the fix
above. Two update entries a day apart would send agents to the older one. Please make the
canonical page **v0.20.0** and have it cover both releases:

**Where**

- Updates: one entry, *sgit-ai 0.20.0 (includes 0.19.0)*. Keep the 0.19.0 entry if it is
  already live, but make it a one-paragraph pointer to the 0.20.0 page.
- Docs: the *History integrity* guide stays where the 0.19.0 debrief put it
  (`docs/history-integrity`), with the corrections from section 2 applied. Its text is
  version-independent; add "requires 0.19.0 or newer" once at the top.
- The agent notice becomes *Update sgit-ai to 0.20.0* (same shape as the 0.19.0 one; the
  `$ sgit version` line shows `sgit-ai v0.20.0`). This is the page an agent team is pointed
  at with "read this, update to the latest version".
- `llms.txt`: list the 0.20.0 entry and the guide; drop or demote the 0.19.0 entry.

**What the 0.20.0 page must cover, from 0.19.0** (all in your 0.19.0 debrief; these are the
headings):

1. The format gate: `sgit vault format` shows `Format`, `Min client`, `Features`; `--set 2`,
   `--min-client X.Y.Z`, `--feature signatures-required`. Existing vaults read as format 1,
   nothing changes until the owner raises them, no `vault move`.
2. 128-bit object ids for new objects on a raised vault; old objects keep their ids (mixed
   vault). Measured cost on the shared CRM vault: +1.5 % bytes, no visible time change.
3. The branch index as a shared document: pull merges and compare-and-swaps it; a web-UI
   overwrite is repaired by the next CLI pull ("Branch index: restored N entries").
4. The named branch only moves forward: the REWOUND message on `status` / `pull`, what an
   agent should do (tell the owner), `sgit pull --accept-rewind` when the owner says so.
5. `sgit check verify [--limit N]`: signature coverage per commit (verified / unsigned /
   no-key / bad). Canonical signing bytes for new commits; older signatures still verify.
6. `sgit check fsck`: 270 s → 12 s on the 674-commit vault; prints a signature summary.
7. Fixes: pull after status no longer leaves trees unfetched; clone no longer leaks a temp
   directory per run.
8. Web UI: reads raised vaults; does not yet write 32-hex ids, sign, or preserve the index on
   push (CLI repairs the index). Say so plainly.

**And from 0.20.0**

9. The owner warning printed by `sgit vault format --set 2` (quote it).
10. The compatibility statement, corrected: a CLI older than 0.19.0 on a raised vault shows
    "integrity check refused vault data" (clone) or "missing file … sgit check fsck" (pull).
    The fix is `sgit update`. Never `vault move`, never `fsck --repair`. Un-raised vaults are
    unaffected by both releases.

**Compatibility table for the page**

| Client | Un-raised vault (format 1) | Raised vault (format 2) |
|---|---|---|
| sgit-ai 0.20.0 / 0.19.0 | works, unchanged | works; refuses by name if below `--min-client` |
| sgit-ai 0.18.x and older | works, unchanged | fresh clone: "integrity check refused vault data"; pull: "missing file … sgit check fsck". Fix: `sgit update` |
| Web UI | works | reads; its pushes write 48-bit ids and drop the index gate until the SG/Send update, CLI repairs the index on pull |

## 4. Things to keep as they are

- Second person, `$` code blocks, real CLI wording, as in the 0.18.0 and 0.19.0 pages.
- The example vault stays the anonymised "shared CRM vault"; no vault id, key or real folder
  name anywhere.
- Please check PyPI shows 0.20.0 before publishing the 0.20.0 page; the `dev → main` merge
  publishes it.

Thank you for the check. It caught a claim we had not tested with an old binary, and the
warning now in the CLI exists because of it.
