## `verify` in sgit_ai/crypto/PKI__Crypto.py (L71-L76)

```python
# L72-L76
r       = int.from_bytes(signature_raw[:32], 'big')
s       = int.from_bytes(signature_raw[32:], 'big')
der_sig = asym_utils.encode_dss_signature(r, s)
public_key.verify(der_sig, data, ec.ECDSA(hashes.SHA256()))
return True
```

**Purpose:** Verifies a raw `r||s` signature. The return value is only ever `True`; failure is an exception from `public_key.verify` (`InvalidSignature`). Every caller must therefore catch, and the ones that treat the bool as the answer (`Vault__Sync__Tag.py:L208` `ok = PKI__Crypto().verify(...)`) get `True` or an exception, never `False`.

**Inputs & Assumptions:**
- `public_key`: the key whose file decrypted under the read key (`Vault__Signatures.py:L38`) or a keyring contact's PEM. Trust: a read-key holder can mint one (TM-R01).
- `signature_raw` (bytes): Trust: **untrusted**. No length check: `[:32]`/`[32:]` on a shorter or longer input produce different `(r, s)`; a 65-byte input puts 33 bytes into `s`. Any such mismatch fails verification at L75 (`test_PKI__Crypto__Hardening.py::test_verify__truncated_signature_fails`, `::test_verify__corrupted_signature_fails`). Nothing here rejects odd lengths up front: **nothing found**, by construction they fail inside the library.
- `data` (bytes): what the caller claims was signed.

**Outputs & Effects:** `True` or raises. Pure.

**Cross-Function Dependencies:**
- Callee `public_key.verify` (external-black-box).
- Callers and how they handle the exception: `Vault__Commit.verify_signature` (`sgit_ai/storage/Vault__Commit.py:L122-L128`: `try` per candidate, `except Exception: continue`, returns False); `hybrid_decrypt` L147-L153 (`except Exception` → `verified=False`); `CLI__PKI.cmd_verify` L142-L145 (`except Exception` → exit); `Vault__GC._verify_pack_signature` L110; `Vault__Sync__Tag.py:L208` (handling not read in this slice).

**Open Questions:**
- unclear; need to inspect `Vault__Sync__Tag.py:L200-L215` to confirm the exception from a bad tag signature is caught rather than aborting the command.
