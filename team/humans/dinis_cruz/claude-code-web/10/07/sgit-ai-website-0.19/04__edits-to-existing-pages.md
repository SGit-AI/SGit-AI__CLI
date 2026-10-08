# Edits to pages published for 0.18.0

## Agents sharing one vault

Under **`sgit status` before you commit**, after the `50+` paragraph, add:

> It can also say `the named branch was REWOUND or rewritten on the server`. That is not a
> count to trust; it means the remote pointer no longer descends from what this clone last
> accepted. Do not `--accept-rewind` on your own; tell the vault owner (see *History
> integrity*).

Under **When something is slow or fails**, add two bullets:

> - **`error: this vault needs sgit-ai >= X.Y.Z and this is …`**: the vault owner raised the
>   vault's minimum client. `sgit update`, then retry.
> - **`error: integrity check refused vault data …` on a clone, or `error: missing file …
>   try "sgit check fsck"` on a pull, on a vault whose owner has raised it**: your sgit is older
>   than 0.19.0 and cannot read the vault's new objects. `sgit update`; do not run `vault move`
>   or `fsck --repair`.
> - **`error: the remote named branch was rewound or rewritten`**: nothing was changed on your
>   side. If the owner confirms a deliberate force push, `sgit pull --accept-rewind`.

In **A session, end to end**, the first line's expected output becomes `sgit-ai v0.19.0`.

## Partial clones

No behaviour change. In *Commands that need the whole vault*, `sgit check verify` works on a
partial clone (it checks what the clone holds) and can be listed with `fsck` as "works on a
scoped clone; walks to the boundary on a shallow one".

## Working with AI agents

In *Multi-agent collaboration*, one sentence after the peer-review paragraph:

> Since 0.19.0 a vault can require signed commits and refuse clients older than a version its
> owner sets; see *History integrity*.

## Update sgit-ai to 0.18.0

Add a line at the top: "0.19.0 is out; the update page for it is *Update sgit-ai to 0.19.0*."
