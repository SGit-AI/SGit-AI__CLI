# 01. The newsroom: what it is, and why now

## In one paragraph

**sgit.newsroom.sgit.ai** (working name) is a newsroom whose beat is the sgit network itself: sgit.ai, riskmandate.ai, graphs.sgit.ai, risks.sgit.ai, the other sites in the network, and the vaults they publish. Every day a small team of agents reads every site, works out what changed, and publishes what matters: an index of what exists, a daily edition that tells the story of what changed and connects the dots, a historian's perspective on what the moment was and what it taught, signals where one project should know about another, and a list of the things falling through the cracks. If nothing happened on a day, nothing is published that day.

## Why now

So many agents now work in parallel across so many sites that nobody, including the founder, can keep up by reading the sites. In the seven days to 24 September 2026, sgit.ai alone shipped 58 releases (its version log is in this zip), riskmandate.ai went from v1.27.0 to v1.34.8 in 29 releases between 20 and 24 September, and new business plans, partnership pages and briefs appeared every few hours. Three problems follow:

1. **No overview.** There is no single place to see, each day, what changed across the network.
2. **Things fall through the cracks.** Asks made in one brief are never picked up; a follow-up promised on one site never happens; two sites describe the same thing differently.
3. **Projects do not know about each other.** An agent writing on riskmandate.ai does not know what an agent wrote on sgit.ai yesterday, or on graphs.sgit.ai last week.

As more people join the team, the same problem gets worse for them. The newsroom is how everybody, human or agent, stays in sync.

## Why it is also a showcase

Every site in the network is published and version-controlled, so what changed is cheap to find exactly. A newsroom that runs on that, and shows its workings, is a clear example of what sgit and agentic workflows make possible: a team producing a lot, kept coherent by other agents whose job is to read, index, narrate and remember.

## Who reads it

- **The founder**, every morning: what happened, what needs a decision, what is stuck.
- **The team**, people and agents, before starting work: what the other projects did that affects theirs.
- **Anyone else**, as an example of how a team that produces a lot stays in sync.

## Its relatives

The network already has two newsrooms, and this one should borrow from both:

- **newsroom.sgit.ai**, "The Future of News": the argument that a story is a graph of evidence, and that every page should carry its provenance. Its snapshot is in `sources/sites/newsroom.sgit.ai/`. Its "honest sentence" (what runs, what is design) is the model for this site's own honesty.
- **pt.newsroom.sgit.ai**, a Portuguese-language newsroom mapping the Portuguese AI ecosystem as a graph. Every claim walks back to a frozen, hashed copy of its source, and there is a human editor of record. Its snapshot is in `sources/sites/pt.newsroom.sgit.ai/`, and its source code is in `SGit-AI/SGit-AI__Website__Newsroom__PT`. Look at its workflows before designing this one.

This newsroom is in English. Its sources are frozen and hashed the same way (see `sources/sites/manifest.json`).

## The first version, in one sentence

A static site that works offline, built from the snapshot in this zip, with the reading room, the librarian's index, five daily editions for 20 to 24 September 2026, the historian's view of the week, the first cross-pollination signals and the loose ends. See `04-first-version.md`.
