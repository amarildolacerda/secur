# SDD ledger — plan: docs/superpowers/plans/2026-08-12-identity-recognition.md

Task 1: complete (commits ac63599..5992f63, review clean)
Task 2: complete (commits 5992f63..4da4380, review clean)
Task 2: minor (deferred): redundant inline `from pathlib import Path` at storage.py:217,228; name-based embedding filename collision theoretically possible (low risk)
Task 3: complete (commits 4da4380..00aad28, review clean)
Task 3: minor (deferred): `build_recognizer` uses `__import__("os").path.exists` instead of top-level `import os` (identity.py:138-141)
Task 4: complete (commits 00aad28..0070383, review clean after fix round 1/5)
Task 4: fix round 1/5 (Important test-hygiene addressed: tests now call real handlers; commits 251724c..0070383, re-review PASS)

**Goals**

- **Primary:** Add identity recognition to the pipeline: enrollment, embedding persistence, recognition (face/reid fallback), identity-based event routing.
- **Secondary:** Keep the implementation lightweight and offline-first (local `.npy` embeddings, SQLite storage), follow existing env-var configuration patterns, and remain compatible with Raspberry Pi constraints.

**Constraints**

- **Data storage:** embeddings stored as `.npy` files in `data/identities` (module-level `IDENTITY_EMBEDDINGS_DIR`).
- **Config style:** use environment variables following existing conventions in `secur/config.py`.
- **Compatibility:** prefer numpy + SQLite; avoid heavy runtime dependencies by default.
- **Security/privacy:** embeddings are currently unencrypted on disk (accepted trade-off for MVP but documented as a concern).

**Architecture (high level)**

- **Modules:** `secur/config.py`, `secur/storage.py`, `secur/identity.py`, plus tests under `tests/`.
- **Runtime flow:** video frame → detector → crop → embed (face or reid) → `IdentityRecognizer.recognize()` → `decide_event()` → alerts/handlers.
- **Persistence:** `EventStorage` manages the `known_identities` table and saves embedding files via `save_identity_embedding` / `load_identity_embedding`.

**Mapping: SDD items → code & tests**

- **Task 1 — Identity configuration:** implements env vars and `IDENTITY_EMBEDDINGS_DIR` in `secur/config.py`; test: [tests/test_identity_config.py](tests/test_identity_config.py#L1).
- **Task 2 — Identity storage:** adds `known_identities` table and embedding persistence APIs in `secur/storage.py`; test: [tests/test_identity_storage.py](tests/test_identity_storage.py#L1).
- **Task 3 — IdentityRecognizer:** implements `secur/identity.py` with `IdentityRecognizer`, `cosine_similarity`, `decide_event`, embedder helpers and `build_recognizer`; test: [tests/test_identity.py](tests/test_identity.py#L1).

**Open/Deferred Notes**

- Redundant inline `from pathlib import Path` occurrences in `secur/storage.py` (noted at two sites); low-priority cleanup.
- Minor style: `build_recognizer` currently uses `__import__("os").path.exists` instead of a top-level `import os` — cosmetic and safe but noted for cleanup.
- Embedding filename collision: filenames include a millisecond timestamp; name-based collisions are theoretically possible but low probability for MVP.

**Status update**

- Tasks 1–3: completed and validated (see individual task reports in this folder).
- Next: run the full identity-related test suite and validate integration with the main pipeline (Task 4).
