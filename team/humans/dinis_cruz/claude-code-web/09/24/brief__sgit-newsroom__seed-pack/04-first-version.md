# 04. The first version (v0.1): build it tonight

The founder is flying tomorrow and wants to read the last few days' docs, briefs and plans offline. So the first version has one hard deadline and a clear order. **Ship something readable early, then improve it.** Commit and push after each step, so whatever state the repo is in when the founder leaves is usable.

## Step 1. The reading room (must have, first hour)

Render every file in `sources/` as a page, with its provenance block, and a reading-room index:

1. **First: what is new since 18 September**, from `sources/history/sgit.ai-new-pages-since-2026-09-18.md` (61 pages), each linking to its local rendered copy.
2. **The business plans**: the five plan vaults in `sources/vaults/` (Company X-Ray, Lesson Loop, Risk Acceptance Office, Connector Twin, Agent as Webmaster). Render their `plan/`, `spec/`, `prototypes/` and `README.md`. Their `index.html` apps work offline as they are; link to them.
3. **The briefs**: `sources/cli-briefs/` and every page under `docs/briefs/` in the sgit.ai snapshot.
4. **Everything else, by site.** `llms-full.txt` files are long: split them into sections on their `#` and `##` headings so they read as pages, not one scroll.

Check it by opening `site/index.html` from the file system with the network off.

## Step 2. The Librarian's index (first evening)

Build `data/index.json` and the index page from the snapshot: every page, by site and type. For the first version the "changes" are the new-pages list and the version logs (`sources/history/sgit.ai-version-log.json`, `sources/sites/riskmandate.ai/versions.md`), because there is no earlier snapshot to diff against. From tomorrow, the diff of manifests is the source.

## Step 3. Five daily editions: 20 to 24 September 2026

One edition per day, from the version-log entries and new pages of that day. sgit.ai's version log has 6, 20, 5, 5 and 7 entries on those days; riskmandate.ai's version record covers the same days. A lead story per day, a few short ones, and "everything else" by site. Mark each edition `reviewed_by:` empty.

## Step 4. The Historian's week

One piece: the week of 18 to 24 September in perspective. What was the moment? The version log is honest about what went wrong and how it was caught, so there is material. Plus `history/lessons.md` with every correction in the week's log turned into a lesson, linked.

## Step 5. Signals and loose ends

The seeds below were noticed while the sources in this zip were being written. **They are leads, not findings.** Check each against the sources, keep the ones that hold, cite them, and drop the rest.

**Cross-pollination seeds**

- **Company X-Ray reuses RiskMandate's pricing ladder** (sgit.ai vault page and `sources/vaults/company-xray/plan/09-reuse-from-riskmandate.md`); riskmandate.ai may not know the X-ray plan exists.
- **Two risk acceptance interval ladders.** risks.sgit.ai and the Risk Acceptance Office plan use one ladder (1 hour, 4 hours, 1 to 2 days, 1 to 2 weeks, a month by default, 6 months); check whether riskmandate.ai uses the same.
- **A RiskMandate price that may differ between pages** (£10 in one place, £5 in another, seen on 24 September). Find both, or drop the seed.
- **A brief that was acted on, and a list that does not know it.** sgit.ai briefed an interview page for riskmandate.ai on 24 September (`docs/briefs/riskmandate-interview-page-and-voice-prompt`), and riskmandate.ai now has `interview-founder-marketing` (its v1.34.2 release note, `sources/sites/riskmandate.ai/versions/1.34.2.md`, calls it "the first interview page"). sgit.ai's briefs index still lists the ask as open. This is the first loose end the newsroom can close, and a good first story: a brief written on one site, built on another the same day.
- **Vault key management** is an open call for collaboration on sgit.ai, and Lesson Loop and Company X-Ray both depend on easy key handover.
- **Append lanes** appear in the telemetry brief, Lesson Loop, Connector Twin and the interview-page brief: one concept page should connect them.
- **Frozen, hashed sources**: pt.newsroom.sgit.ai does this for Portuguese sources; this newsroom does the same for the network; newsroom.sgit.ai argues for it. The three should point at each other.

**Loose-end seeds**

- A CLI transport fix sits on a local branch, not yet landed.
- The founder's own padel vault, the pilot for Lesson Loop, is not yet published.
- Fourteen partnership pages on sgit.ai are proposals; none records a contact made.
- Azure and GCP deployments exist and are not documented; S3-compatible stores other than Amazon S3 are untested (both stated on the cloud partnership pages).
- The RiskMandate partnership-risk brief is an open ask on sgit.ai's briefs index; check whether riskmandate.ai has responded, as it did to the interview-page brief.

## Step 6. The newsroom page, and about

The picture of the desks and the flow, filled from the data of 24 September. The about page with the honest sentence: in v0.1 the desks were run once, by one session, on a snapshot; nothing runs on a schedule yet; nothing has been reviewed by the editor of record.

## Not in the first version

- No schedule or automation. The daily run is a documented command (`05-daily-run.md`), run by hand.
- No deployment required. Make it ready for GitHub Pages, and do not deploy unless asked.
- No model calls from the site. Everything is built ahead of time.
- No pages about individuals. Roles and sites, not people.
