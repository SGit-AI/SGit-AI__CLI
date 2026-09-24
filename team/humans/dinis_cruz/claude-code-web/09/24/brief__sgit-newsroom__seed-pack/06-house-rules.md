# 06. House rules

These are the rules the sgit network's sites already work under. They apply to every page the newsroom publishes.

## Secrets

- **Never publish a vault key or any write credential.** A vault key looks like `sgit_private_vault_...`; anything matching `sgit_private_`, `sgit_vk1_`, or 24 lowercase alphanumerics, a colon, then 4 to 24 more (`[a-z0-9]{24}:[a-z0-9]{4,24}`) must never appear in the site or the repo. The validator must refuse it.
- **Read keys may be published, deliberately.** A `sgit_public_read_<hex>:<vault id>` key that a source site already publishes may be quoted, because the site published it on purpose.
- **Published examples are not secrets.** Some sources quote documented example credentials, for instance sg-compute.sgit.ai's security audit quotes AWS's `AKIAIOSFODNN7EXAMPLE`. The validator should allow a short, named list of such examples, not weaken the pattern.
- **Nothing from private channels.** The sources are the public sites. Do not add anything that was not published.

## Facts

- **Only what the sources say.** Every factual sentence links to the page it came from. If a source is ambiguous, say so.
- **Shipped and proposed are different words.** Most of the network publishes designs and proposals beside things that run. Keep the distinction the source makes, and never upgrade a proposal to a product.
- **Quote exactly.** A quotation is the source's words, character for character, or it is a paraphrase and has no quotation marks.
- **Corrections above the mistake.** When the newsroom gets something wrong, the correction is a new dated note at the top of the page, naming what was wrong and how it was caught. The old text stays, struck through or marked.
- **Compute, don't type.** Any count on a page (pages changed, releases, vaults) is computed by the build from the data.

## People

- **Roles and sites, not people.** Write about what a site or a desk did. The founder may be named as editor of record.
- **They/them** for anyone whose pronouns are not stated in a source.
- **No one who appears only in a private conversation.** If a source mentions a meeting, write about the idea, not the person.

## Style

- British English. Plain words. Short sentences.
- No em-dashes in prose (sgit.ai removed them on 20 September 2026; see its version log).
- No model names or identifiers in the site or the repo.
