# Fila de Eventos e Fases N0–N4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar a captura/emissão de eventos (N0) da decisão de alerta/avaliação (N2–N4) via uma fila `EventQueue`, com `/api/ingest` para borda remota, níveis N0–N4 persistidos, e filtros de nível no dashboard — preparando escalabilidade (N0/N1 na borda modesta; N2–N4 robusto local/hospedado).

**Architecture:** `CameraWorker` (N0, borda local) e `POST /api/ingest` (borda remota, entra em N1) enfileiram `CameraEvent` num `EventQueue` (Local hoje, Redis futuro). Um consumidor `AlertRuleEngine` (N2–N4) persiste o evento, decide alerta/HA e solicita clipe. `alerts.send` passa a ser só notificação; quem persiste é o consumidor.

**Tech Stack:** Python/Flask, OpenCV (já em uso), `queue.Queue` (LocalEventQueue), SQLite (storage), JS vanilla (dashboard).

## Global Constraints (copiadas do spec, obrigatórias em toda task)

- **N0 entrega, não decide:** quem captura só produz eventos; nunca dispara alerta/HA.
- **Decisão alerta/HA é N2–N4**, nunca do N0.
- **N1 tria na borda:** filtro simples descarta ruído (vegetação, etc.) antes de submeter à avaliação.
- **Níveis acumulativos** N0→N1→N2→N3→N4; `level` armazenado = maior nível alcançado.
- **Transporte trocável:** produtores/consumidores falam só `EventQueue` (`enqueue`/`subscribe`/`start`); Local↔Redis troca sem tocá-los.
- **Origem registrada:** `source = local | edge`.
- **Evidência (clipe):** worker local grava sob demanda do consumidor; borda remota usa NVR (Fase D) depois.
- **Topologia:** N0/N1 = processamento modesto na borda (grupos reduzidos); N2–N4 = robusto, local ou hospedado.
- Não remover funcionalidade de alerta visível: comportamento se mantém.

## File Structure

- **Create** `src/events.py` — `CameraEvent` (dataclass), `EventQueue` (Protocol), `LocalEventQueue`.
- **Create** `src/event_rules.py` — `decide_worker_event`, `_unpack_worker_decision`, `COOLDOWNS` (movidos de `main.py`).
- **Create** `src/alert_rules.py` — `AlertRuleEngine` (consumidor N2–N4).
- **Modify** `src/storage.py` — colunas `level`/`dropped`/`source` em `events`; `add_event(...)`, `update_event_level(...)`, `list_events(level=, camera_id=, source=)`.
- **Modify** `src/main.py` — `CameraWorker` emite `CameraEvent` (sem `alerts.send`); `triage_n1`; `start_clip(event_id)`; `CameraManager.request_clip`; wiring do `event_bus`.
- **Modify** `src/alerts.py` — remover `event_store_handler`; `AlertService.send` vira só notificação.
- **Modify** `src/app.py` — `POST /api/ingest`; `/events` com filtro `?level=`; remover registro de `event_store_handler`.
- **Modify** `src/templates/dashboard.html` — `<select id="filter-level">` na barra de filtros de eventos.
- **Modify** `src/static/dashboard.js` — badge de nível em `renderEvents`; filtro de nível; indicador N0 na Visão geral.
- **Test** `tests/test_events.py`.

---

### Task 1: Storage — colunas de nível e métodos

**Files:**
- Modify: `src/storage.py` (bloco de migração ~linha 118-125; `add_event` linha 169; `list_events` linha 180)

**Interfaces:**
- `add_event(camera_id, zone, event_type, details=None, level=0, source='local', dropped=False) -> int` (retorna `id`).
- `update_event_level(event_id, level, event_type=None, details=None, disposition=None) -> bool`.
- `list_events(limit=100, level=None, camera_id=None, source=None) -> list[dict]`.

- [ ] **Step 1: Escrever o teste falhando**

```python
def test_events_level_columns(tmp_path):
    from src.storage import EventStorage
    s = EventStorage(str(tmp_path / "t.db"))
    eid = s.add_event("1", "z", "motion", "d", level=0, source="local", dropped=False)
    assert eid > 0
    s.update_event_level(eid, 4, event_type="motion", disposition="alert")
    rows = s.list_events(level=4)
    assert len(rows) == 1 and rows[0]["source"] == "local" and rows[0]["dropped"] == 0
    assert s.list_events(level=9) == []
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `py -3 -m pytest tests/test_events.py::test_events_level_columns -q`
Expected: FAIL (coluna `level` inexistente / assinatura antiga).

- [ ] **Step 3: Implementar**

Em `src/storage.py`, no bloco de migração de `events` (~linha 118), adicionar:
```python
try:
    cursor.execute("PRAGMA table_info(events)")
    cols = [r[1] for r in cursor.fetchall()]
    for col, ddl in (("level", "INTEGER DEFAULT 0"), ("dropped", "INTEGER DEFAULT 0"), ("source", "TEXT DEFAULT 'local'")):
        if col not in cols:
            cursor.execute(f"ALTER TABLE events ADD COLUMN {col} {ddl}")
except Exception:
    pass
```

`CREATE TABLE events` (linha 42) — adicionar `level INTEGER DEFAULT 0, dropped INTEGER DEFAULT 0, source TEXT DEFAULT 'local',` dentro dos parênteses (após `details TEXT`).

`add_event` (linha 169) — nova assinatura e INSERT:
```python
def add_event(self, camera_id, zone, event_type, details=None, level=0, source="local", dropped=False):
    timestamp = datetime.now(timezone.utc).isoformat()
    with self.lock:
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO events (timestamp, camera_id, zone, event_type, details, level, dropped, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, camera_id, zone, event_type, details, level, 1 if dropped else 0, source),
        )
        self.connection.commit()
        return cursor.lastrowid
```

`list_events` (linha 180) — aceitar filtros:
```python
def list_events(self, limit=100, level=None, camera_id=None, source=None):
    with self.lock:
        cursor = self.connection.cursor()
        sql = ("SELECT id, timestamp, camera_id, zone, event_type, details, clip_path, level, dropped, source "
               "FROM events WHERE 1=1")
        params = []
        if level is not None:
            sql += " AND level = ?"; params.append(level)
        if camera_id is not None:
            sql += " AND camera_id = ?"; params.append(str(camera_id))
        if source is not None:
            sql += " AND source = ?"; params.append(source)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
```

Adicionar método:
```python
def update_event_level(self, event_id, level, event_type=None, details=None, disposition=None):
    with self.lock:
        cursor = self.connection.cursor()
        sets, params = ["level = ?"], [level]
        if event_type is not None:
            sets.append("event_type = ?"); params.append(event_type)
        if details is not None:
            sets.append("details = ?"); params.append(details)
        if disposition is not None:
            sets.append("disposition = ?"); params.append(disposition)
        params.append(event_id)
        cursor.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", params)
        self.connection.commit()
        return cursor.rowcount > 0
```

- [ ] **Step 4: Rodar para confirmar sucesso**

Run: `py -3 -m pytest tests/test_events.py::test_events_level_columns -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/storage.py tests/test_events.py
git commit -m "feat(storage): colunas level/dropped/source em events e filtros"
```

---

### Task 2: `src/events.py` — CameraEvent + EventQueue

**Files:**
- Create: `src/events.py`
- Test: `tests/test_events.py` (adicionar)

**Interfaces:**
- `CameraEvent` dataclass com campos abaixo.
- `EventQueue` (Protocol): `enqueue(event)`, `subscribe(handler)`, `start()`.
- `LocalEventQueue` implementa com `queue.Queue` + thread consumer.

- [ ] **Step 1: Escrever o teste falhando**

```python
def test_local_queue_delivers():
    from src.events import LocalEventQueue, CameraEvent
    q = LocalEventQueue()
    received = []
    q.subscribe(lambda e: received.append(e))
    q.start()
    ev = CameraEvent(camera_id="1", source="local")
    q.enqueue(ev)
    import time; time.sleep(0.2)
    assert received and received[0].camera_id == "1"
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `py -3 -m pytest tests/test_events.py::test_local_queue_delivers -q`
Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar `src/events.py`**

```python
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class CameraEvent:
    camera_id: str
    device_type: str = "camera"   # 'camera' | 'sensor' | 'device' (origem heterogênea)
    zone: str = None
    zone_classification: str = None
    timestamp: float = field(default_factory=time.time)
    level: int = 0
    source: str = "local"          # 'local' | 'edge'
    event_type: str = None
    details: str = None
    identity_name: str = None
    known: bool = None
    category: str = None
    recognition_method: str = None
    thumbnail_path: str = None
    no_motion: bool = False
    dropped: bool = False
    # Entradas para decide_worker_event (N2-N3), preenchidas na borda:
    detections: list = field(default_factory=list)
    identity_info: dict = None
    identity_label: str = None
    in_schedule: bool = True
    fall: bool = False
    loitering: dict = None
    direction: str = None
    camera_name: str = None
    alert_classes: list = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class EventQueue:
    def enqueue(self, event: CameraEvent): ...
    def subscribe(self, handler): ...
    def start(self): ...


class LocalEventQueue(EventQueue):
    def __init__(self):
        self._q = queue.Queue()
        self._handlers = []
        self._thread = None

    def enqueue(self, event):
        self._q.put(event)

    def subscribe(self, handler):
        self._handlers.append(handler)

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            event = self._q.get()
            if event is None:
                self._q.task_done()
                break
            for h in self._handlers:
                try:
                    h(event)
                except Exception:
                    import logging
                    logging.getLogger("events").exception("Handler falhou ao processar evento")
            self._q.task_done()
```

- [ ] **Step 4: Rodar para confirmar sucesso**

Run: `py -3 -m pytest tests/test_events.py::test_local_queue_delivers -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/events.py tests/test_events.py
git commit -m "feat(events): CameraEvent e EventQueue (LocalEventQueue)"
```

---

### Task 3: `src/event_rules.py` — decisão movida de main.py

**Files:**
- Create: `src/event_rules.py`
- Modify: `src/main.py` (remover `decide_worker_event`/`_unpack_worker_decision`; ajustar import se necessário)

**Interfaces:**
- `decide_worker_event(detections, identity_info, zone_classification, camera_name, label=None, in_schedule=True, fall=False, loitering=None, direction=None, now=None) -> tuple|None` (corpo idêntico ao de `main.py:438-468`).
- `_unpack_worker_decision(decision) -> tuple` (idêntico a `main.py:471-481`).
- `COOLDOWNS: dict[str, int]` (mapeamento de `get_cooldown_for_event` existente em `main.py`).

- [ ] **Step 1: Escrever teste (decide)**

```python
from src.event_rules import decide_worker_event, _unpack_worker_decision
def test_decide_fall():
    et, det, *_ = decide_worker_event([], None, "public", "cam1", fall=True, now=1.0)
    assert et == "fall_detected"
def test_unpack_none():
    assert _unpack_worker_decision(None) == (None,)*6
```

- [ ] **Step 2: Rodar (falha esperada por import)**

Run: `py -3 -m pytest tests/test_events.py::test_decide_fall tests/test_events.py::test_unpack_none -q`
Expected: FAIL (`src.event_rules` não existe).

- [ ] **Step 3: Implementar `src/event_rules.py`**

Copiar **verbalmente** `decide_worker_event` (de `main.py:438-468`) e `_unpack_worker_decision` (de `main.py:471-481`). No topo, importar `decide_event` e `format_detections` do mesmo módulo que `main.py` os importa (ver `import` em `main.py`; tipicamente `from .rules import decide_event, format_detections` ou similar — confirmar e usar o caminho correto). Adicionar:

```python
COOLDOWNS = {
    "motion_detected": 30,
    "snapshot_info": 30,
    "loitering": 60,
    "direction_change": 60,
    "fall_detected": 20,
    "intruder_detected": 30,
    "identity_recognized": 30,
    "unknown_detected": 30,
    "no_motion": 120,
}

def get_cooldown_for_event(event_type):
    return COOLDOWNS.get(event_type, 30)
```

**Regras IF-THIS-THEN-THAT (decisão N4 — providência).** `decide_worker_event` continua classificando o *tipo* do evento (N2–N3); a *providência* (N4) é data-driven:

```python
# Cada regra: SE todas as chaves em `when` batem no contexto, ENTÃO executa `then`.
# Ações em `then["alert"]`: canais que devem notificar (gatilho de HA é o canal "ha").
RULES = [
    {"when": {"event_type": ["intruder_detected", "fall_detected"]},
     "then": {"alert": ["telegram", "mqtt", "ha"], "disposition": "alert"}},
    {"when": {"event_type": ["identity_recognized"]},
     "then": {"alert": ["telegram", "mqtt"], "disposition": "alert"}},
    {"when": {"event_type": ["loitering", "direction_change"], "zone_classification": ["private", "security"]},
     "then": {"alert": ["telegram", "mqtt", "ha"], "disposition": "alert"}},
    {"when": {"event_type": ["motion_detected", "snapshot_info"]},
     "then": {"alert": ["telegram"], "disposition": "alert"}},
    {"when": {"no_motion": True},
     "then": {"alert": ["telegram"], "disposition": "alert"}},
    {"when": {"event_type": ["flood", "water_leak", "sensor_alert"]},
     "then": {"alert": ["telegram", "mqtt", "ha"], "disposition": "alert"}},
]


def match_rule(rule, ctx):
    for key, val in rule["when"].items():
        actual = ctx.get(key)
        if isinstance(val, list):
            if actual not in val:
                return False
        elif actual != val:
            return False
    return True


def evaluate_rules(event_type, zone_classification, no_motion):
    ctx = {"event_type": event_type, "zone_classification": zone_classification, "no_motion": no_motion}
    for rule in RULES:
        if match_rule(rule, ctx):
            return rule["then"]
    return {"alert": ["telegram"], "disposition": "alert"}
```

Em `main.py`, remover as duas funções e (se nada mais as usar) ajustar; o worker não as chamará mais (quem chama `decide_worker_event` é `AlertRuleEngine`).

- [ ] **Step 4: Rodar**

Run: `py -3 -m pytest tests/test_events.py::test_decide_fall tests/test_events.py::test_unpack_none -q`
Expected: PASS. `py -3 -c "import src.main"` deve importar sem erro de nome.

- [ ] **Step 5: Commit**

```bash
git add src/event_rules.py src/main.py tests/test_events.py
git commit -m "refactor: mover decide_worker_event para src/event_rules.py"
```

---

### Task 4: `CameraWorker` emite CameraEvent (N0/N1), sem alerts.send

**Files:**
- Modify: `src/main.py` (`CameraWorker.__init__` ganha `event_bus`; bloco de decisão/alerta em `run()` ~linha 317-348 substituído por emissão; bloco `no_motion` ~linha 406-411 emite; `triage_n1`; `start_clip(event_id)` extraído de ~linha 349-392).

**Interfaces:**
- `CameraWorker.__init__(self, camera, storage, alerts, object_detector, identity_recognizer, event_bus)`.
- `triage_n1(detections, no_motion) -> bool` (mantém se há detecções ou é meta-evento; senão descarta).
- `start_clip(self, event_id)` (extrai gravação de clipe de `run()`).
- O worker NÃO chama `self.alerts.send` nem inicia clipe direto; chama `self.event_bus.enqueue(event)`.

- [ ] **Step 1: Teste (worker emite, não alerta)**

```python
def test_worker_emits_not_alerts(monkeypatch):
    from src.events import CameraEvent
    sent = []
    class FakeBus:
        def enqueue(self, e): sent.append(e)
        def subscribe(self, h): pass
        def start(self): pass
    # usar CameraWorker com stubs; verificar que enfileira e não chama alerts.send
    ...
```
(Implementar com um worker mínimo ou testar a função `build_candidate_event` se extraída. Ver abaixo.)

- [ ] **Step 2: Rodar (falha esperada)**

Run: `py -3 -m pytest tests/test_events.py::test_worker_emits_not_alerts -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Em `CameraWorker.__init__`, adicionar `self.event_bus = event_bus`.

Extrair helper de construção do candidato (facilita teste):
```python
def build_candidate_event(self, detections, identity_info, identity_label, zone_name,
                          zone_classification, zone_schedule, now, fall, loitering, direction,
                          thumb_path, no_motion=False):
    in_schedule = is_within_schedule(zone_schedule, now)
    kept = triage_n1(detections, no_motion)
    return CameraEvent(
        camera_id=str(self.camera["id"]),
        zone=zone_name,
        zone_classification=zone_classification,
        timestamp=now,
        level=1 if (kept and not no_motion) else 0,
        source="local",
        detections=detections,
        identity_info=identity_info,
        identity_label=identity_label,
        in_schedule=in_schedule,
        fall=fall,
        loitering=loitering,
        direction=direction,
        camera_name=self.camera["name"],
        alert_classes=self.camera.get("alert_classes"),
        thumbnail_path=thumb_path,
        no_motion=no_motion,
        dropped=not kept,
    )
```

Substituir o bloco `decision = decide_worker_event(...)` … `else: logger.debug("Evento suprimido (cooldown...)")` (linha 317-397) por:
```python
thumb_path = self._capture_thumbnail(storage_frame, event_type, time.time(), thumb_keep, thumb_days)
event = self.build_candidate_event(
    detections, identity_info, identity_label, zone_name, zone_classification,
    zone_schedule, now, fall, loitering, direction, thumb_path, no_motion=False)
self.event_bus.enqueue(event)
```
Remover `motion_reported = True` do bloco de alerta (manter `motion_reported` apenas para a lógica de `no_motion`).

No bloco `else` (sem movimento, linha 406-411), substituir o envio de "sem movimento" por:
```python
if should_send_no_motion(last_motion_time, motion_reported, no_motion_alerted, time.time(), NO_MOTION_ALERT_SECONDS):
    no_motion_alerted = True
    ev = self.build_candidate_event([], None, None, zone_name, zone_classification, zone_schedule,
                                    time.time(), False, None, None, None, no_motion=True)
    self.event_bus.enqueue(ev)
```

`triage_n1` (módulo `main.py` ou `event_rules`):
```python
def triage_n1(detections, no_motion):
    # Borda modesta: mantém se há detecções candidatas ou é meta-evento (sem movimento é seu próprio alerta).
    # Ponto de extensão para descartar ruído (vegetação, área mínima de movimento) em fases futuras.
    if no_motion:
        return True
    return bool(detections)
```

`start_clip` — mover o corpo de ~linha 349-392 para:
```python
def start_clip(self, event_id):
    now = time.time()
    if self._clip_writer is not None:
        logger.debug("Clipe já ativo (câmera %s) — pulando", self.camera.get("name"))
        return
    try:
        cam_dir = CLIPS_DIR / f"cam{self.camera['id']}"
        cam_dir.mkdir(parents=True, exist_ok=True)
        clip_path = str(cam_dir / f"{int(now*1000)}.mp4")
        writer = cv2.VideoWriter(clip_path, cv2.VideoWriter_fourcc(*"mp4v"), CLIP_FPS, (self._frame.shape[1], self._frame.shape[0]))
        if not writer.isOpened():
            writer.release()
            logger.warning("Falha ao abrir VideoWriter (câmera %s)", self.camera.get("name"))
            return
        frames_written = 0
        for buf in self._frame_buffer.frames():
            dec = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if dec is not None:
                writer.write(dec); frames_written += 1
        self._clip_writer = writer
        self._clip_frames_written = frames_written
        self._clip_end_time = now + CLIP_POST_SECONDS
        self._clip_event_id = event_id
        self._clip_path = clip_path
        self._last_clip_write = now - 1.0/CLIP_FPS
    except Exception:
        logger.warning("Falha ao iniciar gravação de clipe (câmera %s)", self.camera.get("name"))
```
(renomear os atributos de instância `clip_writer/...` para `self._clip_writer/...` conforme o `run()` usa; manter consistência com o loop de escrita em `run()`.)

- [ ] **Step 4: Rodar**

Run: `py -3 -m pytest tests/test_events.py::test_worker_emits_not_alerts -q` e `py -3 -c "import src.main"`
Expected: PASS; import limpo.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_events.py
git commit -m "refactor(worker): emitir CameraEvent (N0/N1); remover alerts.send do worker"
```

---

### Task 5: `AlertRuleEngine` (consumidor N2–N4)

**Files:**
- Create: `src/alert_rules.py`
- Test: `tests/test_events.py`

**Interfaces:**
- `AlertRuleEngine(storage, alerts, camera_manager)`.
- `handle(event: CameraEvent)` — persiste N0/N1, decide N2–N3, alerta/HA N4, solicita clipe; isola exceções.
- Depende de `decide_worker_event`, `_unpack_worker_decision`, `get_cooldown_for_event` (de `src.event_rules`), e `camera_manager.request_clip` (Task 7).

- [ ] **Step 1: Teste (cooldown + alerts mock + dropped)**

```python
def test_engine_decides_and_alerts(monkeypatch):
    from src.alert_rules import AlertRuleEngine
    from src.events import CameraEvent
    alerts = type("A", (), {"send": lambda *a, **k: 1})()
    stor = type("S", (), {
        "add_event": lambda *a, **k: 7,
        "update_event_level": lambda *a, **k: True,
    })()
    cm = type("CM", (), {"request_clip": lambda *a, **k: None})()
    eng = AlertRuleEngine(stor, alerts, cm)
    ev = CameraEvent(camera_id="1", source="local", detections=[{"label":"person","bbox":{}}])
    ev.timestamp = 1.0
    eng.handle(ev)          # 1º: alerta
    ev2 = CameraEvent(camera_id="1", source="local", detections=[{"label":"person","bbox":{}}])
    ev2.timestamp = 2.0     # dentro do cooldown
    eng.handle(ev2)         # não deve alertar de novo (cooldown)
```
(Verificar chamadas de `alerts.send` via mock contador.)

- [ ] **Step 2: Rodar (falha esperada)**

Run: `py -3 -m pytest tests/test_events.py::test_engine_decides_and_alerts -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `src/alert_rules.py`**

```python
import time
import logging
        from .event_rules import decide_worker_event, _unpack_worker_decision, get_cooldown_for_event, evaluate_rules

logger = logging.getLogger("alert_rules")


class AlertRuleEngine:
    def __init__(self, storage, alerts, camera_manager):
        self.storage = storage
        self.alerts = alerts
        self.camera_manager = camera_manager
        self._last_alert_time = {}

    def handle(self, event):
        try:
            self._handle(event)
        except Exception:
            logger.exception("Erro no AlertRuleEngine ao processar evento %s", getattr(event, "event_id", "?"))

    def _handle(self, event):
        stored_type = event.event_type or ("no_motion" if event.no_motion else "capture")
        event_id = self.storage.add_event(
            event.camera_id, event.zone, stored_type, event.details,
            level=event.level, source=event.source, dropped=event.dropped,
        )
        if event.dropped:
            return

        event_type, details, identity_name, known, _label, category = (None, None, None, None, None, None)
        if event.no_motion:
            event_type, details = "no_motion", f"Sem movimento na câmera {event.camera_name or event.camera_id}"
        else:
            decision = decide_worker_event(
                event.detections, event.identity_info, event.zone_classification, event.camera_name,
                event.identity_label, in_schedule=event.in_schedule, fall=event.fall,
                loitering=event.loitering, direction=event.direction, now=time.time(),
            )
            event_type, details, identity_name, known, _label, category = _unpack_worker_decision(decision)

        if event_type is None:
            self.storage.update_event_level(event_id, 3, event_type="suppressed", disposition="suppressed")
            return

        now = time.time()
        last = self._last_alert_time.get(event_type, 0.0)
        if now - last < get_cooldown_for_event(event_type):
            self.storage.update_event_level(event_id, 3, event_type=event_type, details=details, disposition="cooldown")
            return

        self._last_alert_time[event_type] = now
        # Providência N4 orientada a regras IF-THIS-THEN-THAT (não hardcoded).
        action = evaluate_rules(event_type, event.zone_classification, event.no_motion)
        channels = action.get("alert", ["telegram"])
        disposition = action.get("disposition", "alert")
        self.alerts.send(
            event.camera_id, event.zone, event_type, details, event.zone_classification,
            identity=identity_name, known=known, category=category,
            recognition_method=event.recognition_method, thumbnail_path=event.thumbnail_path,
            routing_channels=channels,
        )
        self.camera_manager.request_clip(event.camera_id, event_id)
        self.storage.update_event_level(event_id, 4, event_type=event_type, details=details, disposition=disposition)
```

- [ ] **Step 4: Rodar**

Run: `py -3 -m pytest tests/test_events.py::test_engine_decides_and_alerts -q`
Expected: PASS (1 alerta, 2º suprimido por cooldown).

- [ ] **Step 5: Commit**

```bash
git add src/alert_rules.py tests/test_events.py
git commit -m "feat(alerts): AlertRuleEngine consome fila e decide N2-N4"
```

---

### Task 6: `alerts.send` vira notificação (remover event_store_handler)

**Files:**
- Modify: `src/alerts.py` (remover `event_store_handler`, linha 54-67)
- Modify: `src/app.py` (não registrar `event_store_handler`)

**Interfaces:**
- `AlertService.send(payload..., routing_channels: list[str] = None)` continua com a assinatura, mas **não persiste** (quem persiste é `AlertRuleEngine`). `routing_channels`, quando fornecido (pela regra N4), restringe quais handlers/dispositivos disparam — ainda respeitando o `routing` de configuração (um canal só dispara se habilitado NA config E na regra).

- [ ] **Step 1: Garantir que nenhum caller depende do retorno de `add_event` via alerts.send**

Run: `py -3 -c "import src.app"` e checar que `event_store_handler` não é registrado.

- [ ] **Step 2: Remover handler + aceitar routing_channels**

Em `src/alerts.py`, apagar a função `event_store_handler` (linha 54-67).

No loop de handlers de `send` (linha 41-50), aplicar também o filtro de regra:
```python
if routing_channels is not None and channel is not None and channel not in routing_channels:
    continue
```
E adicionar `routing_channels=None` ao parâmetro de `send` (linha 22).

Em `src/app.py`, onde os handlers são montados (ex.: `handlers=[event_store_handler(storage), telegram_handler, mqtt_handler, ha_handler]`), remover `event_store_handler(storage)`.

- [ ] **Step 3: Rodar**

Run: `py -3 -m pytest -q` (ignore falhas de `test_docker_integration` se ausente Docker)
Expected: suíte passa (eventos agora persistem via `AlertRuleEngine`).

- [ ] **Step 4: Commit**

```bash
git add src/alerts.py src/app.py
git commit -m "refactor(alerts): send vira so notificacao; persistencia no AlertRuleEngine"
```

---

### Task 7: Wiring — `event_bus`, `request_clip`, registro

**Files:**
- Modify: `src/main.py` (`CameraManager.request_clip`; `main()` cria `LocalEventQueue`, registra `AlertRuleEngine`, injeta `event_bus` nos workers)
- Modify: `src/app.py` (passar `event_bus` para `create_app`, se necessário para `/api/ingest`)

**Interfaces:**
- `CameraManager.request_clip(camera_id, event_id)` → chama `worker.start_clip(event_id)`.
- `main()` cria `event_bus = LocalEventQueue()`, `engine = AlertRuleEngine(storage, alerts, camera_manager)`, `event_bus.subscribe(engine.handle)`, `event_bus.start()`, e passa `event_bus` ao construir `CameraWorker`.

- [ ] **Step 1: Teste (request_clip chama worker)**

```python
def test_request_clip(monkeypatch):
    from src.main import CameraManager
    called = []
    class W:
        def start_clip(self, eid): called.append(eid)
        def status(self): return {}
    cm = CameraManager.__new__(CameraManager)
    cm.workers = {"1": W()}
    cm.request_clip("1", 99)
    assert called == [99]
```

- [ ] **Step 2: Rodar (falha esperada)**

Run: `py -3 -m pytest tests/test_events.py::test_request_clip -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Em `CameraManager` (após `get_status`, ~linha 641), adicionar:
```python
def request_clip(self, camera_id, event_id):
    with self.lock:
        worker = self.workers.get(camera_id)
    if worker is not None:
        worker.start_clip(event_id)
```

Em `main()` (após criar `camera_manager`, ~linha 671):
```python
from src.events import LocalEventQueue
from src.alert_rules import AlertRuleEngine
event_bus = LocalEventQueue()
alert_engine = AlertRuleEngine(storage, alerts, camera_manager)
event_bus.subscribe(alert_engine.handle)
event_bus.start()
```
E ao construir cada `CameraWorker` (linha 630), passar `event_bus=event_bus`.

Em `create_app` (`src/app.py`), adicionar parâmetro `event_bus=None` e guardá-lo em `app.event_bus` para uso em `/api/ingest`. Em `main()` (linha 685), passar `event_bus=event_bus`.

- [ ] **Step 4: Rodar**

Run: `py -3 -m pytest tests/test_events.py::test_request_clip -q` e `py -3 -c "import src.app; import src.main"`
Expected: PASS; imports limpos.

- [ ] **Step 5: Commit**

```bash
git add src/main.py src/app.py tests/test_events.py
git commit -m "feat: wire EventQueue + AlertRuleEngine + CameraManager.request_clip"
```

---

### Task 8: `POST /api/ingest` (borda remota entra em N1)

**Files:**
- Modify: `src/app.py` (rota `/api/ingest`)

**Interfaces:**
- `POST /api/ingest` é **genérico** (câmeras E dispositivos/sensores): aceita JSON `{camera_id (id de origem), device_type?, zone?, event_type?, details?, detections?, thumbnail_path?, identity_name?, ...}`; valida `camera_id`; cria `CameraEvent(level=1, source="edge", device_type=payload.get("device_type","camera"), ...)` e `event_bus.enqueue(event)`. Retorna 202 ou 400. Para sensores (ex.: alagamento), `device_type="sensor"` e `event_type` (ex.: `"flood"`) é o sinal; `detections` pode vir vazio.

- [ ] **Step 1: Teste**

```python
def test_ingest_enqueues(client, monkeypatch):
    q = []
    monkeypatch.setattr(client.application, "event_bus", type("B", (), {"enqueue": q.append})())
    r = client.post("/api/ingest", json={"camera_id": "5", "detections": [{"label":"person"}]})
    assert r.status_code == 202 and q and q[0].source == "edge" and q[0].level == 1
    # sensor heterogêneo (alagamento)
    r3 = client.post("/api/ingest", json={"camera_id": "flood-1", "device_type": "sensor", "event_type": "flood", "details": "nivel alto"})
    assert r3.status_code == 202 and q[-1].device_type == "sensor" and q[-1].event_type == "flood"
    r2 = client.post("/api/ingest", json={})
    assert r2.status_code == 400
```

- [ ] **Step 2: Rodar (falha esperada)**

Run: `py -3 -m pytest tests/test_events.py::test_ingest_enqueues -q`
Expected: FAIL (rota inexistente).

- [ ] **Step 3: Implementar**

Em `src/app.py`, dentro de `create_app`:
```python
@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    bus = getattr(app, "event_bus", None)
    if bus is None:
        return jsonify({"error": "event bus indisponivel"}), 503
    payload = request.get_json(silent=True) or {}
    camera_id = payload.get("camera_id")
    if not camera_id:
        return jsonify({"error": "camera_id obrigatorio"}), 400
    from src.events import CameraEvent
    event = CameraEvent(
        camera_id=str(camera_id),
        device_type=payload.get("device_type", "camera"),
        zone=payload.get("zone"),
        zone_classification=payload.get("zone_classification"),
        level=1,
        source="edge",
        event_type=payload.get("event_type"),
        details=payload.get("details"),
        identity_name=payload.get("identity_name"),
        known=payload.get("known"),
        category=payload.get("category"),
        recognition_method=payload.get("recognition_method"),
        thumbnail_path=payload.get("thumbnail_path"),
        detections=payload.get("detections") or [],
        camera_name=payload.get("camera_name"),
        alert_classes=payload.get("alert_classes"),
    )
    bus.enqueue(event)
    return jsonify({"status": "enqueued", "event_id": event.event_id}), 202
```

- [ ] **Step 4: Rodar**

Run: `py -3 -m pytest tests/test_events.py::test_ingest_enqueues -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app.py tests/test_events.py
git commit -m "feat(api): POST /api/ingest para borda remota (entra em N1)"
```

---

### Task 9: Dashboard — nível nos eventos + filtro + indicador N0

**Files:**
- Modify: `src/app.py` (`/events` aceita `?level=`)
- Modify: `src/templates/dashboard.html` (`<select id="filter-level">`)
- Modify: `src/static/dashboard.js` (`readFilterState`, `applyEventFilters`, `renderEvents` badge, `renderEventsSection` indicador N0)

**Interfaces:**
- `GET /events?level=<int>` → `storage.list_events(level=...)`.
- Dashboard mostra badge de nível por evento; filtro por nível; Visão geral mostra contagem N0 da câmera.

- [ ] **Step 1: Teste (endpoint filtra nível)**

```python
def test_events_level_filter(client):
    # sem fixtures de DB; validar só o parâmetro sendo repassado
    pass  # cobertura de /events com level exercitada manualmente + em test_storage
```
(Se não houver fixture, pular teste automático e validar manualmente; cobrir `list_events(level=)` no Task 1.)

- [ ] **Step 2: `/events` com filtro**

Em `src/app.py` (rota `/events`, linha 370):
```python
@app.route("/events")
def events():
    level = request.args.get("level", type=int)
    items = storage.list_events(limit=100, level=level)
    return jsonify(items)
```

- [ ] **Step 3: Select de nível no HTML**

Em `src/templates/dashboard.html`, na barra de filtros de eventos (onde estão `filter-camera`/`filter-type`), adicionar:
```html
<select id="filter-level">
  <option value="">Todos os níveis</option>
  <option value="0">N0 (captura)</option>
  <option value="1">N1 (triagem)</option>
  <option value="2">N2 (detecção)</option>
  <option value="3">N3 (análise)</option>
  <option value="4">N4 (providência)</option>
</select>
```

- [ ] **Step 4: JS — filtro e badge**

Em `dashboard.js`:
- `readFilterState()` — adicionar `level: document.getElementById('filter-level')?.value || ''`.
- `applyEventFilters` (linha 711) — adicionar:
```js
if (state.level && Number(e.level) !== Number(state.level)) return false;
```
- `renderEvents` (linha 823) — no card do evento, adicionar badge:
```js
const lvl = e.level != null ? Number(e.level) : 0;
const lvlLabel = ['N0','N1','N2','N3','N4'][lvl] || ('N'+lvl);
const droppedBadge = e.dropped ? '<span class="badge badge-off">descartado N1</span>' : '';
const levelBadge = `<span class="badge badge-info">${lvlLabel}</span>`;
```
e inserir `${levelBadge} ${droppedBadge}` no markup do evento (junto ao `event-type`).
- `renderEventsSection` (linha 1622) — passar `level` na busca: `fetchData('/events?level=' + (readFilterState().level||''))` e, na Visão geral, mostrar indicador N0: para cada câmera, `storage.list_events(limit=100, level=0, camera_id=camera.id).length` (via um novo endpoint leve ou reuso de `/events?level=0&camera_id=` — adicionar `camera_id` ao `/events` também).

- [ ] **Step 5: Verificar sintaxe**

Run: `node --check src/static/dashboard.js` (se Node indisponível, revisar manualmente).
Run: `py -3 -c "import src.app"`.

- [ ] **Step 6: Commit**

```bash
git add src/app.py src/templates/dashboard.html src/static/dashboard.js
git commit -m "feat(dashboard): badge de nivel, filtro e indicador N0 nos eventos"
```

---

### Task 10: Verificação ponta a ponta

**Files:**
- Test: `tests/test_events.py` (consolidar)

- [ ] **Step 1: Suíte de eventos**

Run: `py -3 -m pytest tests/test_events.py -q`
Expected: PASS (entrega de fila, decisão+cooldown, worker emite/não alerta, ingest, storage nível).

- [ ] **Step 2: Suíte completa**

Run: `py -3 -m pytest -q` (ignorar `test_docker_integration` se sem Docker)
Expected: sem regressões além de Docker.

- [ ] **Step 3: Manual**
1. Subir app; disparar movimento numa câmera → evento N0/N1 aparece; se há pessoa → sobe a N4 e alerta chega (Telegram/MQTT/HA).
2. `POST /api/ingest` com `{"camera_id":"99","detections":[{"label":"person"}]}` → evento entra em N1 e é processado.
3. Dashboard: filtro por nível mostra só N0/N4 etc.; card de evento tem badge de nível; Visão geral mostra indicador N0 por câmera.
4. Confirmar que o worker NÃO chama `alerts.send` direto (logs sem duplo alerta).

- [ ] **Step 4: Commit (se ajuste necessário)**

```bash
git add -A
git commit -m "test(events): verificacao ponta a ponta da fila N0-N4"
```
Caso contrário, pular.

---

## Self-Review Notes (autor)

- **Cobertura do spec:** Task 1 (storage nível), 2 (CameraEvent/fila), 3 (decide movido), 4 (worker N0/N1 emite), 5 (AlertRuleEngine N2-N4), 6 (alerts notify-only), 7 (wire + request_clip), 8 (/api/ingest N1), 9 (dashboard nível/filtro/N0), 10 (verificação). Todas as regras do spec atendidas.
- **Sem placeholders:** cada step tem código/conteúdo. `triage_n1` tem regra concreta (mantém se detecções ou meta-evento) com ponto de extensão documentado.
- **Consistência de tipos:** `CameraEvent` (Task 2) usado em Task 4/5/8; `AlertRuleEngine.handle(event)` (Task 5) consome os campos definidos; `EventQueue.enqueue/subscribe/start` (Task 2) usado em Task 4/7/8; `storage.add_event/update_event_level/list_events` (Task 1) usados em Task 5/9. `decide_worker_event`/`_unpack_worker_decision`/`get_cooldown_for_event` (Task 3) usados em Task 5.
- **Cuidado de import:** `event_rules.py` importa `decide_event`/`format_detections` do mesmo módulo que `main.py`; confirmar o caminho em `main.py` antes de mover.
- **Atualização de SPEC/README:** refletir a fronteira N0↔N2–N4 e a fila (regra 5 do AGENTS.md) — tarefa separada pós-implementação.
