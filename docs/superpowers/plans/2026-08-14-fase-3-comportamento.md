# Fase 3 — Detecção de comportamento/anomalia Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar detecção de comportamento/anomalia: loitering (3.1), direção de movimento (3.2), pessoa em zona restrita fora de horário (3.3) e detecção de queda por heurística (3.4).

**Architecture:** Novo módulo puro `secur/tracking.py` (tracking por IoU entre frames, `IoUTracker` com tracks de centroide/idade) + novo módulo puro `secur/behavior.py` (regras `check_loitering`, `check_direction_crossing`, `check_fall`) — ambos sem cv2 e sem I/O, testáveis unitariamente. `decide_worker_event` (em `main.py`) ganha os parâmetros `in_schedule`/`fall`/`loitering`/`direction`/`now` com prioridade identidade > queda > loitering > direção > snapshot > movimento. A linha de direção configurável vive na zona (`zones.direction_line` JSON `{"axis": "vertical"|"horizontal", "position": 0-1}`), validada na API e editável no dashboard. O `CameraWorker` faz o wiring: instancia um tracker por câmera, atualiza a cada frame com movimento e alimenta as regras.

**Tech Stack:** Python 3.10+, SQLite (padrão `PRAGMA table_info` + `ALTER TABLE`), Flask, dashboard pt-BR (HTML/JS vanilla).

## Global Constraints

- Branch `dev`; commits em inglês (`feat:`/`test:`/`docs:`); TDD (teste falha → implementa → passa → commit).
- Venv: `/tmp/secur-venv/bin/python -m pytest tests/<arquivo> -q`.
- Schema: nunca recriar tabelas; usar `PRAGMA table_info` + `ALTER TABLE` para colunas novas.
- Colunas JSON seguem o padrão das fases anteriores: `None` quando não configurado, parse com `json.loads` nos getters.
- `EventStorage.__init__` apaga o DB sob pytest — testes usam `tmp_path`; fechar com `storage.close()`.
- `secur/tracking.py` e `secur/behavior.py` são **módulos puros**: sem `cv2`, sem acesso a storage/config no corpo das funções (config entra como parâmetro).
- **Eventos novos** (reusam o cooldown por evento da Fase 1.3 e o payload genérico do `AlertService.send` — nenhuma mudança em `alerts.py`): `loitering`, `direction_change`, `fall_detected`. `intruder_detected` e `identity_recognized` já existem (identidade).
- **Prioridade de decisão** em `decide_worker_event`: identidade (`intruder_detected`/`identity_recognized`) > `fall_detected` > `loitering` > `direction_change` > `snapshot_info` > `motion_detected`.
- **Fora do horário** (`in_schedule=False`): apenas eventos de identidade válidos passam — `intruder_detected` (desconhecido em zona privativa/segurança, prioridade) e `identity_recognized` (conhecido); `unknown_detected` e todos os demais eventos são suprimidos (retornam `None`).
- **3.4 (queda)**: decisão de viabilidade do spec → modelo de pose local (ângulo do torso) tem custo de inferência proibitivo no hardware alvo e **fica como backlog documentado**; o subset viável é a **heurística de razão de aspecto da bbox** (`w/h >= FALL_ASPECT_RATIO` para `person`), implementada nesta fase. Testes usam bbox sintética em pé vs deitada (equivalente da "pose sintética" do spec).
- **Convenção da linha de direção** (documentada no código): linha vertical — cruzamento esquerda→direita = `"entrando"`, direita→esquerda = `"saindo"`; linha horizontal — cima→baixo = `"entrando"`, baixo→cima = `"saindo"`.
- `direction_line.position` é fração do frame (0-1); o worker converte para pixels multiplicando por `frame.shape[1]` (vertical) ou `frame.shape[0]` (horizontal).
- UI pt-BR, padrões de `dashboard.html`/`dashboard.js` (`.form-row`, modal `hidden-panel`, textarea JSON com prefill no modo edição — mesmo padrão de `exclusion_zones`/`mask_polygons`).
- Timestamps ISO UTC (`datetime.now(timezone.utc).isoformat()`); cooldown usa epoch (`time.time()`).

---

### Task 1: Módulo de tracking por IoU (`secur/tracking.py`)

**Files:**
- Create: `secur/tracking.py`
- Modify: `secur/config.py` (novas env vars)
- Test: `tests/test_tracking.py`

**Interfaces:**
- Consumes: formato de detecção existente `{"label": str, "confidence": float, "bbox": {"x", "y", "w", "h"}}` (produzido por `ObjectDetector`).
- Produces:
  - `bbox_iou(a: dict, b: dict) -> float`
  - `bbox_centroid(bbox: dict) -> tuple` → `(cx, cy)` floats
  - `IoUTracker(iou_threshold: float = 0.3, max_age_seconds: float = 2.0)`
    - `update(detections: list, now: float) -> list` → tracks ativas (dicts)
  - Track: `{"id": int, "label": str, "bbox": dict, "centroid": (float, float), "prev_centroid": (float, float)|None, "first_centroid": (float, float), "first_seen": float, "last_seen": float}`
  - Config: `TRACK_IOU_THRESHOLD` (default `0.3`), `TRACK_MAX_AGE_SECONDS` (default `2.0`)

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_tracking.py`:

```python
from secur.tracking import bbox_iou, bbox_centroid, IoUTracker


def test_bbox_iou_identical():
    bbox = {"x": 10, "y": 10, "w": 50, "h": 50}
    assert bbox_iou(bbox, dict(bbox)) == 1.0


def test_bbox_iou_disjoint():
    a = {"x": 0, "y": 0, "w": 10, "h": 10}
    b = {"x": 100, "y": 100, "w": 10, "h": 10}
    assert bbox_iou(a, b) == 0.0


def test_bbox_iou_partial_overlap():
    a = {"x": 0, "y": 0, "w": 10, "h": 10}
    b = {"x": 5, "y": 0, "w": 10, "h": 10}
    expected = 5 * 10 / (10 * 10 + 10 * 10 - 5 * 10)
    assert abs(bbox_iou(a, b) - expected) < 1e-9


def test_bbox_centroid():
    assert bbox_centroid({"x": 10, "y": 20, "w": 30, "h": 40}) == (25.0, 40.0)


def test_tracker_associates_bbox_across_frames():
    tracker = IoUTracker(iou_threshold=0.3)
    d1 = [{"label": "person", "bbox": {"x": 10, "y": 10, "w": 50, "h": 100}}]
    tracks1 = tracker.update(d1, now=1.0)
    assert len(tracks1) == 1
    track_id = tracks1[0]["id"]
    assert tracks1[0]["first_seen"] == 1.0

    d2 = [{"label": "person", "bbox": {"x": 15, "y": 12, "w": 50, "h": 100}}]
    tracks2 = tracker.update(d2, now=2.0)
    assert len(tracks2) == 1
    assert tracks2[0]["id"] == track_id
    assert tracks2[0]["prev_centroid"] == (35.0, 60.0)
    assert tracks2[0]["centroid"] == (40.0, 62.0)
    assert tracks2[0]["first_seen"] == 1.0


def test_tracker_creates_new_track_when_no_match():
    tracker = IoUTracker(iou_threshold=0.3)
    tracker.update([{"label": "person", "bbox": {"x": 0, "y": 0, "w": 50, "h": 100}}], now=1.0)
    tracks = tracker.update(
        [{"label": "car", "bbox": {"x": 300, "y": 0, "w": 50, "h": 100}}], now=2.0
    )
    assert len(tracks) == 2
    assert {t["label"] for t in tracks} == {"person", "car"}


def test_tracker_expires_stale_tracks():
    tracker = IoUTracker(iou_threshold=0.3, max_age_seconds=2.0)
    tracker.update([{"label": "person", "bbox": {"x": 0, "y": 0, "w": 50, "h": 100}}], now=1.0)
    tracks = tracker.update([], now=10.0)
    assert tracks == []
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_tracking.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'secur.tracking'`

- [ ] **Step 3: Implementar**

Criar `secur/tracking.py`:

```python
"""Tracking de objetos por IoU entre frames consecutivos (por câmera).

Módulo puro (sem cv2): mantém tracks de detecções entre frames para
alimentar as regras de comportamento (loitering, direção de movimento).
"""

from typing import Dict, List, Optional


def bbox_iou(a: Dict, b: Dict) -> float:
    """IoU entre dois bboxes {"x", "y", "w", "h"} (int ou float)."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter == 0.0:
        return 0.0

    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def bbox_centroid(bbox: Dict) -> tuple:
    """Centroide (cx, cy) do bbox {"x", "y", "w", "h"}."""
    return (bbox["x"] + bbox["w"] / 2.0, bbox["y"] + bbox["h"] / 2.0)


class IoUTracker:
    """Associa detecções entre frames por IoU, mantendo tracks por câmera.

    Track: {"id", "label", "bbox", "centroid", "prev_centroid",
            "first_centroid", "first_seen", "last_seen"}.
    Tracks não vistas por `max_age_seconds` são descartadas no próximo
    `update()`.
    """

    def __init__(self, iou_threshold: float = 0.3, max_age_seconds: float = 2.0):
        self.iou_threshold = iou_threshold
        self.max_age_seconds = max_age_seconds
        self._next_id = 0
        self.tracks: Dict[int, Dict] = {}

    def update(self, detections: List[Dict], now: float) -> List[Dict]:
        """Associa `detections` às tracks (greedy, maior IoU acima do limiar).

        Detecções sem match criam tracks novas; tracks com match atualizam
        bbox/centroid (prev_centroid guarda o valor do frame anterior).
        Retorna as tracks ativas (não expiradas).
        """
        used: set = set()
        for det in detections:
            best_id = None
            best_iou = self.iou_threshold
            for track_id, track in self.tracks.items():
                if track_id in used:
                    continue
                iou = bbox_iou(track["bbox"], det["bbox"])
                if iou > best_iou:
                    best_id, best_iou = track_id, iou
            if best_id is None:
                best_id = self._next_id
                self._next_id += 1
                centroid = bbox_centroid(det["bbox"])
                self.tracks[best_id] = {
                    "id": best_id,
                    "label": det["label"],
                    "bbox": det["bbox"],
                    "centroid": centroid,
                    "prev_centroid": None,
                    "first_centroid": centroid,
                    "first_seen": now,
                    "last_seen": now,
                }
            else:
                track = self.tracks[best_id]
                track["prev_centroid"] = track["centroid"]
                track["bbox"] = det["bbox"]
                track["centroid"] = bbox_centroid(det["bbox"])
                track["label"] = det["label"]
                track["last_seen"] = now
            used.add(best_id)

        for track_id in list(self.tracks.keys()):
            if track_id not in used and now - self.tracks[track_id]["last_seen"] > self.max_age_seconds:
                del self.tracks[track_id]

        return list(self.tracks.values())
```

Adicionar ao final de `secur/config.py`:

```python
# Fase 3 — comportamento/anomalia (tracking)
TRACK_IOU_THRESHOLD = float(os.getenv("TRACK_IOU_THRESHOLD", "0.3"))
TRACK_MAX_AGE_SECONDS = float(os.getenv("TRACK_MAX_AGE_SECONDS", "2.0"))
```

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_tracking.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add secur/tracking.py secur/config.py tests/test_tracking.py
git commit -m "feat: IoU object tracker module"
```

---

### Task 2: Regra de loitering (`secur/behavior.py` + config)

**Files:**
- Create: `secur/behavior.py`
- Modify: `secur/config.py` (env vars de loitering)
- Test: `tests/test_behavior.py`

**Interfaces:**
- Consumes: tracks do `IoUTracker.update()` (Task 1).
- Produces:
  - `check_loitering(tracks: list, now: float, loiter_seconds: float, max_distance: float, labels: Optional[set] = None) -> Optional[dict]` — primeira track com `now - first_seen >= loiter_seconds` E deslocamento do centroide desde `first_centroid` <= `max_distance`; `None` se nenhuma.
  - Config: `LOITERING_SECONDS` (default `30`), `LOITERING_MAX_DISTANCE` (default `80`, px), `LOITERING_LABELS` (default `["person", "car", "truck", "bus", "motorcycle", "bicycle"]` — pessoa/veículo, conforme spec 3.1)

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_behavior.py`:

```python
from secur.behavior import check_loitering


def _track(first_seen, label="person", centroid=(10.0, 10.0), first_centroid=(10.0, 10.0)):
    return {
        "id": 1,
        "label": label,
        "centroid": centroid,
        "first_centroid": first_centroid,
        "first_seen": first_seen,
        "last_seen": first_seen + 1,
    }


def test_check_loitering_no_tracks():
    assert check_loitering([], 100.0, 30, 80) is None


def test_check_loitering_not_enough_time():
    tracks = [_track(first_seen=100.0)]
    assert check_loitering(tracks, 120.0, 30, 80) is None


def test_check_loitering_triggers_after_threshold():
    tracks = [_track(first_seen=100.0)]
    track = check_loitering(tracks, 130.0, 30, 80)
    assert track is tracks[0]


def test_check_loitering_ignores_continuous_movement():
    tracks = [_track(first_seen=100.0, centroid=(400.0, 400.0))]
    assert check_loitering(tracks, 130.0, 30, 80) is None


def test_check_loitering_filters_labels():
    tracks = [_track(first_seen=100.0, label="bird")]
    assert check_loitering(tracks, 130.0, 30, 80, labels={"person", "car"}) is None

    tracks = [_track(first_seen=100.0, label="person")]
    assert check_loitering(tracks, 130.0, 30, 80, labels={"person", "car"}) is tracks[0]
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_behavior.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'secur.behavior'`

- [ ] **Step 3: Implementar**

Criar `secur/behavior.py`:

```python
"""Regras puras de comportamento/anomalia (Fase 3).

Recebem tracks/detections e produzem decisões — sem cv2, sem I/O,
sem acesso a config/storage (config entra como parâmetro). O
CameraWorker faz o wiring.
"""

from typing import Dict, List, Optional


def check_loitering(tracks, now, loiter_seconds, max_distance, labels=None):
    """Primeira track que permaneceu na mesma região por >= loiter_seconds.

    `max_distance`: deslocamento máximo (px) do centroide desde o primeiro
    frame para ainda ser considerada "na mesma região".
    `labels`: conjunto de labels considerados (None = todos).
    Retorna a track (dict) ou None.
    """
    if not tracks:
        return None
    for track in tracks:
        if labels is not None and track["label"] not in labels:
            continue
        age = now - track["first_seen"]
        if age < loiter_seconds:
            continue
        dx = track["centroid"][0] - track["first_centroid"][0]
        dy = track["centroid"][1] - track["first_centroid"][1]
        if (dx * dx + dy * dy) ** 0.5 <= max_distance:
            return track
    return None
```

Adicionar a `secur/config.py` (após as vars de tracking):

```python
LOITERING_SECONDS = float(os.getenv("LOITERING_SECONDS", "30"))
LOITERING_MAX_DISTANCE = float(os.getenv("LOITERING_MAX_DISTANCE", "80"))
LOITERING_LABELS = ["person", "car", "truck", "bus", "motorcycle", "bicycle"]
```

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_behavior.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add secur/behavior.py secur/config.py tests/test_behavior.py
git commit -m "feat: loitering behavior rule"
```

---

### Task 3: Regra de direção de movimento (`check_direction_crossing`)

**Files:**
- Modify: `secur/behavior.py`
- Test: `tests/test_behavior.py`

**Interfaces:**
- Consumes: `prev_centroid`/`centroid` das tracks (Task 1) e linha configurada da zona.
- Produces:
  - `check_direction_crossing(prev_centroid: Optional[tuple], curr_centroid: Optional[tuple], line: dict) -> Optional[str]` — `"entrando"`, `"saindo"` ou `None`.
  - `line`: `{"axis": "vertical", "x": px}` ou `{"axis": "horizontal", "y": px}` (pixels absolutos; conversão de fração→px feita pelo worker na Task 8).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_behavior.py`:

```python
from secur.behavior import check_direction_crossing


def test_direction_crossing_vertical_entering():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing((50.0, 60.0), (150.0, 60.0), line) == "entrando"


def test_direction_crossing_vertical_leaving():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing((150.0, 60.0), (50.0, 60.0), line) == "saindo"


def test_direction_crossing_horizontal_entering():
    line = {"axis": "horizontal", "y": 100.0}
    assert check_direction_crossing((50.0, 60.0), (50.0, 150.0), line) == "entrando"


def test_direction_crossing_horizontal_leaving():
    line = {"axis": "horizontal", "y": 100.0}
    assert check_direction_crossing((50.0, 150.0), (50.0, 60.0), line) == "saindo"


def test_direction_crossing_no_cross():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing((50.0, 60.0), (60.0, 60.0), line) is None


def test_direction_crossing_no_prev_centroid():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing(None, (150.0, 60.0), line) is None
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_behavior.py -q`
Expected: 5 passed, 6 FAIL — `ImportError: cannot import name 'check_direction_crossing'`

- [ ] **Step 3: Implementar**

Adicionar ao final de `secur/behavior.py`:

```python
def check_direction_crossing(prev_centroid, curr_centroid, line):
    """Direção do cruzamento da linha entre dois frames (None se não cruzou).

    `line`: {"axis": "vertical", "x": px} ou {"axis": "horizontal", "y": px}.
    Convenção: vertical — esquerda→direita = "entrando", direita→esquerda =
    "saindo"; horizontal — cima→baixo = "entrando", baixo→cima = "saindo".
    """
    if prev_centroid is None or curr_centroid is None:
        return None
    if line["axis"] == "vertical":
        x = line["x"]
        if prev_centroid[0] < x <= curr_centroid[0]:
            return "entrando"
        if prev_centroid[0] > x >= curr_centroid[0]:
            return "saindo"
    else:
        y = line["y"]
        if prev_centroid[1] < y <= curr_centroid[1]:
            return "entrando"
        if prev_centroid[1] > y >= curr_centroid[1]:
            return "saindo"
    return None
```

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_behavior.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add secur/behavior.py tests/test_behavior.py
git commit -m "feat: direction crossing behavior rule"
```

---

### Task 4: Heurística de queda (`check_fall`) + decisão de viabilidade do 3.4

**Files:**
- Modify: `secur/behavior.py`
- Modify: `secur/config.py` (env var)
- Test: `tests/test_behavior.py`

**Interfaces:**
- Consumes: detecções `{"label", "bbox"}` (formato existente).
- Produces:
  - `check_fall(detection: dict, aspect_ratio: float) -> bool` — True se `label == "person"` e `bbox.w / bbox.h >= aspect_ratio` (bbox deitada); `h <= 0` → False.
  - Config: `FALL_ASPECT_RATIO` (default `1.2`)

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_behavior.py`:

```python
from secur.behavior import check_fall


def test_check_fall_lying_person():
    det = {"label": "person", "bbox": {"x": 0, "y": 0, "w": 200, "h": 100}}
    assert check_fall(det, 1.2) is True


def test_check_fall_standing_person():
    det = {"label": "person", "bbox": {"x": 0, "y": 0, "w": 100, "h": 200}}
    assert check_fall(det, 1.2) is False


def test_check_fall_ignores_non_person():
    det = {"label": "car", "bbox": {"x": 0, "y": 0, "w": 200, "h": 100}}
    assert check_fall(det, 1.2) is False


def test_check_fall_zero_height():
    det = {"label": "person", "bbox": {"x": 0, "y": 0, "w": 200, "h": 0}}
    assert check_fall(det, 1.2) is False
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_behavior.py -q`
Expected: 11 passed, 4 FAIL — `ImportError: cannot import name 'check_fall'`

- [ ] **Step 3: Implementar**

Adicionar ao final de `secur/behavior.py`:

```python
def check_fall(detection, aspect_ratio):
    """Heurística de queda: pessoa com bbox deitada (w/h >= aspect_ratio).

    Subset viável do spec 3.4: ângulo do torso exigiria modelo de pose
    local (YOLO-pose) com custo de inferência proibitivo no hardware alvo
    — mantido como backlog (ver README).
    """
    if detection.get("label") != "person":
        return False
    bbox = detection.get("bbox") or {}
    h = bbox.get("h", 0)
    w = bbox.get("w", 0)
    if h <= 0:
        return False
    return (w / h) >= aspect_ratio
```

Adicionar a `secur/config.py` (após as vars de loitering):

```python
FALL_ASPECT_RATIO = float(os.getenv("FALL_ASPECT_RATIO", "1.2"))
```

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_behavior.py -q`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add secur/behavior.py secur/config.py tests/test_behavior.py
git commit -m "feat: fall detection heuristic"
```

---

### Task 5: `decide_worker_event` com comportamento + cooldowns por evento

**Files:**
- Modify: `secur/main.py` (`decide_worker_event`)
- Modify: `secur/config.py` (`ALERT_COOLDOWN_BY_EVENT`)
- Test: `tests/test_main_filters.py`

**Interfaces:**
- Consumes: `decide_event` (existente, `identity.py`), `format_detections` (existente), `check_loitering`/`check_direction_crossing`/`check_fall` (Tasks 2-4 — chamadas pelo worker na Task 8, não aqui).
- Produces — nova assinatura (compatível com a antiga, todos os novos params têm default):
  `decide_worker_event(detections, identity_info, zone_classification, camera_name, label=None, in_schedule=True, fall=False, loitering=None, direction=None, now=None) -> tuple|None`
  - Sempre retorna tupla de 6 elementos quando não suprimido (mesmo formato atual).
  - `None` = suprimido (fora do horário sem evento de identidade válido).
  - Prioridade: identidade > fall > loitering > direction > snapshot > motion.
  - Config: `ALERT_COOLDOWN_BY_EVENT["loitering"]` (env `ALERT_COOLDOWN_LOITERING`, default `300`), `["direction_change"]` (env `ALERT_COOLDOWN_DIRECTION`, default `60`), `["fall_detected"]` (env `ALERT_COOLDOWN_FALL`, default `30`).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_main_filters.py`:

```python
from secur.main import decide_worker_event


def test_decide_worker_event_outside_schedule_suppresses_non_identity():
    assert decide_worker_event([{"label": "person"}], None, "pública", "Cam",
                               in_schedule=False) is None


def test_decide_worker_event_unknown_in_restricted_outside_schedule():
    identity_info = {"known": False, "name": "desconhecido"}
    decision = decide_worker_event([{"label": "person"}], identity_info, "privativa", "Cam",
                                   label="person", in_schedule=False)
    assert decision[0] == "intruder_detected"


def test_decide_worker_event_known_outside_schedule():
    identity_info = {"known": True, "name": "Alice"}
    decision = decide_worker_event([{"label": "person"}], identity_info, "privativa", "Cam",
                                   label="person", in_schedule=False)
    assert decision[0] == "identity_recognized"
    assert decision[2] == "Alice"


def test_decide_worker_event_unknown_public_outside_schedule_suppressed():
    identity_info = {"known": False, "name": "desconhecido"}
    assert decide_worker_event([{"label": "person"}], identity_info, "pública", "Cam",
                               label="person", in_schedule=False) is None


def test_decide_worker_event_fall():
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True,
                                   fall=True, now=100.0)
    assert decision[0] == "fall_detected"


def test_decide_worker_event_loitering_before_direction():
    loitering = {"label": "person", "first_seen": 100.0}
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True,
                                   loitering=loitering, direction="entrando", now=130.0)
    assert decision[0] == "loitering"
    assert "30s" in decision[1]


def test_decide_worker_event_direction():
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True,
                                   direction="entrando", now=100.0)
    assert decision[0] == "direction_change"
    assert "entrando" in decision[1]


def test_decide_worker_event_identity_wins_over_fall():
    identity_info = {"known": True, "name": "Alice"}
    decision = decide_worker_event([], identity_info, "privativa", "Cam", label="person",
                                   in_schedule=True, fall=True, now=100.0)
    assert decision[0] == "identity_recognized"


def test_decide_worker_event_snapshot_and_motion_fallbacks():
    decision = decide_worker_event([{"label": "person"}], None, "pública", "Cam", in_schedule=True)
    assert decision[0] == "snapshot_info"

    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True)
    assert decision[0] == "motion_detected"


def test_get_cooldown_for_event_behavior_events():
    from secur.config import ALERT_COOLDOWN_BY_EVENT
    assert get_cooldown_for_event("loitering") == ALERT_COOLDOWN_BY_EVENT["loitering"]
    assert get_cooldown_for_event("direction_change") == ALERT_COOLDOWN_BY_EVENT["direction_change"]
    assert get_cooldown_for_event("fall_detected") == ALERT_COOLDOWN_BY_EVENT["fall_detected"]
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py -q`
Expected: FAIL — `TypeError: decide_worker_event() got an unexpected keyword argument 'in_schedule'` (e falha de `assert` no cooldown por eventos faltantes)

- [ ] **Step 3: Implementar**

Substituir a função `decide_worker_event` em `secur/main.py` (linhas 345-352) por:

```python
def decide_worker_event(detections, identity_info, zone_classification, camera_name, label=None,
                        in_schedule=True, fall=False, loitering=None, direction=None, now=None):
    """Decide o evento do frame (Fase 3: comportamento/anomalia).

    Prioridade: identidade (intruder_detected/identity_recognized) > queda >
    loitering > direção > snapshot > movimento. Fora do horário
    (in_schedule=False), apenas eventos de identidade válidos passam:
    intruder_detected (desconhecido em zona privativa/segurança, prioridade)
    e identity_recognized (conhecido); os demais retornam None (suprimido).
    """
    if identity_info is not None:
        decision = decide_event(identity_info, zone_classification, camera_name, label)
        if decision is not None:
            if not in_schedule and decision[0] == "unknown_detected":
                return None
            return decision
    if not in_schedule:
        return None
    if fall:
        return ("fall_detected", f"Possível queda de pessoa na câmera {camera_name}", None, None, None, None)
    if loitering is not None:
        seconds = int(now - loitering["first_seen"]) if now is not None else 0
        track_label = loitering.get("label", "Objeto")
        return ("loitering", f"{track_label} na mesma região há {seconds}s (câmera {camera_name})",
                None, None, track_label, None)
    if direction is not None:
        return ("direction_change", f"Movimento {direction} detectado na câmera {camera_name}",
                None, None, None, None)
    if detections:
        return ("snapshot_info", format_detections(detections), None, None, None, None)
    return ("motion_detected", f"Movimento detectado na câmera {camera_name}", None, None, None, None)
```

Adicionar ao `ALERT_COOLDOWN_BY_EVENT` em `secur/config.py` (linhas 24-27):

```python
    "loitering": float(os.getenv("ALERT_COOLDOWN_LOITERING", "300")),
    "direction_change": float(os.getenv("ALERT_COOLDOWN_DIRECTION", "60")),
    "fall_detected": float(os.getenv("ALERT_COOLDOWN_FALL", "30")),
```

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py -q`
Expected: todos passam (incluindo os pré-existentes)

- [ ] **Step 5: Commit**

```bash
git add secur/main.py secur/config.py tests/test_main_filters.py
git commit -m "feat: behavior events in decide_worker_event"
```

---

### Task 6: Storage — coluna `zones.direction_line` + CRUD

**Files:**
- Modify: `secur/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: padrão JSON de `schedule`/`retention_policy` das zonas.
- Produces:
  - Coluna `zones.direction_line TEXT` (migração via `PRAGMA table_info` + `ALTER TABLE`).
  - `add_zone(name, classification='pública', schedule=None, retention_policy=None, direction_line=None) -> int`
  - `update_zone(zone_id, name, classification, schedule=None, retention_policy=None, direction_line=None) -> bool`
  - `list_zones()`/`get_zone()` retornam `direction_line` parseado (ou `None`).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_zone_direction_line_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    line = {"axis": "vertical", "position": 0.5}
    zone_id = storage.add_zone("Sala", "privativa", direction_line=line)
    assert storage.get_zone(zone_id)["direction_line"] == line

    storage.update_zone(zone_id, "Sala", "privativa", direction_line=None)
    assert storage.get_zone(zone_id)["direction_line"] is None

    storage.close()


def test_zone_direction_line_default_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Sala", "privativa")
    assert storage.get_zone(zone_id)["direction_line"] is None
    storage.close()


def test_migration_adds_direction_line_column(tmp_path):
    import sqlite3
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE zones (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL UNIQUE, classification TEXT NOT NULL DEFAULT 'pública', schedule TEXT)"
    )
    conn.execute("INSERT INTO zones (name, classification) VALUES ('Sala', 'privativa')")
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    zone = storage.get_zone(1)
    assert zone is not None
    assert zone["direction_line"] is None
    storage.close()
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: FAIL — `TypeError: add_zone() got an unexpected keyword argument 'direction_line'`

- [ ] **Step 3: Implementar**

Em `secur/storage.py`, no bloco de migração de zonas (linhas 107-115, dentro do `try` que consulta `PRAGMA table_info(zones)`), adicionar após o `if 'retention_policy'`:

```python
                if 'direction_line' not in cols:
                    cursor.execute("ALTER TABLE zones ADD COLUMN direction_line TEXT")
```

Substituir `add_zone` (linhas 251-260) por:

```python
    def add_zone(self, name: str, classification: str = 'pública', schedule=None, retention_policy=None, direction_line=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO zones (name, classification, schedule, retention_policy, direction_line) VALUES (?, ?, ?, ?, ?)",
                (name, classification, json.dumps(schedule) if schedule else None,
                 json.dumps(retention_policy) if retention_policy else None,
                 json.dumps(direction_line) if direction_line else None),
            )
            self.connection.commit()
            return cursor.lastrowid
```

Substituir o SELECT de `list_zones` (linha 265) e o parse (linhas 267-270) por:

```python
            cursor.execute("SELECT id, name, classification, schedule, retention_policy, direction_line FROM zones ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["schedule"] = json.loads(row["schedule"]) if row.get("schedule") else None
            row["retention_policy"] = json.loads(row["retention_policy"]) if row.get("retention_policy") else None
            row["direction_line"] = json.loads(row["direction_line"]) if row.get("direction_line") else None
        return rows
```

Substituir o SELECT de `get_zone` (linha 275) e o parse (linhas 280-281) por:

```python
            cursor.execute("SELECT id, name, classification, schedule, retention_policy, direction_line FROM zones WHERE id = ?", (zone_id,))
            row = cursor.fetchone()
            if not row:
                return None
            zone = dict(row)
        zone["schedule"] = json.loads(zone["schedule"]) if zone.get("schedule") else None
        zone["retention_policy"] = json.loads(zone["retention_policy"]) if zone.get("retention_policy") else None
        zone["direction_line"] = json.loads(zone["direction_line"]) if zone.get("direction_line") else None
        return zone
```

Substituir `update_zone` (linhas 284-293) por:

```python
    def update_zone(self, zone_id: int, name: str, classification: str, schedule=None, retention_policy=None, direction_line=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE zones SET name = ?, classification = ?, schedule = ?, retention_policy = ?, direction_line = ? WHERE id = ?",
                (name, classification, json.dumps(schedule) if schedule else None,
                 json.dumps(retention_policy) if retention_policy else None,
                 json.dumps(direction_line) if direction_line else None, zone_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
```

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: todos passam (incluindo os pré-existentes de zona/migração)

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py tests/test_storage.py
git commit -m "feat: zones direction_line storage"
```

---

### Task 7: API — validação e aceite de `direction_line` nas zonas

**Files:**
- Modify: `secur/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `storage.add_zone`/`update_zone` com `direction_line` (Task 6).
- Produces:
  - `_is_valid_direction_line(line) -> bool` — True se `None` ou dict `{"axis": "vertical"|"horizontal", "position": número 0-1}` (bool NÃO conta como número).
  - POST `/zones` e PUT `/zones/<id>` aceitam `direction_line` e o ecoam na resposta (POST 201, PUT 200).
  - Erro 400: `{"error": "direction_line deve ser {\"axis\": \"vertical|horizontal\", \"position\": 0-1}"}`

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_app.py`:

```python
def test_add_zone_with_direction_line(client):
    resp = client.post("/zones", json={
        "name": "Portão", "classification": "segurança",
        "direction_line": {"axis": "vertical", "position": 0.5},
    })
    assert resp.status_code == 201
    assert resp.json["direction_line"] == {"axis": "vertical", "position": 0.5}


def test_add_zone_rejects_invalid_direction_line(client):
    resp = client.post("/zones", json={
        "name": "Portão", "classification": "segurança",
        "direction_line": {"axis": "diagonal", "position": 0.5},
    })
    assert resp.status_code == 400

    resp = client.post("/zones", json={
        "name": "Portão", "classification": "segurança",
        "direction_line": {"axis": "vertical", "position": 2},
    })
    assert resp.status_code == 400

    resp = client.post("/zones", json={
        "name": "Portão", "classification": "segurança",
        "direction_line": "vertical",
    })
    assert resp.status_code == 400


def test_update_zone_direction_line(client):
    resp = client.post("/zones", json={"name": "Entrada", "classification": "pública"})
    zone_id = resp.json["id"]
    resp = client.put(f"/zones/{zone_id}", json={
        "name": "Entrada", "classification": "pública",
        "direction_line": {"axis": "horizontal", "position": 0.3},
    })
    assert resp.status_code == 200
    assert resp.json["direction_line"] == {"axis": "horizontal", "position": 0.3}
```

- [ ] **Step 2: Rodar e verificar que falha**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: FAIL — POST retorna 201 mas sem `direction_line` na resposta (assert falha)

- [ ] **Step 3: Implementar**

Em `secur/app.py`, adicionar após `_is_valid_retention_policy` (linhas 33-45):

```python
def _is_valid_direction_line(line):
    """True se None ou dict {"axis": "vertical"|"horizontal", "position": float 0-1}."""
    if line is None:
        return True
    if not isinstance(line, dict):
        return False
    axis = line.get("axis")
    position = line.get("position")
    if axis not in ("vertical", "horizontal"):
        return False
    if isinstance(position, bool) or not isinstance(position, (int, float)):
        return False
    return 0.0 <= position <= 1.0
```

Em `add_zone` (linhas 559-584): adicionar leitura do payload após `retention_policy = payload.get("retention_policy")` (linha 565):

```python
        direction_line = payload.get("direction_line")
```

Após o bloco de validação do `retention_policy` (linha 577), adicionar:

```python
        if not _is_valid_direction_line(direction_line):
            return jsonify({"error": "direction_line deve ser {\"axis\": \"vertical|horizontal\", \"position\": 0-1}"}), 400
```

Substituir a chamada ao storage (linha 583) por:

```python
        zone_id = storage.add_zone(name, classification, schedule=schedule,
                                   retention_policy=retention_policy, direction_line=direction_line)
        return jsonify({"id": zone_id, "name": name, "classification": classification,
                        "schedule": schedule, "retention_policy": retention_policy,
                        "direction_line": direction_line}), 201
```

Em `update_zone` (linhas 586-612): adicionar leitura após `retention_policy = payload.get("retention_policy")` (linha 596):

```python
        direction_line = payload.get("direction_line")
```

Após o bloco de validação do `retention_policy` (linha 608), adicionar:

```python
        if not _is_valid_direction_line(direction_line):
            return jsonify({"error": "direction_line deve ser {\"axis\": \"vertical|horizontal\", \"position\": 0-1}"}), 400
```

Substituir a chamada ao storage (linha 610) por:

```python
        storage.update_zone(zone_id, name, classification, schedule=schedule,
                            retention_policy=retention_policy, direction_line=direction_line)
```

(O PUT já responde com `updated_zone` completo de `storage.get_zone` — inclui `direction_line` automaticamente.)

- [ ] **Step 4: Rodar e verificar que passa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: todos passam (incluindo os pré-existentes de zona)

- [ ] **Step 5: Commit**

```bash
git add secur/app.py tests/test_app.py
git commit -m "feat: direction_line zone API"
```

---

### Task 8: Wiring no `CameraWorker` (tracker + regras + supressão por schedule)

**Files:**
- Modify: `secur/main.py` (`CameraWorker.run`)
- Test: nenhum novo (worker não é testável diretamente — padrão das Fases 2/4); rodar a suíte completa como regressão.

**Interfaces:**
- Consumes: `IoUTracker` + `TRACK_IOU_THRESHOLD`/`TRACK_MAX_AGE_SECONDS` (Task 1); `check_loitering`/`LOITERING_*` (Task 2); `check_direction_crossing` (Task 3); `check_fall`/`FALL_ASPECT_RATIO` (Task 4); `decide_worker_event` nova assinatura (Task 5); `zones.direction_line` (Tasks 6-7).
- Produces: comportamento em produção — `loitering`/`direction_change`/`fall_detected` disparados com cooldown próprio; supressão fora do horário via `event_type is None`.

- [ ] **Step 1: Adicionar imports**

Em `secur/main.py`, adicionar aos imports de `secur.config` (bloco atual linhas 7-30, após `is_privacy_mode_on`):

```python
    TRACK_IOU_THRESHOLD,
    TRACK_MAX_AGE_SECONDS,
    LOITERING_SECONDS,
    LOITERING_MAX_DISTANCE,
    LOITERING_LABELS,
    FALL_ASPECT_RATIO,
```

E após `from .identity import ...` (linha 39):

```python
from .tracking import IoUTracker
from .behavior import check_loitering, check_direction_crossing, check_fall
```

- [ ] **Step 2: Instanciar o tracker por câmera**

Em `CameraWorker.run()`, após `motion_detector = MotionDetector(min_area=MOTION_MIN_AREA)` (linha 93), adicionar:

```python
        tracker = IoUTracker(iou_threshold=TRACK_IOU_THRESHOLD, max_age_seconds=TRACK_MAX_AGE_SECONDS)
```

- [ ] **Step 3: Ler `direction_line` da zona**

No bloco de zone lookup (após `zone_retention = zone_obj.get("retention_policy")`, linha 190), adicionar:

```python
                    zone_direction_line = zone_obj.get("direction_line")
```

- [ ] **Step 4: Atualizar tracks e computar regras**

Após o filtro de exclusão (`detections = [d for d in detections if not bbox_center_in_polygons(...)]`, linha 204), adicionar:

```python
                    tracks = tracker.update(detections, now=now)

                    loitering = check_loitering(
                        tracks, now, LOITERING_SECONDS, LOITERING_MAX_DISTANCE, set(LOITERING_LABELS)
                    )

                    fall = any(check_fall(d, FALL_ASPECT_RATIO) for d in detections)

                    direction = None
                    if zone_direction_line and tracks:
                        if zone_direction_line.get("axis") == "vertical":
                            line_px = {"axis": "vertical", "x": zone_direction_line["position"] * frame.shape[1]}
                        else:
                            line_px = {"axis": "horizontal", "y": zone_direction_line["position"] * frame.shape[0]}
                        for t in tracks:
                            direction = check_direction_crossing(t["prev_centroid"], t["centroid"], line_px)
                            if direction is not None:
                                break
```

- [ ] **Step 5: Chamar `decide_worker_event` com os novos parâmetros**

Substituir a chamada atual (linhas 219-221) por:

```python
                    event_type, details, identity_name, known, _label, category = decide_worker_event(
                        detections, identity_info, zone_classification, self.camera["name"], identity_label,
                        in_schedule=is_within_schedule(zone_schedule, now),
                        fall=fall, loitering=loitering, direction=direction, now=now,
                    )
```

- [ ] **Step 6: Substituir a supressão por schedule por `event_type is None`**

Substituir o bloco atual (linhas 246-251):

```python
                        now = time.time()
                        if not is_within_schedule(zone_schedule, now):
                            logger.debug(
                                "Evento suprimido (fora do horário) câmera=%s evento=%s",
                                self.camera.get("name"), event_type,
                            )
```

por:

```python
                        now = time.time()
                        if event_type is None:
                            logger.debug(
                                "Evento suprimido (fora do horário ou sem evento) câmera=%s",
                                self.camera.get("name"),
                            )
```

**Nota:** com o novo fluxo, thumbnails capturados em frames suprimidos ficam com `event_type=None` (a captura continua ocorrendo ANTES da decisão, como hoje). Comportamento aceitável e documentado.

- [ ] **Step 7: Rodar a suíte completa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: todos passam (suíte atual: 153 passed, 2 skipped)

- [ ] **Step 8: Commit**

```bash
git add secur/main.py
git commit -m "feat: worker behavior wiring"
```

---

### Task 9: Dashboard — campo `direction_line` no formulário de zona + docs

**Files:**
- Modify: `secur/templates/dashboard.html`
- Modify: `secur/static/dashboard.js`
- Modify: `README.md`
- Test: nenhum novo (UI) — rodar a suíte completa como regressão.

**Interfaces:**
- Consumes: `zones.direction_line` da API (Task 7) e formato JSON `{"axis", "position"}`.
- Produces: campo editável no dashboard (textarea JSON, prefill no modo edição, validação client-side) e documentação do comportamento.

- [ ] **Step 1: Adicionar o campo ao `zone-dialog`**

Em `secur/templates/dashboard.html`, após o bloco `zone-schedule-end` (linhas 240-242), adicionar:

```html
                        <div class="form-row">
                            <label for="zone-direction-line">Linha de direção (JSON)</label>
                            <textarea id="zone-direction-line" rows="2" placeholder='{"axis":"vertical","position":0.5}'></textarea>
                        </div>
```

- [ ] **Step 2: Prefill no modo edição**

Em `secur/static/dashboard.js`, no `setZoneFormMode` (linhas 522-557), após o bloco que preenche `startInput`/`endInput` (linhas 543-549), adicionar:

```js
  const directionInput = document.getElementById('zone-direction-line');
  if (mode === 'edit' && zone) {
    directionInput.value = zone.direction_line ? JSON.stringify(zone.direction_line) : '';
  } else {
    directionInput.value = '';
  }
```

- [ ] **Step 3: Parse no submit**

Em `secur/static/dashboard.js`, no `submitZoneForm`, após `payload.schedule = schedule;` (linha ~581), adicionar:

```js
  const directionText = document.getElementById('zone-direction-line').value.trim();
  let directionLine = null;
  if (directionText) {
    try {
      directionLine = JSON.parse(directionText);
    } catch (e) {
      message.textContent = 'Linha de direção: JSON inválido.';
      message.classList.add('error');
      return;
    }
  }
  payload.direction_line = directionLine;
```

- [ ] **Step 4: Documentar no README**

Em `README.md`, após a seção `## Privacidade` (linhas 187-193), adicionar:

```markdown
## Comportamento e anomalias (Fase 3)

- **Loitering**: pessoa/veículo na mesma região por ≥ `LOITERING_SECONDS` (default 30s) dispara o evento `loitering` (cooldown próprio, env `ALERT_COOLDOWN_LOITERING`).
- **Direção de movimento**: configure uma linha virtual por zona (`direction_line` JSON: `{"axis":"vertical"|"horizontal","position":0-1}`) — cruzá-la dispara `direction_change` com a direção (entrando/saindo).
- **Zona restrita fora de horário**: desconhecido em zona privativa/segurança fora do schedule da zona → `intruder_detected` (prioridade); pessoa conhecida → `identity_recognized`.
- **Queda (heurística)**: pessoa com bbox deitada (`w/h ≥ FALL_ASPECT_RATIO`, default 1.2) → `fall_detected`. O ângulo do torso por modelo de pose local fica como backlog (custo de inferência no hardware).
```

- [ ] **Step 5: Rodar a suíte completa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: todos passam (suíte atual: 153 passed, 2 skipped)

- [ ] **Step 6: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js README.md
git commit -m "feat: direction_line dashboard field and docs"
```

---

## Self-Review

**1. Cobertura do spec (Fase 3, linhas ~146-182):**
- 3.1 Loitering → Task 2 (regra) + Task 1 (tracking) + Task 5 (evento/cooldown) + Task 8 (wiring). Testes do spec: "associa bbox entre frames" (Task 1), "dispara após o tempo limite" (Task 2), "não dispara com movimento contínuo" (Task 2). ✓
- 3.2 Direção → Task 3 (regra) + Task 6/7 (limite configurável na zona) + Task 9 (UI) + Task 8 (wiring). Teste do spec: "centroide cruza o limite → evento com direção correta" (Task 3 + Task 5). ✓
- 3.3 Zona restrita fora de horário → Task 5 (`in_schedule` + prioridade de identidade). Teste do spec: "regra combinada (fora do horário + desconhecido → intruder)" (Task 5). ✓
- 3.4 Queda → Task 4 (avaliação de viabilidade documentada + heurística `check_fall`) + Task 5 (evento) + README (backlog do pose). Teste do spec: "fixture com pose sintética (em pé vs deitado)" (Task 4, bbox sintética). ✓

**2. Varredura de placeholders:** nenhum "TBD/TODO/similar to Task N" — todas as tasks têm código verbatim e comandos exatos. ✓

**3. Consistência de tipos/nomes entre tasks:**
- Track dict: `first_seen`/`first_centroid`/`centroid`/`prev_centroid`/`label` — definidos na Task 1, consumidos nas Tasks 2/3/5/8 com os mesmos nomes. ✓
- `check_loitering(tracks, now, loiter_seconds, max_distance, labels)` — Task 2 define, Task 8 chama com `set(LOITERING_LABELS)`. ✓
- `check_direction_crossing(prev_centroid, curr_centroid, line)` com `line` em px — Task 3 define, Task 8 converte `position` (fração) × `frame.shape`. ✓
- `check_fall(detection, aspect_ratio)` — Task 4 define, Task 8 chama com `FALL_ASPECT_RATIO`. ✓
- `decide_worker_event(..., in_schedule=True, fall=False, loitering=None, direction=None, now=None)` — Task 5 define (defaults preservam chamadas antigas), Task 8 chama com todos os params. ✓
- `zones.direction_line` JSON `{"axis", "position"}` — Tasks 6/7 (storage/API) e Task 9 (UI) usam o mesmo formato. ✓
- Cooldowns: `loitering`/`direction_change`/`fall_detected` adicionados ao `ALERT_COOLDOWN_BY_EVENT` na Task 5, testados em `test_get_cooldown_for_event_behavior_events`. ✓
- Import circular: `main.py` importa `tracking.py`/`behavior.py` (puros, sem importar `main`/`config`), `behavior.py` não importa nada do projeto. ✓
- `ALERT_COOLDOWN_BY_EVENT` está em `config.py` e `get_cooldown_for_event` em `main.py` (já existente, sem mudança). ✓
