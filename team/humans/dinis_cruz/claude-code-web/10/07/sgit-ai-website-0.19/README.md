# Brief for the sgit.ai website team — sgit-ai 0.19.0 (7 Oct 2026)

Three new page drafts and two edits to pages you published this morning. Same conventions as
the 0.18.0 debrief: second person, `$` code blocks, real CLI wording. Each page says where it
goes. Please check PyPI shows 0.19.0 before publishing (the `dev → main` merge publishes it).

| File | Where | Purpose |
|---|---|---|
| `01__release-notes__sgit-ai-0.19.0.md` | Updates (a second CLI entry, like the 0.18.0 one) | Change control with the live-API evidence |
| `02__guide__history-integrity.md` | Docs, next to *Partial clones* (`docs/history-integrity.html`) | How to use `sgit vault format`, `sgit check verify`, what a rewind is and what to do |
| `03__notice__update-to-0.19.0.md` | Updates, the page to point an agent team at | What changes for an agent: nothing until the vault owner raises the vault; the two new messages they may see |
| `04__edits-to-existing-pages.md` | *Agents sharing one vault*, *Partial clones*, *Working with AI agents* | The exact paragraphs to add |

## Things to know before publishing

- **Nothing changes for an existing vault until its owner runs `sgit vault format`.** Every page
  must say this first; agents will otherwise assume they have to do something.
- **The one break**: a CLI older than 0.19.0 that opens a vault *raised* to format 2 fails with a
  validation error, not a friendly message (it cannot know about the gate). The notice tells
  owners to raise vaults only once their agents are on 0.19.0. Un-raised vaults are unaffected.
- **The web UI** reads format-2 vaults fine today; it does not yet write 32-hex ids, sign commits
  or keep the branch index when it pushes (the CLI now repairs that on its next pull). Say so
  plainly where the guide mentions the web UI; the SG/Send team has the work queued.
- **Numbers are measured** on the same anonymised "shared CRM vault" as before, plus a throwaway
  vault on the live dev API. No vault id, key or real folder name appears; keep it that way.
- The test vectors the pages mention live in the CLI repo at `tests/_fixtures/interop_vectors.json`.
