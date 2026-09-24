# For RiskMandate.ai: the risk side of the partnerships, and a risk mapping for sgit

**A build brief from the sgit.ai site team to the RiskMandate.ai team.** Status: open. Written 24 September 2026.

sgit.ai has just published partnership pages from the vault side: one for each cloud platform and one for each AI provider, with the argument for why sgit fits and what a partnership could be. Every one of those relationships has a second half that sgit.ai deliberately does not write, and that belongs to you: **how the choice of a service changes the risk.** The same agent, deployed with a managed identity service or without one, on a cloud's agent platform or on a laptop, through an API or through a consumer chat product, has a different Agent Behaviour Policy. That difference is the business case, and RiskMandate already has the grammar to state it.

This brief asks for two things. First, the risk side of each partnership, as pages on riskmandate.ai that mirror the sgit.ai ones. Second, a risk mapping for sgit itself, including GDPR and data protection, which is the business case for using sgit and is currently written nowhere.

## What to read first

Your own material, because the point is to extend it, not to start again:

- [The 16 Agent Behaviour Policy vaults](https://riskmandate.ai/agent-behaviour-policy.html), one per deployment shape, each with a grant, a mandate, a delta and a Licence to Operate.
- [The ABP model on abp.sgit.ai](https://abp.sgit.ai/), including the capability grammar (`verb.object.reach`), barriers, undo classes and the JSON at `/data/`.
- [Lab 01, the grant is user-shaped, not data-shaped](https://riskmandate.ai/lab-connector-grants.html), and [Lab 06, every routable address is in the grant](https://riskmandate.ai/lab-network-reach.html), which already cites AWS IAM permissions boundaries as the precedent that works.
- [nhi.sgit.ai's options page](https://nhi.sgit.ai/options/), the closest existing thing to "managed identity against building your own".
- [The Insurability Index](https://riskmandate.ai/insurance.html) and the evidence states on [store.sgit.ai's ledger](https://store.sgit.ai/v1/ledger/).

The sgit side you will be mirroring:

- [Partnerships](https://sgit.ai/partnerships/index.html), with [the cloud platforms hub](https://sgit.ai/partnerships/cloud-platforms.html) and [the AI providers hub](https://sgit.ai/partnerships/ai-providers.html), and one page per organisation linked from each.
- [Before you give an agent a connector, give the connector a twin](https://sgit.ai/articles/connector-twin-before-you-deploy-an-agent.html), whose table of what Gmail and Calendar can and cannot undo is an undo-class input you can reuse, with Google's sources.
- [The security model](https://sgit.ai/security/index.html), [when not to use sgit](https://sgit.ai/docs/limitations.html), [the regulated-sector page](https://sgit.ai/use-cases/health-regulated.html) and [what to do if a vault key is exposed](https://sgit.ai/case-studies/exposed-vault-key.html).

## What already exists, so it is not duplicated

- **ABPs for many of the products in question.** ChatGPT on the web, Claude on the web with connectors, Claude Code on the web and on the command line, Claude Desktop, Google Workspace MCP, Claude with Gmail, Gmail and Drive read-only, Claude with Microsoft 365, Dropbox MCP.
- **One managed-against-local pair.** Claude Code on the web, in an ephemeral managed container, against Claude Code on your own machine. Because the ABPs share one grammar, their counts can already be compared.
- **Identity for agents, compared.** nhi.sgit.ai assesses SPIFFE/SPIRE, a commercial workload-identity broker, and "do nothing: broad credential and hope", with profiles for Microsoft Entra Agent ID and Okta.
- **The browser question.** The Agentic Browser Isolation demo compares an agent in your logged-in browser with one in an isolated identity.

## The three gaps

- **Hyperscaler services are missing.** Cognito, Azure, Bedrock and Vertex appear nowhere on riskmandate.ai or abp.sgit.ai. AWS appears only as the IAM precedent in Lab 06. There is no ABP for any cloud's agent service.
- **Provider comparisons are missing, and so is API against consumer chat.** There are separate ChatGPT and Claude ABPs, but nothing sets providers side by side, and nothing compares using a model through its API with using the same model through a consumer product. ABPs model capability; they do not yet model data use, training, retention or residency.
- **There is no risk mapping for sgit.** The only material is the regulated-sector page on sgit.ai and the statement that sgit holds no compliance certification.

## Part A: the risk side of each partnership

Publish on riskmandate.ai one page per organisation on the sgit.ai partnership pages: AWS, Microsoft Azure, Google Cloud, IBM Cloud, the European clouds, DigitalOcean, Rackspace, Netlify, OpenAI, Anthropic, Mistral AI, Google Gemini, OpenRouter and ElevenLabs. Each page makes the business case in RiskMandate's own terms: **the same deployment, with and without the service, as two ABPs and the delta between them.** sgit.ai will link each of its partnership pages to the matching one.

The comparisons we think carry the most weight, in the order we would do them:

1. **Managed identity against your own.** Amazon Cognito, Microsoft Entra ID (including Entra Agent ID), and Google's identity services, against an application that manages its own users and credentials. What moves: the credential's barrier (a setting you can flip against a boundary enforced above the grant), revocation, the plug profile, and the evidence an underwriter will accept.
2. **A cloud's managed agent service against an agent on a laptop.** For example Amazon Bedrock's agent features, Microsoft's agent service in Azure AI Foundry, and Google's Gemini Enterprise Agent Platform, which is what Vertex AI's documentation now calls it. Please confirm each current product name on the provider's own page before publishing. What moves: reach classes (`host` to `tenant`), network reach, the kill switch, and who can pull the plug.
3. **API against consumer chat.** The same model through OpenAI's API and through ChatGPT on the web; through Anthropic's API and through Claude on the web. The sgit.ai provider pages cite the data facts, with sources: whether data is used for training by default, zero data retention availability, and data residency. These are not capabilities, so they need a place in the ABP. The `material` property proposed in Lab 01 is the nearest existing idea, and a data-handling property on the grant may be the cleanest answer. That is your call.
4. **Provider against provider.** OpenAI, Anthropic, Mistral and Google side by side, in one grammar. Include OpenRouter as a case of its own. Its routing flags, `zdr: true` and `data_collection: "deny"`, are a setting per request rather than a boundary, and that distinction is exactly what the barrier ladder is for.
5. **Plain object storage against a vault.** Any cloud's object storage holding plaintext, against the same data in an sgit vault on that storage. This is the bridge to Part B.

Rules for Part A:

- **Facts come from the provider's own pages,** linked and dated, as on the sgit.ai pages. Where a fact is unverified, say so.
- **Evidence states stay honest:** Measured, Derived or Documented, as the ABP vaults already do.
- **No verdicts on providers.** An ABP "describes and it does not judge". The comparison shows where the delta moves; the reader decides.
- **Not fear.** Every difference is a documented behaviour, not a scenario.

## Part B: a risk mapping for using sgit

This is the one we forgot to ask for, and it may matter most. **Why use sgit? Because it removes specific risks, and the business case should say which, in RiskMandate's grammar and against named obligations.** Write sgit up as a control: the same data and the same agent, with and without a vault.

What we expect the mapping to find, for you to confirm or correct:

- **The host's reach drops to ciphertext.** Without a vault, whoever hosts the data can read it. With one, the host holds ciphertext under opaque identifiers and never a key. That is a boundary, not a setting.
- **Credentials declare themselves.** Vault keys, private read keys and public read keys carry different prefixes, so one secret-scanner rule catches every private key type. That is a detection control with a measurable effect.
- **History turns many actions into "undo: yes".** Every earlier version of every file is kept. For content edits, the undo class moves from "no" to "yes".
- **Revocation is weaker than people expect.** A vault key is a bearer credential with no revocation list. The only remedy for an exposed key is rotation. That is a residual risk to state plainly, with an owner.
- **Recovery does not exist by design.** Lose the key and the vault is gone. That is a residual risk too, and [the key management call for collaboration](https://sgit.ai/partnerships/vault-key-management.html) is sgit's answer in progress.

Then the data protection mapping. Please verify each article's text before citing it, and point at provisions rather than asserting, in the house style of [standards.sgit.ai](https://standards.sgit.ai/):

- **GDPR Article 32, security of processing,** names encryption of personal data as an appropriate measure. That is the headline.
- **GDPR Article 25, data protection by design and by default.** Client-side encryption and minimal server knowledge are design choices, and should be described as such, not as compliance.
- **GDPR Article 34, notifying data subjects of a breach.** Article 34(3)(a) relieves the controller of notifying data subjects where the data was rendered unintelligible, for example by encryption. For a breach of a vault host, this may be the single most concrete business case, and it needs careful, sourced wording.
- **GDPR Article 28, processors.** sgit.ai's regulated-sector page already says storing ciphertext may still be processing, so a host is not automatically outside the processor relationship. Keep that caveat.
- **GDPR Article 17, erasure, against history.** Vault history keeps old ciphertext. Erasure therefore means rotation, re-keying or destroying the key. That is a real tension and should be mapped as one.
- **International transfers.** The EDPB's Recommendations 01/2020 on supplementary measures discuss encrypted storage with a provider in a third country, where the keys stay with the exporter. Check the current text and use case before relying on it.
- **Beyond GDPR:** the UK GDPR and Data Protection Act 2018, and the controls in ISO/IEC 27001 that concern cryptography and key management, which standards.sgit.ai already models.

What to publish:

- **An sgit risk mapping as a vault,** in the ABP vault format, with a read key, so sgit.ai can list it with the others.
- **A page on riskmandate.ai, "What sgit removes, and what it leaves",** written as the business case for adopting sgit: the risks reduced, the residual risks with their owners, and the obligations each one touches. sgit.ai will link it from its security page and from every partnership page.

Rules for Part B:

- **sgit holds no compliance certification of any kind,** and nothing may suggest otherwise.
- **"A link means touched and never complies."** Every citation of a legal provision is a pointer, not a claim of conformance.
- **Read keys yes, vault keys never,** in anything you publish, as on sgit.ai.

## Two inconsistencies we noticed while reading

- **Prices disagree.** Level 1 is £10 on riskmandate.ai's pricing page and £5 on store.sgit.ai's policies and on the licence page.
- **GDPR is modelled in one place and denied in another.** sgit.ai lists a "Standards Atlas: GDPR" vault, while standards.sgit.ai still says "There is no GDPR graph". One of them needs updating, and Part B will need whichever is right.

## Before you call it done

- Every organisation on the sgit.ai partnership pages has a matching riskmandate.ai page, or a stated reason it does not.
- Every comparison is two ABPs and a delta, in the existing grammar, with evidence states.
- Every provider fact is linked to the provider's own page and dated.
- The sgit mapping names at least one residual risk it cannot remove, and names its owner.
- Every GDPR citation points at the provision's text, and no sentence says "compliant".
- No vault key appears anywhere.

## What sgit.ai will do when this lands

Link each partnership page to its risk twin, link the security page to "What sgit removes, and what it leaves", list the sgit risk mapping vault among the published vaults, and record the handover in the briefs index.

## The prompt to hand the builder agent

```
You are working on riskmandate.ai. Read this brief in full, then read the RiskMandate material it lists under "What to read first", then the sgit.ai partnership pages.

Part A. For each organisation on https://sgit.ai/partnerships/cloud-platforms.html and https://sgit.ai/partnerships/ai-providers.html, publish a riskmandate.ai page that states the business case as two Agent Behaviour Policies, the same deployment with and without the service, and the delta between them. Work in this order: managed identity against your own; a cloud's managed agent service against an agent on a laptop; API against consumer chat; provider against provider, with OpenRouter's routing flags as a setting; plain object storage against a vault. Use the existing grammar (grant, mandate, delta, barrier, undo class, verb.object.reach) and evidence states (Measured, Derived, Documented). Link and date every provider fact. Do not judge providers.

Part B. Write sgit up as a control: the same data and agent with and without a vault. Map host reach, self-declaring key prefixes, history as undo, bearer keys with rotation as the only remedy, and no recovery. Then map GDPR Articles 32, 25, 34(3)(a), 28 and 17, and international transfers under EDPB Recommendations 01/2020, each verified against the current text and cited as a pointer, never as compliance. Publish it as an ABP-format vault with a read key, and as a page titled "What sgit removes, and what it leaves".

Rules: public material only; sgit holds no certification; a link means touched and never complies; read keys may be published, vault keys never. Finish with the checklist under "Before you call it done".
```
