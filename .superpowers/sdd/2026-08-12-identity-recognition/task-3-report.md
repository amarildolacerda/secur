# Task 3 Report — IdentityRecognizer core module

## Status
DONE_WITH_CONCERNS

## Commit hash(es)
- 37ce161 (secur/identity.py + tests/test_identity.py)

## Test summary
`tests/test_identity.py`: 3 passed, 1 failed (test_recognize_falls_back_to_reid).
Passing: test_cosine_similarity_basic, test_recognize_known_and_unknown, test_decide_event_routing.
Failing: test_recognize_falls_back_to_reid.

## Concerns
The brief instructs both files to be written verbatim, and the implementation block is reproduced exactly (with the authorized `_embed` typo correction `if emb is not None:`). However, the brief's own test stub is incompatible with that verbatim implementation:

```python
db = type("S", (), {"list_identities": lambda: [], "load_identity_embedding": lambda i: None})()
```

`IdentityRecognizer._refresh_cache` calls `self.storage.list_identities()`. Because Python binds plain functions as instance methods, `db.list_identities()` passes `self` to a 0-argument lambda, raising `TypeError: <lambda>() takes 0 positional arguments but 1 was given`. This is a defect in the test stub, not in `secur/identity.py` — the actual `EventStorage.list_identities(self)` (Task 2) works correctly, as shown by the passing `test_recognize_known_and_unknown` test which uses a real `EventStorage`.

Recommended fix (must be applied to the test, not the module, to stay verbatim on `secur/identity.py`):
- Make the stub methods accept the instance, e.g. `list_identities: lambda self: []`, or wrap with `staticmethod`, or use `type("S", (), {...})` with `staticmethod(...)`.
- Alternatively, the brief may intend the stub to subclass `EventStorage`.

Environment note: the system `python`/`python3` commands are Microsoft Store aliases with no interpreter; tests were run with `py -3.14 -m pytest` (Python 3.14.6, numpy 2.5.2, pytest 9.1.1), which satisfy the project's Python 3.14 target.

## Fix note (2026-08-12)
- Status: FIXED.
- Commit hash: 00aad28 (`test(identity): fix fake db stub binding in test_recognize_falls_back_to_reid`).
- Test summary: `tests/test_identity.py` — 4 passed, 0 failed. `test_recognize_falls_back_to_reid` was repaired by wrapping the fake `db` lambdas in `staticmethod(...)` so they are not bound as instance methods (avoids the injected `self` / `TypeError`). `secur/identity.py` was left unchanged.
