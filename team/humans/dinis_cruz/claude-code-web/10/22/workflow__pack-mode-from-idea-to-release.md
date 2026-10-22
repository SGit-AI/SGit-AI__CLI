# How pack mode went from an article to a release, and the documents along the way

**Dates:** 14–22 Oct 2026. **People:** Dinis (direction, decisions, the review on cli.sgit.ai, the merges to main); the CLI agent (this session: research, spec, implementation, trial, fixes); cli.sgit.ai's build agent (four verification rounds). **Result:** sgit-ai 0.24.0 with pack mode.

## The workflow, as it happened

1. **A problem with numbers.** The newsroom's "Scion and sgit" article claimed a 59 s clone of a small vault. The CLI agent reproduced it, found the real cause (a batch over the Lambda's response limit retried instead of split), fixed it (0.23.0), and wrote the response with measurements. The same work cloned the comms vault (35k objects, 527 MB) and recorded that a full clone took 3½ minutes: the real problem.
2. **Research before code.** Dinis asked for research with no code changes: keys and doors, policies, streaming, then native zip support. Each produced an article draft with live measurements on dev (what the API already allows: presigned multipart, Range on read-url, list, delete; 430 MB head bundle in 3 s; Zip64 verified to 70,000 members). A brief for the SG/Send team on presigned append was written and then parked when a client-only design appeared.
3. **The design conversation.** Over one afternoon the idea narrowed to its shape: a pack per push, a snapshot on the first push and on compaction, the listing as the index, deterministic zips, packs-only vaults (no dual write), CLI-only, a separate vault for the trial, an import from a full clone, an archive instead of deletes. Dinis's corrections along the way are in the spec (the `-imm-` cache contract; vault id is part of key derivation; no dual write).
4. **Spec, then review before build.** The spec went up; Dinis's "Pack mode, read closely" review on cli.sgit.ai gave five decisions (snapshot in its own folder, orphan rule, epoch seconds, scoped clones take packs whole, compression as an option); compression was measured on the comms vault's plaintext before it was accepted.
5. **Build with tests on disk.** Crypto envelope first (with the interop tests), then the packs module, the hooks, import/export, compaction, the CLI; 70-odd tests over a counted in-memory host, including performance gates on request counts and bytes; then the live trial on dev with the comms vault's history and the numbers written down. Throwaway vaults deleted after each run; the comms vault never written to.
6. **Verification by another agent, four rounds in one day.** cli.sgit.ai's build agent re-ran the suites, the how-to on dev, measured loose against pack, and reviewed the code with a reproducing script per finding: 8 findings, then 4, then 4 (one of them caused by a round-2 fix), then 3 nits and "no blockers". Each round got a point-by-point response, a test per finding, and threat-model rows. The reviewer's live check against the released 0.23.0 from PyPI settled the gate question.
7. **Release.** Merged to dev on Dinis's word; dev to main is Dinis's; the pipeline cuts 0.24.0; the email team's agents get `sgit init --packs` and the tester's page.

What made it work: measure before and after every claim; a spec reviewed before the build; tests that run the real code on disk against a counted host so "how many requests" is a measurement; a second agent with its own repro scripts; and a response document for every review so nothing is answered only in chat.

## The documents, in order

| Date | Document | What it is |
|---|---|---|
| 10/16 | `10/16/response__scion-and-sgit-article.md` | The reply to the newsroom article, with the batch fix and its numbers |
| 10/16 | `10/16/article-draft__one-vault-ten-agents-measured.md`, `article-draft__sgit-is-a-standard-one-hash-away.md` | Two article drafts from the same evidence |
| 10/16 | `10/16/research__keys-pki-cow__coverage-map.md`, `article-draft__keys-the-way-git-does-it.md`, `article-draft__copy-on-write-and-the-vault.md` | Research: native keys, doors, current-version-only files, copy-on-write |
| 10/16 | `10/16/article-draft__policies-the-vault-enforces.md`, `article-draft__streaming-changes.md` | Research: vault-enforced policies, streaming changes with provenance |
| 10/20 | `10/20/article-draft__native-zip-support.md` | Research: zip as a native transfer and storage unit, with live measurements and the Zip64 facts |
| 10/20 | `10/20/brief__to-sg-send-team__zip-append-via-s3.md` | A server-side brief (presigned append); parked |
| 10/21 | `10/21/article-draft__a-pack-per-push.md` | The article that explains the design |
| 10/21 | `10/21/spec__pack-mode.md` | The spec, with Dinis's review decisions and the build notes |
| 10/21 | `10/21/note__pack-mode-round-trip.md` | What was built, how the round trip is tested, every measurement (synthetic gates, the live trial, the reviewer's numbers) |
| 10/21 | `10/21/howto__test-pack-mode.md` | The tester's page: step by step on throwaway vaults, what to report, known limits |
| 10/21–22 | `10/21/response__pack-mode-verification.md`, `…-round-2.md`, `…-round-3.md`, `…-round-4.md` | The four review responses, finding by finding |
| 10/22 | `10/22/feature-reference__pack-mode.md` | The one-page reference for the release notes and the feature documentation |
| — | `CHANGELOG.md` (0.24.0), `team/explorer/appsec/threat-model/v0.21.0__threat-model.md` (TM-F37, TM-R38..R40) | The release record and the security record |
| — | `tests/unit/pack/`, `tests/unit/pack/test_Pack_Vault__Review_10_21.py`, `tests/security/test_Security__Fixed__Pack_Members.py` | The tests, including one per review finding: a map of the ways a pack vault can go wrong |

The reviewer's own reports (four markdown files) live with the cli.sgit.ai team; their findings are quoted in the responses above.
