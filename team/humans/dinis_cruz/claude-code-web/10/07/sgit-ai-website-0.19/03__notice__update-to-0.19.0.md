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

**Message 2**, on any command, once the owner has raised the vault:
`this vault needs sgit-ai >= 0.19.0 and this is 0.18.0: run sgit update`. Do exactly that.

## 3. If you are the vault owner

Raise a vault only once every agent writing to it is on 0.19.0; an older agent would fail on
a raised vault with a validation error instead of the message above. Then:

```
$ sgit vault format --set 2 --min-client 0.19.0
```

New objects get 128-bit ids, old ones stay, no move. The guide *History integrity* has the rest.
