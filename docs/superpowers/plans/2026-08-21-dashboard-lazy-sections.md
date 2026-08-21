# Dashboard: Lazy-load de seções no `#main-page` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refatorar o dashboard de SPA monolítico para SPA com lazy-load: só "Visão geral" carrega no boot; as demais seções são buscadas/injetadas sob demanda no `#main-page`, com utilidades comuns em `shared.js` e cada seção em seu próprio módulo JS.

**Architecture:** `dashboard.html` vira um shell (sidebar + `#main-page` + footer). Um núcleo (`core.js`) faz lazy-load: ao clicar na sidebar, busca o fragmento HTML da seção (`GET /section/<nome>`), injeta em `#main-page` e carrega o módulo `sections/<nome>.js` via `dynamic import()` (uma vez), chamando `initSection()`/`teardownSection()`. Utilidades compartilhadas vivem em `shared.js` (fonte única de verdade). Seções auxiliares usam dialog para criar/editar.

**Tech Stack:** Flask + Jinja2 (partials), JavaScript vanilla com ES modules (`<script type="module">`), CSS existente (`style.css` / style guide). Sem novas dependências.

## Global Constraints

- **Boot:** somente "Visão geral" é carregada no boot; todo o resto (Eventos, Câmeras, Zonas, Identidades, Usuários, Permissões, Auditoria, Notificações, Configurações, Retenção) é **lazy**.
- **Mecanismo de JS:** `dynamic import()` de ES modules (`src/static/sections/<nome>.js`), executado uma única vez por seção.
- **`shared.js`:** utilidades comuns (fetch, formatação, dialog genérico, constantes) ficam em `shared.js` — NUNCA duplicadas nos módulos de seção.
- **Dialog:** seções auxiliares usam dialog (`.dialog-overlay` → `.dialog-card` → `.dialog-header` + `<form>` com `.form-row`, `.form-actions` `button-primary`/`button-secondary`, `.form-message`) para criar/editar — padrão de `users.html`.
- **Style guide:** usar SÓ CSS variables/classes do projeto (`var(--primary)`, `var(--muted)`, `var(--radius)`, `button-primary`, etc.); NUNCA cor hardcoded nem raio/borda fixos.
- **Branch:** mudanças entram via PR em `dev`; não commitar em `main`. Commits frequentes por task.
- **Backend:** sem mudança de storage/API; apenas adicionar rota de partial e remover rotas GET que hoje retornam JSON mas passam a ser parciais (se aplicável).

---

## File Structure

- `src/static/shared.js` — **criar**. Utilidades comuns (fetch, cache, formatação, dialog genérico, constantes). Carregado uma vez.
- `src/static/core.js` — **criar**. Núcleo: checagem de sessão, `loadSection()`, navegação da sidebar, cache de seções, polling/teardown.
- `src/templates/dashboard.html` — **modificar** (virar shell mínimo: sidebar + `#main-page` + footer; remover todas as seções hardcoded).
- `src/app.py` — **modificar** (adicionar `GET /section/<nome>` que renderiza `templates/sections/<nome>.html`).
- `src/templates/sections/<nome>.html` — **criar** (11 partials: overview, events, cameras, zones, identities, users, permissions, audit, notifications, settings, retention). Cada contém só o markup da seção (panel + dialogs).
- `src/static/sections/<nome>.js` — **criar** (11 módulos; cada um exporta `initSection()` e opcional `teardownSection()`).
- `src/static/dashboard.js` — **remover** ao final (absorvido por core + sections + shared).
- `src/templates/users.html`, `permissions.html`, `audit.html`, `identities.html` — **remover** se absorvidos como partials (decisão da Task 16).

---

### Task 1: `shared.js` — utilidades comuns

**Files:**
- Create: `src/static/shared.js`

**Interfaces:**
- Produces: `fetchData`, `fetchCached`, `invalidateCache`, `formatUptime`, `timeAgo`, `escapeHtml`, `openDialog`, `closeDialog`, `CameraFault` (exportados via `export`).

- [ ] **Step 1: Criar `src/static/shared.js` com o conteúdo abaixo**

```js
// shared.js — utilidades comuns a todas as seções (fonte única de verdade)
export const CameraFault = {
  FAULT_DEFAULTS: {
    retryIntervalMs: 5000,
    offlineRetryIntervalMs: 15000,
    offlineThresholdMs: 30000,
  },
};

export async function fetchData(url) {
  const response = await fetch(url);
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Não autenticado');
  }
  return response.json();
}

const _apiCache = new Map(); // url -> { ts, promise }
export async function fetchCached(url, ttlMs = 60000) {
  const cached = _apiCache.get(url);
  if (cached && (Date.now() - cached.ts) < ttlMs) return cached.promise;
  const promise = fetchData(url);
  _apiCache.set(url, { ts: Date.now(), promise });
  promise.catch(() => { const c = _apiCache.get(url); if (c && c.promise === promise) _apiCache.delete(url); });
  return promise;
}

export function invalidateCache(url) {
  if (url) _apiCache.delete(url);
  else _apiCache.clear();
}

export function formatUptime(ms) {
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function timeAgo(ts) {
  if (!ts) return '';
  const ms = Date.now() - new Date(ts).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return 'agora';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function openDialog(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden-panel');
}
export function closeDialog(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden-panel');
}
```

- [ ] **Step 2: Verificar sintaxe**

Run: `node --check src/static/shared.js`
Expected: sem erro de sintaxe.

- [ ] **Step 3: Commit**

```bash
git add src/static/shared.js
git commit -m "feat(dashboard): add shared.js with common utilities"
```

---

### Task 2: `core.js` — núcleo de lazy-load

**Files:**
- Create: `src/static/core.js`
- Depends on: `src/static/shared.js` (Task 1)

**Interfaces:**
- Consumes: `shared.js` (não diretamente; core usa `fetchData` de shared se necessário).
- Produces: `loadSection(name)`, `teardownCurrentSection()`, `setupSidebarNavigation()`, `bootDashboard()`.

- [ ] **Step 1: Criar `src/static/core.js`**

```js
// core.js — núcleo do dashboard (shell, lazy-load, navegação)
const SECTION_MODULES = {
  overview: () => import('./sections/overview.js'),
  events: () => import('./sections/events.js'),
  cameras: () => import('./sections/cameras.js'),
  zones: () => import('./sections/zones.js'),
  identities: () => import('./sections/identities.js'),
  users: () => import('./sections/users.js'),
  permissions: () => import('./sections/permissions.js'),
  audit: () => import('./sections/audit.js'),
  notifications: () => import('./sections/notifications.js'),
  settings: () => import('./sections/settings.js'),
  retention: () => import('./sections/retention.js'),
};

const _loadedSections = new Set();
let _currentSection = null;
let _currentTeardown = null;

async function loadSection(name) {
  if (!SECTION_MODULES[name]) { console.warn('Seção desconhecida:', name); return; }
  // teardown da seção anterior
  if (_currentTeardown) { try { _currentTeardown(); } catch (e) { console.error(e); } _currentTeardown = null; }
  const main = document.getElementById('main-page');
  const resp = await fetch(`/section/${name}`);
  if (resp.status === 401) { window.location.href = '/login'; return; }
  main.innerHTML = await resp.text();
  // marca nav ativo
  document.querySelectorAll('.nav-link[data-section], .nav-sublink[data-section]').forEach(l => {
    l.classList.toggle('active', l.dataset.section === name);
  });
  if (!_loadedSections.has(name)) {
    await SECTION_MODULES[name]();
    _loadedSections.add(name);
  }
  const mod = await SECTION_MODULES[name]();
  if (typeof mod.initSection === 'function') mod.initSection();
  if (typeof mod.teardownSection === 'function') _currentTeardown = mod.teardownSection;
  _currentSection = name;
}

function setupSidebarNavigation() {
  document.querySelectorAll('.nav-link[data-section], .nav-sublink[data-section]').forEach(link => {
    link.addEventListener('click', () => loadSection(link.dataset.section));
  });
}

async function bootDashboard() {
  const meResp = await fetch('/api/auth/me');
  if (meResp.status === 401) { window.location.href = '/login'; return; }
  const me = await meResp.json();
  const ub = document.getElementById('user-bar');
  if (ub) {
    ub.style.display = 'flex';
    const nm = document.getElementById('user-bar-name');
    if (nm) nm.textContent = me.user?.username || '';
  }
  setupSidebarNavigation();
  await loadSection('overview'); // única seção no boot
}

window.addEventListener('DOMContentLoaded', bootDashboard);
export { loadSection, setupSidebarNavigation, bootDashboard };
```

- [ ] **Step 2: Verificar sintaxe**

Run: `node --check src/static/core.js`
Expected: sem erro.

- [ ] **Step 3: Commit**

```bash
git add src/static/core.js
git commit -m "feat(dashboard): add core.js lazy-loader and navigation"
```

---

### Task 3: `dashboard.html` — shell mínimo

**Files:**
- Modify: `src/templates/dashboard.html` (substituir todo o conteúdo do `<body>` pelo shell; manter `<head>` com `style.css`)

**Interfaces:**
- Consumes: `core.js`, `shared.js` (Task 1, 2).
- Produces: markup estável com `#main-page` e botões `data-section`.

- [ ] **Step 1: Reescrever `dashboard.html` como shell**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SecurityAI</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <aside class="sidebar">
        <div class="logo">
            <h1>SecurityAI</h1>
            <span>Monitoramento</span>
        </div>
        <nav>
            <button type="button" class="nav-link active" data-section="overview" id="nav-overview">
                <span class="icon">&#x1F4F7;</span><span>Visão geral</span>
            </button>
            <button type="button" class="nav-link" data-section="events" id="nav-events">
                <span class="icon">&#x1F4CB;</span><span>Eventos</span>
            </button>
            <button type="button" class="nav-link" data-section="cameras" id="nav-cameras">
                <span class="icon">&#x1F3A5;</span><span>Câmeras</span>
            </button>
            <div class="nav-divider"></div>
            <div class="nav-group collapsed">
                <button type="button" class="nav-group-head" onclick="document.getElementById('crud-nav-list').parentElement.classList.toggle('collapsed')">
                    <span class="icon">&#x2699;</span><span>Manutenção</span><span class="chev">&#9662;</span>
                </button>
                <div class="nav-group-list" id="crud-nav-list">
                    <button type="button" class="nav-sublink" data-section="zones"><span class="dot" style="background:var(--info)"></span><span>Zonas</span></button>
                    <button type="button" class="nav-sublink" data-section="identities"><span class="dot" style="background:var(--info)"></span><span>Identidades</span></button>
                    <button type="button" class="nav-sublink" data-section="users"><span class="dot" style="background:var(--warn)"></span><span>Usuários</span></button>
                    <button type="button" class="nav-sublink" data-section="permissions"><span class="dot" style="background:var(--danger)"></span><span>Permissões</span></button>
                    <button type="button" class="nav-sublink" data-section="audit"><span class="dot" style="background:var(--muted)"></span><span>Auditoria</span></button>
                    <button type="button" class="nav-sublink" data-section="notifications"><span class="dot" style="background:var(--primary)"></span><span>Notificações</span></button>
                    <button type="button" class="nav-sublink" data-section="settings"><span class="dot" style="background:var(--muted-subtle)"></span><span>Configurações</span></button>
                    <button type="button" class="nav-sublink" data-section="retention"><span class="dot" style="background:var(--warn)"></span><span>Retenção</span></button>
                </div>
            </div>
        </nav>
        <div class="footer-nav">
            <a href="#" id="nav-system-status">v0.2.0</a>
            <div id="user-bar" class="user-bar" style="display:none;">
                <span id="user-bar-name"></span>
                <button type="button" id="logout-btn" class="btn-sm" title="Sair">&#x274C;</button>
            </div>
        </div>
    </aside>

    <div class="main">
        <div id="main-page"><!-- seção lazy-load injetada aqui --></div>
    </div>

    <script type="module" src="/static/shared.js"></script>
    <script type="module" src="/static/core.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/templates/dashboard.html
git commit -m "refactor(dashboard): minimal shell with #main-page"
```

---

### Task 4: Rota de partials em `app.py`

**Files:**
- Modify: `src/app.py` (adicionar rota perto das outras rotas de página, ex. após `@app.route("/")`)
- Depends on: Task 3 (partials em `templates/sections/`)

**Interfaces:**
- Produces: `GET /section/<nome>` → fragmento HTML.

- [ ] **Step 1: Adicionar a rota**

```python
    @app.route("/section/<name>")
    def section_partial(name):
        allowed = {
            "overview", "events", "cameras", "zones", "identities",
            "users", "permissions", "audit", "notifications", "settings", "retention",
        }
        if name not in allowed:
            abort(404)
        return render_template(f"sections/{name}.html")
```

- [ ] **Step 2: Commit**

```bash
git add src/app.py
git commit -m "feat(dashboard): add /section/<name> partial route"
```

---

### Task 5: Seção "overview" (prova de conceito, carregada no boot)

**Files:**
- Create: `src/templates/sections/overview.html`
- Create: `src/static/sections/overview.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js` (`fetchData`, `fetchCached`, `formatUptime`, `CameraFault`, `escapeHtml`, `openDialog`, `closeDialog`).
- Produces: `initSection()` (renderiza tiles de câmeras + summary + offline), `teardownSection()` (para polling).

- [ ] **Step 1: Criar `src/templates/sections/overview.html`** (extrair o `<section id="overview">` de `dashboard.html` original — linhas ~86–110: summary-cards, camera-tiles, camera-offline-bar, camera-offline-section, camera-empty-state, e os dialogs de live player / thumb / clip que a overview usa)

```html
<section class="panel" id="overview">
    <div id="summary-cards" class="grid"></div>
    <div id="camera-tiles" class="grid"></div>
    <div id="camera-offline-bar" class="hidden-panel">
        <span id="camera-offline-toggle-label" class="section-title">Ver offline</span>
        <label class="switch" title="Mostrar câmeras offline">
            <input type="checkbox" id="show-offline-cameras" />
            <span class="slider"></span>
        </label>
    </div>
    <div id="camera-offline-section" class="hidden-panel">
        <div id="camera-offline-list" class="grid"></div>
    </div>
    <div id="camera-empty-state" class="empty-state hidden-panel">
        <p>Nenhuma câmera configurada.</p>
    </div>
</section>
<!-- manter aqui os dialogs usados pela overview: live-player-overlay, thumb-history-overlay, clip-history-overlay, thumb-detail-overlay (copiados do dashboard.html original) -->
```

- [ ] **Step 2: Criar `src/static/sections/overview.js`** movendo para `initSection()` as funções de `dashboard.js` origem:
  - Estado: `cameraFaultState`, `snapshotTimes`, `localThumbnails`, `showOfflineCameras`, constantes `SNAPSHOT_*`, `SNAPSHOT_MAX_AGE_MS`.
  - Funções: `createSummaryCard`, `createCameraCard`, `retrySnapshot`, `retrySnapshotNow`, `onSnapshotError`, `ageLabelFromMs`, `ageLabel`, `refreshSnapshotAges`, `fetchSnapshotTime`, `fetchSnapshotWithHeader`, `onSnapshotLoad`, `scheduleSnapshotRetry`, `markSnapshotOffline`, `refreshSnapshotFallback`, `snapshotObserver`+`observeSnapshots`, `refreshSnapshot`, `updateVisibleSnapshots`, `setupHoverFreshSnapshots`, `buildLastEventMap`, `countEventsByCamera`, `sortCamerasByLastEvent`, `renderCameraTiles`, `updateCameraCard`, `updateOfflineSection`, `setupOfflineToggle`, `statusBadgeClass`, `statusBadgeLabel`, `renderSystemStatus`, `setupSystemStatusLink`, `openLivePlayer`/`closeLivePlayer`, `openThumbHistory`/`closeThumbHistory`, `openThumbDetail`/`closeThumbDetail`, `openClipHistory`/`closeClipHistory`, zoom helpers.
  - `initSection()`: dispara o poll inicial (buscar `/api/dashboard` ou `/api/system-status` + câmeras) e renderiza; armazena o timer em `let _timer` e o retorna/para em `teardownSection()`.
  - `teardownSection()`: `clearInterval(_timer)` e remove listeners de snapshot.

  Estrutura do módulo:
```js
import { fetchData, fetchCached, formatUptime, CameraFault, escapeHtml, openDialog, closeDialog } from '../shared.js';

let _timer = null;
// ... (funções movidas verbatim de dashboard.js, ajustando referências de DOM para dentro de #main-page)

export function initSection() {
  // render inicial + polling
  _timer = setInterval(pollOverview, 5000);
  pollOverview();
}
export function teardownSection() {
  if (_timer) clearInterval(_timer);
  _timer = null;
}
```

- [ ] **Step 3: Verificar no browser** — subir o servidor, abrir `/`, confirmar que a Visão geral carrega (tiles de câmeras + summary) e o polling funciona.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/overview.html src/static/sections/overview.js
git commit -m "feat(dashboard): extract overview section (lazy POC)"
```

---

### Task 6: Seção "events"

**Files:**
- Create: `src/templates/sections/events.html`
- Create: `src/static/sections/events.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js` (`fetchData`, `fetchCached`, `timeAgo`, `escapeHtml`, `openDialog`, `closeDialog`).
- Produces: `initSection()` (render de cards de eventos + filtros), `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/events.html`** extraindo o `<section id="recent-events">` de `dashboard.html` original (linhas ~303–344: chips-bar de filtros + container de cards) e os dialogs `thumb-history-overlay`/`thumb-detail-overlay`/`clip-history-overlay` se usados por eventos.

- [ ] **Step 2: Criar `src/static/sections/events.js`** movendo de `dashboard.js`:
  - Funções: `timeAgo`, `thumbCache`/`THUMB_CACHE_TTL_MS`, `_pickThumb`, `getCameraThumb`, `createEventCard`, `EVENT_FILTERS_KEY`, `readFilterState`, `saveFilterState`, `syncUrl`, `applyEventFilters`, `populateFilterOptions`, `renderEventCards`, `renderEvents`, `setupEventFilters`, `openEventThumbDialog` (e zoom/detail helpers já em overview se compartilhados — mover para `shared.js` se usado por mais de uma seção).
  - `initSection()`/`teardownSection()` com polling de `/api/events`.

- [ ] **Step 3: Verificar no browser** — clicar "Eventos" na sidebar; confirmar cards + filtros.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/events.html src/static/sections/events.js
git commit -m "feat(dashboard): extract events section (lazy)"
```

---

### Task 7: Seção "cameras"

**Files:**
- Create: `src/templates/sections/cameras.html`
- Create: `src/static/sections/cameras.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()` (lista de câmeras + dialog de câmera), `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/cameras.html`** extraindo `<section id="camera-management">` (linhas ~156–182: tabela `camera-table-body`) e o `#camera-dialog` (linhas ~183–238) do `dashboard.html` original.

- [ ] **Step 2: Criar `src/static/sections/cameras.js`** movendo de `dashboard.js`:
  - Funções: `createCameraRow`, `resetCameraList`, `setCameraFormMode`, `showCameraForm`, `hideCameraForm`, `submitCameraForm`, `deleteCamera`, `populateZoneDropdown`, `populateAlertClasses`, `_buildClassCheckbox`, `ALERT_CLASS_GROUPS`, `showMenuMessage`, preview helpers (`resetCameraPreview`, `parsePolygonField`, `drawPlaceholderGrid`, `strokeWithOutline`, `drawExclusionPolygon`, `drawMaskPolygon`, `drawCameraPreview`, `schedulePreviewRedraw`, `loadPreviewFrame`, `previewFrame`/`previewLoadToken`/`previewDebounceTimer`/`previewNote`).
  - `initSection()` renderiza a tabela e liga o botão "Adicionar câmera" (abre `#camera-dialog` via `openDialog`).

- [ ] **Step 3: Verificar no browser** — Câmeras: listar, abrir dialog de criar/editar, salvar.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/cameras.html src/static/sections/cameras.js
git commit -m "feat(dashboard): extract cameras section (lazy)"
```

---

### Task 8: Seção "zones"

**Files:**
- Create: `src/templates/sections/zones.html`
- Create: `src/static/sections/zones.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/zones.html`` extraindo `<section id="zones-management">` (linhas ~240–262) e `#zone-dialog` (linhas ~263–302).

- [ ] **Step 2: Criar `src/static/sections/zones.js`` movendo de `dashboard.js`: `createZoneRow`, `setZoneFormMode`, `showZoneForm`, `hideZoneForm`, `submitZoneForm`, `deleteZone`, e o populate de `zone-classification`/`zone-schedule`/`zone-direction-line`.

- [ ] **Step 3: Verificar no browser** — Zonas: listar, criar/editar via dialog.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/zones.html src/static/sections/zones.js
git commit -m "feat(dashboard): extract zones section (lazy)"
```

---

### Task 9: Seção "identities"

**Files:**
- Create: `src/templates/sections/identities.html`
- Create: `src/static/sections/identities.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/identities.html` extraindo `<section id="identities-management">` (linhas ~392–410) e `#identity-dialog` (linhas ~110–153 do dashboard.html original).

- [ ] **Step 2: Criar `src/static/sections/identities.js` movendo as funções de identidade de `dashboard.js` (form de identidade, capture, submit, delete, lista).

- [ ] **Step 3: Verificar no browser** — Identidades: listar, criar/editar via dialog.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/identities.html src/static/sections/identities.js
git commit -m "feat(dashboard): extract identities section (lazy)"
```

---

### Task 10: Seção "users"

**Files:**
- Create: `src/templates/sections/users.html` (reaproveitar `src/templates/users.html` existente como partial, removendo `<head>`/`<body>`/sidebar — deixar só o panel + `#user-dialog`)
- Create: `src/static/sections/users.js` (reaproveitar o `<script>` de `users.html` atual, envolvendo em `initSection()`)
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js` (`fetchData`, `openDialog`, `closeDialog`).
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/users.html` a partir de `src/templates/users.html` existente: manter o `.panel` (Gestão de Usuários + tabela) e o `#user-dialog`; remover `<!DOCTYPE>`/`<head>`/`<body>`/sidebar e o `#cam-dialog` (ou mantê-lo aqui se for usado só por usuários).

- [ ] **Step 2: Criar `src/static/sections/users.js` movendo o `<script>` de `users.html` para um módulo que exporta `initSection()` (chamando o `init()` original) e `teardownSection()`. Usar `openDialog`/`closeDialog` de `shared.js` em vez das funções locais.

- [ ] **Step 3: Verificar no browser** — Usuários: listar, Criar/Editar via dialog (padrão já alinhado), ativar/inativar, Câmeras.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/users.html src/static/sections/users.js
git commit -m "feat(dashboard): extract users section (lazy, reuse dialog pattern)"
```

---

### Task 11: Seção "permissions"

**Files:**
- Create: `src/templates/sections/permissions.html` (de `permissions.html` existente)
- Create: `src/static/sections/permissions.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/permissions.html` a partir de `permissions.html` existente (só o panel + dialogs).

- [ ] **Step 2: Criar `src/static/sections/permissions.js` movendo o script de `permissions.html` para módulo com `initSection()`/`teardownSection()`.

- [ ] **Step 3: Verificar no browser** — Permissões: listar roles, editar via dialog.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/permissions.html src/static/sections/permissions.js
git commit -m "feat(dashboard): extract permissions section (lazy)"
```

---

### Task 12: Seção "audit"

**Files:**
- Create: `src/templates/sections/audit.html` (de `audit.html` existente)
- Create: `src/static/sections/audit.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/audit.html` a partir de `audit.html` existente (só o panel).

- [ ] **Step 2: Criar `src/static/sections/audit.js` movendo o script de `audit.html`.

- [ ] **Step 3: Verificar no browser** — Auditoria: listar log.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/audit.html src/static/sections/audit.js
git commit -m "feat(dashboard): extract audit section (lazy)"
```

---

### Task 13: Seção "notifications"

**Files:**
- Create: `src/templates/sections/notifications.html`
- Create: `src/static/sections/notifications.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/notifications.html` extraindo `<section id="notifications">` de `dashboard.html` original (linhas ~345–365).

- [ ] **Step 2: Criar `src/static/sections/notifications.js` movendo as funções de notificações/routing de `dashboard.js` (render de canais/eventos, toggle de routing via `/api/notifications/routing`).

- [ ] **Step 3: Verificar no browser** — Notificações: listar canais, alternar routing.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/notifications.html src/static/sections/notifications.js
git commit -m "feat(dashboard): extract notifications section (lazy)"
```

---

### Task 14: Seção "settings"

**Files:**
- Create: `src/templates/sections/settings.html`
- Create: `src/static/sections/settings.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/settings.html` extraindo `<section id="settings">` de `dashboard.html` original (linhas ~366–391).

- [ ] **Step 2: Criar `src/static/sections/settings.js` movendo de `dashboard.js`: `renderSettings`, `appendConfigValue`, `renderSettingsConfig`, `setupSettings` (e o toggle de privacy mode via `/api/settings`).

- [ ] **Step 3: Verificar no browser** — Configurações: exibir/seção de config, alternar privacy mode.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/settings.html src/static/sections/settings.js
git commit -m "feat(dashboard): extract settings section (lazy)"
```

---

### Task 15: Seção "retention"

**Files:**
- Create: `src/templates/sections/retention.html`
- Create: `src/static/sections/retention.js`
- Depends on: Tasks 1–4

**Interfaces:**
- Consumes: `shared.js`.
- Produces: `initSection()`, `teardownSection()`.

- [ ] **Step 1: Criar `src/templates/sections/retention.html` extraindo `<section id="event-retention">` de `dashboard.html` original (linhas ~410–436).

- [ ] **Step 2: Criar `src/static/sections/retention.js` movendo as funções de retenção de `dashboard.js` (form de política de prune, submit via `/api/events/prune`).

- [ ] **Step 3: Verificar no browser** — Retenção: exibir/editar política.

- [ ] **Step 4: Commit**

```bash
git add src/templates/sections/retention.html src/static/sections/retention.js
git commit -m "feat(dashboard): extract retention section (lazy)"
```

---

### Task 16: Limpeza e verificação final

**Files:**
- Delete: `src/static/dashboard.js`
- Delete/ajuste: `src/templates/users.html`, `permissions.html`, `audit.html`, `identities.html` (se já absorvidos como partials em Task 10–12, removê-los; caso contrário, ajustar rotas para apontar para `/section/<nome>`)

**Interfaces:**
- Consumes: todas as tasks anteriores.

- [ ] **Step 1: Remover `src/static/dashboard.js`** (todo o código agora está em shared/core/sections).

- [ ] **Step 2: Decidir destino dos templates órfãos** — como Users/Permissions/Audit/Identities viraram partials em Task 10–12, remover `src/templates/users.html`, `permissions.html`, `audit.html`, `identities.html` e ajustar eventuais rotas que os renderizam (`/users`, `/permissions`, `/audit`, `/identities/view`) para redirecionar a `/section/<nome>` ou renderizar o partial.

- [ ] **Step 3: Verificação manual completa no browser** (login → cada seção via sidebar → criar/editar via dialog → permissões por role admin/chefe_seguranca/vigilante/viewer → polling da overview). Confirmar que nenhuma função comum foi duplicada (está em `shared.js`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(dashboard): remove monolith, finalize lazy sections"
```

---

## Self-Review (checklist)

1. **Spec coverage:** boot=só overview (Task 5 no boot via core.js); resto lazy (Tasks 6–15); shared.js (Task 1); dialog nos auxiliares (Tasks 7–15 usam dialog padrão); sem mudança de backend além da rota de partial (Task 4). ✅
2. **Placeholder scan:** tarefas de extração referenciam funções por nome/linha de `dashboard.js` (extração verbatim) — não são placeholders. ✅
3. **Type consistency:** `initSection()`/`teardownSection()` definidos em todos os módulos e consumidos por `core.js` (Task 2). `shared.js` exporta os nomes importados nas seções. ✅
