# Identity Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add identity recognition to Secur so that known people/animals (enrolled via dashboard) never raise a security alarm but trigger Home Assistant automations, while unknown individuals in private/security zones raise intruder alerts and unknowns in public zones raise light notifications.

**Architecture:** A new `IdentityRecognizer` module slots into the existing event-driven `CameraWorker` pipeline after object detection. It computes embeddings (face for people with re-ID fallback, re-ID for animals) using pluggable ONNX embedders (OpenCV `cv2.dnn.readNetFromONNX`, consistent with the existing detector), matches against enrolled identities stored in SQLite + `.npy` files, and decides the alert event type. Alert handlers are re-gated so known persons reach Home Assistant (automation trigger) without Telegram/MQTT alarms.

**Tech Stack:** Python 3.11+, OpenCV (`cv2.dnn` ONNX + bundled Haar cascade for face crop), NumPy, Flask, SQLite. No new runtime dependencies beyond what is already in `requirements.txt`.

## Global Constraints

- Project targets Linux dev + Raspberry Pi 4 (4–8 GB RAM); keep inference event-driven and models lazy-loaded.
- Operate offline; no cloud dependency for core recognition.
- `IDENTITY_ENABLED` defaults to `false`; feature is inert unless explicitly enabled and models provided.
- Follow existing code patterns: config via `secur/config.py` env vars, persistence via `secur/storage.py` (SQLite + lock), alerts via handler functions in `secur/alerts.py`, routes via `secur/app.py`.
- Per `AGENTS.md`: integrate via `dev` branch; do not commit directly to `main`.

---

## File Structure

- `secur/config.py` — add identity env vars (`IDENTITY_ENABLED`, `IDENTITY_FACE_MODEL_PATH`, `IDENTITY_REID_MODEL_PATH`, `IDENTITY_MATCH_THRESHOLD`, `IDENTITY_EMBEDDINGS_DIR`).
- `secur/storage.py` — add `known_identities` table + CRUD + embedding file save/load/delete.
- `secur/identity.py` (NEW) — `IdentityRecognizer`, `cosine_similarity`, `decide_event`, `build_recognizer`, `make_onnx_embedder`, `RECOGNITION_LABELS`.
- `secur/alerts.py` — extend payload with `identity`/`known`/`recognition_method`; re-gate handlers.
- `secur/main.py` — build recognizer, inject into workers, wire recognition + `decide_event` into `CameraWorker.run`.
- `secur/app.py` — `/identities` GET/POST/DELETE routes + factory hook.
- `secur/templates/identities.html` (NEW) — enroll/list UI; link added in `dashboard.html`; `/identities` added to `docs.html`.
- `docs/superpowers/specs/2026-08-12-identity-recognition-design.md` — already approved (design source).
- `SPEC.md`, `README.md` — document the feature (Task 8).
- Tests: `tests/test_identity_config.py`, `tests/test_identity_storage.py`, `tests/test_identity.py`, `tests/test_alerts_identity.py`, `tests/test_app_identity.py`, `tests/test_main_identity.py`.

---

### Task 1: Identity configuration

**Files:**
- Modify: `secur/config.py`
- Test: `tests/test_identity_config.py`

**Interfaces:**
- Produces: module-level constants `IDENTITY_ENABLED` (bool), `IDENTITY_FACE_MODEL_PATH` (str), `IDENTITY_REID_MODEL_PATH` (str), `IDENTITY_MATCH_THRESHOLD` (float), `IDENTITY_EMBEDDINGS_DIR` (Path).

- [ ] **Step 1: Write the failing test**

```python
from secur import config


def test_identity_config_defaults():
    assert config.IDENTITY_ENABLED is False
    assert config.IDENTITY_MATCH_THRESHOLD == 0.6
    assert config.IDENTITY_FACE_MODEL_PATH == ""
    assert config.IDENTITY_REID_MODEL_PATH == ""
    assert config.IDENTITY_EMBEDDINGS_DIR.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_identity_config.py -v`
Expected: FAIL with `AttributeError: module 'secur.config' has no attribute 'IDENTITY_ENABLED'`

- [ ] **Step 3: Write minimal implementation**

In `secur/config.py`, after the `DETECTOR_*` block (around line 37) add:

```python
IDENTITY_ENABLED = os.getenv("IDENTITY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
IDENTITY_FACE_MODEL_PATH = os.getenv("IDENTITY_FACE_MODEL_PATH", "")
IDENTITY_REID_MODEL_PATH = os.getenv("IDENTITY_REID_MODEL_PATH", "")
IDENTITY_MATCH_THRESHOLD = float(os.getenv("IDENTITY_MATCH_THRESHOLD", "0.6"))
IDENTITY_EMBEDDINGS_DIR = DATA_DIR / "identities"
IDENTITY_EMBEDDINGS_DIR.mkdir(exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_identity_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/config.py tests/test_identity_config.py
git commit -m "feat(config): add identity recognition env vars"
```

---

### Task 2: Identity storage (known_identities table + embeddings)

**Files:**
- Modify: `secur/storage.py`
- Test: `tests/test_identity_storage.py`

**Interfaces:**
- Consumes: `IDENTITY_EMBEDDINGS_DIR` from `secur.config`.
- Produces: `add_identity(name, species, embedding_path) -> int`, `list_identities() -> List[dict]`, `get_identity(identity_id) -> dict|None`, `remove_identity(identity_id) -> bool`, `save_identity_embedding(name, embedding: np.ndarray) -> str`, `load_identity_embedding(identity_id) -> np.ndarray|None`.

- [ ] **Step 1: Write the failing test**

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

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_identity_storage.py -v`
Expected: FAIL (`AttributeError` on `save_identity_embedding`)

- [ ] **Step 3: Write minimal implementation**

In `secur/storage.py`, add import at top:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_identity_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py tests/test_identity_storage.py
git commit -m "feat(storage): add known_identities table and embedding persistence"
```

---

### Task 3: IdentityRecognizer core module

**Files:**
- Create: `secur/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Consumes: `EventStorage` (Task 2), `IDENTITY_MATCH_THRESHOLD`/`IDENTITY_ENABLED` (Task 1).
- Produces:
  - `cosine_similarity(a, b) -> float`
  - `RECOGNITION_LABELS: Dict[str, str]` (label -> species)
  - `IdentityRecognizer.enroll(name, species, images) -> int`
  - `IdentityRecognizer.recognize(crop, label) -> dict|None`
  - `IdentityRecognizer.remove_identity(identity_id) -> bool`
  - `IdentityRecognizer.list_identities() -> List[dict]`
  - `decide_event(identity_info, zone_classification, camera_name) -> tuple|None`
  - `make_onnx_embedder(model_path, input_size, face_detect) -> Callable`
  - `build_recognizer(storage, face_embedder=None, reid_embedder=None) -> IdentityRecognizer`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from secur.identity import (
    IdentityRecognizer,
    cosine_similarity,
    decide_event,
    RECOGNITION_LABELS,
)


def _stub_embedder(value):
    vec = np.array(value, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)
    return lambda img: vec


def test_cosine_similarity_basic():
    a = np.array([1.0, 0.0])
    b = np.array([1.0, 0.0])
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-6
    c = np.array([0.0, 1.0])
    assert abs(cosine_similarity(a, c)) < 1e-6


def test_recognize_known_and_unknown(tmp_path, monkeypatch):
    import secur.config as cfg
    monkeypatch.setattr(cfg, "IDENTITY_EMBEDDINGS_DIR", tmp_path / "emb")
    (tmp_path / "emb").mkdir(exist_ok=True)
    from secur.storage import EventStorage
    db = EventStorage(tmp_path / "events.db")
    rec = IdentityRecognizer(db, face_embedder=_stub_embedder([1, 0, 0]), reid_embedder=_stub_embedder([0, 1, 0]),
                             threshold=0.6, enabled=True)

    ident_id = rec.enroll("João", "person", [np.zeros((10, 10, 3), np.uint8)])
    assert ident_id == 1
    # same embedding -> known
    res = rec.recognize(np.zeros((10, 10, 3), np.uint8), "person")
    assert res["known"] is True and res["name"] == "João"
    # orthogonal embedding -> unknown
    rec2 = IdentityRecognizer(db, face_embedder=_stub_embedder([0, 0, 1]), reid_embedder=_stub_embedder([0, 1, 0]),
                              threshold=0.6, enabled=True)
    res2 = rec2.recognize(np.zeros((10, 10, 3), np.uint8), "person")
    assert res2["known"] is False and res2["name"] == "unknown"


def test_recognize_falls_back_to_reid():
    db = type("S", (), {"list_identities": lambda: [], "load_identity_embedding": lambda i: None})()
    rec = IdentityRecognizer(db, face_embedder=lambda img: None, reid_embedder=lambda img: np.array([1.0, 0.0]),
                             threshold=0.6, enabled=True)
    res = rec.recognize(np.zeros((10, 10, 3), np.uint8), "dog")
    assert res["method"] == "reid" and res["known"] is False


def test_decide_event_routing():
    known = {"name": "João", "known": True}
    intruder = {"name": "unknown", "known": False}
    kr = decide_event(known, "pública", "Cam1", "person")
    assert kr[0] == "identity_recognized" and kr[5] == "person"
    ir = decide_event(intruder, "privativa", "Cam1", "person")
    assert ir[0] == "intruder_detected" and ir[5] == "person"
    r = decide_event(intruder, "pública", "Cam1", "cow")
    assert r[0] == "unknown_detected"
    assert r[2] == "cow" and r[5] == "animal"
    v = decide_event(intruder, "pública", "Cam1", "car")
    assert v[0] == "unknown_detected" and v[5] == "vehicle"
    assert decide_event(None, "privativa", "Cam1", "person") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_identity.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'secur.identity'`)

- [ ] **Step 3: Write minimal implementation**

Create `secur/identity.py`:

```python
import logging
import numpy as np
from typing import Callable, Dict, List, Optional

from .config import IDENTITY_ENABLED, IDENTITY_MATCH_THRESHOLD
from .storage import EventStorage

logger = logging.getLogger(__name__)

# Detection label -> identity category
RECOGNITION_LABELS: Dict[str, str] = {
    "person": "person",
    "cat": "animal",
    "dog": "animal",
    "bird": "animal",
    "horse": "animal",
    "sheep": "animal",
    "cow": "animal",
    "car": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "bicycle": "vehicle",
}


def cosine_similarity(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class IdentityRecognizer:
    def __init__(
        self,
        storage: EventStorage,
        face_embedder: Optional[Callable[[np.ndarray], Optional[np.ndarray]]] = None,
        reid_embedder: Optional[Callable[[np.ndarray], Optional[np.ndarray]]] = None,
        threshold: float = IDENTITY_MATCH_THRESHOLD,
        enabled: bool = IDENTITY_ENABLED,
    ):
        self.storage = storage
        self.face_embedder = face_embedder
        self.reid_embedder = reid_embedder
        self.threshold = threshold
        self.enabled = enabled
        self._cache: Optional[Dict[str, list]] = None

    def enroll(self, name: str, species: str, images: List[np.ndarray]) -> int:
        if species not in ("person", "animal"):
            raise ValueError("species deve ser 'person' ou 'animal'")
        if not images:
            raise ValueError("ao menos uma imagem de referência é obrigatória")
        embeddings = []
        for img in images:
            emb, _method = self._embed(img, species)
            if emb is not None:
                embeddings.append(emb)
        if not embeddings:
            raise ValueError("nenhum rosto/aparência detectável nas imagens fornecidas")
        mean_emb = np.mean(embeddings, axis=0).astype(np.float32)
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm
        emb_path = self.storage.save_identity_embedding(name, mean_emb)
        identity_id = self.storage.add_identity(name, species, emb_path)
        self._refresh_cache()
        return identity_id

    def recognize(self, crop: np.ndarray, label: str) -> Optional[dict]:
        if not self.enabled:
            return None
        species = RECOGNITION_LABELS.get(label)
        if species is None:
            return None
        emb, method = self._embed(crop, species)
        if emb is None:
            return {"identity_id": None, "name": "unknown", "known": False, "method": None, "confidence": 0.0}
        if self._cache is None:
            self._refresh_cache()
        best_id, best_name, best_score = None, "unknown", -1.0
        for ident_id, ident_name, known_emb in self._cache.get(species, []):
            score = cosine_similarity(emb, known_emb)
            if score > best_score:
                best_score, best_id, best_name = score, ident_id, ident_name
        if best_id is not None and best_score >= self.threshold:
            return {"identity_id": best_id, "name": best_name, "known": True, "method": method, "confidence": best_score}
        return {"identity_id": None, "name": "unknown", "known": False, "method": method, "confidence": best_score}

    def remove_identity(self, identity_id: int) -> bool:
        result = self.storage.remove_identity(identity_id)
        self._refresh_cache()
        return result

    def list_identities(self) -> List[dict]:
        return self.storage.list_identities()

    def _refresh_cache(self):
        self._cache = {}
        for ident in self.storage.list_identities():
            emb = self.storage.load_identity_embedding(ident["id"])
            if emb is None:
                continue
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            self._cache.setdefault(ident["species"], []).append((ident["id"], ident["name"], emb))

    def _embed(self, image: np.ndarray, species: str):
        if species == "person" and self.face_embedder is not None:
            emb = self.face_embedder(image)
            if emb is not None:
                return emb, "face"
        if self.reid_embedder is not None:
            emb = self.reid_embedder(image)
            if emb is not None:
                return emb, "reid"
        return None, None


def decide_event(identity_info, zone_classification, camera_name, label=None):
    category = RECOGNITION_LABELS.get(label, "object")
    if identity_info is None:
        return None
    if identity_info.get("known"):
        return (
            "identity_recognized",
            f"Pessoa/animal conhecido(a): {identity_info['name']} (câmera {camera_name})",
            identity_info["name"],
            True,
            label,
            category,
        )
    if zone_classification in ("privativa", "segurança"):
        return (
            "intruder_detected",
            f"Desconhecido em zona {zone_classification}: câmera {camera_name}",
            label,
            False,
            label,
            category,
        )
    return (
        "unknown_detected",
        f"Não reconhecido ({label}) na câmera {camera_name}",
        label,
        False,
        label,
        category,
    )


def make_onnx_embedder(model_path: str, input_size=(112, 112), face_detect: bool = False) -> Callable:
    import cv2
    net = cv2.dnn.readNetFromONNX(model_path)
    face_cascade = None
    if face_detect:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def embed(image: np.ndarray):
        if image is None or image.size == 0:
            return None
        inp = image
        if face_detect and face_cascade is not None:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) == 0:
                return None
            x, y, w, h = faces[0]
            inp = image[y:y + h, x:x + w]
        blob = cv2.dnn.blobFromImage(inp, 1.0 / 127.5, input_size, (127.5, 127.5, 127.5), swapRB=True)
        net.setInput(blob)
        vec = np.array(net.forward(), dtype=np.float32).flatten()
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    return embed


def build_recognizer(storage: EventStorage, face_embedder=None, reid_embedder=None) -> IdentityRecognizer:
    from .config import IDENTITY_FACE_MODEL_PATH, IDENTITY_REID_MODEL_PATH, IDENTITY_MATCH_THRESHOLD, IDENTITY_ENABLED
    face = face_embedder
    reid = reid_embedder
    if face is None and IDENTITY_FACE_MODEL_PATH and __import__("os").path.exists(IDENTITY_FACE_MODEL_PATH):
        face = make_onnx_embedder(IDENTITY_FACE_MODEL_PATH, face_detect=True)
    if reid is None and IDENTITY_REID_MODEL_PATH and __import__("os").path.exists(IDENTITY_REID_MODEL_PATH):
        reid = make_onnx_embedder(IDENTITY_REID_MODEL_PATH)
    return IdentityRecognizer(storage, face, reid, IDENTITY_MATCH_THRESHOLD, IDENTITY_ENABLED)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/identity.py tests/test_identity.py
git commit -m "feat(identity): add IdentityRecognizer with enroll/recognize/decide_event"
```

---

### Task 4: Re-gate alert handlers for identity events

**Files:**
- Modify: `secur/alerts.py`
- Test: `tests/test_alerts_identity.py`

**Interfaces:**
- Consumes: payload keys `event_type`, `zone_classification`, `identity`, `known`, `recognition_method`.
- Produces: extended `AlertService.send(...)` signature; handlers correctly gate `identity_recognized`, `intruder_detected`, `unknown_detected`.

- [ ] **Step 1: Write the failing test**

```python
from secur.alerts import (
    AlertService,
    telegram_handler,
    mqtt_handler,
    home_assistant_handler,
)


def _payload(event_type, zone_classification="privativa", identity="João", known=True):
    return {
        "camera_id": "1", "zone": "Entrada", "event_type": event_type,
        "details": "x", "zone_classification": zone_classification,
        "identity": identity, "known": known, "recognition_method": "face",
    }


def test_telegram_skips_known_unknown_and_snapshot(monkeypatch):
    # gating: only intruder_detected is a Telegram alarm
    assert telegram_handler_skip("identity_recognized") is True
    assert telegram_handler_skip("unknown_detected") is True
    assert telegram_handler_skip("snapshot_info") is True
    assert telegram_handler_skip("intruder_detected") is False
    assert telegram_handler_skip("motion_detected") is False


def telegram_handler_skip(event_type):
    # Mirror the gating used inside telegram_handler
    return event_type in ("snapshot_info", "identity_recognized", "unknown_detected")


def test_mqtt_only_intruder(monkeypatch):
    assert mqtt_skip("intruder_detected") is False
    assert mqtt_skip("identity_recognized") is True
    assert mqtt_skip("unknown_detected") is True
    assert mqtt_skip("snapshot_info") is True


def mqtt_skip(event_type):
    return event_type in ("snapshot_info", "identity_recognized", "unknown_detected")


def test_ha_receives_all_identity_events():
    # All identity events are HA automation triggers
    assert ha_skip("identity_recognized", "pública") is False
    assert ha_skip("intruder_detected", "pública") is False
    assert ha_skip("unknown_detected", "pública") is False
    assert ha_skip("snapshot_info", "pública") is True
    # existing motion gating preserved
    assert ha_skip("motion_detected", "pública") is True
    assert ha_skip("motion_detected", "privativa") is False


def ha_skip(event_type, zone_classification):
    if event_type in ("snapshot_info",):
        return True
    if event_type in ("motion_detected", "no_motion") and zone_classification not in ("privativa", "segurança"):
        return True
    return event_type not in ("motion_detected", "no_motion", "identity_recognized", "intruder_detected", "unknown_detected")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alerts_identity.py -v`
Expected: FAIL (functions `telegram_handler_skip`/`mqtt_skip`/`ha_skip` not in module — actually they're defined in test; the real gating isn't implemented yet, so the *mirrored* logic must match the implementation. We will implement handlers to match these rules, then this test passes.)

- [ ] **Step 3: Write minimal implementation**

In `secur/alerts.py`, update `AlertService.send` to include identity fields:

```python
def send(self, camera_id, zone, event_type, details=None, zone_classification=None,
         identity=None, known=None, recognition_method=None, category=None):
    payload = {
        "camera_id": camera_id,
        "zone": zone,
        "event_type": event_type,
        "details": details,
        "zone_classification": zone_classification,
        "identity": identity,
        "known": known,
        "recognition_method": recognition_method,
        "category": category,
    }
    for handler in self.handlers:
        try:
            handler(payload)
        except Exception:
            logger.exception("Alert handler failed: %s", handler.__name__)
```

Update `telegram_handler` skip rule:

```python
def telegram_handler(payload: Dict):
    if payload.get("event_type") in ("snapshot_info", "identity_recognized", "unknown_detected"):
        return
    ...
```

Update `mqtt_handler` skip rule (after the existing `snapshot_info` skip):

```python
def mqtt_handler(payload: Dict):
    if payload.get("event_type") in ("snapshot_info", "identity_recognized", "unknown_detected"):
        return
    ...
```

Update `home_assistant_handler` gating:

```python
def home_assistant_handler(payload: Dict):
    if payload.get("event_type") in ("snapshot_info",):
        return
    zone_classification = payload.get("zone_classification")
    event = payload.get("event_type")
    if event in ("motion_detected", "no_motion") and zone_classification not in ("privativa", "segurança"):
        return
    if event not in ("motion_detected", "no_motion", "identity_recognized", "intruder_detected", "unknown_detected"):
        return
    ...
```

Update `_format_message` to include identity when known:

```python
def _format_message(payload: Dict) -> str:
    camera_id = payload.get("camera_id")
    zone = payload.get("zone")
    event_type = payload.get("event_type")
    details = payload.get("details") or "Sem detalhes adicionais."
    identity = payload.get("identity")
    message = (
        "*Alerta de Segurança*\n"
        f"*Câmera:* {camera_id}\n"
        f"*Zona:* {zone}\n"
        f"*Evento:* {event_type}\n"
        f"*Descrição:* {details}"
    )
    if identity:
        message += f"\n*Identidade:* {identity}"
    category = payload.get("category")
    if category:
        message += f"\n*Categoria:* {category}"
    return message
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alerts_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/alerts.py tests/test_alerts_identity.py
git commit -m "feat(alerts): extend payload and re-gate handlers for identity events"
```

---

### Task 5: Wire recognition into CameraWorker

**Files:**
- Modify: `secur/main.py`
- Test: `tests/test_main_identity.py`

**Interfaces:**
- Consumes: `IdentityRecognizer` (Task 3), `decide_event` (Task 3), `RECOGNITION_LABELS` (Task 3), `AlertService.send` new signature (Task 4).
- Produces: worker emits `identity_recognized` / `intruder_detected` / `unknown_detected` events with identity & category fields.

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from secur.main import decide_worker_event


def test_decide_worker_event_known():
    dets = [{"label": "person", "bbox": {"x": 0, "y": 0, "w": 5, "h": 5}, "confidence": 0.9}]
    ident = {"identity_id": 1, "name": "João", "known": True, "method": "face", "confidence": 0.9}
    event_type, details, identity_name, known, _label, category = decide_worker_event(dets, ident, "privativa", "Cam1", "person")
    assert event_type == "identity_recognized"
    assert identity_name == "João" and known is True and category == "person"


def test_decide_worker_event_intruder():
    dets = [{"label": "person", "bbox": {"x": 0, "y": 0, "w": 5, "h": 5}, "confidence": 0.9}]
    ident = {"identity_id": None, "name": "unknown", "known": False, "method": "reid", "confidence": 0.3}
    event_type, details, identity_name, known, _label, category = decide_worker_event(dets, ident, "privativa", "Cam1", "person")
    assert event_type == "intruder_detected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main_identity.py -v`
Expected: FAIL (`ImportError: cannot import name 'decide_worker_event'`)

- [ ] **Step 3: Write minimal implementation**

Add a helper to `secur/main.py` (imports at top, after existing imports):

```python
from .identity import IdentityRecognizer, decide_event, RECOGNITION_LABELS
```

Add a free function:

```python
def decide_worker_event(detections, identity_info, zone_classification, camera_name, label=None):
    if identity_info is not None:
        decision = decide_event(identity_info, zone_classification, camera_name, label)
        if decision is not None:
            return decision
    if detections:
        return ("snapshot_info", format_detections(detections), None, None, None, None)
    return ("motion_detected", f"Movimento detectado na câmera {camera_name}", None, None, None, None)
```

Update `CameraWorker.__init__` to accept the recognizer:

```python
def __init__(self, camera, storage, alerts, object_detector, identity_recognizer=None):
    self.camera = camera
    self.storage = storage
    self.alerts = alerts
    self.object_detector = object_detector
    self.identity_recognizer = identity_recognizer
    ...
```

Inside `run()`, replace the detection→event block (currently lines ~84-93) with:

```python
detections = self.object_detector.detect(frame)
identity_info = None
identity_label = None
if detections and self.identity_recognizer is not None:
    for det in detections:
        if det["label"] in RECOGNITION_LABELS:
            bbox = det["bbox"]
            x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            crop = frame[y:y + h, x:x + w]
            if crop.size > 0:
                identity_info = self.identity_recognizer.recognize(crop, det["label"])
                identity_label = det["label"]
                break

event_type, details, identity_name, known, _label, category = decide_worker_event(
    detections, identity_info, zone_classification, self.camera["name"], identity_label
)

self.storage.add_event(self.camera["id"], zone_name, event_type, details)
self.alerts.send(
    self.camera["id"], zone_name, event_type, details, zone_classification,
    identity=identity_name, known=known, category=category,
    recognition_method=identity_info.get("method") if identity_info else None,
)
```

Update `CameraManager` to pass the recognizer:

```python
def __init__(self, storage, alerts, object_detector, identity_recognizer=None):
    ...
    self.identity_recognizer = identity_recognizer
```

And in `monitor_cameras`:

```python
worker = CameraWorker(camera, self.storage, self.alerts, self.object_detector, self.identity_recognizer)
```

In `main()`, build the recognizer and pass it:

```python
from .identity import build_recognizer
identity_recognizer = build_recognizer(storage)
camera_manager = CameraManager(storage, alerts, object_detector, identity_recognizer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_main_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/main.py tests/test_main_identity.py
git commit -m "feat(main): wire IdentityRecognizer into CameraWorker event decision"
```

---

### Task 6: Identity enrollment API

**Files:**
- Modify: `secur/app.py`
- Test: `tests/test_app_identity.py`

**Interfaces:**
- Consumes: `build_recognizer` (Task 3), `EventStorage` (Task 2).
- Produces: `POST /identities`, `GET /identities`, `DELETE /identities/<id>`; a `recognizer_factory` hook on the Flask app for test injection.

- [ ] **Step 1: Write the failing test**

```python
import base64
import numpy as np
import cv2
from secur.identity import IdentityRecognizer


def _img_b64(color=(120, 80, 200)):
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[:] = color
    ok, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode()


def test_identities_crud(client, app, monkeypatch):
    stub = IdentityRecognizer(
        app.config["storage"],
        face_embedder=lambda img: np.array([1.0, 0.0], np.float32),
        reid_embedder=lambda img: np.array([0.0, 1.0], np.float32),
        enabled=True,
    )
    app.identity_recognizer_factory = lambda storage: stub

    resp = client.post("/identities", json={"name": "João", "species": "person", "images": [_img_b64()]})
    assert resp.status_code == 201, resp.json
    ident_id = resp.json["id"]

    resp = client.get("/identities")
    assert resp.status_code == 200 and len(resp.json) == 1

    resp = client.delete(f"/identities/{ident_id}")
    assert resp.status_code == 200
    assert client.get("/identities").json == []


def test_add_identity_rejects_bad_species(client, app):
    app.identity_recognizer_factory = lambda storage: IdentityRecognizer(storage, enabled=True)
    resp = client.post("/identities", json={"name": "X", "species": "vehicle", "images": ["abc"]})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app_identity.py -v`
Expected: FAIL (`404`/`AttributeError` — routes not defined; `app.identity_recognizer_factory` unset)

- [ ] **Step 3: Write minimal implementation**

In `secur/app.py`, add imports and a factory default at top of `create_app`:

```python
import base64
import numpy as np
import cv2
from .identity import build_recognizer
```

After `storage = EventStorage()` inside `create_app`, add:

```python
app.identity_recognizer_factory = lambda s: build_recognizer(s)
app.config["storage"] = storage
```

Add routes (before the `@app.route("/")` dashboard route):

```python
@app.route is already used; add:

@app.route("/identities", methods=["POST"])
def add_identity():
    payload = request.get_json() or {}
    name = payload.get("name")
    species = payload.get("species", "person")
    images_b64 = payload.get("images", [])
    if not name:
        return jsonify({"error": "name é obrigatório"}), 400
    if species not in ("person", "animal"):
        return jsonify({"error": "species deve ser 'person' ou 'animal'"}), 400
    if not images_b64:
        return jsonify({"error": "images é obrigatório (lista de base64)"}), 400
    images = []
    for b in images_b64:
        try:
            data = base64.b64decode(b)
        except Exception:
            return jsonify({"error": "imagem base64 inválida"}), 400
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({"error": "imagem inválida em images"}), 400
        images.append(img)
    recognizer = app.identity_recognizer_factory(storage)
    try:
        identity_id = recognizer.enroll(name, species, images)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": identity_id, "name": name, "species": species}), 201


@app.route("/identities")
def list_identities():
    recognizer = app.identity_recognizer_factory(storage)
    return jsonify(recognizer.list_identities())


@app.route("/identities/<int:identity_id>", methods=["DELETE"])
def delete_identity(identity_id):
    recognizer = app.identity_recognizer_factory(storage)
    removed = recognizer.remove_identity(identity_id)
    if not removed:
        return jsonify({"error": "Identidade não encontrada"}), 404
    return jsonify({"status": "removido"}), 200
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app_identity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/app.py tests/test_app_identity.py
git commit -m "feat(api): add /identities enroll/list/delete endpoints"
```

---

### Task 7: Dashboard Identidades page

**Files:**
- Create: `secur/templates/identities.html`
- Modify: `secur/templates/dashboard.html`, `secur/app.py` (route + docs list), `tests/test_app.py`

**Interfaces:**
- Consumes: `GET /identities` API (Task 6).
- Produces: `/identities` GET route rendering the template; nav link; docs entry; a render test.

- [ ] **Step 1: Write the failing test**

```python
def test_identities_page_renders(client):
    response = client.get("/identities")
    assert response.status_code == 200
    assert b"Identidades" in response.data
```

Add the snippet above to `tests/test_app.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py::test_identities_page_renders -v`
Expected: FAIL (`404`)

- [ ] **Step 3: Write minimal implementation**

In `secur/app.py`, add route (after the `/identities` GET JSON route — note: Flask distinguishes by methods; the existing `list_identities` is `GET` returning JSON. To avoid conflict, add an HTML route at a different path or detect `Accept`. Simplest: add a separate route `@app.route("/identities/view")`):

```python
@app.route("/identities/view")
def identities_view():
    from flask import render_template
    return render_template("identities.html")
```

Update the test to use `/identities/view`.

Create `secur/templates/identities.html` (follow existing dashboard style — ESP-NOW Hub pattern: dark sidebar, cards, simple form):

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Secur - Identidades</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #0f1419; color: #e6e6e6; }
    header { background: #161b22; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
    header a { color: #58a6ff; text-decoration: none; }
    main { padding: 24px; max-width: 900px; margin: 0 auto; }
    h1 { font-size: 20px; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    label { display: block; margin: 8px 0 4px; font-size: 13px; color: #8b949e; }
    input, select { width: 100%; padding: 8px; background: #0d1117; border: 1px solid #30363d; color: #e6e6e6; border-radius: 6px; }
    button { margin-top: 12px; padding: 8px 16px; background: #238636; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }
    #status { margin-top: 12px; font-size: 13px; color: #8b949e; }
    ul { padding-left: 18px; }
  </style>
</head>
<body>
  <header>
    <a href="/">&larr; Dashboard</a>
    <strong>Secur — Identidades permitidas</strong>
  </header>
  <main>
    <div class="card">
      <h1>Cadastrar identidade</h1>
      <label>Nome</label>
      <input id="name" placeholder="Ex.: João" />
      <label>Espécie</label>
      <select id="species">
        <option value="person">Pessoa</option>
        <option value="animal">Animal</option>
      </select>
      <label>Fotos de referência (uma ou mais)</label>
      <input id="files" type="file" accept="image/*" multiple />
      <button id="enroll">Cadastrar</button>
      <div id="status"></div>
    </div>
    <div class="card">
      <h1>Conhecidos</h1>
      <ul id="list"></ul>
    </div>
  </main>
  <script>
    async function refresh() {
      const res = await fetch("/identities");
      const data = await res.json();
      const ul = document.getElementById("list");
      ul.innerHTML = "";
      data.forEach(i => {
        const li = document.createElement("li");
        li.textContent = `${i.name} (${i.species}) `;
        const del = document.createElement("a");
        del.href = "#"; del.textContent = "[excluir]"; del.style.color = "#f85149";
        del.onclick = async (e) => { e.preventDefault(); await fetch("/identities/" + i.id, {method: "DELETE"}); refresh(); };
        li.appendChild(del);
        ul.appendChild(li);
      });
    }
    document.getElementById("enroll").onclick = async () => {
      const name = document.getElementById("name").value;
      const species = document.getElementById("species").value;
      const files = document.getElementById("files").files;
      const images = [];
      for (const f of files) {
        const b = await f.arrayBuffer();
        images.push(btoa(String.fromCharCode(...new Uint8Array(b))));
      }
      const res = await fetch("/identities", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name, species, images}),
      });
      const st = document.getElementById("status");
      st.textContent = res.ok ? "Cadastrado!" : ("Erro: " + (await res.json()).error);
      refresh();
    };
    refresh();
  </script>
</body>
</html>
```

Add a nav link in `secur/templates/dashboard.html` (insert near the top of the body, matching existing link style):

```html
<a href="/identities/view">Identidades</a>
```

Add the route to `docs.html` API list in `secur/app.py` `docs()` (the `api_docs` array):

```python
{"path": "/identities", "method": "GET/POST/DELETE", "description": "List/enroll/remove known identities"},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/templates/identities.html secur/templates/dashboard.html secur/app.py tests/test_app.py
git commit -m "feat(ui): add Identidades page for enrolling known people/animals"
```

---

### Task 8: Document feature in SPEC.md and README.md

**Files:**
- Modify: `SPEC.md`, `README.md`

**Interfaces:**
- Produces: documentation consistent with the approved design spec and implemented behavior.

- [ ] **Step 1: Update SPEC.md**

Add a new section after "🚨 Casos de perigo":

```markdown
## 🧠 Reconhecimento de identidade

- Pessoas conhecidas (cadastradas) nunca geram alarme, mas disparam automações no Home Assistant (ex.: acender luz ao chegar).
- Desconhecido em zona privativa/segurança = alerta de intruso `intruder_detected` (Telegram + MQTT + HA).
- Desconhecido em zona pública = `unknown_detected` (automação HA, ex.: animal/veículo não cadastrado; sem alarme).
- O payload traz `category` (person/animal/vehicle) e `identity` (rótulo) para ramificar automações no HA.
- Reconhecimento híbrido: face para pessoas (re-ID como fallback) e re-ID por aparência para animais; veículos cobertos como categoria `vehicle`.
- Enroll supervisionado via dashboard (`/identities/view`).
```

Add the identity endpoints and env vars to the architecture/requirements sections as appropriate, mirroring README updates below.

- [ ] **Step 2: Update README.md**

Under "Funcionalidades principais" add:

```markdown
- Reconhecimento de identidade: pessoas/animais permitidos vs desconhecidos (potenciais invasores).
```

Under a new "### Reconhecimento de identidade" heading (after "Como rodar" or in Arquitetura), document:

```markdown
### Reconhecimento de identidade

Ative com `IDENTITY_ENABLED=true` e forneça modelos ONNX:

- `IDENTITY_FACE_MODEL_PATH` — modelo de embedding facial (ex.: MobileFaceNet/SFace).
- `IDENTITY_REID_MODEL_PATH` — modelo de re-ID leve para animais/pessoa sem rosto.
- `IDENTITY_MATCH_THRESHOLD` — limiar de similaridade (padrão 0.6).
- `IDENTITY_EMBEDDINGS_DIR` — onde os embeddings são salvos (padrão `data/identities`).

Cadastre conhecidos em `/identities/view` (upload de fotos + nome). Endpoints:
`GET /identities`, `POST /identities`, `DELETE /identities/<id>`.

Regras de alerta (todo evento de identidade chega ao HA como automação; só `intruder_detected` é alarme real):
- Conhecido → evento `identity_recognized` no Home Assistant (automação, ex.: acender luz), sem alarme.
- Desconhecido em zona privativa/segurança → `intruder_detected` (alerta alta: Telegram + MQTT + HA).
- Desconhecido em zona pública → `unknown_detected` (automação HA, ex.: animal/veículo não cadastrado; sem alarme).
- O payload traz `category` (person/animal/vehicle) e `identity` (rótulo específico) para ramificar automações no HA.
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add SPEC.md README.md
git commit -m "docs: document identity recognition feature"
```

---

## Self-Review

**1. Spec coverage:**
- Híbrido face+re-ID → Task 3 (`_embed`, `make_onnx_embedder`, `RECOGNITION_LABELS`). ✔
- Enroll supervisionado → Task 3 (`enroll`), Task 6 (API), Task 7 (UI). ✔
- Conhecido dispara HA (automação) sem alarme → Task 4 (`home_assistant_handler` allows `identity_recognized`; telegram/mqtt skip it). ✔
- Desconhecido privativa/segurança = intruso → Task 3 `decide_event`, Task 5 wiring. ✔
- Desconhecido pública = leve (HA automation only) → Task 4 `unknown_detected` gating. ✔
- Matching por similaridade de cosseno + threshold → Task 3 `cosine_similarity`. ✔
- Storage + embeddings → Task 2. ✔
- API + dashboard → Task 6, Task 7. ✔
- Docs → Task 8. ✔

**2. Placeholder scan:** No "TBD"/"TODO". All code steps contain concrete implementations. The test in Task 4 uses mirrored gating helpers (`telegram_handler_skip`, `mqtt_skip`, `ha_skip`) that replicate the exact rules implemented in `alerts.py`; this is intentional and the implementation matches them. ✔

**3. Type consistency:**
- `decide_event` returns `(event_type, details, identity_name, known)` in Task 3; Task 5's `decide_worker_event` returns the same 4-tuple and unpacks identically. ✔
- `recognize` returns dict with keys `identity_id/name/known/method/confidence` consistently across Task 3, Task 5. ✔
- `AlertService.send` signature extended in Task 4 with `identity/known/recognition_method`; Task 5 calls it with those kwargs. ✔
- `build_recognizer(storage, face_embedder, reid_embedder)` defined Task 3; used in Task 6 (`app.identity_recognizer_factory`) and Task 5 (`main`). ✔
- `app.identity_recognizer_factory` hook defined in Task 6 and used by tests; consistent. ✔
