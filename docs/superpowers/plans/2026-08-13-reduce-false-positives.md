# Fase 1 — Reduzir Falsos Positivos: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar as 4 features da Fase 1 do roadmap (filtro por classe de objeto, zonas de exclusão por câmera, cooldown configurável por evento e horário de alerta por zona) para reduzir falsos positivos no `secur`.

**Architecture:** Configuração persistida em SQLite (colunas novas em `cameras` e `zones` com JSON), filtros aplicados no `CameraWorker.run()` via funções puras testáveis (`filter_detections_by_classes`, `is_within_schedule`, `get_cooldown_for_event`), geometria de polígonos em novo módulo `secur/geometry.py`, e exposição via API + dashboard.

**Tech Stack:** Python 3.10+, Flask, SQLite (sqlite3), OpenCV (cv2), pytest.

## Global Constraints

- Branch de trabalho: `dev` (nunca `main`). Verificar com `git branch --show-current` antes de começar.
- TDD: escrever o teste primeiro, ver falhar, implementar, ver passar, commitar.
- Commits frequentes e pequenos, mensagem em inglês no estilo do repo (`feat: ...`, `test: ...`).
- Testes rodam com: `/tmp/secur-venv/bin/python -m pytest tests/<arquivo> -q` (venv em `/tmp/secur-venv` — não recriar).
- UI em pt-BR; seguir os padrões existentes de `dashboard.html`/`dashboard.js` (`.form-row`, `.button-*`, `escapeHtml`).
- Não alterar comportamento existente quando a nova config não for usada (defaults preservam o comportamento atual).
- Migração de schema: usar o padrão `PRAGMA table_info` + `ALTER TABLE` já usado para `thumbnail_path` em `storage.py`.
- `EventStorage.__init__` apaga o DB se rodando sob pytest — testes usam `tmp_path` para DBs frescos.

---

### Task 1: Storage — colunas novas em `cameras` e `zones`

**Files:**
- Modify: `secur/storage.py` (imports, `_create_tables`, `add_camera`, `list_cameras`, `get_camera`, `update_camera`, `add_zone`, `list_zones`, `get_zone`, `update_zone`)
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: nada novo (schema atual de `cameras`/`zones`).
- Produces:
  - `EventStorage.add_camera(name, source, zone=None, alert_classes=None, exclusion_zones=None) -> int`
  - `EventStorage.update_camera(camera_id, name, source, zone=None, alert_classes=None, exclusion_zones=None) -> bool`
  - `EventStorage.list_cameras() -> List[dict]` (dicts com `alert_classes`/`exclusion_zones` parsed de JSON ou `None`)
  - `EventStorage.get_camera(camera_id) -> dict | None`
  - `EventStorage.add_zone(name, classification='pública', schedule=None) -> int`
  - `EventStorage.update_zone(zone_id, name, classification, schedule=None) -> bool`
  - `EventStorage.list_zones() -> List[dict]` (dicts com `schedule` parsed ou `None`)
  - `EventStorage.get_zone(zone_id) -> dict | None`

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_camera_alert_classes_and_exclusion_zones(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    cam_id = storage.add_camera(
        "Cam", "source://x", "entrada",
        alert_classes=["person", "car"],
        exclusion_zones=[[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]],
    )
    cam = storage.get_camera(cam_id)
    assert cam["alert_classes"] == ["person", "car"]
    assert cam["exclusion_zones"] == [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]

    storage.update_camera(cam_id, "Cam", "source://y", "entrada", alert_classes=["person"])
    cam = storage.get_camera(cam_id)
    assert cam["alert_classes"] == ["person"]
    assert cam["exclusion_zones"] is None

    storage.close()


def test_camera_defaults_alert_classes_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")
    cam = storage.get_camera(cam_id)
    assert cam["alert_classes"] is None
    assert cam["exclusion_zones"] is None
    storage.close()


def test_zone_schedule_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    zone_id = storage.add_zone("Sala", "privativa", schedule={"start": "22:00", "end": "06:00"})
    zone = storage.get_zone(zone_id)
    assert zone["schedule"] == {"start": "22:00", "end": "06:00"}

    storage.update_zone(zone_id, "Sala", "privativa", schedule=None)
    zone = storage.get_zone(zone_id)
    assert zone["schedule"] is None

    storage.close()


def test_migration_adds_new_columns(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE cameras (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source TEXT NOT NULL, zone TEXT)"
    )
    conn.execute(
        "CREATE TABLE zones (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, classification TEXT NOT NULL DEFAULT 'pública')"
    )
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada", alert_classes=["person"])
    assert storage.get_camera(cam_id)["alert_classes"] == ["person"]
    zone_id = storage.add_zone("Z", "pública", schedule={"start": "08:00", "end": "18:00"})
    assert storage.get_zone(zone_id)["schedule"] == {"start": "08:00", "end": "18:00"}
    storage.close()
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: FAIL — `sqlite3.OperationalError: table cameras has no column named alert_classes` (ou similar).

- [ ] **Step 3: Implementar**

Em `secur/storage.py`:

1. Adicionar `import json` no topo (após `import logging`).

2. Em `_create_tables`, substituir o `CREATE TABLE IF NOT EXISTS cameras` por:

```python
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    zone TEXT,
                    alert_classes TEXT,
                    exclusion_zones TEXT
                )
                """
            )
```

3. Em `_create_tables`, substituir o `CREATE TABLE IF NOT EXISTS zones` por:

```python
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS zones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    classification TEXT NOT NULL DEFAULT 'pública',
                    schedule TEXT
                )
                """
            )
```

4. Em `_create_tables`, logo após o bloco de migração do `thumbnail_path` (antes do `CREATE TABLE IF NOT EXISTS camera_thumbnails`), adicionar as migrações:

```python
            # Ensure new camera columns exist for older DBs
            try:
                cursor.execute("PRAGMA table_info(cameras)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'alert_classes' not in cols:
                    cursor.execute("ALTER TABLE cameras ADD COLUMN alert_classes TEXT")
                if 'exclusion_zones' not in cols:
                    cursor.execute("ALTER TABLE cameras ADD COLUMN exclusion_zones TEXT")
            except Exception:
                pass
            # Ensure schedule column exists for older DBs
            try:
                cursor.execute("PRAGMA table_info(zones)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'schedule' not in cols:
                    cursor.execute("ALTER TABLE zones ADD COLUMN schedule TEXT")
            except Exception:
                pass
```

5. Substituir `add_camera`:

```python
    def add_camera(self, name: str, source: str, zone: str = None, alert_classes=None, exclusion_zones=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, source, zone, alert_classes, exclusion_zones) VALUES (?, ?, ?, ?, ?)",
                (name, source, zone,
                 json.dumps(alert_classes) if alert_classes else None,
                 json.dumps(exclusion_zones) if exclusion_zones else None),
            )
            self.connection.commit()
            return cursor.lastrowid
```

6. Substituir `list_cameras`:

```python
    def list_cameras(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone, alert_classes, exclusion_zones FROM cameras ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["alert_classes"] = json.loads(row["alert_classes"]) if row.get("alert_classes") else None
            row["exclusion_zones"] = json.loads(row["exclusion_zones"]) if row.get("exclusion_zones") else None
        return rows
```

7. Substituir `get_camera`:

```python
    def get_camera(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone, alert_classes, exclusion_zones FROM cameras WHERE id = ?", (camera_id,))
            row = cursor.fetchone()
            if not row:
                return None
            camera = dict(row)
        camera["alert_classes"] = json.loads(camera["alert_classes"]) if camera.get("alert_classes") else None
        camera["exclusion_zones"] = json.loads(camera["exclusion_zones"]) if camera.get("exclusion_zones") else None
        return camera
```

8. Substituir `update_camera`:

```python
    def update_camera(self, camera_id: int, name: str, source: str, zone: str = None, alert_classes=None, exclusion_zones=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE cameras SET name = ?, source = ?, zone = ?, alert_classes = ?, exclusion_zones = ? WHERE id = ?",
                (name, source, zone,
                 json.dumps(alert_classes) if alert_classes else None,
                 json.dumps(exclusion_zones) if exclusion_zones else None,
                 camera_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
```

9. Substituir `add_zone`:

```python
    def add_zone(self, name: str, classification: str = 'pública', schedule=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO zones (name, classification, schedule) VALUES (?, ?, ?)",
                (name, classification, json.dumps(schedule) if schedule else None),
            )
            self.connection.commit()
            return cursor.lastrowid
```

10. Substituir `list_zones`:

```python
    def list_zones(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification, schedule FROM zones ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["schedule"] = json.loads(row["schedule"]) if row.get("schedule") else None
        return rows
```

11. Substituir `get_zone`:

```python
    def get_zone(self, zone_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification, schedule FROM zones WHERE id = ?", (zone_id,))
            row = cursor.fetchone()
            if not row:
                return None
            zone = dict(row)
        zone["schedule"] = json.loads(zone["schedule"]) if zone.get("schedule") else None
        return zone
```

12. Substituir `update_zone`:

```python
    def update_zone(self, zone_id: int, name: str, classification: str, schedule=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE zones SET name = ?, classification = ?, schedule = ? WHERE id = ?",
                (name, classification, json.dumps(schedule) if schedule else None, zone_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: PASS (todos os testes do arquivo, incluindo os existentes).

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py tests/test_storage.py
git commit -m "feat: add alert_classes, exclusion_zones and zone schedule to storage"
```

---

### Task 2: Geometria — `secur/geometry.py`

**Files:**
- Create: `secur/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `point_in_polygon(x: float, y: float, polygon: List[dict]) -> bool` — ray casting; `polygon` é lista de `{"x": int, "y": int}`.
  - `bbox_center_in_polygons(bbox: dict, polygons: List[List[dict]]) -> bool` — True se o centro da bbox (`{"x","y","w","h"}`) está dentro de qualquer polígono.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_geometry.py`:

```python
from secur.geometry import point_in_polygon, bbox_center_in_polygons

SQUARE = [
    {"x": 0, "y": 0},
    {"x": 100, "y": 0},
    {"x": 100, "y": 100},
    {"x": 0, "y": 100},
]


def test_point_inside_square():
    assert point_in_polygon(50, 50, SQUARE) is True


def test_point_outside_square():
    assert point_in_polygon(150, 50, SQUARE) is False


def test_point_on_edge_inside():
    assert point_in_polygon(0, 50, SQUARE) is True


def test_point_invalid_polygon():
    assert point_in_polygon(50, 50, [{"x": 0, "y": 0}]) is False


def test_bbox_center_inside():
    bbox = {"x": 40, "y": 40, "w": 20, "h": 20}  # centro (50, 50)
    assert bbox_center_in_polygons(bbox, [SQUARE]) is True


def test_bbox_center_outside():
    bbox = {"x": 140, "y": 40, "w": 20, "h": 20}  # centro (150, 50)
    assert bbox_center_in_polygons(bbox, [SQUARE]) is False


def test_bbox_no_polygons():
    bbox = {"x": 40, "y": 40, "w": 20, "h": 20}
    assert bbox_center_in_polygons(bbox, []) is False
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_geometry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'secur.geometry'`.

- [ ] **Step 3: Implementar**

Criar `secur/geometry.py`:

```python
def point_in_polygon(x, y, polygon):
    """Ray casting: True se (x, y) está dentro do polígono."""
    if not polygon or len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]["x"], polygon[i]["y"]
        xj, yj = polygon[j]["x"], polygon[j]["y"]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def bbox_center_in_polygons(bbox, polygons):
    """True se o centro da bbox está dentro de qualquer polígono de exclusão."""
    cx = bbox["x"] + bbox["w"] / 2
    cy = bbox["y"] + bbox["h"] / 2
    return any(point_in_polygon(cx, cy, poly) for poly in polygons)
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_geometry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/geometry.py tests/test_geometry.py
git commit -m "feat: add polygon geometry helpers for exclusion zones"
```

---

### Task 3: MotionDetector com zonas de exclusão

**Files:**
- Modify: `secur/motion.py`
- Test: `tests/test_motion.py`

**Interfaces:**
- Consumes: `point_in_polygon` de `secur.geometry`.
- Produces: `MotionDetector.detect(frame, exclusion_polygons=None) -> bool` — contornos cujo centroide está dentro de um polígono de exclusão são ignorados.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_motion.py`:

```python
def test_motion_detector_exclusion_zone():
    detector = MotionDetector(min_area=100)
    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    frame2 = frame1.copy()
    cv2.rectangle(frame2, (50, 50), (150, 150), (255, 255, 255), -1)

    detector.detect(frame1)
    # Exclui a região inteira onde está o movimento (centroide ~100,100)
    exclusion = [[{"x": 0, "y": 0}, {"x": 200, "y": 0}, {"x": 200, "y": 200}, {"x": 0, "y": 200}]]
    assert detector.detect(frame2, exclusion_polygons=exclusion) is False


def test_motion_detector_exclusion_zone_other_region():
    detector = MotionDetector(min_area=100)
    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    frame2 = frame1.copy()
    cv2.rectangle(frame2, (50, 50), (150, 150), (255, 255, 255), -1)

    detector.detect(frame1)
    # Exclui apenas o canto superior esquerdo; movimento no centro permanece
    exclusion = [[{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 50}, {"x": 0, "y": 50}]]
    assert detector.detect(frame2, exclusion_polygons=exclusion) is True
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_motion.py -q`
Expected: FAIL — `TypeError: detect() got an unexpected keyword argument 'exclusion_polygons'`.

- [ ] **Step 3: Implementar**

Substituir `secur/motion.py` inteiro:

```python
import cv2

from .geometry import point_in_polygon


class MotionDetector:
    def __init__(self, min_area: int = 5000):
        self.min_area = min_area
        self.previous_frame = None

    def detect(self, frame, exclusion_polygons=None):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.previous_frame is None:
            self.previous_frame = gray
            return False

        delta = cv2.absdiff(self.previous_frame, gray)
        self.previous_frame = gray

        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            if cv2.contourArea(contour) < self.min_area:
                continue
            if exclusion_polygons:
                moments = cv2.moments(contour)
                if moments["m00"] != 0:
                    cx = moments["m10"] / moments["m00"]
                    cy = moments["m01"] / moments["m00"]
                    if any(point_in_polygon(cx, cy, poly) for poly in exclusion_polygons):
                        continue
            return True

        return False
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_motion.py -q`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add secur/motion.py tests/test_motion.py
git commit -m "feat: support exclusion polygons in MotionDetector"
```

---

### Task 4: Funções puras de filtro em `main.py`

**Files:**
- Modify: `secur/main.py` (imports + funções puras)
- Test: `tests/test_main_filters.py` (novo)

**Interfaces:**
- Consumes: `ALERT_COOLDOWN_SECONDS` de `secur.config` (já importado).
- Produces:
  - `filter_detections_by_classes(detections: List[dict], alert_classes: Optional[List[str]]) -> List[dict]` — mantém só detecções cujo `label` está em `alert_classes`; `None`/vazio = todas.
  - `is_within_schedule(schedule: Optional[dict], now: Optional[float] = None) -> bool` — True se `now` (epoch) está dentro de `{"start": "HH:MM", "end": "HH:MM"}`; sem schedule → True; suporta virada de meia-noite (start > end).
  - `get_cooldown_for_event(event_type: str) -> float` — cooldown específico por evento com fallback para o global.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_main_filters.py`:

```python
import time
from datetime import datetime

from secur.config import ALERT_COOLDOWN_SECONDS
from secur.main import filter_detections_by_classes, get_cooldown_for_event, is_within_schedule


def _epoch_at(hour, minute):
    now = datetime.now()
    return time.mktime(now.replace(hour=hour, minute=minute, second=0, microsecond=0).timetuple())


def test_filter_detections_by_classes_none_keeps_all():
    dets = [{"label": "person"}, {"label": "car"}]
    assert filter_detections_by_classes(dets, None) == dets
    assert filter_detections_by_classes(dets, []) == dets


def test_filter_detections_by_classes_filters():
    dets = [{"label": "person"}, {"label": "car"}, {"label": "bird"}]
    assert filter_detections_by_classes(dets, ["person", "car"]) == [
        {"label": "person"},
        {"label": "car"},
    ]


def test_filter_detections_by_classes_no_match():
    dets = [{"label": "bird"}]
    assert filter_detections_by_classes(dets, ["person"]) == []


def test_is_within_schedule_no_schedule():
    assert is_within_schedule(None) is True
    assert is_within_schedule({}) is True


def test_is_within_schedule_day_window():
    schedule = {"start": "08:00", "end": "18:00"}
    assert is_within_schedule(schedule, _epoch_at(10, 0)) is True
    assert is_within_schedule(schedule, _epoch_at(7, 59)) is False
    assert is_within_schedule(schedule, _epoch_at(18, 1)) is False


def test_is_within_schedule_overnight_window():
    schedule = {"start": "22:00", "end": "06:00"}
    assert is_within_schedule(schedule, _epoch_at(23, 30)) is True
    assert is_within_schedule(schedule, _epoch_at(3, 0)) is True
    assert is_within_schedule(schedule, _epoch_at(12, 0)) is False


def test_get_cooldown_for_event_fallback():
    assert get_cooldown_for_event("motion_detected") == ALERT_COOLDOWN_SECONDS
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py -q`
Expected: FAIL — `ImportError: cannot import name 'filter_detections_by_classes'`.

- [ ] **Step 3: Implementar**

Em `secur/main.py`, adicionar após `format_detections` (antes de `should_capture_thumbnail`):

```python
def filter_detections_by_classes(detections, alert_classes):
    """Mantém apenas detecções cujo label está em alert_classes.
    alert_classes None/vazio = todas as classes."""
    if not alert_classes:
        return detections
    allowed = set(alert_classes)
    return [d for d in detections if d["label"] in allowed]


def is_within_schedule(schedule, now=None):
    """True se `now` (epoch) está dentro do schedule {"start": "HH:MM", "end": "HH:MM"}.
    Sem schedule → sempre True. Suporta virada de meia-noite (start > end)."""
    if not schedule:
        return True
    start = schedule.get("start")
    end = schedule.get("end")
    if not start or not end:
        return True
    now = now if now is not None else time.time()
    current = time.strftime("%H:%M", time.localtime(now))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def get_cooldown_for_event(event_type):
    """Cooldown específico por evento, com fallback para o global."""
    return ALERT_COOLDOWN_BY_EVENT.get(event_type, ALERT_COOLDOWN_SECONDS)
```

E adicionar `ALERT_COOLDOWN_BY_EVENT` ao import de `secur.config` no topo de `main.py`:

```python
from .config import (
    DEFAULT_CAMERAS,
    DETECTOR_CLASSES,
    DETECTOR_CONFIDENCE,
    DETECTOR_IOU,
    DETECTOR_MODEL_PATH,
    FRAME_WAIT_SECONDS,
    SERVER_HOST,
    SERVER_PORT,
    MOTION_MIN_AREA,
    NO_MOTION_ALERT_SECONDS,
    ALERT_COOLDOWN_SECONDS,
    ALERT_COOLDOWN_BY_EVENT,
    THUMBNAILS_DIR,
    THUMBNAIL_INTERVAL_SECONDS,
    THUMBNAIL_HISTORY_SIZE,
)
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/main.py tests/test_main_filters.py
git commit -m "feat: add class filter, schedule check and per-event cooldown helpers"
```

---

### Task 5: Config — cooldown por evento

**Files:**
- Modify: `secur/config.py`
- Test: `tests/test_main_filters.py` (adicionar teste)

**Interfaces:**
- Consumes: nada.
- Produces: `ALERT_COOLDOWN_BY_EVENT: dict` — cooldown específico por tipo de evento (ex: `intruder_detected` mais agressivo que o global).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar ao final de `tests/test_main_filters.py`:

```python
def test_get_cooldown_for_event_specific():
    from secur.config import ALERT_COOLDOWN_BY_EVENT
    assert get_cooldown_for_event("intruder_detected") == ALERT_COOLDOWN_BY_EVENT["intruder_detected"]
```

- [ ] **Step 2: Rodar o teste para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py::test_get_cooldown_for_event_specific -q`
Expected: FAIL — `KeyError: 'intruder_detected'` (ou `ImportError` de `ALERT_COOLDOWN_BY_EVENT`).

- [ ] **Step 3: Implementar**

Em `secur/config.py`, após a linha de `ALERT_COOLDOWN_SECONDS`:

```python
# Suppress repeated events of the same type within this window (per camera)
ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))
# Cooldown específico por tipo de evento (fallback: ALERT_COOLDOWN_SECONDS)
ALERT_COOLDOWN_BY_EVENT = {
    "intruder_detected": float(os.getenv("ALERT_COOLDOWN_INTRUDER", "30")),
    "unknown_detected": float(os.getenv("ALERT_COOLDOWN_UNKNOWN", "30")),
}
```

- [ ] **Step 4: Rodar o teste para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/config.py tests/test_main_filters.py
git commit -m "feat: per-event alert cooldown configuration"
```

---

### Task 6: `CameraWorker.run()` — aplicar filtros, cooldown por evento e horário

**Files:**
- Modify: `secur/main.py` (`CameraWorker.run`, imports de `geometry`)

**Interfaces:**
- Consumes: `filter_detections_by_classes`, `is_within_schedule`, `get_cooldown_for_event` (Task 4), `bbox_center_in_polygons` (Task 2), `ALERT_COOLDOWN_BY_EVENT` (Task 5).
- Produces: comportamento do worker:
  - `motion_detector.detect(frame, exclusion_polygons=...)` — movimento em zona excluída não dispara nada.
  - Detecções filtradas por `alert_classes` da câmera; se a câmera tem `alert_classes` e nenhuma detecção relevante → alerta suprimido (thumbnail ainda capturado).
  - Detecções com centro da bbox dentro de polígono de exclusão → descartadas.
  - Cooldown por evento: `get_cooldown_for_event(event_type)`.
  - Horário: se a zona tem `schedule` e `now` está fora → alerta suprimido.

- [ ] **Step 1: Rodar a suíte existente para baseline**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_identity.py tests/test_motion.py -q`
Expected: PASS (baseline antes da mudança).

- [ ] **Step 2: Implementar**

Em `secur/main.py`:

1. Adicionar ao import de `secur.config` (já feito na Task 4) e adicionar import de geometria após `from .motion import MotionDetector`:

```python
from .geometry import bbox_center_in_polygons
```

2. Substituir o bloco de lookup de zona em `run()` (linhas ~81-88) por:

```python
            # Look up zone classification and schedule (once)
            zone_name = self.camera.get("zone")
            zone_classification = None
            zone_schedule = None
            if zone_name:
                zones = self.storage.list_zones()
                zone_obj = next((z for z in zones if z["name"] == zone_name), None)
                if zone_obj:
                    zone_classification = zone_obj.get("classification")
                    zone_schedule = zone_obj.get("schedule")
```

3. Substituir a linha `motion_detected = motion_detector.detect(frame)` por:

```python
            exclusion_polygons = self.camera.get("exclusion_zones") or []
            motion_detected = motion_detector.detect(frame, exclusion_polygons=exclusion_polygons)
```

4. Substituir o bloco `try:` do processamento de detecções (linhas ~95-130) por:

```python
                try:
                    detections = self.object_detector.detect(frame)
                    detections = filter_detections_by_classes(detections, self.camera.get("alert_classes"))
                    if exclusion_polygons:
                        detections = [d for d in detections if not bbox_center_in_polygons(d["bbox"], exclusion_polygons)]

                    alert_classes = self.camera.get("alert_classes")
                    if alert_classes and not detections:
                        logger.debug(
                            "Evento suprimido (filtro de classes) câmera=%s",
                            self.camera.get("name"),
                        )
                    else:
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

                        now = time.time()
                        if not is_within_schedule(zone_schedule, now):
                            logger.debug(
                                "Evento suprimido (fora do horário) câmera=%s evento=%s",
                                self.camera.get("name"), event_type,
                            )
                        elif now - last_alert_time.get(event_type, 0.0) >= get_cooldown_for_event(event_type):
                            last_alert_time[event_type] = now
                            self.alerts.send(
                                self.camera["id"], zone_name, event_type, details, zone_classification,
                                identity=identity_name, known=known, category=category,
                                recognition_method=identity_info.get("method") if identity_info else None,
                            )
                        else:
                            logger.debug(
                                "Evento suprimido (cooldown %ss) câmera=%s evento=%s",
                                get_cooldown_for_event(event_type), self.camera.get("name"), event_type,
                            )
                except Exception:
                    logger.exception("Erro no processamento do frame (câmera %s)", self.camera.get("name"))
                    time.sleep(1)
                    continue
```

Nota: o bloco de thumbnail (após o `try/except`) permanece inalterado — thumbnails continuam sendo capturados mesmo quando o alerta é suprimido por filtro de classes.

- [ ] **Step 3: Rodar a suíte para verificar que nada quebrou**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_identity.py tests/test_motion.py tests/test_main_filters.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add secur/main.py
git commit -m "feat: apply class filter, exclusion zones, per-event cooldown and zone schedule in worker"
```

---

### Task 7: API — aceitar novas configs em câmeras e zonas

**Files:**
- Modify: `secur/app.py` (`add_camera`, `update_camera`, `add_zone`, `update_zone`, endpoint `/api/classes`)
- Test: `tests/test_app.py`, `tests/test_zones.py`

**Interfaces:**
- Consumes: `EventStorage` com novos campos (Task 1), `DETECTOR_CLASSES` de `secur.config`.
- Produces:
  - `POST /cameras` e `PUT /cameras/<id>` aceitam `alert_classes` (lista) e `exclusion_zones` (lista de polígonos); retornam 400 se não forem listas.
  - `POST /zones` e `PUT /zones/<id>` aceitam `schedule` (`{"start": "HH:MM", "end": "HH:MM"}`); retornam 400 se inválido.
  - `GET /api/classes` → `{"classes": ["person", ...]}` (lista de `DETECTOR_CLASSES`).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_app.py`:

```python
def test_add_camera_with_alert_classes(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    response = client.post(
        "/cameras",
        data=json.dumps({
            "name": "Cam", "source": "valid-source", "zone": "entrada",
            "alert_classes": ["person", "car"],
            "exclusion_zones": [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]],
        }),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["alert_classes"] == ["person", "car"]
    assert response.json["exclusion_zones"] == [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]


def test_add_camera_rejects_invalid_alert_classes(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    response = client.post(
        "/cameras",
        data=json.dumps({"name": "Cam", "source": "valid-source", "alert_classes": "person"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_api_classes(client):
    response = client.get("/api/classes")
    assert response.status_code == 200
    assert "person" in response.json["classes"]
```

Adicionar ao final de `tests/test_zones.py`:

```python
def test_add_zone_with_schedule(client):
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Sala", "classification": "privativa",
                         "schedule": {"start": "22:00", "end": "06:00"}}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["schedule"] == {"start": "22:00", "end": "06:00"}


def test_add_zone_invalid_schedule(client):
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Sala", "classification": "privativa",
                         "schedule": {"start": "25:00", "end": "06:00"}}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_update_zone_with_schedule(client):
    res = client.post(
        "/zones",
        data=json.dumps({"name": "Z", "classification": "pública"}),
        content_type="application/json",
    )
    zone_id = res.json["id"]

    response = client.put(
        f"/zones/{zone_id}",
        data=json.dumps({"name": "Z", "classification": "privativa",
                         "schedule": {"start": "08:00", "end": "18:00"}}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["schedule"] == {"start": "08:00", "end": "18:00"}
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py tests/test_zones.py -q`
Expected: FAIL — campos novos não são aceitos/retornados (ex: `alert_classes` ausente na resposta, ou 400 inesperado).

- [ ] **Step 3: Implementar**

Em `secur/app.py`:

1. Adicionar `import time` no topo (após `import logging`).

2. Adicionar helper de validação de schedule após `logger = logging.getLogger(__name__)`:

```python
def _is_valid_schedule(schedule):
    if not isinstance(schedule, dict):
        return False
    start = schedule.get("start")
    end = schedule.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return False
    try:
        time.strptime(start, "%H:%M")
        time.strptime(end, "%H:%M")
    except ValueError:
        return False
    return True
```

3. Substituir `add_camera` (linhas ~180-193):

```python
    @app.route("/cameras", methods=["POST"])
    def add_camera():
        payload = request.get_json() or {}
        name = payload.get("name")
        source = payload.get("source")
        zone = payload.get("zone")
        alert_classes = payload.get("alert_classes")
        exclusion_zones = payload.get("exclusion_zones")

        if not name or not source:
            return jsonify({"error": "name and source são obrigatórios"}), 400

        if alert_classes is not None and not isinstance(alert_classes, list):
            return jsonify({"error": "alert_classes deve ser uma lista"}), 400
        if exclusion_zones is not None and not isinstance(exclusion_zones, list):
            return jsonify({"error": "exclusion_zones deve ser uma lista de polígonos"}), 400

        if not CameraStream.validate_source(source):
            return jsonify({"error": "source inválido ou stream inacessível"}), 400

        camera_id = storage.add_camera(name, source, zone, alert_classes=alert_classes, exclusion_zones=exclusion_zones)
        return jsonify({
            "id": camera_id, "name": name, "source": source, "zone": zone,
            "alert_classes": alert_classes, "exclusion_zones": exclusion_zones,
        }), 201
```

4. Substituir `update_camera` (linhas ~195-214):

```python
    @app.route("/cameras/<int:camera_id>", methods=["PUT"])
    def update_camera(camera_id):
        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404

        payload = request.get_json() or {}
        name = payload.get("name")
        source = payload.get("source")
        zone = payload.get("zone")
        alert_classes = payload.get("alert_classes")
        exclusion_zones = payload.get("exclusion_zones")

        if not name or not source:
            return jsonify({"error": "name and source são obrigatórios"}), 400

        if alert_classes is not None and not isinstance(alert_classes, list):
            return jsonify({"error": "alert_classes deve ser uma lista"}), 400
        if exclusion_zones is not None and not isinstance(exclusion_zones, list):
            return jsonify({"error": "exclusion_zones deve ser uma lista de polígonos"}), 400

        if not CameraStream.validate_source(source):
            return jsonify({"error": "source inválido ou stream inacessível"}), 400

        storage.update_camera(camera_id, name, source, zone, alert_classes=alert_classes, exclusion_zones=exclusion_zones)
        updated_camera = storage.get_camera(camera_id)
        return jsonify(updated_camera), 200
```

5. Adicionar endpoint `/api/classes` após a rota `/api/notifications/routing` (antes da seção Identity):

```python
    @app.route("/api/classes")
    def classes():
        from .config import DETECTOR_CLASSES
        return jsonify({"classes": DETECTOR_CLASSES})
```

6. Substituir `add_zone` (linhas ~414-431):

```python
    @app.route("/zones", methods=["POST"])
    def add_zone():
        payload = request.get_json() or {}
        name = payload.get("name")
        classification = payload.get("classification", "pública")
        schedule = payload.get("schedule")

        if not name:
            return jsonify({"error": "name é obrigatório"}), 400

        if classification not in ('privativa', 'segurança', 'pública'):
            return jsonify({"error": "classification deve ser: privativa, segurança ou pública"}), 400

        if schedule is not None and not _is_valid_schedule(schedule):
            return jsonify({"error": "schedule deve ser {\"start\": \"HH:MM\", \"end\": \"HH:MM\"}"}), 400

        existing = storage.list_zones()
        if any(z["name"] == name for z in existing):
            return jsonify({"error": "Zona com esse nome já existe"}), 400

        zone_id = storage.add_zone(name, classification, schedule=schedule)
        return jsonify({"id": zone_id, "name": name, "classification": classification, "schedule": schedule}), 201
```

7. Substituir `update_zone` (linhas ~433-451):

```python
    @app.route("/zones/<int:zone_id>", methods=["PUT"])
    def update_zone(zone_id):
        zone = storage.get_zone(zone_id)
        if not zone:
            return jsonify({"error": "Zona não encontrada"}), 404

        payload = request.get_json() or {}
        name = payload.get("name")
        classification = payload.get("classification")
        schedule = payload.get("schedule")

        if not name or not classification:
            return jsonify({"error": "name e classification são obrigatórios"}), 400

        if classification not in ('privativa', 'segurança', 'pública'):
            return jsonify({"error": "classification deve ser: privativa, segurança ou pública"}), 400

        if schedule is not None and not _is_valid_schedule(schedule):
            return jsonify({"error": "schedule deve ser {\"start\": \"HH:MM\", \"end\": \"HH:MM\"}"}), 400

        storage.update_zone(zone_id, name, classification, schedule=schedule)
        updated_zone = storage.get_zone(zone_id)
        return jsonify(updated_zone), 200
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py tests/test_zones.py -q`
Expected: PASS (todos, incluindo os existentes).

- [ ] **Step 5: Commit**

```bash
git add secur/app.py tests/test_app.py tests/test_zones.py
git commit -m "feat: accept alert classes, exclusion zones and zone schedule in API"
```

---

### Task 8: Dashboard — form de câmera (classes + exclusões) e form de zona (horário)

**Files:**
- Modify: `secur/templates/dashboard.html`, `secur/static/dashboard.js`

**Interfaces:**
- Consumes: `GET /api/classes` (Task 7), campos `alert_classes`/`exclusion_zones`/`schedule` nas respostas de `/cameras` e `/zones`.
- Produces: UI pt-BR para configurar as 4 features da Fase 1.

- [ ] **Step 1: Implementar o HTML**

Em `secur/templates/dashboard.html`:

1. No form de câmera (`#camera-form`), após o bloco do `#camera-zone` (linha ~161), adicionar:

```html
                        <div class="form-row">
                            <label for="camera-alert-classes">Classes de alerta (vazio = todas)</label>
                            <div id="camera-alert-classes" class="checkbox-group"></div>
                        </div>
                        <div class="form-row">
                            <label for="camera-exclusion-zones">Zonas de exclusão (JSON)</label>
                            <textarea id="camera-exclusion-zones" rows="3" placeholder='[{"x":0,"y":0},{"x":100,"y":0},{"x":100,"y":100}]'></textarea>
                        </div>
```

2. No form de zona (`#zone-form`), após o bloco do `#zone-classification` (linha ~212), adicionar:

```html
                        <div class="form-row">
                            <label for="zone-schedule-start">Horário de alerta (início)</label>
                            <input id="zone-schedule-start" type="time">
                        </div>
                        <div class="form-row">
                            <label for="zone-schedule-end">Horário de alerta (fim)</label>
                            <input id="zone-schedule-end" type="time">
                        </div>
```

3. Na tabela de câmeras (`#camera-management` thead, linha ~132), adicionar colunas:

```html
                                <th>Zona</th>
                                <th>Classes</th>
                                <th>Exclusões</th>
                                <th>Ações</th>
```

- [ ] **Step 2: Implementar o JS**

Em `secur/static/dashboard.js`:

1. Adicionar função de população de classes (após `populateZoneDropdown`):

```javascript
async function populateAlertClasses(selected) {
  const container = document.getElementById('camera-alert-classes');
  if (!container) return;
  let classes = [];
  try {
    const data = await fetchData('/api/classes');
    classes = data.classes || [];
  } catch (e) { return; }
  const selectedSet = new Set(selected || []);
  container.innerHTML = classes.map(cls => `
    <label class="checkbox-inline">
      <input type="checkbox" value="${cls}" ${selectedSet.has(cls) ? 'checked' : ''} /> ${cls}
    </label>
  `).join('');
}
```

2. Em `setCameraFormMode`, após `zoneInput.value = camera.zone || '';` (modo edit) e após `form.reset();` (modo add), adicionar:

```javascript
    populateAlertClasses(camera ? camera.alert_classes : null);
    const exclusionInput = document.getElementById('camera-exclusion-zones');
    if (exclusionInput) {
      exclusionInput.value = camera && camera.exclusion_zones ? JSON.stringify(camera.exclusion_zones) : '';
    }
```

3. Em `submitCameraForm`, após montar `payload` (linha ~339), adicionar antes do `if (!payload.name ...)`:

```javascript
  const checkedClasses = Array.from(document.querySelectorAll('#camera-alert-classes input:checked')).map(i => i.value);
  const exclusionText = document.getElementById('camera-exclusion-zones').value.trim();
  let exclusionZones = null;
  if (exclusionText) {
    try {
      exclusionZones = JSON.parse(exclusionText);
    } catch (e) {
      message.textContent = 'Zonas de exclusão: JSON inválido.';
      message.classList.add('error');
      return;
    }
  }
  payload.alert_classes = checkedClasses.length ? checkedClasses : null;
  payload.exclusion_zones = exclusionZones;
```

4. Em `setZoneFormMode`, adicionar no modo edit e no modo add:

```javascript
    const startInput = document.getElementById('zone-schedule-start');
    const endInput = document.getElementById('zone-schedule-end');
    if (mode === 'edit' && zone) {
      startInput.value = (zone.schedule && zone.schedule.start) || '';
      endInput.value = (zone.schedule && zone.schedule.end) || '';
    } else {
      startInput.value = '';
      endInput.value = '';
    }
```

5. Em `submitZoneForm`, após montar `payload` (linha ~458), adicionar:

```javascript
  const startInput = document.getElementById('zone-schedule-start');
  const endInput = document.getElementById('zone-schedule-end');
  let schedule = null;
  if (startInput.value || endInput.value) {
    schedule = { start: startInput.value || '00:00', end: endInput.value || '23:59' };
  }
  payload.schedule = schedule;
```

6. Em `createCameraRow` (linha ~222), substituir por:

```javascript
function createCameraRow(camera) {
  const classesText = camera.alert_classes && camera.alert_classes.length
    ? camera.alert_classes.join(', ')
    : 'todas';
  const exclusionsText = camera.exclusion_zones && camera.exclusion_zones.length
    ? `${camera.exclusion_zones.length} polígono(s)`
    : '—';
  return `
    <tr>
      <td>${camera.id}</td>
      <td>${camera.name}</td>
      <td>${camera.source}</td>
      <td>${camera.zone || '-'}</td>
      <td>${classesText}</td>
      <td>${exclusionsText}</td>
      <td class="table-actions">
        <button class="button-secondary button-mini edit-camera" data-camera-id="${camera.id}">Editar</button>
        <button class="button-secondary button-mini delete-camera" data-camera-id="${camera.id}">Excluir</button>
      </td>
    </tr>
  `;
}
```

- [ ] **Step 3: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py tests/test_zones.py -q`
Expected: PASS (API continua funcionando; UI não tem testes automatizados neste repo).

Verificação manual (se houver servidor rodando): abrir o dashboard, editar uma câmera → checkboxes de classes aparecem; salvar com classes selecionadas → coluna "Classes" mostra; editar uma zona → campos de horário aparecem.

- [ ] **Step 4: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js
git commit -m "feat: dashboard UI for alert classes, exclusion zones and zone schedule"
```

---

### Task 9: Suíte completa + docs

**Files:**
- Modify: `secur/app.py` (rota `/docs` — adicionar `/api/classes`)

**Interfaces:**
- Consumes: tudo das Tasks 1-8.
- Produces: suíte verde e docs atualizada.

- [ ] **Step 1: Atualizar `/docs`**

Em `secur/app.py`, na lista `api_docs` (linha ~171), adicionar após a entrada de `/api/notifications/routing`:

```python
            {"path": "/api/classes", "method": "GET", "description": "Lista de classes de objetos detectáveis (filtro por câmera)"},
```

- [ ] **Step 2: Rodar a suíte completa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: PASS (todos os testes, incluindo os novos).

- [ ] **Step 3: Commit**

```bash
git add secur/app.py
git commit -m "docs: document /api/classes endpoint"
```

---

## Self-Review

**1. Spec coverage (roadmap Fase 1):**
- 1.1 Filtro por classe de objeto → Tasks 1 (coluna `alert_classes`), 4 (`filter_detections_by_classes`), 6 (aplicação no worker), 7 (API), 8 (UI). ✅
- 1.2 Zonas de exclusão por câmera → Tasks 1 (coluna `exclusion_zones`), 2 (`geometry.py`), 3 (`MotionDetector`), 6 (filtro de detecções), 7 (API), 8 (UI). ✅
- 1.3 Cooldown configurável por evento → Tasks 4 (`get_cooldown_for_event`), 5 (`ALERT_COOLDOWN_BY_EVENT`), 6 (uso no worker). ✅
- 1.4 Horário de alerta por zona → Tasks 1 (coluna `schedule`), 4 (`is_within_schedule`), 6 (uso no worker), 7 (API), 8 (UI). ✅

**2. Placeholder scan:** Nenhum TBD/TODO; todo passo tem código completo e comandos exatos.

**3. Type consistency:**
- `alert_classes`/`exclusion_zones`/`schedule` sempre `None` quando não configurados (storage parseia JSON → `None`; API valida listas/dict).
- `filter_detections_by_classes(detections, alert_classes)` — Task 4 define, Task 6 usa com `self.camera.get("alert_classes")`. ✅
- `is_within_schedule(schedule, now)` — Task 4 define, Task 6 usa com `zone_schedule`. ✅
- `get_cooldown_for_event(event_type)` — Task 4 define, Task 5 adiciona `ALERT_COOLDOWN_BY_EVENT`, Task 6 usa. ✅
- `bbox_center_in_polygons(bbox, polygons)` — Task 2 define, Task 6 usa com `d["bbox"]` e `exclusion_polygons`. ✅
- `MotionDetector.detect(frame, exclusion_polygons=None)` — Task 3 define, Task 6 usa. ✅
- `point_in_polygon(x, y, polygon)` — Task 2 define, Task 3 usa com centroide do contorno. ✅