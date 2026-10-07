# Addendum to the SG/Send team: what the live API run showed (7 Oct, evening)

**Sequencing update:** the gate, `author_key_id`, warn-mode verification, ref monotonicity and
format 2 all ship together as **sgit-ai 0.19.0** (one merge), not as 0.19 then 0.20. Nothing
changes for an un-raised vault; a vault is raised per owner decision with `sgit vault format`.

Everything in your reply held on the live dev Lambda; one shape to confirm, one request.

1. **Q1 confirmed from our side**: 44-character object names written, read, batch-read and
   listed on `dev.send.sgraph.ai` from a mixed-id vault (`th8bfzj1`, left on the server for you
   to open in the vault UI: ids of both widths in one tree).
2. **`write-if-match` conflict shape**: a stale match returns **HTTP 200** with
   `results[i].status == "conflict"` and `results[i].current` (base64 of the stored bytes).
   Our index writer now handles that (it had only looked at a top-level status, which is the
   in-memory server's shape). Please keep that shape stable, or tell us if the user Lambda will
   move to a 409/412; we handle both.
3. **The index merge is live on our side**: the CLI's `pull` repairs the single-entry overwrite
   (tested against the real server: 3 branches and the gate restored after an overwrite). Your
   read-modify-write fix is still what makes the gate reliable *between* CLI pulls.
4. **Request**: when `list` gets its continuation token, name the field and we ship the client
   side in the same release (the clone sweep is the only caller).
