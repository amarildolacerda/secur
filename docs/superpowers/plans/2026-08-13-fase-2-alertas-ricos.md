# Fase 2 — Alertas Ricos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enriquecer os alertas com snapshot no Telegram (2.1), clipe de vídeo por evento (2.2), mensagem com contexto completo (2.3) e revisão de clipes no dashboard (2.4).

**Architecture:** Payload de alerta extensível via kwargs opcionais (`thumbnail_path`, `clip_path`) sem alterar a assinatura de `AlertService.send()`; buffer circular de frames no `CameraWorker` grava MP4 (janela pré/pós evento) registrado na nova tabela `event_clips`; `telegram_handler` anexa snapshot via `sendPhoto` com fallback para texto; rotas `/clips/*` + modal no dashboard seguem o padrão de thumbnails.

**Tech Stack:** Python 3.10+, Flask, OpenCV (`cv2.VideoWriter`), SQLite (padrão `PRAGMA table_info` + `ALTER TABLE`), Telegram Bot API (`sendPhoto`/`sendMessage`).

## Global Constraints

- Branch `dev`; commits em inglês (`feat:`/`test:`/`docs:`); TDD (teste falha → implementa → passa → commit).
- Venv: `/tmp/secur-venv/bin/python -m pytest tests/<arquivo> -q`.
- `AlertService.send()` NÃO muda a assinatura posicional — só ganha kwargs opcionais.
- Schema: nunca recriar tabelas; usar `PRAGMA table_info` + `ALTER TABLE` para colunas novas.
- UI pt-BR, padrões de `dashboard.html`/`dashboard.js` (`.form-row`, `.button-*`, modal com `hidden-panel`).
- `EventStorage.__init__` apaga o DB sob pytest — testes usam `tmp_path`.
- `event_store_handler` grava eventos; `send()` retorna o id do evento gravado (novo, usado pelo worker para linkar clipe).
- Clipe é gravado APÓS o alerta (buffer pré + frames pós); `clip_path` vai para `events.clip_path` e `event_clips` — o payload do alerta NÃO carrega `clip_path` (ainda não existe no momento do send).

---

### Task 1: `AlertService.send()` com kwargs opcionais + retorno do event_id

**Files:**
- Modify: `secur/alerts.py` (`AlertService.send`, `event_store_handler`)
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: nada novo.
- Produces:
  - `AlertService.send(camera_id, zone, event_type, details=None, zone_classification=None, identity=None, known=None, recognition_method=None, category=None, routing=None, thumbnail_path=None, clip_path=None) -> Optional[int]` — inclui `thumbnail_path`/`clip_path` no payload; retorna o id do evento gravado pelo `event_store_handler` (ou `None`).
  - `event_store_handler(storage)` — o handler interno retorna `storage.add_event(...)` (id).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_alerts.py`:

```python
def test_alert_service_payload_includes_optional_paths(monkeypatch):
    called = []

    def handler(payload):
        called.append(payload)

    service = AlertService()
    service.register_handler(handler)
    service.send(
        "1", "entrada", "motion_detected", "teste",
        thumbnail_path="/tmp/thumb.jpg", clip_path="/tmp/clip.mp4",
    )

    assert called[0]["thumbnail_path"] == "/tmp/thumb.jpg"
    assert called[0]["clip_path"] == "/tmp/clip.mp4"


def test_alert_service_returns_event_id(monkeypatch):
    class FakeStorage:
        def add_event(self, camera_id, zone, event_type, details=None):
            return 42

    service = AlertService(storage=FakeStorage())
    event_id = service.send("1", "entrada", "motion_detected", "teste")
    assert event_id == 42


def test_alert_service_returns_none_without_store_handler():
    service = AlertService()
    service.register_handler(lambda payload: None)
    assert service.send("1", "entrada", "motion_detected") is None
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py::test_alert_service_payload_includes_optional_paths tests/test_alerts.py::test_alert_service_returns_event_id tests/test_alerts.py::test_alert_service_returns_none_without_store_handler -q`
Expected: FAIL — `KeyError: 'thumbnail_path'` e `event_id is None`.

- [ ] **Step 3: Implementar**

Em `secur/alerts.py`, substituir `AlertService.send` e `event_store_handler`:

```python
class AlertService:
    def __init__(self, storage=None):
        self.handlers = []
        if storage is not None:
            self.register_handler(event_store_handler(storage))

    def register_handler(self, handler):
        self.handlers.append(handler)

    def send(self, camera_id, zone, event_type, details=None, zone_classification=None,
             identity=None, known=None, recognition_method=None, category=None, routing=None,
             thumbnail_path=None, clip_path=None):
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
            "thumbnail_path": thumbnail_path,
            "clip_path": clip_path,
        }
        if routing is None:
            routing = getattr(self, "routing", None)
        event_id = None
        for handler in self.handlers:
            channel = getattr(handler, "channel", None)
            if channel is not None and routing is not None and not is_enabled(routing, channel, event_type):
                continue
            try:
                result = handler(payload)
                if result is not None and event_id is None:
                    event_id = result
            except Exception:
                logger.exception("Alert handler failed: %s", handler.__name__)
        return event_id


def event_store_handler(storage):
    """Handler que grava o evento na tabela interna (dashboard). Nunca filtrado por routing."""
    def handler(payload: Dict):
        try:
            return storage.add_event(
                payload.get("camera_id"),
                payload.get("zone"),
                payload.get("event_type"),
                payload.get("details"),
            )
        except Exception:
            logger.exception("Falha ao gravar evento na tabela interna")
            return None
    return handler
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py -q`
Expected: PASS (todos, incluindo os existentes).

- [ ] **Step 5: Commit**

```bash
git add secur/alerts.py tests/test_alerts.py
git commit -m "feat: optional thumbnail/clip paths in alert payload and event id return"
```

---

### Task 2: `_format_message` com contexto completo (2.3)

**Files:**
- Modify: `secur/alerts.py` (`_format_message`)
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: payload com `zone_classification`, `known`, `recognition_method`, `thumbnail_path`, `clip_path` (Task 1).
- Produces: `_format_message(payload) -> str` — mensagem Markdown com todos os campos presentes.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_alerts.py`:

```python
def test_format_message_full_context():
    from secur.alerts import _format_message
    payload = {
        "camera_id": "1",
        "zone": "Sala",
        "event_type": "intruder_detected",
        "details": "Pessoa detectada",
        "zone_classification": "privativa",
        "identity": "João",
        "known": True,
        "recognition_method": "face",
        "category": "person",
        "thumbnail_path": "/tmp/thumb.jpg",
        "clip_path": "/tmp/clip.mp4",
    }
    text = _format_message(payload)
    assert "privativa" in text
    assert "João" in text
    assert "face" in text
    assert "person" in text
    assert "thumb.jpg" in text
    assert "clip.mp4" in text


def test_format_message_minimal():
    from secur.alerts import _format_message
    text = _format_message({"camera_id": "1", "zone": "entrada", "event_type": "motion_detected"})
    assert "Sem detalhes adicionais" in text
    assert "privativa" not in text
    assert "Identidade" not in text
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py::test_format_message_full_context tests/test_alerts.py::test_format_message_minimal -q`
Expected: FAIL — `"privativa" not in text`.

- [ ] **Step 3: Implementar**

Em `secur/alerts.py`, substituir `_format_message`:

```python
def _format_message(payload: Dict) -> str:
    camera_id = payload.get("camera_id")
    zone = payload.get("zone")
    event_type = payload.get("event_type")
    details = payload.get("details") or "Sem detalhes adicionais."
    identity = payload.get("identity")
    message = (
        "*Alerta de Segurança*\n"
        f"*Câmera:* {_escape_markdown(camera_id)}\n"
        f"*Zona:* {_escape_markdown(zone)}\n"
        f"*Evento:* {_escape_markdown(event_type)}\n"
        f"*Descrição:* {_escape_markdown(details)}"
    )
    zone_classification = payload.get("zone_classification")
    if zone_classification:
        message += f"\n*Classificação:* {_escape_markdown(zone_classification)}"
    if identity:
        message += f"\n*Identidade:* {_escape_markdown(identity)}"
    known = payload.get("known")
    if known is not None:
        message += f"\n*Conhecido:* {_escape_markdown('sim' if known else 'não')}"
    recognition_method = payload.get("recognition_method")
    if recognition_method:
        message += f"\n*Método:* {_escape_markdown(recognition_method)}"
    category = payload.get("category")
    if category:
        message += f"\n*Categoria:* {_escape_markdown(category)}"
    thumbnail_path = payload.get("thumbnail_path")
    if thumbnail_path:
        message += f"\n*Snapshot:* {_escape_markdown(thumbnail_path)}"
    clip_path = payload.get("clip_path")
    if clip_path:
        message += f"\n*Clipe:* {_escape_markdown(clip_path)}"
    return message
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/alerts.py tests/test_alerts.py
git commit -m "feat: full context in alert message (zone, identity, method, snapshot, clip)"
```

---

### Task 3: Snapshot no Telegram via `sendPhoto` (2.1)

**Files:**
- Modify: `secur/alerts.py` (`telegram_handler`)
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: `payload["thumbnail_path"]` (Task 1).
- Produces: `telegram_handler(payload)` — envia `sendPhoto` com o arquivo quando `thumbnail_path` existe no disco; fallback `sendMessage` caso contrário ou se o upload falhar.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_alerts.py`:

```python
def test_telegram_handler_sends_photo(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"jpegdata")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    called = {}

    def fake_post(url, data=None, files=None, timeout=None):
        called["url"] = url
        called["data"] = data
        called["files"] = files
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({
        "camera_id": "1", "zone": "entrada", "event_type": "motion_detected",
        "details": "detalhe", "thumbnail_path": str(thumb),
    })

    assert called["url"].startswith("https://api.telegram.org/bottoken123/sendPhoto")
    assert called["data"]["chat_id"] == "chat123"
    assert "photo" in called["files"]
    assert called["timeout"] == 10


def test_telegram_handler_falls_back_to_text_when_thumbnail_missing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    called = {}

    def fake_post(url, data=None, files=None, timeout=None):
        called["url"] = url
        called["data"] = data
        called["files"] = files
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({
        "camera_id": "1", "zone": "entrada", "event_type": "motion_detected",
        "details": "detalhe", "thumbnail_path": "/tmp/nao-existe.jpg",
    })

    assert called["url"].startswith("https://api.telegram.org/bottoken123/sendMessage")
    assert called["files"] is None


def test_telegram_handler_photo_failure_falls_back_to_text(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"jpegdata")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    calls = []

    def fake_post(url, data=None, files=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError("upload failed")
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({
        "camera_id": "1", "zone": "entrada", "event_type": "motion_detected",
        "details": "detalhe", "thumbnail_path": str(thumb),
    })

    assert len(calls) == 2
    assert calls[1].startswith("https://api.telegram.org/bottoken123/sendMessage")
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py::test_telegram_handler_sends_photo tests/test_alerts.py::test_telegram_handler_falls_back_to_text_when_thumbnail_missing tests/test_alerts.py::test_telegram_handler_photo_failure_falls_back_to_text -q`
Expected: FAIL — `sendMessage` chamado mesmo com thumbnail presente.

- [ ] **Step 3: Implementar**

Em `secur/alerts.py`, substituir `telegram_handler`:

```python
def telegram_handler(payload: Dict):
    api_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not api_token or not chat_id:
        logger.debug("Telegram handler skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured")
        return

    text = _format_message(payload)
    thumbnail_path = payload.get("thumbnail_path")
    if thumbnail_path and os.path.exists(thumbnail_path):
        url = f"https://api.telegram.org/bot{api_token}/sendPhoto"
        data = {"chat_id": chat_id, "caption": text, "parse_mode": "Markdown"}
        try:
            with open(thumbnail_path, "rb") as f:
                response = requests.post(url, data=data, files={"photo": f}, timeout=10)
            response.raise_for_status()
            logger.info("Telegram photo sent for camera_id=%s event=%s", payload.get("camera_id"), payload.get("event_type"))
            return
        except Exception:
            logger.exception("Telegram photo failed, falling back to text for camera_id=%s", payload.get("camera_id"))

    url = f"https://api.telegram.org/bot{api_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        logger.info("Telegram alert sent for camera_id=%s event=%s", payload.get("camera_id"), payload.get("event_type"))
    except Exception:
        logger.exception("Telegram alert failed for camera_id=%s", payload.get("camera_id"))
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/alerts.py tests/test_alerts.py
git commit -m "feat: attach event snapshot to Telegram alert with text fallback"
```

---

### Task 4: Storage — tabela `event_clips` + coluna `events.clip_path`

**Files:**
- Modify: `secur/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: padrão `camera_thumbnails` (arquivo em disco + metadados + prune).
- Produces:
  - Tabela `event_clips(id, camera_id, event_id, timestamp, path, duration_s)`.
  - `add_event_clip(camera_id, event_id, path, duration_s) -> int`
  - `list_event_clips(camera_id, limit=20) -> List[dict]`
  - `get_event_clip(clip_id) -> Optional[dict]`
  - `prune_event_clips(camera_id, keep=20)` — apaga arquivos + registros excedentes.
  - `remove_event_clips(camera_id)` — apaga todos os arquivos + registros da câmera.
  - `update_event_clip_path(event_id, clip_path) -> bool` — coluna `events.clip_path`.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_event_clips_crud_and_prune(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    files = []
    for i in range(3):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"mp4data")
        files.append(str(p))
        storage.add_event_clip(cam_id, None, str(p), 10.0)

    clips = storage.list_event_clips(cam_id)
    assert len(clips) == 3
    assert clips[0]["path"] == files[2]
    assert clips[0]["duration_s"] == 10.0

    storage.prune_event_clips(cam_id, keep=2)
    clips = storage.list_event_clips(cam_id)
    assert len(clips) == 2
    assert not Path(files[0]).exists()

    storage.remove_event_clips(cam_id)
    assert storage.list_event_clips(cam_id) == []
    assert not Path(files[1]).exists()
    storage.close()


def test_event_clip_get_and_404(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"mp4data")
    clip_id = storage.add_event_clip(cam_id, None, str(p), 5.0)

    clip = storage.get_event_clip(clip_id)
    assert clip["camera_id"] == cam_id
    assert clip["duration_s"] == 5.0
    assert storage.get_event_clip(9999) is None
    storage.close()


def test_update_event_clip_path(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    event_id = storage.add_event("1", "entrada", "motion_detected", "teste")

    assert storage.update_event_clip_path(event_id, "/tmp/clip.mp4") is True
    events = storage.list_events(limit=10)
    assert events[0]["clip_path"] == "/tmp/clip.mp4"

    assert storage.update_event_clip_path(9999, "/tmp/x.mp4") is False
    storage.close()
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: FAIL — `AttributeError: 'EventStorage' object has no attribute 'add_event_clip'`.

- [ ] **Step 3: Implementar**

Em `secur/storage.py`:

1. Na `_create_tables`, após o bloco de `camera_thumbnails`, adicionar:

```python
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS event_clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    event_id INTEGER,
                    timestamp TEXT NOT NULL,
                    path TEXT NOT NULL,
                    duration_s REAL
                )
                """
            )
```

2. Após o bloco de migração de `zones.schedule`, adicionar migração de `events.clip_path`:

```python
            # Ensure clip_path column exists for older DBs
            try:
                cursor.execute("PRAGMA table_info(events)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'clip_path' not in cols:
                    cursor.execute("ALTER TABLE events ADD COLUMN clip_path TEXT")
            except Exception:
                pass
```

3. Após `get_camera_thumbnail`, adicionar os métodos:

```python
    def add_event_clip(self, camera_id: int, event_id, path: str, duration_s: float) -> int:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO event_clips (camera_id, event_id, timestamp, path, duration_s) VALUES (?, ?, ?, ?, ?)",
                (camera_id, event_id, timestamp, path, duration_s),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_event_clips(self, camera_id: int, limit: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, camera_id, event_id, timestamp, path, duration_s FROM event_clips "
                "WHERE camera_id = ? ORDER BY id DESC LIMIT ?",
                (camera_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_event_clip(self, clip_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, camera_id, event_id, timestamp, path, duration_s FROM event_clips WHERE id = ?",
                (clip_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def prune_event_clips(self, camera_id: int, keep: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
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

    def remove_event_clips(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT path FROM event_clips WHERE camera_id = ?", (camera_id,))
            rows = cursor.fetchall()
            for row in rows:
                try:
                    Path(row["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover clipe %s", row["path"])
            cursor.execute("DELETE FROM event_clips WHERE camera_id = ?", (camera_id,))
            self.connection.commit()

    def update_event_clip_path(self, event_id: int, clip_path: str) -> bool:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE events SET clip_path = ? WHERE id = ?",
                (clip_path, event_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py tests/test_storage.py
git commit -m "feat: event clips storage with prune and event clip_path link"
```

---

### Task 5: Config + worker — buffer circular e gravação de clipe (2.2)

**Files:**
- Modify: `secur/config.py`, `secur/main.py` (`CameraWorker.run`)
- Test: `tests/test_main_filters.py` (função pura de buffer)

**Interfaces:**
- Consumes: `add_event_clip`, `prune_event_clips`, `update_event_clip_path` (Task 4); `send()` retorna event_id (Task 1).
- Produces:
  - `config.py`: `CLIP_PRE_SECONDS` (10), `CLIP_POST_SECONDS` (10), `CLIP_FPS` (5), `CLIPS_DIR`.
  - `main.py`: `CircularFrameBuffer` (classe pura testável) com `push(frame)`, `frames()`, `maxlen`.
  - `CameraWorker.run()`: mantém buffer; ao enviar alerta, inicia gravação (buffer pré + frames pós por `CLIP_POST_SECONDS`); finaliza com `cv2.VideoWriter` → `add_event_clip` + `update_event_clip_path` + `prune_event_clips`.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_main_filters.py`:

```python
def test_circular_frame_buffer_keeps_newest():
    from secur.main import CircularFrameBuffer
    buf = CircularFrameBuffer(maxlen=3)
    for i in range(5):
        buf.push(i)
    assert buf.frames() == [2, 3, 4]


def test_circular_frame_buffer_empty():
    from secur.main import CircularFrameBuffer
    buf = CircularFrameBuffer(maxlen=3)
    assert buf.frames() == []
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py::test_circular_frame_buffer_keeps_newest tests/test_main_filters.py::test_circular_frame_buffer_empty -q`
Expected: FAIL — `ImportError: cannot import name 'CircularFrameBuffer'`.

- [ ] **Step 3: Implementar**

1. Em `secur/config.py`, após `THUMBNAIL_HISTORY_SIZE`:

```python
CLIP_PRE_SECONDS = float(os.getenv("CLIP_PRE_SECONDS", "10"))
CLIP_POST_SECONDS = float(os.getenv("CLIP_POST_SECONDS", "10"))
CLIP_FPS = int(os.getenv("CLIP_FPS", "5"))
CLIPS_DIR = DATA_DIR / "clips"
CLIPS_DIR.mkdir(exist_ok=True)
CLIP_HISTORY_SIZE = int(os.getenv("CLIP_HISTORY_SIZE", "20"))
```

2. Em `secur/main.py`, adicionar ao import de config:

```python
    CLIP_PRE_SECONDS,
    CLIP_POST_SECONDS,
    CLIP_FPS,
    CLIPS_DIR,
    CLIP_HISTORY_SIZE,
```

3. Em `secur/main.py`, adicionar a classe (após `get_cooldown_for_event`, antes de `should_capture_thumbnail`):

```python
class CircularFrameBuffer:
    """Buffer circular de frames (janela pré-evento). Descarta o mais antigo."""

    def __init__(self, maxlen: int):
        self.maxlen = maxlen
        self._items = []

    def push(self, frame):
        self._items.append(frame)
        if len(self._items) > self.maxlen:
            self._items.pop(0)

    def frames(self):
        return list(self._items)
```

4. Em `CameraWorker.run()`, substituir o início do loop:

```python
    def run(self):
        camera_stream = CameraStream(self.camera["source"])
        motion_detector = MotionDetector(min_area=MOTION_MIN_AREA)
        last_motion_time = None
        no_motion_alerted = False
        last_alert_time = {}
        last_thumb_time = None
        frame_buffer = CircularFrameBuffer(maxlen=max(1, int(CLIP_PRE_SECONDS * CLIP_FPS)))
        clip_writer = None
        clip_end_time = 0.0
        clip_event_id = None
        clip_path = None

        while not self.stop_event.is_set():
            frame = camera_stream.read()
            if frame is None:
                time.sleep(1)
                continue

            frame_buffer.push(frame)

            # Finalize clip recording after the post-event window
            if clip_writer is not None:
                if time.time() < clip_end_time:
                    clip_writer.write(frame)
                else:
                    clip_writer.release()
                    clip_writer = None
                    if clip_event_id is not None:
                        try:
                            self.storage.update_event_clip_path(clip_event_id, clip_path)
                        except Exception:
                            logger.warning("Falha ao linkar clipe ao evento (câmera %s)", self.camera.get("name"))
                    try:
                        self.storage.prune_event_clips(self.camera["id"], keep=CLIP_HISTORY_SIZE)
                    except Exception:
                        logger.warning("Falha ao podar clipes (câmera %s)", self.camera.get("name"))
```

5. No bloco de alerta (dentro do `elif now - last_alert_time...`), substituir o `self.alerts.send(...)` por:

```python
                            event_id = self.alerts.send(
                                self.camera["id"], zone_name, event_type, details, zone_classification,
                                identity=identity_name, known=known, category=category,
                                recognition_method=identity_info.get("method") if identity_info else None,
                                thumbnail_path=thumb_path,
                            )
                            # Start clip recording: pre-event buffer + post-event frames
                            try:
                                cam_dir = CLIPS_DIR / f"cam{self.camera['id']}"
                                cam_dir.mkdir(parents=True, exist_ok=True)
                                clip_path = cam_dir / f"{int(now * 1000)}.mp4"
                                writer = cv2.VideoWriter(
                                    str(clip_path),
                                    cv2.VideoWriter_fourcc(*"mp4v"),
                                    CLIP_FPS,
                                    (frame.shape[1], frame.shape[0]),
                                )
                                for buf_frame in frame_buffer.frames():
                                    writer.write(buf_frame)
                                clip_writer = writer
                                clip_end_time = now + CLIP_POST_SECONDS
                                clip_event_id = event_id
                                self.storage.add_event_clip(self.camera["id"], event_id, str(clip_path), CLIP_PRE_SECONDS + CLIP_POST_SECONDS)
                            except Exception:
                                logger.warning("Falha ao iniciar gravação de clipe (câmera %s)", self.camera.get("name"))
```

6. Antes do bloco de alerta, capturar o thumbnail do frame atual (para o snapshot no Telegram). No início do `else:` do filtro de classes (antes de `now = time.time()`), adicionar:

```python
                        thumb_path = None
                        if should_capture_thumbnail(last_thumb_time, time.time(), THUMBNAIL_INTERVAL_SECONDS):
                            try:
                                cam_dir = THUMBNAILS_DIR / f"cam{self.camera['id']}"
                                cam_dir.mkdir(parents=True, exist_ok=True)
                                filename = f"{int(time.time() * 1000)}.jpg"
                                path = cam_dir / filename
                                ok, jpg = cv2.imencode(".jpg", frame)
                                if ok:
                                    path.write_bytes(jpg.tobytes())
                                    self.storage.add_camera_thumbnail(self.camera["id"], str(path), event_type)
                                    self.storage.prune_camera_thumbnails(self.camera["id"], keep=THUMBNAIL_HISTORY_SIZE)
                                    last_thumb_time = time.time()
                                    thumb_path = str(path)
                            except Exception:
                                logger.warning("Falha ao capturar thumbnail (câmera %s)", self.camera.get("name"))
```

Nota: o bloco de thumbnail existente (após o try/except) permanece — como `last_thumb_time` foi atualizado, `should_capture_thumbnail` retorna False e não duplica.

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_filters.py tests/test_main_identity.py tests/test_motion.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/config.py secur/main.py tests/test_main_filters.py
git commit -m "feat: circular frame buffer and event clip recording in worker"
```

---

### Task 6: API — rotas `/clips/*` e `/camera/<id>/clips` (2.4)

**Files:**
- Modify: `secur/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `list_event_clips`, `get_event_clip` (Task 4).
- Produces:
  - `GET /camera/<id>/clips` → lista de clipes com `url` (`/clips/<id>/video`).
  - `GET /clips/<id>` → metadados do clipe (404 se inexistente).
  - `GET /clips/<id>/video` → `send_file` MP4 (404 se arquivo não existe).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_app.py`:

```python
def test_camera_clips_route(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    resp = client.post("/cameras", json={"name": "Cam", "source": "source://x", "zone": "entrada"})
    cam_id = resp.json["id"]

    resp = client.get(f"/camera/{cam_id}/clips")
    assert resp.status_code == 200
    assert resp.json == []


def test_camera_clips_route_404(client):
    resp = client.get("/camera/999/clips")
    assert resp.status_code == 404


def test_clip_metadata_route_404(client):
    resp = client.get("/clips/999")
    assert resp.status_code == 404


def test_clip_video_route_404(client):
    resp = client.get("/clips/999/video")
    assert resp.status_code == 404
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: FAIL — `404 Not Found` (rotas não existem).

- [ ] **Step 3: Implementar**

Em `secur/app.py`, após a rota `thumbnail_image` (linha ~165), adicionar:

```python
    @app.route("/camera/<int:camera_id>/clips")
    def camera_clips(camera_id):
        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404
        items = storage.list_event_clips(camera_id, limit=20)
        out = []
        for it in items:
            out.append({
                "id": it["id"],
                "timestamp": it["timestamp"],
                "duration_s": it["duration_s"],
                "url": f"/clips/{it['id']}/video",
            })
        return jsonify(out)

    @app.route("/clips/<int:clip_id>")
    def clip_metadata(clip_id):
        item = storage.get_event_clip(clip_id)
        if not item:
            return jsonify({"error": "Clipe não encontrado"}), 404
        return jsonify(item)

    @app.route("/clips/<int:clip_id>/video")
    def clip_video(clip_id):
        item = storage.get_event_clip(clip_id)
        if not item:
            return jsonify({"error": "Clipe não encontrado"}), 404
        path = item["path"]
        if not os.path.exists(path):
            return jsonify({"error": "Clipe não encontrado"}), 404
        return send_file(path, mimetype="video/mp4")
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add secur/app.py tests/test_app.py
git commit -m "feat: clip metadata and video streaming routes"
```

---

### Task 7: Dashboard — modal de revisão de clipes (2.4)

**Files:**
- Modify: `secur/templates/dashboard.html`, `secur/static/dashboard.js`

**Interfaces:**
- Consumes: `GET /camera/<id>/clips` e `GET /clips/<id>/video` (Task 6).
- Produces: botão "Clipes" no card da câmera + modal com `<video controls>` (padrão do histórico de thumbnails).

- [ ] **Step 1: Implementar o HTML**

Em `secur/templates/dashboard.html`, localizar o overlay de thumbnails (`thumb-history-overlay`) e adicionar após ele um overlay de clipes:

```html
            <div id="clip-history-overlay" class="dialog-overlay hidden-panel" role="dialog" aria-modal="true" aria-labelledby="clip-history-title">
                <div class="dialog-card">
                    <div class="dialog-header">
                        <h3 id="clip-history-title">Clipes</h3>
                        <button id="clip-history-close" type="button" class="button-close" aria-label="Fechar">×</button>
                    </div>
                    <div id="clip-history-grid" style="display:flex;flex-direction:column;gap:12px;max-height:60vh;overflow-y:auto;"></div>
                    <div id="clip-history-empty" style="display:none;color:var(--muted-subtle);padding:12px 0;">Nenhum clipe gravado.</div>
                </div>
            </div>
```

- [ ] **Step 2: Implementar o JS**

Em `secur/static/dashboard.js`, após `closeThumbHistory`, adicionar:

```javascript
/* ========== Clip History ========== */

function openClipHistory(cameraId, cameraName) {
  const overlay = document.getElementById('clip-history-overlay');
  const title = document.getElementById('clip-history-title');
  const grid = document.getElementById('clip-history-grid');
  const empty = document.getElementById('clip-history-empty');

  title.textContent = `Clipes — ${cameraName}`;
  grid.innerHTML = '';
  empty.style.display = 'none';
  overlay.classList.remove('hidden-panel');

  fetch(`/camera/${cameraId}/clips`)
    .then(r => r.json())
    .then(items => {
      if (!items || items.length === 0) {
        empty.style.display = '';
        return;
      }
      grid.innerHTML = items.map(item => `
        <div class="clip-history-item">
          <video src="${item.url}" controls preload="metadata" style="width:100%;border-radius:var(--radius-sm);"></video>
          <span style="font-size:0.8rem;color:var(--muted-subtle);">
            ${new Date(item.timestamp).toLocaleString()} — ${item.duration_s ? item.duration_s.toFixed(0) + 's' : ''}
          </span>
        </div>
      `).join('');
    })
    .catch(() => {
      empty.textContent = 'Falha ao carregar clipes.';
      empty.style.display = '';
    });
}

function closeClipHistory() {
  const overlay = document.getElementById('clip-history-overlay');
  if (overlay) overlay.classList.add('hidden-panel');
}
```

Em `createCameraRow`, adicionar botão "Clipes" na coluna de ações:

```javascript
        <button class="button-secondary button-mini clips-camera" data-camera-id="${camera.id}">Clipes</button>
```

No bloco de event delegation (onde `edit-camera`/`delete-camera` são tratados), adicionar:

```javascript
    if (target.classList.contains('clips-camera')) {
      const cameraId = target.dataset.cameraId;
      const camera = cameras.find(c => String(c.id) === String(cameraId));
      openClipHistory(cameraId, camera ? camera.name : 'Câmera');
      return;
    }
```

No bloco de inicialização (onde `thumb-history-close` é ligado), adicionar:

```javascript
  document.getElementById('clip-history-close').addEventListener('click', closeClipHistory);
```

- [ ] **Step 3: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py tests/test_zones.py -q`
Expected: PASS (API continua funcionando; UI não tem testes automatizados).

- [ ] **Step 4: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js
git commit -m "feat: clip review modal in dashboard"
```

---

### Task 8: `/docs` + suíte completa

**Files:**
- Modify: `secur/app.py` (rota `/docs`)

**Interfaces:**
- Consumes: tudo das Tasks 1-7.
- Produces: suíte verde e docs atualizada.

- [ ] **Step 1: Atualizar `/docs`**

Em `secur/app.py`, na lista `api_docs`, adicionar após a entrada de `/thumbnails/<id>/image`:

```python
            {"path": "/camera/<id>/clips", "method": "GET", "description": "Lista os últimos clipes de vídeo da câmera"},
            {"path": "/clips/<id>", "method": "GET", "description": "Metadados de um clipe"},
            {"path": "/clips/<id>/video", "method": "GET", "description": "Stream MP4 de um clipe"},
```

- [ ] **Step 2: Rodar a suíte completa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: PASS (todos os testes, incluindo os novos).

- [ ] **Step 3: Commit**

```bash
git add secur/app.py
git commit -m "docs: document clip endpoints"
```

---

## Self-Review

**1. Spec coverage (Fase 2):**
- 2.1 Snapshot no Telegram → Task 1 (payload `thumbnail_path`), Task 3 (`sendPhoto` + fallback). ✅
- 2.2 Clipe de vídeo por evento → Task 4 (`event_clips` + `events.clip_path`), Task 5 (buffer + gravação). ✅
- 2.3 Contexto completo → Task 2 (`_format_message`). ✅
- 2.4 Revisão de clipes → Task 6 (rotas), Task 7 (modal). ✅

**2. Placeholder scan:** Nenhum TBD/TODO; todo passo tem código completo e comandos exatos.

**3. Type consistency:**
- `send()` retorna `event_id` (Task 1) — Task 5 usa para `add_event_clip`/`update_event_clip_path`. ✅
- `thumbnail_path` no payload (Task 1) — Task 3 usa no `telegram_handler`; Task 5 passa `thumb_path`. ✅
- `add_event_clip(camera_id, event_id, path, duration_s)` (Task 4) — Task 5 chama com `(self.camera["id"], event_id, str(clip_path), CLIP_PRE_SECONDS + CLIP_POST_SECONDS)`. ✅
- `CircularFrameBuffer(maxlen)` com `push`/`frames` (Task 5) — testes e worker usam as mesmas assinaturas. ✅
- `list_event_clips(camera_id, limit=20)` (Task 4) — Task 6 usa com `limit=20`. ✅
- `get_event_clip(clip_id)` (Task 4) — Task 6 usa nas rotas. ✅
- `CLIP_PRE_SECONDS`/`CLIP_POST_SECONDS`/`CLIP_FPS`/`CLIPS_DIR`/`CLIP_HISTORY_SIZE` (Task 5) — definidos em config, usados no worker. ✅