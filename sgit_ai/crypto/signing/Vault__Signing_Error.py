class Vault__Signing_Error(Exception):
    """User signing (the signer's own SSH / OpenPGP key) failed or is misconfigured.
    Nothing was written: no commit, no ref move, no tag. Re-exported by core's
    Vault__Errors (crypto never imports core)."""
