=== TASK 2: Identity storage (known_identities table + embeddings) ===

**Files:**
- Modify: `secur/storage.py`
- Test: `tests/test_identity_storage.py`

**Interfaces:**
- Consumes: `IDENTITY_EMBEDDINGS_DIR` from `secur.config` (already added in Task 1).
- Produces: `add_identity(name, species, embedding_path) -> int`, `list_identities() -> List[dict]`, `get_identity(identity_id) -> dict|None`, `remove_identity(identity_id) -> bool`, `save_identity_embedding(name, embedding: np.ndarray) -> str`, `load_identity_embedding(identity_id) -> np.ndarray|None`.

Steps:
1. Write `tests/test_identity_storage.py`:
```python
import numpy as np
from secur.storage import EventStorage


def test_known_identities_crud(tmp_path, monkeypatch):
    import secur.config as cfg
    monkeypatch.setattr(cfg, "IDENTITY_EMBEDDINGS_DIR", tmp_path / "emb")
    (tmp_path / "emb").mkdir(exist_ok=True)
    from secur import storage as storage_mod
    monkeypatch.setattr(storage_mod, "IDENTITY_EMBEDDINGS_DIR", tmp_path / "emb")

    db = EventStorage(tmp_path / "events.db")
    emb = np.random.rand(128).astype(np.float32)
    path = db.save_identity_embedding("João", emb)
    assert (tmp_path / "emb" / path.split("/")[-1]).exists()

    ident_id = db.add_identity("João", "person", path)
    loaded = db.load_identity_embedding(ident_id)
    assert loaded is not None and loaded.shape == (128,)

    rows = db.list_identities()
    assert len(rows) == 1 and rows[0]["name"] == "João" and rows[0]["species"] == "person"

    assert db.remove_identity(ident_id) is True
    assert db.list_identities() == []
    db.close()
```
2. Run `python -m pytest tests/test_identity_storage.py -v` → expect FAIL (`AttributeError` on `save_identity_embedding`).
3. In `secur/storage.py`, add import at top:
```python
import time
import numpy as np
from .config import DB_PATH, IDENTITY_EMBEDDINGS_DIR
```
Add the `known_identities` table inside `_create_tables` (after the `zones` table creation):
```python
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS known_identities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        species TEXT NOT NULL DEFAULT 'person',
        created_at TEXT NOT NULL,
        embedding_path TEXT NOT NULL
    )
    """
)
```
Add these methods to `EventStorage` (after `seed_zones`):
```python
def save_identity_embedding(self, name: str, embedding: np.ndarray) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in name)
    filename = f"{safe}_{int(time.time() * 1000)}.npy"
    path = IDENTITY_EMBEDDINGS_DIR / filename
    np.save(str(path), np.asarray(embedding, dtype=np.float32))
    return str(path)

def add_identity(self, name: str, species: str, embedding_path: str):
    timestamp = datetime.utcnow().isoformat() + "Z"
    with self.lock:
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO known_identities (name, species, created_at, embedding_path) VALUES (?, ?, ?, ?)",
            (name, species, timestamp, embedding_path),
        )
        self.connection.commit()
        return cursor.lastrowid

def list_identities(self):
    with self.lock:
        cursor = self.connection.cursor()
        cursor.execute("SELECT id, name, species, created_at FROM known_identities ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]

def get_identity(self, identity_id: int):
    with self.lock:
        cursor = self.connection.cursor()
        cursor.execute("SELECT id, name, species, created_at, embedding_path FROM known_identities WHERE id = ?", (identity_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def load_identity_embedding(self, identity_id: int):
    ident = self.get_identity(identity_id)
    if not ident:
        return None
    from pathlib import Path
    p = Path(ident["embedding_path"])
    if not p.exists():
        return None
    return np.load(str(p))

def remove_identity(self, identity_id: int):
    ident = self.get_identity(identity_id)
    if not ident:
        return False
    try:
        from pathlib import Path
        Path(ident["embedding_path"]).unlink(missing_ok=True)
    except Exception:
        logger.warning("Falha ao remover arquivo de embedding para identidade %s", identity_id)
    with self.lock:
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM known_identities WHERE id = ?", (identity_id,))
        self.connection.commit()
        return cursor.rowcount > 0
```
4. Run `python -m pytest tests/test_identity_storage.py -v` → expect PASS.
5. Commit: `git add secur/storage.py tests/test_identity_storage.py && git commit -m "feat(storage): add known_identities table and embedding persistence"`
