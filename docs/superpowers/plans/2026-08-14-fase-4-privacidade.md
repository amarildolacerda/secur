# Fase 4 — Privacidade e Robustez Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar mascaramento de regiões (4.1), retenção seletiva por zona (4.2), modo privacidade (4.3) e badge "100% local" (4.4).

**Architecture:** `cameras.mask_polygons` (JSON, mesmo formato de `exclusion_zones` da Fase 1) com blur gaussiano aplicado ANTES de salvar thumbnail/clipe/snapshot — detecção sempre usa o frame original; `zones.retention_policy` (JSON `{"thumbnails": N, "clips": N, "days": N}`) respeitada pelos `prune_*`; flag global `PRIVACY_MODE` (env + tabela `settings`) desliga o reconhecimento de identidade com toggle via API/dashboard; badge estático no footer + documentação.

**Tech Stack:** Python 3.10+, OpenCV (`cv2.GaussianBlur`/`cv2.fillPoly`), SQLite (padrão `PRAGMA table_info` + `ALTER TABLE`), Flask, dashboard pt-BR.

## Global Constraints

- Branch `dev`; commits em inglês (`feat:`/`test:`/`docs:`); TDD (teste falha → implementa → passa → commit).
- Venv: `/tmp/secur-venv/bin/python -m pytest tests/<arquivo> -q`.
- Schema: nunca recriar tabelas; usar `PRAGMA table_info` + `ALTER TABLE` para colunas novas.
- `mask_polygons` e `retention_policy` seguem o padrão JSON das colunas da Fase 1: `None` quando não configurado, parse com `json.loads` nos getters.
- `mask_polygons` usa EXATAMENTE o formato de `exclusion_zones` (lista de polígonos; cada polígono é uma lista de `{"x": int, "y": int}`).
- **A máscara NUNCA é aplicada no frame de detecção** — detecção usa o frame original; blur só nos frames que serão persistidos/exibidos (thumbnail, clipe, snapshot).
- `EventStorage.__init__` apaga o DB sob pytest — testes usam `tmp_path`.
- UI pt-BR, padrões de `dashboard.html`/`dashboard.js` (`.form-row`, `.switch`/`.slider`, modal `hidden-panel`).
- `storage.py` já importa `from datetime import datetime, timezone` — adicionar `timedelta` no mesmo import.
- Timestamps ISO UTC (`datetime.now(timezone.utc).isoformat()`) — comparação lexicográfica de strings ISO é válida para o mesmo formato/timezone.

---

### Task 1: Storage — coluna `cameras.mask_polygons` + CRUD

**Files:**
- Modify: `secur/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: padrão JSON de `alert_classes`/`exclusion_zones` (já existente).
- Produces:
  - Coluna `cameras.mask_polygons TEXT` (migração via `PRAGMA table_info` + `ALTER TABLE`).
  - `add_camera(name, source, zone=None, alert_classes=None, exclusion_zones=None, mask_polygons=None) -> int`
  - `update_camera(camera_id, name, source, zone=None, alert_classes=None, exclusion_zones=None, mask_polygons=None) -> bool`
  - `list_cameras()`/`get_camera()` retornam `mask_polygons` parseado (ou `None`).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_camera_mask_polygons_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    polygons = [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]
    cam_id = storage.add_camera("Cam", "source://x", "entrada", mask_polygons=polygons)
    cam = storage.get_camera(cam_id)
    assert cam["mask_polygons"] == polygons

    storage.update_camera(cam_id, "Cam", "source://y", "entrada", mask_polygons=None)
    cam = storage.get_camera(cam_id)
    assert cam["mask_polygons"] is None

    storage.close()


def test_camera_mask_polygons_default_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")
    cam = storage.get_camera(cam_id)
    assert cam["mask_polygons"] is None
    assert cam["exclusion_zones"] is None
    storage.close()


def test_migration_adds_mask_polygons_column(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE cameras (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source TEXT NOT NULL, zone TEXT)"
    )
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    cam_id = storage.add_camera(
        "Cam", "source://x", "entrada",
        mask_polygons=[[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]],
    )
    assert storage.get_camera(cam_id)["mask_polygons"] == [
        [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]
    ]
    storage.close()
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py::test_camera_mask_polygons_crud tests/test_storage.py::test_camera_mask_polygons_default_none tests/test_storage.py::test_migration_adds_mask_polygons_column -q`
Expected: FAIL — `TypeError: add_camera() got an unexpected keyword argument 'mask_polygons'`.

- [ ] **Step 3: Implementar**

Em `secur/storage.py`:

1. Na `_create_tables`, dentro do bloco `try:` de migração das colunas de `cameras` (após o `if 'exclusion_zones' not in cols:`), adicionar:

```python
                if 'mask_polygons' not in cols:
                    cursor.execute("ALTER TABLE cameras ADD COLUMN mask_polygons TEXT")
```

2. Substituir `add_camera`:

```python
    def add_camera(self, name: str, source: str, zone: str = None, alert_classes=None, exclusion_zones=None, mask_polygons=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, source, zone, alert_classes, exclusion_zones, mask_polygons) VALUES (?, ?, ?, ?, ?, ?)",
                (name, source, zone,
                 json.dumps(alert_classes) if alert_classes else None,
                 json.dumps(exclusion_zones) if exclusion_zones else None,
                 json.dumps(mask_polygons) if mask_polygons else None),
            )
            self.connection.commit()
            return cursor.lastrowid
```

3. Substituir `list_cameras` (SELECT e parse):

```python
    def list_cameras(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone, alert_classes, exclusion_zones, mask_polygons FROM cameras ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["alert_classes"] = json.loads(row["alert_classes"]) if row.get("alert_classes") else None
            row["exclusion_zones"] = json.loads(row["exclusion_zones"]) if row.get("exclusion_zones") else None
            row["mask_polygons"] = json.loads(row["mask_polygons"]) if row.get("mask_polygons") else None
        return rows
```

4. Substituir `get_camera` (SELECT e parse):

```python
    def get_camera(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, source, zone, alert_classes, exclusion_zones, mask_polygons FROM cameras WHERE id = ?", (camera_id,))
            row = cursor.fetchone()
            if not row:
                return None
            camera = dict(row)
        camera["alert_classes"] = json.loads(camera["alert_classes"]) if camera.get("alert_classes") else None
        camera["exclusion_zones"] = json.loads(camera["exclusion_zones"]) if camera.get("exclusion_zones") else None
        camera["mask_polygons"] = json.loads(camera["mask_polygons"]) if camera.get("mask_polygons") else None
        return camera
```

5. Substituir `update_camera`:

```python
    def update_camera(self, camera_id: int, name: str, source: str, zone: str = None, alert_classes=None, exclusion_zones=None, mask_polygons=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE cameras SET name = ?, source = ?, zone = ?, alert_classes = ?, exclusion_zones = ?, mask_polygons = ? WHERE id = ?",
                (name, source, zone,
                 json.dumps(alert_classes) if alert_classes else None,
                 json.dumps(exclusion_zones) if exclusion_zones else None,
                 json.dumps(mask_polygons) if mask_polygons else None,
                 camera_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: PASS (inclui os existentes).

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py tests/test_storage.py
git commit -m "feat: camera mask_polygons storage column and CRUD"
```

---

### Task 2: Módulo `masking.py` — blur por polígonos (4.1)

**Files:**
- Create: `secur/masking.py`
- Test: `tests/test_masking.py`

**Interfaces:**
- Consumes: formato de polígonos de `exclusion_zones`/`mask_polygons` (Task 1) — lista de `{"x","y"}`.
- Produces:
  - `apply_mask_blur(frame, polygons) -> np.ndarray` — cópia do frame com blur gaussiano nas regiões dos polígonos (frame original NÃO é mutado).
  - `frame_for_storage(frame, mask_polygons)` — retorna frame mascarado se `mask_polygons` configurado, senão o MESMO frame (sem cópia; quem salva não precisa de cópia).

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_masking.py`:

```python
import numpy as np
from secur.masking import apply_mask_blur, frame_for_storage

POLYGONS = [[{"x": 40, "y": 40}, {"x": 60, "y": 40}, {"x": 60, "y": 60}, {"x": 40, "y": 60}]]


def _frame_with_white_square():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[45:55, 45:55] = 255  # quadrado branco 10x10 no centro
    return frame


def test_apply_mask_blur_masks_polygon_region():
    frame = _frame_with_white_square()
    out = apply_mask_blur(frame, POLYGONS)
    # dentro do polígono o blur espalha o branco com o fundo preto
    assert int(out[50, 50, 0]) < 200
    # fora do polígono permanece intacto
    assert int(out[10, 10, 0]) == 0


def test_apply_mask_blur_keeps_original_intact():
    frame = _frame_with_white_square()
    original = frame.copy()
    apply_mask_blur(frame, POLYGONS)
    assert np.array_equal(frame, original)


def test_apply_mask_blur_no_polygons_returns_copy():
    frame = _frame_with_white_square()
    out = apply_mask_blur(frame, None)
    assert np.array_equal(out, frame)
    assert out is not frame


def test_frame_for_storage_no_polygons_returns_same_frame():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    assert frame_for_storage(frame, None) is frame
    assert frame_for_storage(frame, []) is frame


def test_frame_for_storage_with_polygons_returns_masked():
    frame = _frame_with_white_square()
    out = frame_for_storage(frame, POLYGONS)
    assert not np.array_equal(out, frame)
    assert int(out[50, 50, 0]) < 200
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_masking.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'secur.masking'`.

- [ ] **Step 3: Implementar**

Criar `secur/masking.py`:

```python
"""Mascaramento de regiões para privacidade (Fase 4.1).

A máscara é aplicada APENAS nos frames que serão persistidos ou exibidos
(thumbnail, clipe, snapshot). O frame de detecção SEMPRE usa o original.
"""

import cv2
import numpy as np


def apply_mask_blur(frame, polygons):
    """Retorna cópia do frame com blur gaussiano nas regiões dos polígonos.

    polygons é uma lista de polígonos; cada polígono é uma lista de
    {"x": int, "y": int} (mesmo formato de exclusion_zones/mask_polygons).
    O frame original nunca é modificado.
    """
    if not polygons:
        return frame.copy()
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for poly in polygons:
        pts = np.array([[p["x"], p["y"]] for p in poly], dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    blurred = cv2.GaussianBlur(frame, (0, 0), 15)
    out = frame.copy()
    out[mask > 0] = blurred[mask > 0]
    return out


def frame_for_storage(frame, mask_polygons):
    """Frame pronto para persistência/exibição: mascarado se configurado.

    Sem polígonos retorna o MESMO frame (sem cópia) para não alocar memória
    no hot path do worker.
    """
    if mask_polygons:
        return apply_mask_blur(frame, mask_polygons)
    return frame
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_masking.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/masking.py tests/test_masking.py
git commit -m "feat: polygon mask blur helper for storage frames"
```

---

### Task 3: Worker — aplicar blur antes de salvar thumbnail/clipe (4.1)

**Files:**
- Modify: `secur/main.py` (`CameraWorker.run`)

**Interfaces:**
- Consumes: `frame_for_storage(frame, mask_polygons)` (Task 2); `self.camera["mask_polygons"]` (Task 1, já parseado por `list_cameras`).
- Produces: `CameraWorker.run()` usa frame mascarado (`storage_frame`) para buffer do clipe, thumbnail e `clip_writer.write`; detecção/movimento continuam com `frame` original.

- [ ] **Step 1: Escrever os testes que falham**

Não há teste direto do worker (thread + câmera real — mesmo padrão da Fase 2). A lógica pura já está testada na Task 2. Verificação: a suíte existente não deve quebrar e o módulo deve importar.

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_masking.py -q`
Expected: PASS (pré-condição).

- [ ] **Step 2: Implementar**

Em `secur/main.py`:

1. Adicionar ao import do topo (após `from .geometry import bbox_center_in_polygons`):

```python
from .masking import frame_for_storage
```

2. No início do `while` do `run()`, logo após o bloco `frame = camera_stream.read()` / `if frame is None:` e antes de `now = time.time()`, calcular o frame mascarado UMA vez por frame:

```python
            # Máscara de privacidade: o que é salvo/exibido (thumbnail, clipe,
            # snapshot) usa o frame mascarado; a detecção abaixo usa `frame` original.
            storage_frame = frame_for_storage(frame, self.camera.get("mask_polygons"))
```

3. No push do buffer pré-evento (bloco `if now - last_buffer_push >= 1.0 / CLIP_FPS:`), trocar o frame codificado:

```python
                ok, jpg = cv2.imencode(".jpg", storage_frame)
```

4. No write pós-evento do clipe (dentro de `if now < clip_end_time:`):

```python
                            clip_writer.write(storage_frame)
```

5. No primeiro bloco de thumbnail (dentro do `else:` do filtro de classes, bloco `if should_capture_thumbnail(...)`), trocar o frame codificado:

```python
                                ok, jpg = cv2.imencode(".jpg", storage_frame)
```

6. No segundo bloco de thumbnail (após o `except` do processamento, bloco contínuo de movimento), trocar o frame codificado:

```python
                        ok, jpg = cv2.imencode(".jpg", storage_frame)
```

Nota: os frames do buffer já chegam mascarados (item 3) — o clipe inteiro (pré + pós) fica mascarado. A detecção (`motion_detector.detect(frame)`, `object_detector.detect(frame)`, crop de identidade) continua usando `frame`.

- [ ] **Step 3: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_masking.py tests/test_main_filters.py -q`
Expected: PASS.

Run: `/tmp/secur-venv/bin/python -c "import secur.main"` no diretório `/mnt/c/git/secur`
Expected: sem erro de import.

- [ ] **Step 4: Commit**

```bash
git add secur/main.py
git commit -m "feat: apply mask blur before saving thumbnails and clips"
```

---

### Task 4: API — `mask_polygons` nos endpoints de câmera + snapshot mascarado (4.1)

**Files:**
- Modify: `secur/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `storage.add_camera`/`update_camera` com `mask_polygons` (Task 1); `frame_for_storage` (Task 2).
- Produces:
  - `POST /cameras` e `PUT /cameras/<id>` aceitam `mask_polygons` (lista de polígonos; 400 se não for lista) e retornam no JSON.
  - `GET /camera/<id>/snapshot` retorna o frame com máscara aplicada.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_app.py`:

```python
def test_add_camera_with_mask_polygons(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    polygons = [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]
    response = client.post(
        "/cameras",
        data=json.dumps({"name": "Cam", "source": "valid-source", "zone": "entrada", "mask_polygons": polygons}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["mask_polygons"] == polygons


def test_add_camera_rejects_invalid_mask_polygons(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    response = client.post(
        "/cameras",
        data=json.dumps({"name": "Cam", "source": "valid-source", "mask_polygons": "not-a-list"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_update_camera_mask_polygons(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    resp = client.post("/cameras", json={"name": "Cam", "source": "valid-source", "zone": "entrada"})
    cam_id = resp.json["id"]

    polygons = [[{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 50}]]
    resp = client.put(
        f"/cameras/{cam_id}",
        data=json.dumps({"name": "Cam", "source": "valid-source", "zone": "entrada", "mask_polygons": polygons}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["mask_polygons"] == polygons


def test_snapshot_route_applies_mask_polygons(client, monkeypatch):
    import cv2
    import numpy as np
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))

    class FakeCapture:
        def __init__(self, source):
            pass

        def isOpened(self):
            return True

        def set(self, *args, **kwargs):
            return True

        def read(self):
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[45:55, 45:55] = 255  # quadrado branco no centro
            return True, frame

        def release(self):
            pass

    monkeypatch.setattr("secur.app.cv2.VideoCapture", FakeCapture)

    resp = client.post(
        "/cameras",
        data=json.dumps({
            "name": "Cam", "source": "source://x", "zone": "entrada",
            "mask_polygons": [[{"x": 40, "y": 40}, {"x": 60, "y": 40}, {"x": 60, "y": 60}, {"x": 40, "y": 60}]],
        }),
        content_type="application/json",
    )
    cam_id = resp.json["id"]

    resp = client.get(f"/camera/{cam_id}/snapshot")
    assert resp.status_code == 200
    arr = cv2.imdecode(np.frombuffer(resp.data, np.uint8), cv2.IMREAD_COLOR)
    # dentro do polígono o blur espalhou o branco com o fundo preto
    assert int(arr[50, 50, 0]) < 200
    # fora do polígono permanece preto (JPEG pode variar ~poucos níveis)
    assert int(arr[10, 10, 0]) < 10


def test_snapshot_route_without_mask_keeps_frame(client, monkeypatch):
    import cv2
    import numpy as np
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))

    class FakeCapture:
        def __init__(self, source):
            pass

        def isOpened(self):
            return True

        def set(self, *args, **kwargs):
            return True

        def read(self):
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[45:55, 45:55] = 255
            return True, frame

        def release(self):
            pass

    monkeypatch.setattr("secur.app.cv2.VideoCapture", FakeCapture)

    resp = client.post("/cameras", json={"name": "Cam", "source": "source://x", "zone": "entrada"})
    cam_id = resp.json["id"]

    resp = client.get(f"/camera/{cam_id}/snapshot")
    assert resp.status_code == 200
    arr = cv2.imdecode(np.frombuffer(resp.data, np.uint8), cv2.IMREAD_COLOR)
    assert int(arr[50, 50, 0]) > 200  # branco puro preservado
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py::test_add_camera_with_mask_polygons tests/test_app.py::test_add_camera_rejects_invalid_mask_polygons tests/test_app.py::test_update_camera_mask_polygons tests/test_app.py::test_snapshot_route_applies_mask_polygons tests/test_app.py::test_snapshot_route_without_mask_keeps_frame -q`
Expected: FAIL — `KeyError: 'mask_polygons'` no JSON de resposta e snapshot sem máscara.

- [ ] **Step 3: Implementar**

Em `secur/app.py`:

1. Adicionar ao import do topo (após `from .storage import EventStorage`):

```python
from .masking import frame_for_storage
```

2. No `add_camera`, após `exclusion_zones = payload.get("exclusion_zones")`:

```python
        mask_polygons = payload.get("mask_polygons")
```

Após a validação de `exclusion_zones`:

```python
        if mask_polygons is not None and not isinstance(mask_polygons, list):
            return jsonify({"error": "mask_polygons deve ser uma lista de polígonos"}), 400
```

Trocar a chamada ao storage e o JSON de resposta:

```python
        camera_id = storage.add_camera(name, source, zone, alert_classes=alert_classes, exclusion_zones=exclusion_zones, mask_polygons=mask_polygons)
        return jsonify({
            "id": camera_id, "name": name, "source": source, "zone": zone,
            "alert_classes": alert_classes, "exclusion_zones": exclusion_zones,
            "mask_polygons": mask_polygons,
        }), 201
```

3. No `update_camera`, após `exclusion_zones = payload.get("exclusion_zones")`:

```python
        mask_polygons = payload.get("mask_polygons")
```

Após a validação de `exclusion_zones`:

```python
        if mask_polygons is not None and not isinstance(mask_polygons, list):
            return jsonify({"error": "mask_polygons deve ser uma lista de polígonos"}), 400
```

Trocar a chamada ao storage:

```python
        storage.update_camera(camera_id, name, source, zone, alert_classes=alert_classes, exclusion_zones=exclusion_zones, mask_polygons=mask_polygons)
```

4. Na rota `camera_snapshot`, após `result["frame"]` ser validado (antes do `cv2.imencode`):

```python
        frame = result["frame"]
        frame = frame_for_storage(frame, camera.get("mask_polygons"))
        success, jpg = cv2.imencode(".jpg", frame)
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/app.py tests/test_app.py
git commit -m "feat: mask_polygons API on camera endpoints and masked snapshot"
```

---

### Task 5: Dashboard — editor de máscara no form da câmera (4.1)

**Files:**
- Modify: `secur/templates/dashboard.html`, `secur/static/dashboard.js`

**Interfaces:**
- Consumes: `POST/PUT /cameras` com `mask_polygons` (Task 4).
- Produces: textarea JSON "Máscara (JSON)" no form da câmera (padrão de `exclusion_zones`) + coluna "Máscara" na tabela de gerenciamento.

- [ ] **Step 1: Implementar o HTML**

Em `secur/templates/dashboard.html`, após o form-row de `camera-exclusion-zones` (linhas ~168-171), adicionar:

```html
                        <div class="form-row">
                            <label for="camera-mask-polygons">Máscara de privacidade (JSON)</label>
                            <textarea id="camera-mask-polygons" rows="3" placeholder='[{"x":0,"y":0},{"x":100,"y":0},{"x":100,"y":100}]'></textarea>
                            <small style="color:var(--muted-subtle);">Regiões com blur nos thumbnails, clipes e snapshot. Mesmo formato das zonas de exclusão.</small>
                        </div>
```

Na tabela de câmeras (`camera-management`), adicionar a coluna na cabeçalho:

```html
                                <th>Exclusões</th>
                                <th>Máscara</th>
                                <th>Ações</th>
```

- [ ] **Step 2: Implementar o JS**

Em `secur/static/dashboard.js`:

1. Em `createCameraRow`, após `exclusionsText`, adicionar:

```javascript
  const maskText = camera.mask_polygons && camera.mask_polygons.length
    ? `${camera.mask_polygons.length} polígono(s)`
    : '—';
```

E no HTML da linha (após o `<td>${exclusionsText}</td>`):

```javascript
      <td>${maskText}</td>
```

2. Em `setCameraFormMode`, após o bloco do `exclusionInput`, adicionar:

```javascript
  const maskInput = document.getElementById('camera-mask-polygons');
  if (maskInput) {
    maskInput.value = camera && camera.mask_polygons ? JSON.stringify(camera.mask_polygons) : '';
  }
```

3. Em `submitCameraForm`, após o parse de `exclusionZones`, adicionar:

```javascript
  const maskText = document.getElementById('camera-mask-polygons').value.trim();
  let maskPolygons = null;
  if (maskText) {
    try {
      maskPolygons = JSON.parse(maskText);
    } catch (e) {
      message.textContent = 'Máscara de privacidade: JSON inválido.';
      message.classList.add('error');
      return;
    }
  }
  payload.mask_polygons = maskPolygons;
```

- [ ] **Step 3: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS (API intacta; UI sem testes automatizados).

- [ ] **Step 4: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js
git commit -m "feat: mask polygon editor in camera form"
```

---

### Task 6: Storage — `zones.retention_policy` + prune por idade (4.2)

**Files:**
- Modify: `secur/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: padrão JSON de `zones.schedule`.
- Produces:
  - Coluna `zones.retention_policy TEXT` (migração) — JSON `{"thumbnails": N, "clips": N, "days": N}` (campos opcionais).
  - `add_zone(name, classification='pública', schedule=None, retention_policy=None) -> int`
  - `update_zone(zone_id, name, classification, schedule=None, retention_policy=None) -> bool`
  - `list_zones()`/`get_zone()` retornam `retention_policy` parseado.
  - `prune_camera_thumbnails(camera_id, keep=20, max_age_days=None)` — além do `keep`, remove registros com timestamp mais antigo que `max_age_days` dias.
  - `prune_event_clips(camera_id, keep=20, max_age_days=None)` — idem para clipes.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_zone_retention_policy_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    policy = {"thumbnails": 5, "clips": 3, "days": 7}
    zone_id = storage.add_zone("Sala", "privativa", retention_policy=policy)
    assert storage.get_zone(zone_id)["retention_policy"] == policy

    storage.update_zone(zone_id, "Sala", "privativa", retention_policy=None)
    assert storage.get_zone(zone_id)["retention_policy"] is None
    storage.close()


def test_zone_retention_policy_default_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Sala", "privativa")
    assert storage.get_zone(zone_id)["retention_policy"] is None
    storage.close()


def test_migration_adds_retention_policy_column(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE zones (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, classification TEXT NOT NULL DEFAULT 'pública')"
    )
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Z", "pública", retention_policy={"days": 30})
    assert storage.get_zone(zone_id)["retention_policy"] == {"days": 30}
    storage.close()


def test_prune_thumbnails_by_max_age(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    old_file = tmp_path / "old.jpg"
    old_file.write_bytes(b"jpegdata")
    old_id = storage.add_camera_thumbnail(cam_id, str(old_file), "motion_detected")
    storage.connection.execute(
        "UPDATE camera_thumbnails SET timestamp = '2020-01-01T00:00:00+00:00' WHERE id = ?",
        (old_id,),
    )
    storage.connection.commit()

    new_file = tmp_path / "new.jpg"
    new_file.write_bytes(b"jpegdata")
    storage.add_camera_thumbnail(cam_id, str(new_file), "motion_detected")

    storage.prune_camera_thumbnails(cam_id, keep=10, max_age_days=7)
    thumbs = storage.list_camera_thumbnails(cam_id)
    assert len(thumbs) == 1
    assert thumbs[0]["path"] == str(new_file)
    assert not Path(old_file).exists()
    storage.close()


def test_prune_clips_by_max_age(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    old_file = tmp_path / "old.mp4"
    old_file.write_bytes(b"mp4data")
    old_id = storage.add_event_clip(cam_id, None, str(old_file), 10.0)
    storage.connection.execute(
        "UPDATE event_clips SET timestamp = '2020-01-01T00:00:00+00:00' WHERE id = ?",
        (old_id,),
    )
    storage.connection.commit()

    new_file = tmp_path / "new.mp4"
    new_file.write_bytes(b"mp4data")
    storage.add_event_clip(cam_id, None, str(new_file), 10.0)

    storage.prune_event_clips(cam_id, keep=10, max_age_days=7)
    clips = storage.list_event_clips(cam_id)
    assert len(clips) == 1
    assert clips[0]["path"] == str(new_file)
    assert not Path(old_file).exists()
    storage.close()
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py::test_zone_retention_policy_crud tests/test_storage.py::test_zone_retention_policy_default_none tests/test_storage.py::test_migration_adds_retention_policy_column tests/test_storage.py::test_prune_thumbnails_by_max_age tests/test_storage.py::test_prune_clips_by_max_age -q`
Expected: FAIL — `TypeError: add_zone() got an unexpected keyword argument 'retention_policy'`.

- [ ] **Step 3: Implementar**

Em `secur/storage.py`:

1. Trocar o import de datetime para incluir `timedelta`:

```python
from datetime import datetime, timezone, timedelta
```

2. Na `_create_tables`, dentro do bloco `try:` de migração de `zones` (após o `if 'schedule' not in cols:`), adicionar:

```python
                if 'retention_policy' not in cols:
                    cursor.execute("ALTER TABLE zones ADD COLUMN retention_policy TEXT")
```

3. Substituir `add_zone`:

```python
    def add_zone(self, name: str, classification: str = 'pública', schedule=None, retention_policy=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO zones (name, classification, schedule, retention_policy) VALUES (?, ?, ?, ?)",
                (name, classification, json.dumps(schedule) if schedule else None,
                 json.dumps(retention_policy) if retention_policy else None),
            )
            self.connection.commit()
            return cursor.lastrowid
```

4. Substituir `list_zones` (SELECT e parse):

```python
    def list_zones(self):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification, schedule, retention_policy FROM zones ORDER BY id ASC")
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["schedule"] = json.loads(row["schedule"]) if row.get("schedule") else None
            row["retention_policy"] = json.loads(row["retention_policy"]) if row.get("retention_policy") else None
        return rows
```

5. Substituir `get_zone` (SELECT e parse):

```python
    def get_zone(self, zone_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name, classification, schedule, retention_policy FROM zones WHERE id = ?", (zone_id,))
            row = cursor.fetchone()
            if not row:
                return None
            zone = dict(row)
        zone["schedule"] = json.loads(zone["schedule"]) if zone.get("schedule") else None
        zone["retention_policy"] = json.loads(zone["retention_policy"]) if zone.get("retention_policy") else None
        return zone
```

6. Substituir `update_zone`:

```python
    def update_zone(self, zone_id: int, name: str, classification: str, schedule=None, retention_policy=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE zones SET name = ?, classification = ?, schedule = ?, retention_policy = ? WHERE id = ?",
                (name, classification, json.dumps(schedule) if schedule else None,
                 json.dumps(retention_policy) if retention_policy else None, zone_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
```

7. Substituir `prune_camera_thumbnails`:

```python
    def prune_camera_thumbnails(self, camera_id: int, keep: int = 20, max_age_days: int = None):
        with self.lock:
            cursor = self.connection.cursor()
            if max_age_days:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
                cursor.execute(
                    "SELECT id, path FROM camera_thumbnails WHERE camera_id = ? AND timestamp < ?",
                    (camera_id, cutoff),
                )
                for item in [dict(row) for row in cursor.fetchall()]:
                    try:
                        Path(item["path"]).unlink(missing_ok=True)
                    except Exception:
                        logger.warning("Falha ao remover thumbnail %s", item["path"])
                    cursor.execute("DELETE FROM camera_thumbnails WHERE id = ?", (item["id"],))
            cursor.execute(
                "SELECT id, path FROM camera_thumbnails WHERE camera_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                (camera_id, keep),
            )
            excess = [dict(row) for row in cursor.fetchall()]
            for item in excess:
                try:
                    Path(item["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover thumbnail %s", item["path"])
                cursor.execute("DELETE FROM camera_thumbnails WHERE id = ?", (item["id"],))
            self.connection.commit()
```

8. Substituir `prune_event_clips`:

```python
    def prune_event_clips(self, camera_id: int, keep: int = 20, max_age_days: int = None):
        with self.lock:
            cursor = self.connection.cursor()
            if max_age_days:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
                cursor.execute(
                    "SELECT id, path FROM event_clips WHERE camera_id = ? AND timestamp < ?",
                    (camera_id, cutoff),
                )
                for item in [dict(row) for row in cursor.fetchall()]:
                    try:
                        Path(item["path"]).unlink(missing_ok=True)
                    except Exception:
                        logger.warning("Falha ao remover clipe %s", item["path"])
                    cursor.execute("DELETE FROM event_clips WHERE id = ?", (item["id"],))
            cursor.execute(
                "SELECT id, path FROM event_clips WHERE camera_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                (camera_id, keep),
            )
            excess = [dict(row) for row in cursor.fetchall()]
            for item in excess:
                try:
                    Path(item["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover clipe %s", item["path"])
                cursor.execute("DELETE FROM event_clips WHERE id = ?", (item["id"],))
            self.connection.commit()
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py tests/test_storage.py
git commit -m "feat: zone retention policy storage and age-based prune"
```

---

### Task 7: Worker + API — política de retenção aplicada ao prune (4.2)

**Files:**
- Modify: `secur/main.py`, `secur/app.py`
- Test: `tests/test_main_filters.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `resolve_retention` (produzida aqui); `zones.retention_policy` (Task 6); `prune_*` com `max_age_days` (Task 6).
- Produces:
  - `resolve_retention(policy, kind, default) -> (keep, days)` — função pura: `keep = policy.get(kind) if kind in policy else default`; `days = policy.get("days")`; sem política → `(default, None)`.
  - `CameraWorker.run()`: resolve a política da zona da câmera e passa `keep`/`max_age_days` aos 3 prunes (clip, thumbnail do alerta, thumbnail contínuo).
  - `POST /zones` e `PUT /zones/<id>` aceitam `retention_policy` (dict com `thumbnails`/`clips`/`days` ints >= 0; 400 se inválido).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_main_filters.py`:

```python
def test_resolve_retention_default_when_no_policy():
    from secur.main import resolve_retention
    assert resolve_retention(None, "thumbnails", 30) == (30, None)
    assert resolve_retention({}, "thumbnails", 30) == (30, None)


def test_resolve_retention_policy_values():
    from secur.main import resolve_retention
    policy = {"thumbnails": 5, "clips": 3, "days": 7}
    assert resolve_retention(policy, "thumbnails", 30) == (5, 7)
    assert resolve_retention(policy, "clips", 20) == (3, 7)


def test_resolve_retention_partial_policy():
    from secur.main import resolve_retention
    policy = {"days": 2}
    assert resolve_retention(policy, "thumbnails", 30) == (30, 2)


def test_resolve_retention_zero_keep_is_respected():
    from secur.main import resolve_retention
    policy = {"thumbnails": 0}
    assert resolve_retention(policy, "thumbnails", 30) == (0, None)
```

Adicionar ao final de `tests/test_app.py`:

```python
def test_add_zone_with_retention_policy(client):
    resp = client.post(
        "/zones",
        data=json.dumps({"name": "Entrada", "classification": "pública",
                         "retention_policy": {"thumbnails": 5, "clips": 3, "days": 7}}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json["retention_policy"] == {"thumbnails": 5, "clips": 3, "days": 7}


def test_add_zone_rejects_invalid_retention_policy(client):
    resp = client.post(
        "/zones",
        data=json.dumps({"name": "Entrada", "classification": "pública", "retention_policy": "5"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    resp = client.post(
        "/zones",
        data=json.dumps({"name": "Entrada", "classification": "pública", "retention_policy": {"days": -1}}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_update_zone_retention_policy(client):
    resp = client.post("/zones", json={"name": "Entrada", "classification": "pública"})
    zone_id = resp.json["id"]
    resp = client.put(
        f"/zones/{zone_id}",
        data=json.dumps({"name": "Entrada", "classification": "pública",
                         "retention_policy": {"thumbnails": 10}}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["retention_policy"] == {"thumbnails": 10}
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py::test_resolve_retention_default_when_no_policy tests/test_main_filters.py::test_resolve_retention_policy_values tests/test_main_filters.py::test_resolve_retention_partial_policy tests/test_main_filters.py::test_resolve_retention_zero_keep_is_respected tests/test_app.py::test_add_zone_with_retention_policy tests/test_app.py::test_add_zone_rejects_invalid_retention_policy tests/test_app.py::test_update_zone_retention_policy -q`
Expected: FAIL — `ImportError: cannot import name 'resolve_retention'` e `retention_policy` não aceito nas zonas.

- [ ] **Step 3: Implementar**

Em `secur/main.py`:

1. Adicionar a função pura (após `get_cooldown_for_event`, antes de `CircularFrameBuffer`):

```python
def resolve_retention(policy, kind, default):
    """Resolve (keep, max_age_days) da política de retenção da zona para um tipo.

    policy: dict {"thumbnails": N, "clips": N, "days": N} (campos opcionais).
    kind: "thumbnails" ou "clips".
    Sem política → (default, None). keep=0 é respeitado (apaga tudo).
    """
    if not policy:
        return default, None
    keep = policy.get(kind)
    days = policy.get("days")
    return (int(keep) if keep is not None else default,
            int(days) if days is not None else None)
```

2. Em `CameraWorker.run()`, adicionar variáveis persistentes no início (após `clip_frames_written = 0`):

```python
        thumb_keep, thumb_days = THUMBNAIL_HISTORY_SIZE, None
        clip_keep, clip_days = CLIP_HISTORY_SIZE, None
```

3. No bloco de lookup de zona (onde `zone_classification`/`zone_schedule` são resolvidos), dentro do `if zone_obj:`, adicionar:

```python
                    zone_retention = zone_obj.get("retention_policy")
                    thumb_keep, thumb_days = resolve_retention(zone_retention, "thumbnails", THUMBNAIL_HISTORY_SIZE)
                    clip_keep, clip_days = resolve_retention(zone_retention, "clips", CLIP_HISTORY_SIZE)
```

4. Trocar as 3 chamadas de prune:
   - Finalização do clipe (`self.storage.prune_event_clips(self.camera["id"], keep=CLIP_HISTORY_SIZE)`):

```python
                            self.storage.prune_event_clips(self.camera["id"], keep=clip_keep, max_age_days=clip_days)
```

   - Thumbnail do alerta (`self.storage.prune_camera_thumbnails(self.camera["id"], keep=THUMBNAIL_HISTORY_SIZE)` no bloco do alerta):

```python
                                    self.storage.prune_camera_thumbnails(self.camera["id"], keep=thumb_keep, max_age_days=thumb_days)
```

   - Thumbnail contínuo (bloco pós-except):

```python
                            self.storage.prune_camera_thumbnails(self.camera["id"], keep=thumb_keep, max_age_days=thumb_days)
```

Em `secur/app.py`:

5. Adicionar o validador (após `_is_valid_schedule`):

```python
def _is_valid_retention_policy(policy):
    """True se policy é None ou dict com chaves opcionais thumbnails/clips/days (ints >= 0)."""
    if policy is None:
        return True
    if not isinstance(policy, dict):
        return False
    for key in ("thumbnails", "clips", "days"):
        if key in policy:
            value = policy[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return False
    return True
```

6. Em `add_zone`, após `schedule = payload.get("schedule")`:

```python
        retention_policy = payload.get("retention_policy")
```

Após a validação de `schedule`:

```python
        if not _is_valid_retention_policy(retention_policy):
            return jsonify({"error": "retention_policy deve ser {\"thumbnails\": N, \"clips\": N, \"days\": N}"}), 400
```

Trocar a chamada e o retorno:

```python
        zone_id = storage.add_zone(name, classification, schedule=schedule, retention_policy=retention_policy)
        return jsonify({"id": zone_id, "name": name, "classification": classification, "schedule": schedule, "retention_policy": retention_policy}), 201
```

7. Em `update_zone`, após `schedule = payload.get("schedule")`:

```python
        retention_policy = payload.get("retention_policy")
```

Após a validação de `schedule`:

```python
        if not _is_valid_retention_policy(retention_policy):
            return jsonify({"error": "retention_policy deve ser {\"thumbnails\": N, \"clips\": N, \"days\": N}"}), 400
```

Trocar a chamada:

```python
        storage.update_zone(zone_id, name, classification, schedule=schedule, retention_policy=retention_policy)
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/main.py secur/app.py tests/test_main_filters.py tests/test_app.py
git commit -m "feat: zone retention policy applied to pruning and zone API"
```

---

### Task 8: Modo privacidade — settings table + gate de identidade + API (4.3)

**Files:**
- Modify: `secur/config.py`, `secur/storage.py`, `secur/main.py`, `secur/app.py`
- Test: `tests/test_storage.py`, `tests/test_main_filters.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `build_recognizer`/`IdentityRecognizer` (existentes em `main.py`); `_make_recognizer` (existente em `app.py`).
- Produces:
  - `config.py`: `PRIVACY_MODE` (env, default `"false"`; true para `1/true/yes/on`).
  - `storage.py`: tabela `settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)`; `get_setting(key, default=None)`; `set_setting(key, value)`.
  - `main.py`: `is_privacy_mode_on(value) -> bool` (função pura); `CameraWorker.identity_enabled() -> bool` (checa a flag com cache de 5s; requer `identity_recognizer`); `CameraWorker.run()` usa `identity_enabled()` no bloco de identidade; `main()`: env força `"true"` na tabela, seed `"false"` se ausente, e `identity_recognizer = None` se a flag estiver ativa.
  - `app.py`: `GET /api/settings` → `{"privacy_mode": bool}`; `PUT /api/settings` aceita `{"privacy_mode": bool}` (400 se não for bool).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_settings_get_set(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    assert storage.get_setting("privacy_mode") is None
    assert storage.get_setting("privacy_mode", "false") == "false"

    storage.set_setting("privacy_mode", "true")
    assert storage.get_setting("privacy_mode") == "true"

    storage.set_setting("privacy_mode", "false")
    assert storage.get_setting("privacy_mode") == "false"
    storage.close()
```

Adicionar ao final de `tests/test_main_filters.py`:

```python
def test_is_privacy_mode_on():
    from secur.main import is_privacy_mode_on
    assert is_privacy_mode_on("true") is True
    assert is_privacy_mode_on("True") is True
    assert is_privacy_mode_on("false") is False
    assert is_privacy_mode_on(None) is False


def test_worker_identity_enabled_respects_privacy_mode():
    from secur.main import CameraWorker

    class FakeStorage:
        def __init__(self):
            self.value = "false"

        def get_setting(self, key, default=None):
            return self.value

    worker = CameraWorker(
        camera={"id": 1, "name": "Cam"},
        storage=FakeStorage(),
        alerts=None,
        object_detector=None,
        identity_recognizer=object(),
    )
    assert worker.identity_enabled() is True

    worker.storage.value = "true"
    worker._privacy_check_time = 0.0  # força recarga do cache
    assert worker.identity_enabled() is False


def test_worker_identity_enabled_without_recognizer():
    from secur.main import CameraWorker

    class FakeStorage:
        def get_setting(self, key, default=None):
            return "false"

    worker = CameraWorker(
        camera={"id": 1, "name": "Cam"},
        storage=FakeStorage(),
        alerts=None,
        object_detector=None,
        identity_recognizer=None,
    )
    assert worker.identity_enabled() is False
```

Adicionar ao final de `tests/test_app.py`:

```python
def test_settings_get_default(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json == {"privacy_mode": False}


def test_settings_put_and_get(client):
    resp = client.put("/api/settings", json={"privacy_mode": True})
    assert resp.status_code == 200
    assert resp.json == {"privacy_mode": True}
    assert client.get("/api/settings").json["privacy_mode"] is True


def test_settings_put_invalid(client):
    resp = client.put("/api/settings", json={"privacy_mode": "yes"})
    assert resp.status_code == 400


def test_settings_put_turns_off_again(client):
    client.put("/api/settings", json={"privacy_mode": True})
    resp = client.put("/api/settings", json={"privacy_mode": False})
    assert resp.status_code == 200
    assert client.get("/api/settings").json["privacy_mode"] is False
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py::test_settings_get_set tests/test_main_filters.py::test_is_privacy_mode_on tests/test_main_filters.py::test_worker_identity_enabled_respects_privacy_mode tests/test_main_filters.py::test_worker_identity_enabled_without_recognizer tests/test_app.py::test_settings_get_default tests/test_app.py::test_settings_put_and_get tests/test_app.py::test_settings_put_invalid tests/test_app.py::test_settings_put_turns_off_again -q`
Expected: FAIL — `AttributeError: 'EventStorage' object has no attribute 'get_setting'`, `ImportError: cannot import name 'is_privacy_mode_on'`, `404 Not Found` para `/api/settings`.

- [ ] **Step 3: Implementar**

Em `secur/config.py`, após `IDENTITY_MATCH_THRESHOLD`:

```python
PRIVACY_MODE = os.getenv("PRIVACY_MODE", "false").lower() in ("1", "true", "yes", "on")
```

Em `secur/storage.py`:

1. Na `_create_tables`, após a tabela `notification_routing`, adicionar:

```python
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
```

2. Após `seed_default_routing`, adicionar os métodos:

```python
    def get_setting(self, key: str, default=None):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self.connection.commit()
```

Em `secur/main.py`:

3. Adicionar `PRIVACY_MODE` ao import de config (bloco existente):

```python
    PRIVACY_MODE,
```

4. Adicionar a função pura (após `resolve_retention`):

```python
def is_privacy_mode_on(value):
    """True se o valor da settings/environment representa modo privacidade ativo."""
    return str(value).lower() == "true"
```

5. No `CameraWorker.__init__`, após `self.identity_recognizer = identity_recognizer`:

```python
        self._privacy_check_time = 0.0
        self._privacy_on = False
```

6. Adicionar o método (após `status()`):

```python
    def identity_enabled(self):
        """Reconhecimento de identidade habilitado? (flag de privacidade com cache de 5s)."""
        now = time.time()
        if now - self._privacy_check_time >= 5.0:
            self._privacy_check_time = now
            try:
                self._privacy_on = is_privacy_mode_on(self.storage.get_setting("privacy_mode"))
            except Exception:
                self._privacy_on = False
        return self.identity_recognizer is not None and not self._privacy_on
```

7. No `run()`, trocar a condição do bloco de identidade:

```python
                    if detections and self.identity_enabled():
```

8. Em `main()`, antes de `identity_recognizer = build_recognizer(storage)`:

```python
    if PRIVACY_MODE:
        storage.set_setting("privacy_mode", "true")
    elif storage.get_setting("privacy_mode") is None:
        storage.set_setting("privacy_mode", "false")

    if is_privacy_mode_on(storage.get_setting("privacy_mode")):
        logger.info("Modo privacidade ativo — reconhecimento de identidade desligado")
        identity_recognizer = None
    else:
        identity_recognizer = build_recognizer(storage)
```

Em `secur/app.py`:

9. Adicionar as rotas (após a rota `/api/classes`):

```python
    @app.route("/api/settings")
    def settings_get():
        privacy_mode = storage.get_setting("privacy_mode", "false")
        return jsonify({"privacy_mode": is_privacy_mode_on(privacy_mode)})

    @app.route("/api/settings", methods=["PUT"])
    def settings_put():
        payload = request.get_json() or {}
        privacy_mode = payload.get("privacy_mode")
        if not isinstance(privacy_mode, bool):
            return jsonify({"error": "privacy_mode deve ser booleano"}), 400
        storage.set_setting("privacy_mode", "true" if privacy_mode else "false")
        return jsonify({"privacy_mode": privacy_mode}), 200
```

E o import no topo (após `from .masking import frame_for_storage`):

```python
from .main import is_privacy_mode_on
```

Atenção: `app.py` já importa de `main.py`? Não — `main.py` importa `create_app` de `app.py` (import circular potencial). Para evitar circular import, `main.py` importa `app` no corpo (`from .app import create_app` no topo do `main.py`). Se `app.py` importar `is_privacy_mode_on` do topo de `main.py`, e `main.py` importa `create_app` do topo de `app.py` — ciclo: `app` → `main` → `app`. Solução: definir `is_privacy_mode_on` em `secur/config.py` (sem dependências) e importar de lá nos dois módulos.

- [ ] **Step 3b: Implementar (correção do import circular)**

Em `secur/config.py`, após `PRIVACY_MODE`:

```python
def is_privacy_mode_on(value):
    """True se o valor da settings/environment representa modo privacidade ativo."""
    return str(value).lower() == "true"
```

Em `secur/main.py`:
- NÃO importar `is_privacy_mode_on` de si mesmo; adicionar ao import de config:

```python
    PRIVACY_MODE,
    is_privacy_mode_on,
```

- Remover a definição local de `is_privacy_mode_on` (item 4 acima fica apenas no config).

Em `secur/app.py`, o import no topo:

```python
from .config import is_privacy_mode_on
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py tests/test_main_filters.py tests/test_app.py -q`
Expected: PASS.

Run: `/tmp/secur-venv/bin/python -c "import secur.main; import secur.app"` no diretório `/mnt/c/git/secur`
Expected: sem erro (sem import circular).

- [ ] **Step 5: Commit**

```bash
git add secur/config.py secur/storage.py secur/main.py secur/app.py tests/test_storage.py tests/test_main_filters.py tests/test_app.py
git commit -m "feat: privacy mode setting and identity gate"
```

---

### Task 9: Dashboard — toggle de privacidade + badge "100% local" + docs (4.3/4.4)

**Files:**
- Modify: `secur/templates/dashboard.html`, `secur/static/dashboard.js`, `secur/static/style.css`, `secur/app.py` (rota `/docs`), `README.md`

**Interfaces:**
- Consumes: `GET/PUT /api/settings` (Task 8).
- Produces: nav "Configurações" com toggle de modo privacidade (switch padrão existente); badge estático "100% local" no footer com tooltip; `/docs` lista `/api/settings`; README documenta as 4 features de privacidade.

- [ ] **Step 1: Implementar o HTML**

Em `secur/templates/dashboard.html`:

1. No nav, após o botão de `notifications`, adicionar:

```html
            <button type="button" class="nav-link" data-section="settings" id="nav-settings">
                <span class="icon">&#x1F512;</span>
                <span>Configurações</span>
            </button>
```

2. Após o painel `notifications` (antes de `identities-management`), adicionar o painel:

```html
            <section class="panel hidden-panel" id="settings">
                <h2>Configurações</h2>
                <div class="card">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                        <div>
                            <strong>Modo privacidade</strong>
                            <p style="color:var(--muted-subtle);font-size:0.85rem;margin:4px 0 0;">
                                Desliga o reconhecimento de identidade (faces/ReID). Movimento e
                                detecção de objetos continuam ativos. Tudo permanece 100% local.
                            </p>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="privacy-mode-toggle" />
                            <span class="slider"></span>
                        </label>
                    </div>
                </div>
            </section>
```

3. No footer (`app-footer`), após `<span id="status-workers">`:

```html
            <span class="local-badge" title="Todo o processamento acontece no dispositivo. Nada sai dele, exceto pelos canais que você configurar (Telegram, MQTT, Home Assistant).">100% local</span>
```

- [ ] **Step 2: Implementar o CSS**

Em `secur/static/style.css`, adicionar ao final:

```css
.local-badge {
  background: #1f8a4c;
  color: #fff;
  border-radius: var(--radius-pill, 999px);
  padding: 2px 10px;
  font-size: 0.72rem;
  font-weight: 600;
}
```

- [ ] **Step 3: Implementar o JS**

Em `secur/static/dashboard.js`:

1. Adicionar (após o bloco de Clip History, antes de `createCameraRow`):

```javascript
/* ========== Settings ========== */

async function renderSettings() {
  const toggle = document.getElementById('privacy-mode-toggle');
  if (!toggle) return;
  try {
    const data = await fetchData('/api/settings');
    toggle.checked = !!data.privacy_mode;
  } catch (e) { /* offline: mantém estado atual */ }
}

function setupSettings() {
  const toggle = document.getElementById('privacy-mode-toggle');
  if (!toggle) return;
  toggle.addEventListener('change', async () => {
    const res = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ privacy_mode: toggle.checked }),
    });
    if (!res.ok) {
      toggle.checked = !toggle.checked;
      showMenuMessage('Falha ao salvar configuração.', 'camera-form-message');
    }
  });
}
```

2. Em `renderDashboard`, após `populateZoneDropdown(zones);`, adicionar:

```javascript
  renderSettings();
```

3. No bloco de setup (após `setupZoneForm();`), adicionar:

```javascript
setupSettings();
```

- [ ] **Step 4: Atualizar `/docs` e README**

Em `secur/app.py`, na lista `api_docs` de `/docs`, adicionar após a entrada de `/api/classes`:

```python
            {"path": "/api/settings", "method": "GET", "description": "Flags globais (modo privacidade)"},
            {"path": "/api/settings", "method": "PUT", "description": "Atualiza flags globais (privacy_mode)"},
```

Em `README.md`, adicionar após a seção "Funcionalidades principais" (antes de "Casos de perigo"):

```markdown
## Privacidade

- **100% local**: todo o processamento (detecção, reconhecimento, gravação) roda no dispositivo; nada sai dele, exceto pelos canais que você configurar explicitamente (Telegram, MQTT, Home Assistant).
- **Mascaramento de regiões**: configure polígonos de máscara por câmera (formato JSON igual ao das zonas de exclusão) no dashboard; o blur é aplicado antes de salvar thumbnail, clipe e snapshot — a detecção usa sempre o frame original.
- **Modo privacidade**: desliga o reconhecimento de identidade (movimento e objetos continuam ativos). Ative via env `PRIVACY_MODE=true`, pela API `PUT /api/settings` ou pelo toggle no dashboard (Configurações).
- **Retenção seletiva**: política por zona (`retention_policy` JSON com `thumbnails`, `clips` e `days`) controla o prune de thumbnails e clipes.
```

- [ ] **Step 5: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS (inclui `test_docs_route` com as novas entradas presentes no HTML).

Run: `/tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: PASS (suíte completa, incluindo os novos testes das Tasks 1-8).

- [ ] **Step 6: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js secur/static/style.css secur/app.py README.md
git commit -m "feat: privacy toggle, 100% local badge and privacy docs"
```

---

## Self-Review

**1. Spec coverage (Fase 4):**
- 4.1 Mascaramento de regiões → Task 1 (storage `mask_polygons`), Task 2 (`apply_mask_blur`/`frame_for_storage`), Task 3 (worker salva mascarado), Task 4 (API + snapshot), Task 5 (editor dashboard). ✅
- 4.2 Retenção seletiva → Task 6 (`zones.retention_policy` + prune por idade), Task 7 (worker aplica política + API zonas). ✅
- 4.3 Modo privacidade → Task 8 (flag + settings table + gate do worker + API `/api/settings`), Task 9 (toggle dashboard). ✅
- 4.4 Garantia 100% local → Task 9 (badge footer + README). ✅

**2. Placeholder scan:** Nenhum TBD/TODO; todo passo tem código completo e comandos exatos. Import circular de `is_privacy_mode_on` resolvido no próprio plano (definido em `config.py`, sem dependências). ✅

**3. Type consistency:**
- `add_camera`/`update_camera` com `mask_polygons` (Task 1) — Task 4 chama com o mesmo kwarg. ✅
- `frame_for_storage(frame, mask_polygons)` (Task 2) — Task 3 usa com `self.camera.get("mask_polygons")`; Task 4 usa com `camera.get("mask_polygons")`. ✅
- `prune_camera_thumbnails(camera_id, keep=20, max_age_days=None)` / `prune_event_clips(...)` (Task 6) — Task 7 chama com `keep=thumb_keep, max_age_days=thumb_days` / `clip_keep, clip_days`. ✅
- `resolve_retention(policy, kind, default) -> (keep, days)` (Task 7) — testes e worker usam as mesmas assinaturas. ✅
- `get_setting(key, default=None)` / `set_setting(key, value)` (Task 8) — worker `identity_enabled()`, `main()` e rotas `/api/settings` usam; testes cobrem. ✅
- `is_privacy_mode_on(value)` (Task 8, em `config.py`) — importada por `main.py` e `app.py`; testes cobrem. ✅
- `identity_enabled()` (Task 8) — usado no `run()` do worker; testes instanciam `CameraWorker` sem iniciar thread. ✅

**4. Regra-chave do spec:** a máscara nunca toca o frame de detecção — `storage_frame` é calculado após o read e usado SOMENTE nos pontos de persistência/exibição (Task 3, passos 3-6); detecção/movimento/identidade continuam com `frame` (Task 3 nota). ✅
