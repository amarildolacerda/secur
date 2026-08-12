# Task 2 Report — Identity storage (known_identities table + embeddings)

**Status:** DONE

**Commit hash(es):** 4da4380

**Test summary:** `tests/test_identity_storage.py::test_known_identities_crud` PASSED — full CRUD (save embedding, add/list/get/load/remove identity) verified against a temp DB.

**Concerns:**
- `datetime.utcnow()` is deprecated in Python 3.14 (emits DeprecationWarning). The code follows the existing `add_event`/`add_zone` pattern which also uses `utcnow()`; left as-is for consistency. Consider a later cleanup to timezone-aware UTC across storage.
- `save_identity_embedding` / `load_identity_embedding` write/read `.npy` files in a shared module-level `IDENTITY_EMBEDDINGS_DIR`. The test monkeypatches both `secur.config` and `secur.storage` module attributes to point at the temp dir. If other code imports `IDENTITY_EMBEDDINGS_DIR` directly (not via the storage module), the monkeypatch wouldn't redirect them — no such usage exists yet.
- Embeddings are stored as unencrypted files on disk; acceptable per offline/lightweight constraint but worth noting for a surveillance system.
