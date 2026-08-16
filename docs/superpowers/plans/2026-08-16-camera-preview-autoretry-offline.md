# Camera Preview Auto-Retry + Offline Badge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-retry camera snapshot previews on failure and show an "Offline" badge on the card after ~5 min of no response, recovering automatically when the preview returns — purely on the frontend.

**Architecture:** A small pure-logic module (`camera_fault.js`, dual-export for browser + Node) decides fault-state transitions from `(state, event, now)`. `dashboard.js` holds a per-camera `cameraFaultState` map and timers, calls the pure logic on image `onerror`/`onload`, and renders the badge by reading `cameraFaultState`. No backend change.

**Tech Stack:** Vanilla JS (browser), `node --test` for unit tests (Node 18+), Flask serving static files.

## Global Constraints

- Mudança **puramente frontend**; não alterar `src/main.py`, `src/app.py` nem endpoints.
- Badge "Offline" **no mesmo card** (câmera permanece na grade, não vai para a seção offline do backend).
- Limiar p/ Offline: **5 min** (`SNAPSHOT_OFFLINE_THRESHOLD_MS = 300000`).
- Auto-retry: **15 s** enquanto "retrying" (`SNAPSHOT_RETRY_INTERVAL_MS = 15000`); sondagem **30 s** quando "offline" (`SNAPSHOT_OFFLINE_RETRY_INTERVAL_MS = 30000`).
- Auto-recuperação: ao carregar o preview com sucesso, volta ao estado normal sozinho.
- Estado de falha é **por câmera** (mapa `cameraFaultState[id]`), sobrevive ao poll/re-render, mas não persiste entre recarregamentos de página.

---

## File Structure

- **Create** `src/static/camera_fault.js` — lógica pura de transição de estado (dual-export browser/Node). Sem DOM, sem timers.
- **Create** `tests/test_camera_fault.js` — testes Node da lógica pura.
- **Modify** `src/templates/dashboard.html:414` — incluir `<script src="/static/camera_fault.js"></script>` antes de `dashboard.js`.
- **Modify** `src/static/dashboard.js` — constantes, mapa `cameraFaultState`, handlers (`onSnapshotError`, `onSnapshotLoad`, `scheduleSnapshotRetry`, `markSnapshotOffline`), integração em `createCameraCard` e `renderCameraTiles`.

---

### Task 1: Lógica pura de transição de falha (testável)

**Files:**
- Create: `src/static/camera_fault.js`
- Test: `tests/test_camera_fault.js`

**Interfaces:**
- Produces: `CameraFault.transitionFault(state, event, now, cfg)` → `{ state, reload, offline }`; `CameraFault.nextRetryIntervalMs(state, cfg)` → `number`; `CameraFault.FAULT_DEFAULTS` (objeto com `retryIntervalMs`, `offlineRetryIntervalMs`, `offlineThresholdMs`).
  - `state`: `null` (ok) ou `{ status: 'retrying'|'offline', firstFailAt: number, timer: null }`. `event`: `'error' | 'load'`. `cfg`: opcional, mescla sobre `FAULT_DEFAULTS`.
  - `reload`: `true` quando o preview deve ser recarregado (img.src atualizado pelo chamador).
  - `offline`: `true` quando a transição resultou em estado `offline`.

- [ ] **Step 1: Escrever o teste falhando**

```js
const test = require('node:test');
const assert = require('node:assert');
const { transitionFault, nextRetryIntervalMs, FAULT_DEFAULTS } = require('../../src/static/camera_fault.js');

test('erro vindo de estado limpo -> retrying e recarrega', () => {
  const { state, reload, offline } = transitionFault(null, 'error', 1000);
  assert.strictEqual(state.status, 'retrying');
  assert.strictEqual(state.firstFailAt, 1000);
  assert.strictEqual(reload, true);
  assert.strictEqual(offline, false);
});

test('erro dentro do limiar continua retrying', () => {
  const s = { status: 'retrying', firstFailAt: 1000, timer: null };
  const { state, offline } = transitionFault(s, 'error', 1000 + 60000, FAULT_DEFAULTS);
  assert.strictEqual(state.status, 'retrying');
  assert.strictEqual(offline, false);
});

test('erro apos limiar de 5min -> offline', () => {
  const s = { status: 'retrying', firstFailAt: 1000, timer: null };
  const { state, offline } = transitionFault(s, 'error', 1000 + 300000, FAULT_DEFAULTS);
  assert.strictEqual(state.status, 'offline');
  assert.strictEqual(offline, true);
});

test('load -> recupera (estado nulo)', () => {
  const s = { status: 'offline', firstFailAt: 1000, timer: null };
  const { state, reload } = transitionFault(s, 'load', 5000);
  assert.strictEqual(state, null);
  assert.strictEqual(reload, false);
});

test('intervalo de retry usa valor offline quando offline', () => {
  const s = { status: 'offline', firstFailAt: 0, timer: null };
  assert.strictEqual(nextRetryIntervalMs(s, FAULT_DEFAULTS), FAULT_DEFAULTS.offlineRetryIntervalMs);
  assert.strictEqual(nextRetryIntervalMs(null, FAULT_DEFAULTS), FAULT_DEFAULTS.retryIntervalMs);
  assert.strictEqual(nextRetryIntervalMs({ status: 'retrying', firstFailAt: 0, timer: null }, FAULT_DEFAULTS), FAULT_DEFAULTS.retryIntervalMs);
});
```

- [ ] **Step 2: Rodar teste para confirmar falha**

Run: `node --test tests/test_camera_fault.js`
Expected: FAIL (módulo `camera_fault.js` não existe).

- [ ] **Step 3: Implementar o módulo puro**

```js
(function (global, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.CameraFault = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const FAULT_DEFAULTS = {
    retryIntervalMs: 15000,
    offlineRetryIntervalMs: 30000,
    offlineThresholdMs: 300000,
  };

  function transitionFault(state, event, now, cfg) {
    const c = Object.assign({}, FAULT_DEFAULTS, cfg || {});
    if (event === 'load') {
      return { state: null, reload: false, offline: false };
    }
    const prev = state || { status: 'retrying', firstFailAt: now, timer: null };
    if (prev.status === 'retrying' && (now - prev.firstFailAt) >= c.offlineThresholdMs) {
      return {
        state: { status: 'offline', firstFailAt: prev.firstFailAt, timer: null },
        reload: true,
        offline: true,
      };
    }
    return {
      state: { status: prev.status, firstFailAt: prev.firstFailAt, timer: null },
      reload: true,
      offline: false,
    };
  }

  function nextRetryIntervalMs(state, cfg) {
    const c = Object.assign({}, FAULT_DEFAULTS, cfg || {});
    if (state && state.status === 'offline') return c.offlineRetryIntervalMs;
    return c.retryIntervalMs;
  }

  return { FAULT_DEFAULTS, transitionFault, nextRetryIntervalMs };
});
```

- [ ] **Step 4: Rodar teste para confirmar sucesso**

Run: `node --test tests/test_camera_fault.js`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add src/static/camera_fault.js tests/test_camera_fault.js
git commit -m "feat(dashboard): add pure camera fault-state transition logic"
```

---

### Task 2: Handlers de retry/offline com timers no dashboard.js

**Files:**
- Modify: `src/static/dashboard.js` (topo: constantes + mapa; novos handlers)
- Modify: `src/templates/dashboard.html:414` (incluir `camera_fault.js`)

**Interfaces:**
- Consumes: `CameraFault.transitionFault`, `CameraFault.nextRetryIntervalMs`, `CameraFault.FAULT_DEFAULTS` (do Task 1).
- Produces: funções globais `onSnapshotError(cameraId, el)`, `onSnapshotLoad(cameraId, el)`, `scheduleSnapshotRetry(cameraId)`, `markSnapshotOffline(cameraId)`; variável `cameraFaultState`.

- [ ] **Step 1: Incluir o módulo no HTML antes de dashboard.js**

Em `src/templates/dashboard.html`, antes da linha `<script src="/static/dashboard.js"></script>`:
```html
<script src="/static/camera_fault.js"></script>
```

- [ ] **Step 2: Adicionar constantes e mapa no topo de dashboard.js**

Após as declarações de `let` iniciais (perto de `let showOfflineCameras = false;`):
```js
const SNAPSHOT_RETRY_INTERVAL_MS = CameraFault.FAULT_DEFAULTS.retryIntervalMs;
const SNAPSHOT_OFFLINE_RETRY_INTERVAL_MS = CameraFault.FAULT_DEFAULTS.offlineRetryIntervalMs;
const SNAPSHOT_OFFLINE_THRESHOLD_MS = CameraFault.FAULT_DEFAULTS.offlineThresholdMs;
// id -> { status:'retrying'|'offline', firstFailAt, timer }
const cameraFaultState = {};
```

- [ ] **Step 3: Implementar handlers e timer (colar após `retrySnapshot`)**

```js
function retrySnapshotNow(cameraId) {
  const img = document.getElementById(`snapshot-${cameraId}`);
  if (!img) return;
  const wrapper = img.parentElement;
  wrapper.classList.add('loading');
  wrapper.classList.remove('error');
  img.style.display = '';
  img.nextElementSibling.style.display = 'none';
  img.src = `/camera/${cameraId}/snapshot?ts=${Date.now()}`;
}

function onSnapshotError(cameraId, el) {
  const wrapper = el.parentElement;
  wrapper.classList.remove('loading');
  wrapper.classList.add('error');
  const img = el;
  img.style.display = 'none';
  img.nextElementSibling.style.display = 'flex';

  const prev = cameraFaultState[cameraId] || null;
  const { state, reload } = CameraFault.transitionFault(prev, 'error', Date.now());
  cameraFaultState[cameraId] = state;
  if (reload) retrySnapshotNow(cameraId);
  scheduleSnapshotRetry(cameraId);
  refreshSnapshotFallback(cameraId);
}

function onSnapshotLoad(cameraId, el) {
  const wrapper = el.parentElement;
  wrapper.classList.remove('loading');
  wrapper.classList.remove('error');
  const t = cameraFaultState[cameraId];
  if (t && t.timer) clearTimeout(t.timer);
  delete cameraFaultState[cameraId];
  refreshSnapshotFallback(cameraId);
}

function scheduleSnapshotRetry(cameraId) {
  const state = cameraFaultState[cameraId];
  if (!state || state.timer) return;
  const interval = CameraFault.nextRetryIntervalMs(state);
  state.timer = setTimeout(() => {
    state.timer = null;
    const res = CameraFault.transitionFault(state, 'error', Date.now());
    cameraFaultState[cameraId] = res.state;
    if (res.offline) refreshSnapshotFallback(cameraId);
    if (res.reload) retrySnapshotNow(cameraId);
    if (res.state && res.state.status === 'offline') {
      // já offline: segue sondando no intervalo lento (auto-recuperação)
      scheduleSnapshotRetry(cameraId);
    } else if (res.state) {
      scheduleSnapshotRetry(cameraId);
    }
  }, interval);
}

function markSnapshotOffline(cameraId) {
  const state = cameraFaultState[cameraId];
  if (!state) return;
  state.status = 'offline';
  refreshSnapshotFallback(cameraId);
  scheduleSnapshotRetry(cameraId);
}

function refreshSnapshotFallback(cameraId) {
  const img = document.getElementById(`snapshot-${cameraId}`);
  if (!img) return;
  const wrapper = img.parentElement;
  const fallback = wrapper.querySelector('.camera-preview-error');
  if (!fallback) return;
  const state = cameraFaultState[cameraId];
  const msg = fallback.querySelector('span');
  if (msg) {
    if (state && state.status === 'offline') {
      msg.textContent = 'Sem resposta (offline)';
    } else if (state && state.status === 'retrying') {
      msg.textContent = 'Tentando novamente…';
    } else {
      msg.textContent = 'Falha ao carregar preview';
    }
  }
}
```

- [ ] **Step 4: Verificar sintaxe**

Run: `node --check src/static/dashboard.js`
Expected: sem erro de sintaxe.

- [ ] **Step 5: Commit**

```bash
git add src/static/dashboard.js src/templates/dashboard.html
git commit -m "feat(dashboard): wire snapshot retry/offline handlers with timers"
```

---

### Task 3: Badge e integração no card e no render

**Files:**
- Modify: `src/static/dashboard.js` — `createCameraCard` (handler nos `<img>`, badge offline), `renderCameraTiles` (ler `cameraFaultState`).

**Interfaces:**
- Consumes: `cameraFaultState` (Task 2), `createCameraCard(camera, offline, lastEventTs)` e `renderCameraTiles(cameras, workerStatus, lastEventMap)` já existentes.
- Produces: card com `onSnapshotError`/`onSnapshotLoad` e badge "Offline" quando `cameraFaultState[id].status === 'offline'`.

- [ ] **Step 1: Trocar os handlers inline do `<img>` em createCameraCard**

Localizar em `createCameraCard` (por volta de `src/static/dashboard.js:106-117`) os atributos:
```js
onload="this.parentElement.classList.remove('loading'); this.parentElement.classList.remove('error');"
onerror="this.parentElement.classList.remove('loading'); this.parentElement.classList.add('error'); this.style.display='none'; this.nextElementSibling.style.display='flex';"
```
Substituir por:
```js
onload="onSnapshotLoad(${camera.id}, this)"
onerror="onSnapshotError(${camera.id}, this)"
```
E o texto do fallback (`:113` `<span>Falha ao carregar preview</span>`) já será atualizado por `refreshSnapshotFallback`.

- [ ] **Step 2: Aplicar badge offline a partir de cameraFaultState em createCameraCard**

No início de `createCameraCard`, antes de montar `offlineBadge`:
```js
const faultOffline = cameraFaultState[camera.id] && cameraFaultState[camera.id].status === 'offline';
const offline = arguments[1] || faultOffline;
```
e usar `offline` (em vez do parâmetro recebido) para `offlineBadge` e na classe `camera-card-offline`. Como `createCameraCard(camera, offline=false, lastEventTs=null)` já recebe `offline`, basta sobrescrever a variável local `offline` com `offline || faultOffline`.

- [ ] **Step 3: renderCameraTiles lê cameraFaultState para manter badge na grade**

Em `renderCameraTiles` (por volta de `src/static/dashboard.js:204-211`), após calcular `activeIds`/`onlineCameras`, garantir que câmeras com falha crônica sejam renderizadas na grade online com `offline=true` (badge). O split para a seção offline do backend (`offlineCameras`) permanece baseado em `workerStatus`. Nenhuma mudança no split é necessária além de passar o `faultOffline` via `createCameraCard` (já coberto no Step 2).

- [ ] **Step 4: Verificar sintaxe**

Run: `node --check src/static/dashboard.js`
Expected: sem erro de sintaxe.

- [ ] **Step 5: Commit**

```bash
git add src/static/dashboard.js
git commit -m "feat(dashboard): show offline badge from fault state and keep card in grid"
```

---

### Task 4: Verificação ponta a ponta (manual) + regressão de lógica

**Files:**
- Test: reuso de `tests/test_camera_fault.js`.

- [ ] **Step 1: Rodar testes de lógica pura**

Run: `node --test tests/test_camera_fault.js`
Expected: PASS.

- [ ] **Step 2: Verificação manual no dashboard**

1. Iniciar a aplicação (ex.: `python run.py` ou docker-compose).
2. Na Visão geral, derrubar/desconectar a fonte de **uma** câmera (ex.: parar o stream daquela câmera).
3. Observar: o card dessa câmera mostra "Tentando novamente…" e o botão "Tentar novamente" continua clicável.
4. Aguardar ~5 min sem resposta: o card passa a mostrar badge "Offline" e "Sem resposta (offline)".
5. Restabelecer a fonte da câmera: dentro de no máximo ~30 s o preview carrega sozinho e o card volta ao normal (sem badge).
6. Confirmar que o poll de 5 s não zera o estado nem cria timers duplicados (sem rajada de requisições `/snapshot`).
7. Confirmar que câmeras saudáveis (worker `healthy`) com preview ok não são afetadas.

- [ ] **Step 3: Commit (se houver ajuste de CSS necessário)**

Se for preciso estilo extra para o badge/texto, editar `src/static/style.css` (reuso de `.badge-offline` / `.camera-card-offline` já existentes) e:
```bash
git add src/static/style.css
git commit -m "style(dashboard): ensure offline badge readable on retrying/offline states"
```
Caso contrário, pular este commit.

---

## Self-Review Notes (autor)

- Cobertura do spec: Task 1 cobre transição retrying→offline e recuperação (auto-retry + auto-recuperação). Task 2 cobre timers e badge via estado. Task 3 cobre badge no card e sobrevivência ao re-render. Task 4 cobre verificação e regressão.
- Sem placeholders: cada step tem comando/código concreto.
- Consistência de tipos: `transitionFault`/`nextRetryIntervalMs`/`FAULT_DEFAULTS` definidos no Task 1 e consumidos nos Tasks 2–3 com mesmos nomes.
