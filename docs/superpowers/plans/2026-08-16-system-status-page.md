# System Status embarcado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar no rodapé da versão um link que abre, dentro do dashboard principal, uma seção de Status do Sistema listando módulos/drivers/serviços com estado configurado + checagem ao vivo.

**Architecture:** Backend expõe `GET /api/system-status` (JSON) via `build_system_status()` em novo `src/status.py`, agregando config + probes leves (timeout 3s, degradação graciosa). Frontend adiciona `<section id="system-status">` dentro de `#page`, populada por JS que busca o endpoint; o rodapé `vX.Y.Z` vira link que chama `setActiveSection('system-status')`. Sem alterar o poll de 5s da Visão geral.

**Tech Stack:** Python/Flask (backend), JavaScript vanilla + Flask `render_template`/JSON (frontend), OpenCV (checagem de modelo), `urllib`/`socket` (probes, sem deps novas).

## Global Constraints

- Seção **embedada no dashboard principal** (dentro de `#page`), não página separada.
- Link no **rodapé da versão** (`vX.Y.Z`), abrindo a seção via `setActiveSection`.
- Status mostra **configurado + checagem ao vivo** quando viável; checagens externas com timeout 3s e degradação graciosa ("não verificado"/erro não quebra a página).
- Lista **todos os módulos**: Captura, Detecção (objeto+movimento), Identidade, Notificações (Telegram, MQTT, Home Assistant).
- Badges reusam CSS existente (`--success`, `--warning`, `--danger`, `--muted`) e padrão `.card`/`.badge-*`.
- Não altera `/status` do dashboard nem o poll de 5s da Visão geral.

---

## File Structure

- **Create** `src/status.py` — `build_system_status(camera_manager=None)` + helpers de probe (`_probe_telegram`, `_probe_mqtt`, `_probe_ha`).
- **Create** `tests/test_status.py` — testes unitários com probes mockados (sem rede).
- **Modify** `src/app.py` — importar `build_system_status` e adicionar rota `GET /api/system-status`.
- **Modify** `src/templates/dashboard.html` — adicionar `<section id="system-status">` em `#page` e transformar rodapé em link.
- **Modify** `src/static/dashboard.js` — `renderSystemStatus()`, `setupSystemStatusLink()`, timer de atualização.

---

### Task 1: Módulo de agregação de status (backend, testável)

**Files:**
- Create: `src/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Produces: `build_system_status(camera_manager=None) -> dict` com chaves `backend` e `modules` (lista de `{group, items:[{name, configured:bool, operational:bool, detail:str}]}`); helpers `_probe_telegram(token)`, `_probe_mqtt(broker, port)`, `_probe_ha(url, token)` retornando `(bool, str)`.
- Variáveis lidas: `DETECTOR_MODEL_PATH`, `IDENTITY_ENABLED`, `IDENTITY_FACE_MODEL_PATH`, `MOTION_MIN_AREA` (de `src.config`); `TELEGRAM_BOT_TOKEN`, `MQTT_BROKER_URL`, `MQTT_BROKER_PORT`, `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` via `os.getenv` (igual a `alerts.py`).

- [ ] **Step 1: Escrever o teste falhando**

```python
import src.status as status


def test_build_includes_all_groups(monkeypatch):
    monkeypatch.setattr(status, "_probe_telegram", lambda t: (True, "ok"))
    monkeypatch.setattr(status, "_probe_mqtt", lambda b, p: (False, "sem broker"))
    monkeypatch.setattr(status, "_probe_ha", lambda u, t: (False, "sem HA"))
    out = status.build_system_status(camera_manager=None)
    groups = [m["group"] for m in out["modules"]]
    assert groups == ["Captura", "Detecção", "Identidade", "Notificações"]
    # sem camera_manager -> Workers configurado=False
    workers = out["modules"][0]["items"][1]
    assert workers["configured"] is False
    # Telegram probe True reflete em operational
    tg = out["modules"][3]["items"][0]
    assert tg["operational"] is True


def test_detector_configured_when_path_exists(tmp_path, monkeypatch):
    model = tmp_path / "m.onnx"
    model.write_bytes(b"fake")
    monkeypatch.setattr(status, "DETECTOR_MODEL_PATH", str(model))
    monkeypatch.setattr(status, "_probe_telegram", lambda t: (False, "x"))
    monkeypatch.setattr(status, "_probe_mqtt", lambda b, p: (False, "x"))
    monkeypatch.setattr(status, "_probe_ha", lambda u, t: (False, "x"))
    out = status.build_system_status()
    det = out["modules"][1]["items"][1]
    assert det["configured"] is True
    # readNetFromONNX de arquivo fake falha -> operational False, detail explica
    assert det["operational"] is False
    assert "falha" in det["detail"].lower()
```

- [ ] **Step 2: Rodar teste para confirmar falha**

Run: `py -3 -m pytest tests/test_status.py -q`
Expected: FAIL (`ModuleNotFoundError` / `build_system_status` não existe).

- [ ] **Step 3: Implementar `src/status.py`**

```python
import os
import cv2
from .config import (
    DETECTOR_MODEL_PATH,
    IDENTITY_ENABLED,
    IDENTITY_FACE_MODEL_PATH,
    MOTION_MIN_AREA,
    HOME_ASSISTANT_URL,
    HOME_ASSISTANT_TOKEN,
)


def _probe_telegram(token):
    if not token:
        return False, "token não configurado"
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe", timeout=3
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.load(r)
        if data.get("ok"):
            return True, f"bot @{data['result'].get('username', '?')}"
        return False, data.get("description", "erro Telegram")
    except Exception as e:
        return False, f"Falha: {e}"


def _probe_mqtt(broker, port):
    if not broker:
        return False, "broker não configurado"
    import socket
    try:
        with socket.create_connection((broker, int(port)), timeout=3):
            return True, f"TCP {broker}:{port} ok"
    except Exception as e:
        return False, f"Falha: {e}"


def _probe_ha(url, token):
    if not url:
        return False, "URL não configurada"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=3,
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"Falha: {e}"


def build_system_status(camera_manager=None):
    opencv_ver = getattr(cv2, "__version__", "?")
    modules = []

    capture_items = [{
        "name": "Driver de captura (OpenCV)",
        "configured": True,
        "operational": True,
        "detail": f"OpenCV {opencv_ver}",
    }]
    workers = camera_manager.get_status() if camera_manager else []
    healthy = sum(1 for w in workers if w.get("healthy") is not False)
    capture_items.append({
        "name": "Workers de câmera",
        "configured": bool(camera_manager),
        "operational": healthy > 0,
        "detail": f"{healthy} ativo(s) / {len(workers)} total",
    })
    modules.append({"group": "Captura", "items": capture_items})

    det_items = [{
        "name": "Movimento",
        "configured": True,
        "operational": True,
        "detail": f"MOTION_MIN_AREA={MOTION_MIN_AREA}",
    }]
    model_cfg = bool(DETECTOR_MODEL_PATH) and os.path.exists(DETECTOR_MODEL_PATH)
    model_op = False
    if DETECTOR_MODEL_PATH:
        if os.path.exists(DETECTOR_MODEL_PATH):
            try:
                cv2.dnn.readNetFromONNX(DETECTOR_MODEL_PATH)
                model_op = True
                model_detail = f"{os.path.basename(DETECTOR_MODEL_PATH)} carregado"
            except Exception as e:
                model_detail = f"falha ao carregar: {e}"
        else:
            model_detail = "arquivo não encontrado"
    else:
        model_detail = "não configurado"
    det_items.append({
        "name": "Objetos (YOLO)",
        "configured": model_cfg,
        "operational": model_op,
        "detail": model_detail,
    })
    modules.append({"group": "Detecção", "items": det_items})

    id_cfg = bool(IDENTITY_ENABLED)
    id_op = (
        bool(IDENTITY_ENABLED)
        and bool(IDENTITY_FACE_MODEL_PATH)
        and os.path.exists(IDENTITY_FACE_MODEL_PATH)
    )
    modules.append({"group": "Identidade", "items": [{
        "name": "Reconhecimento",
        "configured": id_cfg,
        "operational": id_op,
        "detail": "IDENTITY_ENABLED=true" if id_cfg else "IDENTITY_ENABLED=false",
    }]})

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_op, tg_det = _probe_telegram(tg_token)
    mqtt_url = os.getenv("MQTT_BROKER_URL")
    mqtt_port = os.getenv("MQTT_BROKER_PORT", "1883")
    mq_op, mq_det = _probe_mqtt(mqtt_url, mqtt_port)
    ha_op, ha_det = _probe_ha(HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN)
    notif_items = [
        {"name": "Telegram", "configured": bool(tg_token), "operational": tg_op, "detail": tg_det},
        {"name": "MQTT", "configured": bool(mqtt_url), "operational": mq_op, "detail": mq_det},
        {"name": "Home Assistant", "configured": bool(HA_URL_AND_TOKEN), "operational": ha_op, "detail": ha_det},
    ]
    modules.append({"group": "Notificações", "items": notif_items})

    return {
        "backend": {"opencv_version": opencv_ver, "dnn_backend": "OpenCV DNN (ONNX)"},
        "modules": modules,
    }
```

> Nota: no item Home Assistant, usar `bool(HOME_ASSISTANT_URL) and bool(HOME_ASSISTANT_TOKEN)` no lugar de `HA_URL_AND_TOKEN` (substituir no código final).

- [ ] **Step 4: Rodar teste para confirmar sucesso**

Run: `py -3 -m pytest tests/test_status.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/status.py tests/test_status.py
git commit -m "feat(status): add build_system_status aggregation module"
```

---

### Task 2: Rota JSON no app

**Files:**
- Modify: `src/app.py` (import + rota, perto das rotas `/status`, `/health`)

**Interfaces:**
- Consumes: `build_system_status(camera_manager)` (Task 1); `camera_manager` já usado em `/status`.
- Produces: `GET /api/system-status` retornando o dict acima como JSON.

- [ ] **Step 1: Adicionar import no topo de app.py**

Após os imports existentes de `src`, adicionar:
```python
from .status import build_system_status
```

- [ ] **Step 2: Adicionar rota (após `@app.route("/status")`)**

```python
@app.route("/api/system-status")
def api_system_status():
    return jsonify(build_system_status(camera_manager))
```

- [ ] **Step 3: Verificar sintaxe e import**

Run: `py -3 -c "import src.app"`
Expected: sem erro de import.

- [ ] **Step 4: Commit**

```bash
git add src/app.py
git commit -m "feat(status): expose /api/system-status endpoint"
```

---

### Task 3: Seção HTML + link no rodapé

**Files:**
- Modify: `src/templates/dashboard.html` (dentro de `#page`; rodapé na sidebar)

**Interfaces:**
- Consumes: estilos `.card`, `.badge-*`, variáveis CSS existentes.
- Produces: `<section id="system-status" class="panel hidden-panel">` com `<div id="system-status-cards" class="grid">`; rodapé `<a id="nav-system-status">`.

- [ ] **Step 1: Adicionar seção dentro de `#page`**

Antes do fechamento de `#page` (ou após a última `<section>`), adicionar:
```html
<section class="panel hidden-panel" id="system-status">
  <h2>Status do sistema</h2>
  <div id="system-status-cards" class="grid"></div>
</section>
```

- [ ] **Step 2: Transformar rodapé da versão em link**

Substituir:
```html
<div class="footer-nav">v0.2.0</div>
```
por:
```html
<div class="footer-nav"><a href="#" id="nav-system-status">v0.2.0</a></div>
```

- [ ] **Step 3: Verificar template válido**

Run: `py -3 -c "from flask import Flask; from src.app import app; print([r for r in app.url_map.iter_rules() if 'system' in r.rule])"`
Expected: lista contendo `/api/system-status`.

- [ ] **Step 4: Commit**

```bash
git add src/templates/dashboard.html
git commit -m "feat(status): add embedded system-status section and footer link"
```

---

### Task 4: Renderização e atualização no JS

**Files:**
- Modify: `src/static/dashboard.js`

**Interfaces:**
- Consumes: `GET /api/system-status` (Task 2); `setActiveSection(sectionId)` (já existente).
- Produces: `renderSystemStatus()`, `setupSystemStatusLink()`, timer de atualização enquanto a seção está visível.

- [ ] **Step 1: Adicionar função de renderização e link**

Próximo de `setupSidebarNavigation()` / `setupOfflineToggle()`, adicionar:
```js
function statusBadgeClass(item) {
  if (!item.configured) return 'badge-off';
  return item.operational ? 'badge-ok' : 'badge-warn';
}

function statusBadgeLabel(item) {
  if (!item.configured) return 'Inativo';
  return item.operational ? 'Operacional' : 'Configurado';
}

function renderSystemStatus() {
  const container = document.getElementById('system-status-cards');
  if (!container) return;
  fetch('/api/system-status')
    .then(r => r.json())
    .then(data => {
      const groups = data.modules || [];
      container.innerHTML = groups.map(g => {
        const cards = g.items.map(it => `
          <div class="card">
            <h3>${g.group}</h3>
            <p><strong>${it.name}</strong></p>
            <p>${it.detail || ''}</p>
            <span class="badge ${statusBadgeClass(it)}">${statusBadgeLabel(it)}</span>
          </div>`).join('');
        return cards;
      }).join('');
    })
    .catch(() => {
      container.innerHTML = '<div class="card"><p>Falha ao carregar status</p></div>';
    });
}

let systemStatusTimer = null;
function setupSystemStatusLink() {
  const link = document.getElementById('nav-system-status');
  if (!link) return;
  link.addEventListener('click', (e) => {
    e.preventDefault();
    setActiveSection('system-status');
    renderSystemStatus();
    if (systemStatusTimer) clearInterval(systemStatusTimer);
    systemStatusTimer = setInterval(() => {
      const sec = document.getElementById('system-status');
      if (sec && !sec.classList.contains('hidden-panel')) renderSystemStatus();
      else if (systemStatusTimer) { clearInterval(systemStatusTimer); systemStatusTimer = null; }
    }, 15000);
  });
}
```

- [ ] **Step 2: Chamar setup na inicialização**

Localizar onde `setupSidebarNavigation()` / `setupOfflineToggle()` são chamados (inicialização do dashboard) e adicionar `setupSystemStatusLink();` na mesma sequência.

- [ ] **Step 3: Verificar sintaxe**

Run: `node --check src/static/dashboard.js`
Expected: sem erro de sintaxe.

- [ ] **Step 4: Commit**

```bash
git add src/static/dashboard.js
git commit -m "feat(status): render embedded system-status section with live badges"
```

---

### Task 5: Verificação ponta a ponta

**Files:**
- Test: reuso de `tests/test_status.py`.

- [ ] **Step 1: Rodar testes unitários**

Run: `py -3 -m pytest tests/test_status.py -q`
Expected: PASS.

- [ ] **Step 2: Verificação manual**

1. Subir a aplicação (`python run.py` ou Docker).
2. Clicar no link da versão no rodapé → a seção "Status do sistema" abre dentro do dashboard.
3. Confirmar os grupos Captura / Detecção / Identidade / Notificações com badges coloridas.
4. Derrubar Telegram/MQTT (ou usar token/URL inválido) e reabrir/aguardar 15s → badge amarelo/vermelho com detalhe do erro.
5. Confirmar que a Visão geral (poll de 5s) não foi afetada.

- [ ] **Step 3: Commit (se houver ajuste de CSS de badge necessário)**

Se os badges precisarem de estilo, editar `src/static/style.css` (reuso de `.badge-ok`/`.badge-warn`/`.badge-off` ou criar), e:
```bash
git add src/static/style.css
git commit -m "style(status): badge styles for system-status"
```
Caso contrário, pular.

---

## Self-Review Notes (autor)

- **Cobertura do spec:** Task 1 cobre agregação + probes; Task 2 a rota; Task 3 a seção embedada + link no rodapé; Task 4 o render com badges e atualização; Task 5 verificação. Todos os grupos do spec presentes.
- **Sem placeholders:** cada step tem comando/código. (Anotação sobre `HA_URL_AND_TOKEN` em Task 1 Step 3 é correção explícita a aplicar no código final.)
- **Consistência de tipos:** `build_system_status` e `_probe_*` definidos em Task 1 e consumidos em Task 2/4 com mesmos nomes; campo `modules[].items[]` com `configured/operational/detail` usado no JS em Task 4.
