## `_directory_of` in sgit_ai/core/actions/verify/Vault__Signatures.py (L89-L91)

**Purpose:** The vault root from a components object: `os.path.dirname(str(c.sg_dir))`.

**Inputs & Assumptions:** `c.sg_dir` is `<directory>/.sg_vault` (`Vault__Sync__Base._init_components` L365; `Vault__Components.sg_dir` is a plain `str`, `sgit_ai/core/Vault__Components.py:L20`). For the components built by `Step__Clone__Verify_Signatures` (L119-L128) `sg_dir` is `str(input.sg_dir)`, set by the clone pipeline to the same shape. Nothing checks the shape; a `sg_dir` without a parent would yield `''`.

**Outputs & Effects:** Returns a path string; no effects.

**Cross-Function Dependencies:** Called only by `verify_chain` L64, and only when `index is None`.

**Open Questions:** none.
