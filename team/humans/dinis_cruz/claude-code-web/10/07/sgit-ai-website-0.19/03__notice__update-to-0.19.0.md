# Update sgit-ai to 0.19.0

*Two minutes. For an agent, or a person running agents, told "read this and update".*

## 1. Update and check

```
$ sgit update
$ sgit version
sgit-ai v0.19.0
```

## 2. What changes for you: nothing, until the vault owner raises the vault

Every command works as in 0.18.0. Three things are new, and two messages you might see.

| New | What it means for you |
|---|---|
| `sgit check verify` | lists how many commits in the vault have a verifiable signature. Read-only |
| `sgit vault format` | shows the vault's format and minimum client. Only the vault owner changes it |
| `sgit check fsck` | now takes seconds, not minutes, and prints a signature summary |

**Message 1**, on `status` or `pull`:
`the named branch was REWOUND or rewritten on the server`. Someone force-pushed, or the server
served an old pointer. Do not accept it on your own; tell the vault owner. If the owner says it
was deliberate: `sgit pull --accept-rewind`.

**Message 2**, on any command, once the owner has raised the vault and you are on 0.19.0 or
newer but below the vault's minimum: `this vault needs sgit-ai >= X.Y.Z and this is …: run
sgit update`. Do exactly that.

**Message 3**, if you are still on 0.18.0 or older when the owner raises the vault. Your
client cannot know about the gate, so it blames the data:

```
error: integrity check refused vault data … the host served corrupt or substituted content   (clone)
error: missing file — object obj-cas-imm-… is not in the local store … try "sgit check fsck"  (pull)
```

Neither hint applies. Do not run `vault move` or `fsck --repair`. Run `sgit update` and retry.

## 3. If you are the vault owner

Raise a vault only once every agent writing to it is on 0.19.0; an older agent fails on a
raised vault with the misleading "refused" / "missing file" messages above, not with "update".
Then:

```
$ sgit vault format --set 2 --min-client 0.19.0
```

New objects get 128-bit ids, old ones stay, no move. The guide *History integrity* has the rest.
