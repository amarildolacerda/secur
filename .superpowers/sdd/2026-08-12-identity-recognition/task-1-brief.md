=== TASK 1: Identity configuration ===

**Files:**
- Modify: `secur/config.py`
- Test: `tests/test_identity_config.py`

**Interfaces:**
- Produces: module-level constants `IDENTITY_ENABLED` (bool), `IDENTITY_FACE_MODEL_PATH` (str), `IDENTITY_REID_MODEL_PATH` (str), `IDENTITY_MATCH_THRESHOLD` (float), `IDENTITY_EMBEDDINGS_DIR` (Path).

Steps:
1. Write `tests/test_identity_config.py` asserting defaults:
   - `config.IDENTITY_ENABLED is False`
   - `config.IDENTITY_MATCH_THRESHOLD == 0.6`
   - `config.IDENTITY_FACE_MODEL_PATH == ""`
   - `config.IDENTITY_REID_MODEL_PATH == ""`
   - `config.IDENTITY_EMBEDDINGS_DIR.exists()`
2. Run `python -m pytest tests/test_identity_config.py -v` → expect FAIL (AttributeError).
3. In `secur/config.py` after the DETECTOR_* block add:
   ```python
   IDENTITY_ENABLED = os.getenv("IDENTITY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
   IDENTITY_FACE_MODEL_PATH = os.getenv("IDENTITY_FACE_MODEL_PATH", "")
   IDENTITY_REID_MODEL_PATH = os.getenv("IDENTITY_REID_MODEL_PATH", "")
   IDENTITY_MATCH_THRESHOLD = float(os.getenv("IDENTITY_MATCH_THRESHOLD", "0.6"))
   IDENTITY_EMBEDDINGS_DIR = DATA_DIR / "identities"
   IDENTITY_EMBEDDINGS_DIR.mkdir(exist_ok=True)
   ```
4. Run test → expect PASS.
5. Commit: `git add secur/config.py tests/test_identity_config.py && git commit -m "feat(config): add identity recognition env vars"`
