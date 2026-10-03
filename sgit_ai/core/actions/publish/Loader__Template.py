"""The bundled loader template `sgit publish` emits as index.html.

Invariant I4: this file is BYTE-IDENTICAL across every vault and every
publish — nothing in a vault can change what publish emits, because vault
content is ciphertext at publish time. The loader's internal JavaScript is
the Web team's to author (00 §6); sgit only emits the file. Until the Web
team's template lands, this placeholder documents the contract it must
implement (01 §7) and renders the honest minimum.
"""

LOADER_TEMPLATE = """\
<!doctype html>
<!-- sgit loader — bundled template, byte-identical across every vault (invariant I4).
     Authored contract (01 section 7), implementation owned by the Web team:
       1. key discovery: #fragment, else a sgit_public_read_* file beside this page,
          else a stored key for this vault, else render cover.json and ask.
       2. classify the key BY DECLARATION (port of Vault__Crypto.classify_key):
          REFUSE sgit_private_vault_* — this page only ever needs a READ key.
       3. fragment hygiene (SP-6): strip via history.replaceState, never place the
          fragment in a link, an img/fetch URL, or follow a redirect carrying it.
       4. fetch api/vault/read/{vault_id}/{file_id}, else ../bare/{file_id};
          decrypt in-page; the host never receives the key (invariant I2).
-->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Encrypted vault</title>
</head>
<body>
<h1>&#128274; Encrypted vault</h1>
<p>This vault is published as ciphertext. This page and the host cannot read
its contents; a read key is required to open it.</p>
<p>Open this page over HTTP (<code>sgit vault serve</code>) with the vault's
loader application to browse it, or clone it with
<code>sgit clone &lt;read-key&gt;:&lt;vault-id&gt; --base-url &lt;this URL&gt;</code>.</p>
</body>
</html>
"""
