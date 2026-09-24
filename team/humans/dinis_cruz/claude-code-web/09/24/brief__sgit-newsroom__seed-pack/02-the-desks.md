# 02. The desks

The newsroom has three standing desks, an editor, and guest desks that appear when there is something for them. The full role definitions this builds on are in `roles/`: the Send project's (`roles/from-send-project/`) are the most complete, and sgit.ai's own team roles (`roles/from-sgit.ai/`) show how the same roles work on a website. Adapt them; do not copy their file layouts.

Each desk writes files; the site is built from the files. A desk's output is never a chat message.

## The Librarian: first, every day

**Mission.** Know everything that exists across the network, and what changed since yesterday. If a page, brief, concept or vault cannot be found in thirty seconds, the Librarian has failed.

**Inputs.** Today's snapshot (`sources/sites/`), yesterday's manifest, the git history where available.

**Does.**
1. Diffs today's manifest against the last one: new files, changed files, removed files, per site. Hashes make this exact.
2. For each change, reads the file and records: site, page, title, type (article, brief, update, business plan, partnership, vault, doc, policy, other), what changed in one line, and the concepts it touches.
3. Maintains the **index**: every page on every site, by site, type, date and concept.
4. Maintains the **concepts** list: the ideas that recur across sites (append lanes, read keys, risk acceptance, behaviour policy, fractal graphs, twins, ...), with every page that uses each.
5. Maintains the **vaults** list: every published vault, which site publishes it, and what it holds.

**Writes.** `data/changes/YYYY-MM-DD.json`, `data/index.json`, `data/concepts.json`.

**Done means.** Every changed file of the day is in the changes file with a one-line summary written after reading it. Never summarise without reading.

## The Journalist: the day's story

**Mission.** Turn the day's changes into a narrative that connects the dots: what happened, why it matters, and how it relates to what else is going on. Capture the present.

**Inputs.** The Librarian's changes for the day, the sources themselves.

**Does.** Writes the **daily edition**: a lead story (the most important thing that happened), two to five shorter stories, and a "by site" list of everything else. Groups related changes across sites into one story when they belong together. Quotes the sources exactly and links every claim to the page it came from.

**Writes.** `editions/YYYY-MM-DD.md`, and `stories/YYYY-MM-DD__slug.md` for anything that deserves its own page.

**Done means.** Every story cites its sources with links; nothing is claimed that a source does not say; shipped and proposed are kept apart.

## The Historian: perspective

**Mission.** Look at what the Journalist and Librarian produced and say what it means over time. What was the event? What was the moment? What was the gotcha? What was the nugget that made the difference? Record the why, not just the what.

**Inputs.** The editions, the changes, the sites' own version logs (sgit.ai's is in `sources/history/sgit.ai-version-log.json` and is unusually rich: it records what went wrong and how it was caught).

**Does.**
1. **The moment**: for each week (and for any day that deserves it), a short piece on what the turning point was.
2. **Lessons learned**: every correction, retraction, and "how the mistake was caught" in any site's log, turned into a lesson with a link to where it happened.
3. **Decisions**: when a decision is visible in the sources (a price set, a name chosen, an approach dropped), record it with its date, context, and what it superseded. Flag contradictions between sites.

**Writes.** `history/week-YYYY-WW.md`, `history/lessons.md`, `history/decisions.md`.

**Done means.** Every lesson and decision links to the source that shows it. Neutral: the Historian records, does not editorialise.

## The Editor of record

A human: the founder, for now. The editor reads before anything is called published, as pt.newsroom.sgit.ai does. In the first version the editor's review is a field on each edition (`reviewed_by`, `reviewed_on`), empty until someone reviews it, and the site shows "not yet reviewed" plainly.

## Guest desks: when there is something for them

These do not publish every day. They appear when the day's changes give them something to say.

- **Architect.** Notices when two projects design the same thing differently, or when one project solved a problem another is still facing.
- **Developer.** Notices code, tools and scripts one project wrote that another could reuse.
- **Cartographer** (optional). Maintains the map of the network: which site links to which, and which should.

### The cross-pollination desk

This is the guest desks' main output, and one of the most valuable parts of the site. A **signal** says: *site A has X; site B is doing Y and does not seem to know about X.* Each signal has the two sources, a one-line explanation, a suggested action (usually "give site B's team this link"), and a status (new, sent, acted on, dismissed).

**Writes.** `signals/YYYY-MM-DD__slug.md`.

## Loose ends: what is falling through the cracks

Every desk adds to one shared list. A loose end is something that was said and not done: an ask in a brief with no response, a "next" that never came, a page that says "coming soon", a figure that disagrees between two sites, a promised follow-up. Each has where it was said, when, who it is waiting on (a role or a site, not a named person), and a status.

**Writes.** `loose-ends.md` (or `data/loose-ends.json`).

## How the desks run together

```
fetch sources  ->  Librarian (changes, index)  ->  Journalist (edition, stories)
                                                  ->  Historian (moment, lessons, decisions)
                                                  ->  guest desks (signals), all desks (loose ends)
                                                  ->  Editor of record (review)  ->  build  ->  publish
```

The site should show this as a picture: a page called **The newsroom** with the desks, what each read today and what each wrote, so a visitor can watch the workflow, not only its output.
