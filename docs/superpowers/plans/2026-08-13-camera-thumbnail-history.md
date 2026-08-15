# Histórico de Thumbnails + Configuração de Notificações — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guardar os últimos 20 thumbnails por câmera (capturados em movimento, máx. 1 a cada 10s), acessíveis ao clicar no card da câmera, e criar painel de configuração de notificações por evento × canal (Telegram/automação), com `no_motion` desativado no Telegram por default.

**Architecture:** Thumbnails salvos como JPEG em `data/thumbnails/cam<id>/` com metadados na tabela SQLite `camera_thumbnails`; captura no `CameraWorker.run()` com throttle de 10s; rotas Flask para listar/servir; modal de histórico no dashboard. Notificações: tabela `notification_routing` (channel, event_type, enabled), módulo `notifications.py` com registro canônico de canais/eventos/defaults, `AlertService.send()` consulta o routing antes de despachar; seção "Notificações" na dashboard com toggles.

**Tech Stack:** Python 3.11+, Flask, SQLite, OpenCV (cv2), pytest, JavaScript vanilla, CSS (style guide do projeto).

## Global Constraints

- Testes rodam com: `/tmp/secur-venv/bin/python -m pytest tests/<arquivo> -q` (venv já criado; se ausente: `python3 -m venv /tmp/secur-venv && /tmp/secur-venv/bin/pip install -r requirements.txt`).
- Branch de trabalho: `dev` (nunca `main`). Commits locais no `dev`; sem push automático.
- UI deve seguir o style guide em `.opencode/skills/style/SKILL.md` (variáveis CSS `--primary`, `--surface`, `--border`, `--radius`, etc.; tema claro).
- Textos da UI em pt-BR.
- `object_detected` é legado (não é mais produzido) — oculto no painel, mas presente no registro com `legacy: true`.
- Defaults de routing: Telegram envia `motion_detected`, `intruder_detected`, `object_detected`; NÃO envia `no_motion`, `snapshot_info`, `identity_recognized`, `unknown_detected`. Automação envia todos exceto `snapshot_info`.
- `no_motion` continua indo para automação (MQTT/HA) — apenas Telegram é desativado por default.
- Handlers internos mantêm lógica própria (ex: HA ignora zona pública) — a config é camada adicional no `AlertService.send()`.

---

### Task 1: Storage — tabelas e métodos de thumbnails e routing

**Files:**
- Modify: `secur/storage.py` (adicionar tabelas em `_create_tables` e métodos novos)
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces:
  - `EventStorage.add_camera_thumbnail(camera_id: int, path: str, event_type: str) -> int`
  - `EventStorage.list_camera_thumbnails(camera_id: int, limit: int = 20) -> list[dict]` (dicts com `id`, `timestamp`, `event_type`, `path`; mais recentes primeiro)
  - `EventStorage.prune_camera_thumbnails(camera_id: int, keep: int = 20) -> None` (apaga do DB e do disco os excedentes)
  - `EventStorage.remove_camera_thumbnails(camera_id: int) -> None` (apaga todos arquivos + registros)
  - `EventStorage.get_camera_thumbnail(thumb_id: int) -> dict | None` (dict com `id`, `camera_id`, `timestamp`, `event_type`, `path`)
  - `EventStorage.get_routing(channel: str) -> dict[str, bool]`
  - `EventStorage.set_routing(channel: str, event_type: str, enabled: bool) -> None`
  - `EventStorage.get_all_routing() -> dict[str, dict[str, bool]]`
  - `EventStorage.seed_default_routing(defaults: dict[str, dict[str, bool]]) -> None` (grava apenas se tabela vazia)

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_storage.py`:

```python
def test_camera_thumbnails_crud_and_prune(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    # create fake thumbnail files on disk
    files = []
    for i in range(3):
        p = tmp_path / f"thumb_{i}.jpg"
        p.write_bytes(b"jpegdata")
        files.append(str(p))
        storage.add_camera_thumbnail(cam_id, str(p), "motion_detected")

    thumbs = storage.list_camera_thumbnails(cam_id)
    assert len(thumbs) == 3
    # most recent first
    assert thumbs[0]["path"] == files[2]
    assert thumbs[0]["event_type"] == "motion_detected"

    # prune keeps only the newest 2
    storage.prune_camera_thumbnails(cam_id, keep=2)
    thumbs = storage.list_camera_thumbnails(cam_id)
    assert len(thumbs) == 2
    assert thumbs[0]["path"] == files[2]
    assert not Path(files[0]).exists()  # oldest file deleted from disk

    # remove all
    storage.remove_camera_thumbnails(cam_id)
    assert storage.list_camera_thumbnails(cam_id) == []
    assert not Path(files[1]).exists()
    assert not Path(files[2]).exists()
    storage.close()


def test_notification_routing_seed_and_update(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    defaults = {
        "telegram": {"motion_detected": True, "no_motion": False},
        "automation": {"motion_detected": True, "no_motion": True},
    }
    storage.seed_default_routing(defaults)
    assert storage.get_routing("telegram") == {"motion_detected": True, "no_motion": False}

    # seeding again does not overwrite
    storage.seed_default_routing({"telegram": {"motion_detected": False}})
    assert storage.get_routing("telegram")["motion_detected"] is True

    storage.set_routing("telegram", "no_motion", True)
    assert storage.get_routing("telegram")["no_motion"] is True

    all_routing = storage.get_all_routing()
    assert all_routing["automation"]["no_motion"] is True
    storage.close()
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: FAIL — `AttributeError: 'EventStorage' object has no attribute 'add_camera_thumbnail'`

- [ ] **Step 3: Implementar**

Em `secur/storage.py`:

1. Adicionar import de `shutil` no topo (junto aos outros imports):
```python
import shutil
```

2. Em `_create_tables`, após o bloco do `known_identities` (antes de `self.connection.commit()`), adicionar:

```python
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_thumbnails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT,
                    path TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_routing (
                    channel TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (channel, event_type)
                )
                """
            )
```

3. Adicionar os métodos novos ao final da classe (antes de `close`):

```python
    def add_camera_thumbnail(self, camera_id: int, path: str, event_type: str) -> int:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO camera_thumbnails (camera_id, timestamp, event_type, path) VALUES (?, ?, ?, ?)",
                (camera_id, timestamp, event_type, path),
            )
            self.connection.commit()
            return cursor.lastrowid

    def list_camera_thumbnails(self, camera_id: int, limit: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, timestamp, camera_id, event_type, path FROM camera_thumbnails "
                "WHERE camera_id = ? ORDER BY id DESC LIMIT ?",
                (camera_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def prune_camera_thumbnails(self, camera_id: int, keep: int = 20):
        with self.lock:
            cursor = self.connection.cursor()
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

    def remove_camera_thumbnails(self, camera_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT path FROM camera_thumbnails WHERE camera_id = ?", (camera_id,))
            rows = cursor.fetchall()
            for row in rows:
                try:
                    Path(row["path"]).unlink(missing_ok=True)
                except Exception:
                    logger.warning("Falha ao remover thumbnail %s", row["path"])
            cursor.execute("DELETE FROM camera_thumbnails WHERE camera_id = ?", (camera_id,))
            self.connection.commit()

    def get_camera_thumbnail(self, thumb_id: int):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, camera_id, timestamp, event_type, path FROM camera_thumbnails WHERE id = ?",
                (thumb_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_routing(self, channel: str) -> dict:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT event_type, enabled FROM notification_routing WHERE channel = ?",
                (channel,),
            )
            return {row["event_type"]: bool(row["enabled"]) for row in cursor.fetchall()}

    def set_routing(self, channel: str, event_type: str, enabled: bool):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO notification_routing (channel, event_type, enabled) VALUES (?, ?, ?) "
                "ON CONFLICT(channel, event_type) DO UPDATE SET enabled = excluded.enabled",
                (channel, event_type, int(enabled)),
            )
            self.connection.commit()

    def get_all_routing(self) -> dict:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT channel, event_type, enabled FROM notification_routing")
            routing = {}
            for row in cursor.fetchall():
                routing.setdefault(row["channel"], {})[row["event_type"]] = bool(row["enabled"])
            return routing

    def seed_default_routing(self, defaults: dict):
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) AS c FROM notification_routing")
            if cursor.fetchone()["c"] > 0:
                return
            for channel, events in defaults.items():
                for event_type, enabled in events.items():
                    cursor.execute(
                        "INSERT INTO notification_routing (channel, event_type, enabled) VALUES (?, ?, ?)",
                        (channel, event_type, int(enabled)),
                    )
            self.connection.commit()
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_storage.py -q`
Expected: PASS (todos os testes do arquivo, incluindo os 2 novos)

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py secur/storage.py
git commit -m "feat(storage): tabelas e métodos de thumbnails por câmera e routing de notificações"
```

---

### Task 2: Registro canônico de canais/eventos + dispatch com routing

**Files:**
- Create: `secur/notifications.py`
- Modify: `secur/alerts.py` (AlertService.send consulta routing; remover skips hardcode dos handlers)
- Modify: `secur/main.py` (seed_default_routing no boot)
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: `EventStorage.get_routing(channel)`, `EventStorage.seed_default_routing(defaults)` (Task 1)
- Produces:
  - `notifications.CHANNELS: list[dict]` — `[{"key": "telegram", "label": "Telegram"}, {"key": "automation", "label": "Automação"}]`
  - `notifications.EVENT_TYPES: list[dict]` — cada um com `key`, `label`, `category` ("alerta"/"info"), `legacy` (bool)
  - `notifications.DEFAULT_ROUTING: dict[str, dict[str, bool]]`
  - `notifications.is_enabled(routing: dict, channel: str, event_type: str) -> bool` — default True se canal/evento ausente
  - `AlertService.send(...)` — agora aceita `routing: dict = None` e pula handlers cujo canal está desabilitado

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_alerts.py`:

```python
from secur.notifications import CHANNELS, EVENT_TYPES, DEFAULT_ROUTING, is_enabled


def test_notifications_registry():
    assert [c["key"] for c in CHANNELS] == ["telegram", "automation"]
    keys = [e["key"] for e in EVENT_TYPES]
    assert "motion_detected" in keys
    assert "no_motion" in keys
    assert "object_detected" in keys
    legacy = [e for e in EVENT_TYPES if e.get("legacy")]
    assert [e["key"] for e in legacy] == ["object_detected"]


def test_default_routing_no_motion_off_telegram():
    assert DEFAULT_ROUTING["telegram"]["no_motion"] is False
    assert DEFAULT_ROUTING["telegram"]["motion_detected"] is True
    assert DEFAULT_ROUTING["automation"]["no_motion"] is True
    assert DEFAULT_ROUTING["automation"]["snapshot_info"] is False


def test_is_enabled_defaults_true():
    assert is_enabled({}, "telegram", "motion_detected") is True
    assert is_enabled({"telegram": {"motion_detected": False}}, "telegram", "motion_detected") is False
    assert is_enabled({"telegram": {"motion_detected": False}}, "telegram", "no_motion") is True


def test_alert_service_respects_routing(monkeypatch):
    called = []

    def handler(payload):
        called.append(payload)
    handler.channel = "telegram"

    service = AlertService()
    service.register_handler(handler)
    routing = {"telegram": {"motion_detected": False}}
    service.send("1", "entrada", "motion_detected", "teste", routing=routing)
    assert called == []

    service.send("1", "entrada", "no_motion", "teste", routing=routing)
    assert len(called) == 1
    assert called[0]["event_type"] == "no_motion"


def test_alert_service_skips_no_motion_for_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    def fake_post(*args, **kwargs):
        raise AssertionError("requests.post should not be called for no_motion")

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)

    service = AlertService()
    service.register_handler(telegram_handler)
    service.routing = {"telegram": {"no_motion": False}}
    service.send("1", "entrada", "no_motion", "teste")
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'secur.notifications'`

- [ ] **Step 3: Implementar**

3a. Criar `secur/notifications.py`:

```python
"""Registro canônico de canais de notificação e tipos de evento."""

CHANNELS = [
    {"key": "telegram", "label": "Telegram"},
    {"key": "automation", "label": "Automação"},
]

EVENT_TYPES = [
    {"key": "motion_detected", "label": "Movimento detectado", "category": "alerta", "legacy": False},
    {"key": "no_motion", "label": "Sem movimento", "category": "info", "legacy": False},
    {"key": "snapshot_info", "label": "Objetos detectados (info)", "category": "info", "legacy": False},
    {"key": "identity_recognized", "label": "Identidade reconhecida", "category": "info", "legacy": False},
    {"key": "intruder_detected", "label": "Intruso em zona restrita", "category": "alerta", "legacy": False},
    {"key": "unknown_detected", "label": "Não reconhecido", "category": "alerta", "legacy": False},
    {"key": "object_detected", "label": "Objeto detectado (legado)", "category": "alerta", "legacy": True},
]

DEFAULT_ROUTING = {
    "telegram": {
        "motion_detected": True,
        "no_motion": False,
        "snapshot_info": False,
        "identity_recognized": False,
        "intruder_detected": True,
        "unknown_detected": False,
        "object_detected": True,
    },
    "automation": {
        "motion_detected": True,
        "no_motion": True,
        "snapshot_info": False,
        "identity_recognized": True,
        "intruder_detected": True,
        "unknown_detected": True,
        "object_detected": True,
    },
}


def is_enabled(routing: dict, channel: str, event_type: str) -> bool:
    """True se o canal não tem config para o evento (default permissivo)."""
    channel_routing = routing.get(channel)
    if channel_routing is None:
        return True
    return channel_routing.get(event_type, True)
```

3b. Em `secur/alerts.py`:

- Adicionar import: `from .notifications import is_enabled`
- Alterar `AlertService.send` para aceitar e aplicar routing:

```python
    def send(self, camera_id, zone, event_type, details=None, zone_classification=None,
             identity=None, known=None, recognition_method=None, category=None, routing=None):
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
            channel = getattr(handler, "channel", None)
            if channel is not None and routing is not None and not is_enabled(routing, channel, event_type):
                continue
            try:
                handler(payload)
            except Exception:
                logger.exception("Alert handler failed: %s", handler.__name__)
```

- Remover os skips hardcode dos handlers e anotar o canal de cada um:

`telegram_handler` — remover a linha 39 (`if payload.get("event_type") in (...): return`) e adicionar antes da função:

```python
telegram_handler.channel = "telegram"
```

`mqtt_handler` — remover a linha 65 (`if payload.get("event_type") in (...): return`) e adicionar:

```python
mqtt_handler.channel = "automation"
```

`home_assistant_handler` — remover a linha 136 (`if payload.get("event_type") in ("snapshot_info",): return`) e adicionar:

```python
home_assistant_handler.channel = "automation"
```

3c. Em `secur/main.py`:

- Adicionar import: `from .notifications import DEFAULT_ROUTING`
- Em `main()`, após `storage = EventStorage()`:

```python
    storage.seed_default_routing(DEFAULT_ROUTING)
```

- Em `main()`, carregar routing e passar ao `AlertService`:

```python
    alerts = AlertService()
    alerts.register_handler(telegram_handler)
    alerts.register_handler(mqtt_handler)
    alerts.register_handler(home_assistant_handler)
    alerts.routing = storage.get_all_routing()
```

- Alterar `AlertService.send` para usar `self.routing` quando o argumento `routing` não for passado. Em `secur/alerts.py`, no `send`:

```python
        if routing is None:
            routing = getattr(self, "routing", None)
```

(inserir logo após a construção do payload, antes do loop de handlers)

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_alerts.py -q`
Expected: PASS (todos, incluindo os 5 novos)

- [ ] **Step 5: Commit**

```bash
git add secur/notifications.py secur/alerts.py secur/main.py tests/test_alerts.py
git commit -m "feat(alerts): routing configurável por evento × canal com defaults (no_motion off no Telegram)"
```

---

### Task 3: Captura de thumbnails no CameraWorker

**Files:**
- Modify: `secur/config.py` (constantes `THUMBNAILS_DIR`, `THUMBNAIL_INTERVAL_SECONDS`, `THUMBNAIL_HISTORY_SIZE`)
- Modify: `secur/main.py` (captura no `CameraWorker.run()` + função auxiliar `should_capture_thumbnail`)
- Test: `tests/test_main_identity.py`

**Interfaces:**
- Consumes: `EventStorage.add_camera_thumbnail`, `EventStorage.prune_camera_thumbnails` (Task 1)
- Produces:
  - `config.THUMBNAILS_DIR: Path` — `DATA_DIR / "thumbnails"`
  - `config.THUMBNAIL_INTERVAL_SECONDS: float` — 10.0
  - `config.THUMBNAIL_HISTORY_SIZE: int` — 20
  - `main.should_capture_thumbnail(last_thumb_time: float | None, now: float, interval: float) -> bool`

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_main_identity.py`:

```python
from secur.main import should_capture_thumbnail


def test_should_capture_thumbnail_interval():
    assert should_capture_thumbnail(None, 1000.0, 10.0) is True
    assert should_capture_thumbnail(1000.0, 1005.0, 10.0) is False
    assert should_capture_thumbnail(1000.0, 1010.0, 10.0) is True
    assert should_capture_thumbnail(1000.0, 1010.0001, 10.0) is True
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_identity.py -q`
Expected: FAIL — `ImportError: cannot import name 'should_capture_thumbnail'`

- [ ] **Step 3: Implementar**

3a. Em `secur/config.py`, adicionar ao final:

```python
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
THUMBNAILS_DIR.mkdir(exist_ok=True)
THUMBNAIL_INTERVAL_SECONDS = float(os.getenv("THUMBNAIL_INTERVAL_SECONDS", "10"))
THUMBNAIL_HISTORY_SIZE = int(os.getenv("THUMBNAIL_HISTORY_SIZE", "20"))
```

3b. Em `secur/main.py`:

- Adicionar `import cv2` no topo (após `import threading`):

```python
import cv2
```

- Adicionar ao import de config: `THUMBNAILS_DIR, THUMBNAIL_INTERVAL_SECONDS, THUMBNAIL_HISTORY_SIZE`
- Adicionar a função auxiliar (após `format_detections`):

```python
def should_capture_thumbnail(last_thumb_time, now, interval):
    if last_thumb_time is None:
        return True
    return (now - last_thumb_time) >= interval
```

- Em `CameraWorker.run()`, no início do `while` (junto com `last_alert_time = {}`), adicionar:

```python
        last_thumb_time = None
```

- Dentro do bloco `if motion_detected:`, após o `try/except` de processamento (após a linha do `except`/`continue`), adicionar a captura — colocar logo após o bloco `try/except` do processamento, ainda dentro do `if motion_detected:`:

```python
                # Thumbnail history: capture at most 1 per interval during continuous motion
                now_thumb = time.time()
                if should_capture_thumbnail(last_thumb_time, now_thumb, THUMBNAIL_INTERVAL_SECONDS):
                    try:
                        cam_dir = THUMBNAILS_DIR / f"cam{self.camera['id']}"
                        cam_dir.mkdir(parents=True, exist_ok=True)
                        filename = f"{int(now_thumb * 1000)}.jpg"
                        path = cam_dir / filename
                        ok, jpg = cv2.imencode(".jpg", frame)
                        if ok:
                            path.write_bytes(jpg.tobytes())
                            self.storage.add_camera_thumbnail(self.camera["id"], str(path), event_type)
                            self.storage.prune_camera_thumbnails(self.camera["id"], keep=THUMBNAIL_HISTORY_SIZE)
                            last_thumb_time = now_thumb
                    except Exception:
                        logger.warning("Falha ao capturar thumbnail (câmera %s)", self.camera.get("name"))
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_main_identity.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add secur/config.py secur/main.py tests/test_main_identity.py
git commit -m "feat(main): captura de thumbnails em movimento com intervalo de 10s e retenção de 20"
```

---

### Task 4: API — rotas de thumbnails e notificações

**Files:**
- Modify: `secur/app.py` (rotas novas + DELETE de câmera limpa thumbnails + /docs)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `EventStorage.list_camera_thumbnails`, `EventStorage.remove_camera_thumbnails`, `EventStorage.get_all_routing`, `EventStorage.set_routing`, `EventStorage.get_camera` (Task 1); `notifications.CHANNELS`, `notifications.EVENT_TYPES` (Task 2)
- Produces:
  - `GET /camera/<int:camera_id>/thumbnails` → 200 JSON `[{id, timestamp, event_type, url}]` | 404
  - `GET /thumbnails/<int:thumb_id>/image` → 200 JPEG | 404
  - `GET /api/notifications` → 200 `{channels, events, routing}`
  - `PUT /api/notifications/routing` → 200 `{status: "ok"}` | 400 (canal/evento inválido)

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `tests/test_app.py`:

```python
def test_camera_thumbnails_route(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    resp = client.post("/cameras", json={"name": "Cam", "source": "source://x", "zone": "entrada"})
    assert resp.status_code == 201
    cam_id = resp.json["id"]

    # no thumbnails yet
    resp = client.get(f"/camera/{cam_id}/thumbnails")
    assert resp.status_code == 200
    assert resp.json == []


def test_camera_thumbnails_route_404(client):
    resp = client.get("/camera/999/thumbnails")
    assert resp.status_code == 404


def test_thumbnail_image_route_404(client):
    resp = client.get("/thumbnails/999/image")
    assert resp.status_code == 404


def test_notifications_get(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    body = resp.json
    assert [c["key"] for c in body["channels"]] == ["telegram", "automation"]
    assert "motion_detected" in [e["key"] for e in body["events"]]
    assert "routing" in body


def test_notifications_put(client):
    resp = client.put("/api/notifications/routing", json={"channel": "telegram", "event_type": "no_motion", "enabled": True})
    assert resp.status_code == 200
    body = client.get("/api/notifications").json
    assert body["routing"]["telegram"]["no_motion"] is True


def test_notifications_put_invalid(client):
    resp = client.put("/api/notifications/routing", json={"channel": "nope", "event_type": "no_motion", "enabled": True})
    assert resp.status_code == 400
    resp = client.put("/api/notifications/routing", json={"channel": "telegram", "event_type": "nope", "enabled": True})
    assert resp.status_code == 400
```

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: FAIL — `404 NOT FOUND` nas rotas novas

- [ ] **Step 3: Implementar**

Em `secur/app.py`:

3a. Adicionar imports no topo:

```python
import os
from .notifications import CHANNELS, EVENT_TYPES
from flask import send_file
```

3b. Adicionar as rotas novas (após a rota `camera_snapshot`, antes de `/docs`):

```python
    @app.route("/camera/<int:camera_id>/thumbnails")
    def camera_thumbnails(camera_id):
        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404
        items = storage.list_camera_thumbnails(camera_id, limit=20)
        out = []
        for it in items:
            out.append({
                "id": it["id"],
                "timestamp": it["timestamp"],
                "event_type": it["event_type"],
                "url": f"/thumbnails/{it['id']}/image",
            })
        return jsonify(out)

    @app.route("/thumbnails/<int:thumb_id>/image")
    def thumbnail_image(thumb_id):
        item = storage.get_camera_thumbnail(thumb_id)
        if not item:
            return jsonify({"error": "Thumbnail não encontrado"}), 404
        path = item["path"]
        if not os.path.exists(path):
            return jsonify({"error": "Thumbnail não encontrado"}), 404
        return send_file(path, mimetype="image/jpeg")
```

3c. Rotas de notificações (após as rotas de zonas, antes de `/`):

```python
    @app.route("/api/notifications")
    def notifications_get():
        routing = storage.get_all_routing()
        return jsonify({
            "channels": CHANNELS,
            "events": EVENT_TYPES,
            "routing": routing,
        })

    @app.route("/api/notifications/routing", methods=["PUT"])
    def notifications_put():
        payload = request.get_json() or {}
        channel = payload.get("channel")
        event_type = payload.get("event_type")
        enabled = payload.get("enabled")
        if enabled is None:
            return jsonify({"error": "enabled é obrigatório"}), 400
        valid_channels = {c["key"] for c in CHANNELS}
        valid_events = {e["key"] for e in EVENT_TYPES}
        if channel not in valid_channels:
            return jsonify({"error": "canal inválido"}), 400
        if event_type not in valid_events:
            return jsonify({"error": "evento inválido"}), 400
        storage.set_routing(channel, event_type, bool(enabled))
        return jsonify({"status": "ok"}), 200
```

3d. Em `delete_camera`, adicionar limpeza de thumbnails:

```python
    @app.route("/cameras/<int:camera_id>", methods=["DELETE"])
    def delete_camera(camera_id):
        removed = storage.remove_camera(camera_id)
        if not removed:
            return jsonify({"error": "Câmera não encontrada"}), 404
        storage.remove_camera_thumbnails(camera_id)
        return jsonify({"status": "removido"}), 200
```

3e. Em `/docs`, adicionar as novas entradas na lista `api_docs`:

```python
            {"path": "/camera/<id>/thumbnails", "method": "GET", "description": "Lista os últimos thumbnails da câmera"},
            {"path": "/thumbnails/<id>/image", "method": "GET", "description": "Imagem JPEG de um thumbnail"},
            {"path": "/api/notifications", "method": "GET", "description": "Canais, eventos e routing de notificações"},
            {"path": "/api/notifications/routing", "method": "PUT", "description": "Atualiza routing de um evento em um canal"},
```

- [ ] **Step 4: Rodar os testes para ver passar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS (todos, incluindo os 6 novos)

- [ ] **Step 5: Commit**

```bash
git add secur/storage.py secur/app.py tests/test_app.py
git commit -m "feat(api): rotas de thumbnails por câmera e configuração de notificações"
```

---

### Task 5: UI — histórico de thumbnails no card da câmera

**Files:**
- Modify: `secur/templates/dashboard.html` (modal de histórico + botão "Ao vivo" no card)
- Modify: `secur/static/dashboard.js` (clique no preview abre histórico; `openThumbnailHistory`; botão "Ao vivo")
- Modify: `secur/static/style.css` (estilos do grid de histórico)
- Test: verificação manual (sem teste automatizado de JS no projeto)

**Interfaces:**
- Consumes: `GET /camera/<id>/thumbnails`, `GET /thumbnails/<id>/image` (Task 4)

- [ ] **Step 1: Adicionar o modal de histórico no HTML**

Em `secur/templates/dashboard.html`, após o bloco do Live Player Modal (após a linha do `</div>` que fecha `live-player-overlay`, antes de `<script src=...hls.js...>`), adicionar:

```html
    <!-- Thumbnail History Modal -->
    <div id="thumb-history-overlay" class="dialog-overlay hidden-panel" role="dialog" aria-modal="true">
        <div class="dialog-card thumb-history-card">
            <div class="dialog-header">
                <h3 id="thumb-history-title">Histórico</h3>
                <button type="button" class="button-close" aria-label="Fechar" onclick="closeThumbHistory()">×</button>
            </div>
            <div id="thumb-history-grid" class="thumb-history-grid"></div>
            <p id="thumb-history-empty" class="thumb-history-empty">Nenhum thumbnail capturado ainda.</p>
        </div>
    </div>
```

- [ ] **Step 2: Alterar o card da câmera e adicionar as funções JS**

Em `secur/static/dashboard.js`:

2a. Em `createCameraCard`, substituir o wrapper do preview (linha 75) para abrir o histórico e adicionar botão "Ao vivo":

```javascript
      <div class="camera-preview-wrapper" onclick="openThumbHistory(${camera.id}, '${camera.name}')" style="cursor:pointer;">
        <img
          id="${imgId}"
          class="camera-preview"
          src="/camera/${camera.id}/snapshot?ts=${Date.now()}"
          alt="Preview da câmera"
          onload="this.parentElement.classList.remove('loading'); this.parentElement.classList.remove('error');"
          onerror="this.parentElement.classList.remove('loading'); this.parentElement.classList.add('error'); this.style.display='none'; this.nextElementSibling.style.display='flex';"
        />
        <div class="camera-preview-error" style="display:none;">
          <span>Falha ao carregar preview</span>
          <button class="button-mini" onclick="event.stopPropagation(); retrySnapshot(${camera.id})">Tentar novamente</button>
        </div>
      </div>
      <div class="camera-card-actions">
        <button class="button-secondary button-mini" onclick="event.stopPropagation(); openLivePlayer(${camera.id}, '${camera.name}', '${camera.source}')">Ao vivo</button>
      </div>
```

2b. Adicionar as funções de histórico (após `closeLivePlayer`):

```javascript
/* ========== Thumbnail History ========== */

function openThumbHistory(cameraId, cameraName) {
  const overlay = document.getElementById('thumb-history-overlay');
  const title = document.getElementById('thumb-history-title');
  const grid = document.getElementById('thumb-history-grid');
  const empty = document.getElementById('thumb-history-empty');

  title.textContent = `Histórico — ${cameraName}`;
  grid.innerHTML = '';
  empty.style.display = 'none';
  overlay.classList.remove('hidden-panel');

  fetch(`/camera/${cameraId}/thumbnails`)
    .then(r => r.json())
    .then(items => {
      if (!items || items.length === 0) {
        empty.style.display = '';
        return;
      }
      grid.innerHTML = items.map(item => `
        <div class="thumb-history-item">
          <img src="${item.url}" alt="thumbnail" loading="lazy" />
          <span class="thumb-history-time">${new Date(item.timestamp).toLocaleString()}</span>
          <span class="thumb-history-event">${item.event_type}</span>
        </div>
      `).join('');
    })
    .catch(() => {
      empty.textContent = 'Falha ao carregar histórico.';
      empty.style.display = '';
    });
}

function closeThumbHistory() {
  const overlay = document.getElementById('thumb-history-overlay');
  if (overlay) overlay.classList.add('hidden-panel');
}
```

- [ ] **Step 3: Adicionar estilos CSS**

Em `secur/static/style.css`, adicionar ao final:

```css
/* Thumbnail History */
.thumb-history-card {
  max-width: 720px;
  width: 90%;
}
.thumb-history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
  max-height: 60vh;
  overflow-y: auto;
}
.thumb-history-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--surface);
}
.thumb-history-item img {
  width: 100%;
  height: 90px;
  object-fit: cover;
  display: block;
}
.thumb-history-time {
  display: block;
  font-size: 0.7rem;
  color: var(--muted);
  padding: 4px 8px 0;
}
.thumb-history-event {
  display: block;
  font-size: 0.68rem;
  color: var(--muted-subtle);
  padding: 0 8px 6px;
}
.thumb-history-empty {
  color: var(--muted);
  text-align: center;
  padding: 16px;
}
.camera-card-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}
```

- [ ] **Step 4: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS (nada quebrado)

Verificação manual (se ambiente disponível): iniciar o app e clicar no preview de uma câmera → modal de histórico abre; botão "Ao vivo" abre o player.

- [ ] **Step 5: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js secur/static/style.css
git commit -m "feat(ui): histórico de thumbnails no card da câmera + botão Ao vivo"
```

---

### Task 6: UI — seção de configuração de notificações

**Files:**
- Modify: `secur/templates/dashboard.html` (nav + seção)
- Modify: `secur/static/dashboard.js` (render + toggle)
- Modify: `secur/static/style.css` (estilos da tabela de toggles)
- Test: verificação manual

**Interfaces:**
- Consumes: `GET /api/notifications`, `PUT /api/notifications/routing` (Task 4)

- [ ] **Step 1: Adicionar nav e seção no HTML**

Em `secur/templates/dashboard.html`:

1a. Na sidebar, após o botão `nav-recent-events` (após a linha 31), adicionar:

```html
            <button type="button" class="nav-link" data-section="notifications" id="nav-notifications">
                <span class="icon">&#x1F514;</span>
                <span>Notificações</span>
            </button>
```

1b. Após a seção `recent-events` (após a linha 238), adicionar:

```html
            <section class="panel hidden-panel" id="notifications">
                <div class="panel-header">
                    <div>
                        <h2>Configuração de notificações</h2>
                        <p>Escolha quais tipos de evento são notificados em cada canal.</p>
                    </div>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Evento</th>
                                <th>Categoria</th>
                                <th id="notif-channel-headers"></th>
                            </tr>
                        </thead>
                        <tbody id="notifications-table-body"></tbody>
                    </table>
                </div>
            </section>
```

- [ ] **Step 2: Adicionar render e toggle no JS**

Em `secur/static/dashboard.js`, adicionar (após `renderZoneManagement`):

```javascript
/* ========== Notifications config ========== */

async function renderNotifications() {
  const body = document.getElementById('notifications-table-body');
  if (!body) return;
  let data;
  try {
    data = await fetchData('/api/notifications');
  } catch (e) {
    body.innerHTML = '<tr><td colspan="3">Falha ao carregar configuração.</td></tr>';
    return;
  }

  const headerRow = document.getElementById('notif-channel-headers');
  if (headerRow) {
    headerRow.innerHTML = data.channels.map(c => `<th>${c.label}</th>`).join('');
  }

  const events = data.events.filter(e => !e.legacy);
  body.innerHTML = events.map(event => {
    const cells = data.channels.map(channel => {
      const enabled = !!(data.routing[channel.key] && data.routing[channel.key][event.key]);
      return `
        <td class="notif-toggle-cell">
          <label class="switch">
            <input type="checkbox" data-channel="${channel.key}" data-event="${event.key}" ${enabled ? 'checked' : ''} />
            <span class="slider"></span>
          </label>
        </td>
      `;
    }).join('');
    const categoryLabel = event.category === 'alerta' ? 'Alerta' : 'Info';
    return `
      <tr>
        <td>${escapeHtml(event.label)}</td>
        <td><span class="badge ${event.category === 'alerta' ? 'badge-alert' : 'badge-info'}">${categoryLabel}</span></td>
        ${cells}
      </tr>
    `;
  }).join('');

  body.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.addEventListener('change', async () => {
      const payload = {
        channel: input.dataset.channel,
        event_type: input.dataset.event,
        enabled: input.checked,
      };
      const res = await fetch('/api/notifications/routing', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        input.checked = !input.checked;
        showMenuMessage('Falha ao salvar configuração.', 'camera-form-message');
      }
    });
  });
}
```

E chamar `renderNotifications()` dentro de `renderDashboard()` (após `renderZoneManagement(zones);`):

```javascript
  renderNotifications();
```

- [ ] **Step 3: Adicionar estilos CSS**

Em `secur/static/style.css`, adicionar ao final:

```css
/* Notifications config */
.notif-toggle-cell {
  text-align: center;
}
.switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--border-strong);
  border-radius: var(--radius-pill);
  transition: background 0.2s;
}
.slider::before {
  content: "";
  position: absolute;
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}
.switch input:checked + .slider {
  background: var(--primary);
}
.switch input:checked + .slider::before {
  transform: translateX(18px);
}
.badge-alert {
  background: rgba(220, 38, 38, 0.12);
  color: var(--danger);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
  font-size: 0.7rem;
}
.badge-info {
  background: rgba(37, 99, 235, 0.12);
  color: var(--info);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
  font-size: 0.7rem;
}
```

- [ ] **Step 4: Verificar**

Run: `/tmp/secur-venv/bin/python -m pytest tests/test_app.py -q`
Expected: PASS

Verificação manual: abrir a seção "Notificações" na dashboard → tabela com eventos × canais e toggles; alternar um toggle → PUT salva e estado persiste após reload.

- [ ] **Step 5: Commit**

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js secur/static/style.css
git commit -m "feat(ui): seção de configuração de notificações por evento × canal"
```

---

### Task 7: Verificação final e revisão

**Files:**
- Test: todos os testes

- [ ] **Step 1: Rodar a suíte completa**

Run: `/tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: PASS (todos os testes, incluindo os novos)

- [ ] **Step 2: Revisar o diff**

Run: `git diff dev --stat`
Expected: mudanças apenas nos arquivos listados nas tasks 1-6

- [ ] **Step 3: Verificar cobertura do spec**

Conferir manualmente contra o spec `docs/superpowers/specs/2026-08-13-camera-thumbnail-history-design.md`:
- [ ] Tabela `camera_thumbnails` + métodos (Task 1)
- [ ] Tabela `notification_routing` + métodos (Task 1)
- [ ] Registro canônico de canais/eventos + defaults (Task 2)
- [ ] Dispatch respeita routing (Task 2)
- [ ] Captura com intervalo 10s e retenção 20 (Task 3)
- [ ] Rotas de thumbnails e notificações + /docs (Task 4)
- [ ] DELETE de câmera limpa thumbnails (Task 4)
- [ ] Modal de histórico + botão "Ao vivo" (Task 5)
- [ ] Seção "Notificações" com toggles (Task 6)
- [ ] `no_motion` off no Telegram por default (Task 2)

- [ ] **Step 4: Commit final (se houver ajustes)**

```bash
git add -A
git commit -m "chore: ajustes finais"
```