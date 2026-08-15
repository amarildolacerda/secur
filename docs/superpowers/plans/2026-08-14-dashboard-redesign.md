# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesenhar o dashboard do secur (front-end puro): Visão geral com grade de câmeras em destaque (lazy-load + agrupamento offline) e aba Eventos com cards + filtros persistentes (URL/localStorage), inspirado no dashboard do frigate.

**Architecture:** Mudanças APENAS em `secur/templates/dashboard.html`, `secur/static/dashboard.js` e `secur/static/style.css`. Zero mudanças em Python. A Visão geral ganha a grade de câmeras (com IntersectionObserver para lazy-load de snapshots e seção "Offline" baseada em `/status` → `worker_status`); a aba Eventos vira grid de cards com thumbnail (casado via `/camera/<id>/thumbnails`, cache em memória), chips de filtro (câmera/zona/tipo/período/só-alertas) aplicados client-side sobre os 100 eventos carregados, estado persistido em localStorage + URL (`?camera=&zone=&type=&since=&alerts=`).

**Tech Stack:** Flask + Jinja2 (server-rendered, intocado), JS vanilla, CSS com variáveis existentes (`--primary`, `--danger`, `--radius`, etc.), IntersectionObserver.

## Global Constraints

- Branch `dev`; commits em inglês (`feat:`); UI pt-BR.
- Abordagem A aprovada: front-end puro — NENHUMA mudança em Python (app.py, main.py, storage.py, config.py, tests/).
- Fontes de dados existentes (não mudar): `GET /events` → `[{id, timestamp, camera_id, zone, event_type, details, clip_path}]` (limit 100); `GET /status` → `{status, camera_count, recent_events, cameras, worker_status?, active_workers?}` onde `worker_status` = `[{camera_id, name, zone, source, running}]`; `GET /camera/<id>/thumbnails` → `[{id, timestamp, event_type, url}]` (limit 20, mais recentes primeiro); `GET /api/notifications` → `{channels, events: [{key, label, category: "alerta"|"info", legacy}], routing}`.
- Reusar as classes CSS existentes (`.grid`, `.card`, `.panel`, `.badge-alert`, `.badge-info`, `.button-*`, `.hidden-panel`); novos componentes seguem as variáveis do `:root`.
- O polling de 5s existente (`setInterval(renderDashboard, 5000)`) é mantido, mas atualização de snapshots fica condicionada à visibilidade (`in-viewport`).
- Se `worker_status` ausente em `/status` → sem agrupamento offline (grade única) — fallback definido.
- Verificação por task: `node --check secur/static/dashboard.js` + `/tmp/secur-venv/bin/python -m pytest tests/ -q` (regressão: 191 passed, 2 skipped) — padrão do ciclo F3.

---

### Task 1: Visão geral — grade de câmeras com lazy-load e agrupamento offline

**Files:**
- Modify: `secur/templates/dashboard.html:69-72` (section overview), `:24-27` (remover nav-link Câmeras), `:250-253` (remover section camera-status)
- Modify: `secur/static/dashboard.js:63-94` (createCameraCard), `:1024-1037` (bloco camera-list no renderDashboard), `:1157-1160` (setup/polling)
- Modify: `secur/static/style.css` (classes novas ao final)

**Interfaces:**
- Consumes: `GET /status` → `{cameras: [...], worker_status?: [{camera_id, running}]}`
- Produces: `createCameraCard(camera, offline=false)` (card com `data-camera-id`, sem src inicial), `renderCameraTiles(cameras, workerStatus)`, `observeSnapshots()`, `updateVisibleSnapshots(cameras)` — usados pela Task 2 para reusar o mesmo tile na aba Eventos? Não — usados pelo próprio polling.

- [ ] **Step 1: Substituir a section `overview` no HTML**

Em `secur/templates/dashboard.html:69-72`, substituir:

```html
            <section class="panel" id="overview">
                <h2>Visão geral</h2>
                <div id="summary-cards" class="grid"></div>
            </section>
```

por:

```html
            <section class="panel" id="overview">
                <h2>Visão geral</h2>
                <div id="summary-cards" class="grid"></div>
                <div id="camera-tiles" class="grid"></div>
                <div id="camera-offline-section" class="hidden-panel">
                    <h3 class="section-title">Câmeras offline</h3>
                    <div id="camera-offline-list" class="grid"></div>
                </div>
                <div id="camera-empty-state" class="empty-state hidden-panel">
                    <div class="empty-icon">&#x1F4F7;</div>
                    <h3>Nenhuma câmera cadastrada</h3>
                    <p>Adicione uma câmera para começar a monitorar.</p>
                    <button type="button" class="button-primary" id="empty-add-camera">Adicionar câmera</button>
                </div>
            </section>
```

- [ ] **Step 2: Remover a seção `camera-status` e o nav-link Câmeras**

Em `secur/templates/dashboard.html:24-27`, remover o botão de nav:

```html
            <button type="button" class="nav-link" data-section="camera-status" id="nav-camera-status">
                <span class="icon">&#x1F50D;</span>
                <span>Câmeras</span>
            </button>
```

Em `secur/templates/dashboard.html:250-253`, remover a section inteira:

```html
            <section class="panel hidden-panel" id="camera-status">
                <h2>Status das câmeras</h2>
                <div id="camera-list" class="grid"></div>
            </section>
```

(A grade de câmeras agora mora na Visão geral — a aba "Câmeras" era redundante.)

- [ ] **Step 3: Reescrever `createCameraCard` no JS**

Em `secur/static/dashboard.js:63-94`, substituir a função inteira por:

```javascript
function createCameraCard(camera, offline = false) {
  const zoneLabel = camera.zone || '-';
  const imgId = `snapshot-${camera.id}`;
  const offlineBadge = offline
    ? '<span class="badge-offline">Offline</span>'
    : '';

  return `
    <div class="card camera-card${offline ? ' camera-card-offline' : ''}">
      <div class="camera-card-header">
        <strong>${camera.name}</strong>
        <span class="camera-badge">ID ${camera.id}</span>
      </div>
      <p>Zona: ${zoneLabel} ${offlineBadge}</p>
      <p class="camera-source">Fonte: ${camera.source}</p>
      <div
        class="camera-preview-wrapper"
        data-camera-id="${camera.id}"
        onclick="openThumbHistory(${camera.id}, '${camera.name}')"
        style="cursor:pointer;"
      >
        <img
          id="${imgId}"
          class="camera-preview"
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
    </div>
  `;
}
```

Notas: o `<img>` NÃO tem `src` inicial (lazy-load — o src é setado quando o tile entra no viewport). O `data-camera-id` no wrapper alimenta o observer.

- [ ] **Step 4: Adicionar observer, render de tiles e atualização visível**

Em `secur/static/dashboard.js`, adicionar após `function retrySnapshot(...)` (linha ~106):

```javascript
/* ========== Camera tiles (lazy-load) ========== */

const snapshotObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    const wrapper = entry.target;
    const img = wrapper.querySelector('.camera-preview');
    if (entry.isIntersecting) {
      wrapper.classList.add('in-viewport');
      if (img && !img.dataset.loaded) {
        img.dataset.loaded = '1';
        img.src = `/camera/${wrapper.dataset.cameraId}/snapshot?ts=${Date.now()}`;
      }
    } else {
      wrapper.classList.remove('in-viewport');
    }
  });
}, { rootMargin: '100px' });

function observeSnapshots() {
  document.querySelectorAll('.camera-preview-wrapper').forEach(wrapper => {
    snapshotObserver.observe(wrapper);
  });
}

function updateVisibleSnapshots(cameras) {
  cameras.forEach(camera => {
    const img = document.getElementById(`snapshot-${camera.id}`);
    if (img && img.dataset.loaded && img.parentElement.classList.contains('in-viewport') && !img.parentElement.classList.contains('error')) {
      img.src = `/camera/${camera.id}/snapshot?ts=${Date.now()}`;
    }
  });
}

function renderCameraTiles(cameras, workerStatus) {
  const tilesContainer = document.getElementById('camera-tiles');
  const offlineSection = document.getElementById('camera-offline-section');
  const offlineList = document.getElementById('camera-offline-list');
  const emptyState = document.getElementById('camera-empty-state');
  if (!tilesContainer) return;

  if (!cameras.length) {
    tilesContainer.innerHTML = '';
    if (offlineSection) offlineSection.classList.add('hidden-panel');
    if (emptyState) emptyState.classList.remove('hidden-panel');
    return;
  }
  if (emptyState) emptyState.classList.add('hidden-panel');

  const activeIds = new Set((workerStatus || []).filter(w => w.running).map(w => w.camera_id));
  const offlineCameras = workerStatus ? cameras.filter(c => !activeIds.has(c.id)) : [];
  const onlineCameras = workerStatus ? cameras.filter(c => activeIds.has(c.id)) : cameras;

  tilesContainer.innerHTML = onlineCameras.map(c => createCameraCard(c, false)).join('');
  if (offlineCameras.length) {
    offlineList.innerHTML = offlineCameras.map(c => createCameraCard(c, true)).join('');
    offlineSection.classList.remove('hidden-panel');
  } else if (offlineSection) {
    offlineSection.classList.add('hidden-panel');
  }
  observeSnapshots();
}
```

- [ ] **Step 5: Atualizar `renderDashboard`**

Em `secur/static/dashboard.js:1024-1037`, substituir o bloco do camera-list:

```javascript
  // Only render camera cards if not already present (avoids snapshot flicker)
  const cameraList = document.getElementById('camera-list');
  if (!cameraList.dataset.rendered) {
    cameraList.innerHTML = cameras.map(createCameraCard).join('');
    cameraList.dataset.rendered = '1';
  } else {
    // Update only snapshot images with new timestamp
    cameras.forEach(camera => {
      const img = document.getElementById(`snapshot-${camera.id}`);
      if (img && !img.parentElement.classList.contains('error')) {
        img.src = `/camera/${camera.id}/snapshot?ts=${Date.now()}`;
      }
    });
  }
```

por:

```javascript
  // Camera tiles: lazy-load + offline grouping (status via /status worker_status).
  // Renderiza a grade UMA vez (guard dataset.rendered) — re-render a cada poll de 5s
  // recriaria os <img> sem src e perderia o estado 'loaded' do lazy-load.
  const cameraTiles = document.getElementById('camera-tiles');
  if (!cameraTiles.dataset.rendered) {
    cameraTiles.dataset.rendered = '1';
    let workerStatus = null;
    try {
      const status = await fetchData('/status');
      workerStatus = status.worker_status || null;
    } catch (e) { /* offline: grade única */ }
    renderCameraTiles(cameras, workerStatus);
  }
  updateVisibleSnapshots(cameras);
```

- [ ] **Step 6: Wire do empty-state**

Em `secur/static/dashboard.js`, adicionar ao final da seção `setup` (após `setupCameraForm();` ~linha 1152):

```javascript
  const emptyAddCamera = document.getElementById('empty-add-camera');
  if (emptyAddCamera) {
    emptyAddCamera.addEventListener('click', () => {
      setActiveSection('camera-management');
      showCameraForm('add');
    });
  }
```

- [ ] **Step 7: CSS dos novos componentes**

Adicionar ao final de `secur/static/style.css`:

```css
/* Dashboard redesign (Fase 5) */
#camera-tiles {
  margin-top: 16px;
}

.section-title {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  font-weight: 600;
  color: var(--muted);
  margin: 20px 0 10px;
}

.camera-card-offline {
  opacity: 0.65;
  border-color: var(--border-strong);
}

.badge-offline {
  display: inline-block;
  background: rgba(220, 38, 38, 0.12);
  color: var(--danger);
  border-radius: var(--radius-pill);
  padding: 1px 8px;
  font-size: 0.68rem;
  font-weight: 600;
  margin-left: 6px;
  vertical-align: middle;
}

.camera-preview-wrapper {
  aspect-ratio: 16 / 9;
  min-height: 0;
}

.camera-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  background: var(--surface-2);
  margin-top: 16px;
}

.empty-state .empty-icon {
  font-size: 2.2rem;
  margin-bottom: 10px;
}

.empty-state h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
}

.empty-state p {
  font-size: 0.82rem;
  color: var(--muted);
  margin-bottom: 14px;
}

/* Carrega previews com aspect-ratio; a aba "Câmeras" foi removida */
@media (max-width: 700px) {
  .camera-preview-wrapper {
    aspect-ratio: 16 / 9;
  }
}
```

- [ ] **Step 8: Verificação + commit**

Run: `node --check secur/static/dashboard.js && /tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: `node --check` sem output (OK) e `191 passed, 2 skipped` (regressão — nenhuma mudança em Python).

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js secur/static/style.css
git commit -m "feat: dashboard overview camera grid"
```

---

### Task 2: Eventos — cards com thumbnail e filtros persistentes

**Files:**
- Modify: `secur/templates/dashboard.html:259-270` (section recent-events)
- Modify: `secur/static/dashboard.js:337-350` (createEventRow), `:1039-1040` (eventsTable no renderDashboard), `:1157-1160` (setup/polling)
- Modify: `secur/static/style.css` (classes dos cards/chips ao final)

**Interfaces:**
- Consumes: `GET /events` → `[{id, timestamp, camera_id, zone, event_type, details, clip_path}]`; `GET /camera/<id>/thumbnails` → `[{id, timestamp, event_type, url}]`; `GET /api/notifications` → `{events: [{key, category: "alerta"|"info"}]}` (para o filtro "só alertas").
- Produces: `timeAgo(ts)`, `createEventCard(event, thumbUrl)`, `applyEventFilters(events, alertTypes)`, `syncUrl()`/`applyUrl()`, `renderEvents(events, alertTypes)` — helpers locais da aba Eventos.

- [ ] **Step 2: Corrigir `resetCameraList` (fix Important do review da Task 1)**

O review da Task 1 encontrou: `resetCameraList()` (dashboard.js:479-482) deleta `camera-list.dataset.rendered`, mas `#camera-list` foi removido na Task 1 e o guard de re-render agora é `camera-tiles.dataset.rendered` — que nunca é limpo. Consequência: após adicionar/editar/excluir câmera, a grade da Visão geral não re-renderiza (câmera nova não aparece, empty state não some, câmera removida permanece).

Em `secur/static/dashboard.js:479-482`, substituir:

```javascript
function resetCameraList() {
  const cameraList = document.getElementById('camera-list');
  if (cameraList) delete cameraList.dataset.rendered;
}
```

por:

```javascript
function resetCameraList() {
  const cameraTiles = document.getElementById('camera-tiles');
  if (cameraTiles) delete cameraTiles.dataset.rendered;
}
```

- [ ] **Step 3:** Substituir a section `recent-events` no HTML**

Em `secur/templates/dashboard.html:259-270`, substituir:

```html
            <section class="panel hidden-panel" id="recent-events">
                <h2>Eventos recentes</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Timestamp</th>
                            <th>Câmera</th>
                            <th>Zona</th>
                            <th>Evento</th>
                            <th>Detalhes</th>
                        </tr>
                    </thead>
                    <tbody id="events-table"></tbody>
                </table>
            </section>
```

por:

```html
            <section class="panel hidden-panel" id="recent-events">
                <div class="panel-header">
                    <div>
                        <h2>Eventos recentes</h2>
                        <p>Últimos 100 eventos carregados.</p>
                    </div>
                </div>
                <div class="chips-bar" id="event-filters">
                    <select id="filter-camera" class="chip-select"><option value="">Todas as câmeras</option></select>
                    <select id="filter-zone" class="chip-select"><option value="">Todas as zonas</option></select>
                    <select id="filter-type" class="chip-select"><option value="">Todos os tipos</option></select>
                    <select id="filter-since" class="chip-select">
                        <option value="">Todo o período</option>
                        <option value="1">Última hora</option>
                        <option value="24">Últimas 24h</option>
                        <option value="168">Últimos 7 dias</option>
                    </select>
                    <label class="checkbox-inline" title="Mostrar apenas eventos de alerta">
                        <input type="checkbox" id="filter-alerts" /> Só alertas
                    </label>
                    <button type="button" class="button-secondary button-mini" id="filter-clear">Limpar</button>
                </div>
                <div id="events-grid" class="grid"></div>
                <div id="events-empty" class="empty-state hidden-panel">
                    <div class="empty-icon">&#x1F50D;</div>
                    <h3>Nenhum evento encontrado</h3>
                    <p id="events-empty-text">Ajuste os filtros para ver resultados.</p>
                    <button type="button" class="button-primary" id="events-clear-filters">Limpar filtros</button>
                </div>
            </section>
```

- [ ] **Step 3:** Substituir `createEventRow` por helpers de card**

Em `secur/static/dashboard.js:337-350`, substituir a função inteira por:

```javascript
/* ========== Event cards ========== */

function timeAgo(ts) {
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return 'agora';
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

const thumbCache = {};

function getCameraThumb(cameraId, eventTs) {
  if (!cameraId) return Promise.resolve(null);
  if (thumbCache[cameraId] === undefined) {
    thumbCache[cameraId] = fetch(`/camera/${cameraId}/thumbnails`)
      .then(r => r.ok ? r.json() : [])
      .catch(() => []);
  }
  return thumbCache[cameraId].then(items => {
    if (!items || !items.length) return null;
    let best = null;
    let bestDiff = Infinity;
    items.forEach(item => {
      const diff = Math.abs(new Date(item.timestamp).getTime() - new Date(eventTs).getTime());
      if (diff < bestDiff) { bestDiff = diff; best = item; }
    });
    return best ? best.url : null;
  });
}

function createEventCard(event, thumbUrl) {
  const isAlert = event.event_type !== 'snapshot_info';
  const badge = isAlert
    ? '<span class="badge badge-alert">alerta</span>'
    : '<span class="badge badge-info">info</span>';
  const thumbHtml = thumbUrl
    ? `<img class="event-thumb" src="${thumbUrl}" alt="thumbnail" loading="lazy" />`
    : '<div class="event-thumb event-thumb-empty">&#x1F4F7;</div>';
  return `
    <div class="card event-card">
      ${thumbHtml}
      <div class="event-card-body">
        <div class="event-card-header">
          <span class="event-type">${event.event_type} ${badge}</span>
          <span class="event-time" data-ts="${new Date(event.timestamp).toISOString()}">${timeAgo(event.timestamp)}</span>
        </div>
        <p class="event-meta">Câmera ${event.camera_id || '-'}${event.zone ? ' · ' + event.zone : ''}</p>
        ${event.details ? `<p class="event-details">${event.details}</p>` : ''}
      </div>
    </div>
  `;
}
```

- [ ] **Step 4:** Adicionar filtros + URL/localStorage + render**

Em `secur/static/dashboard.js`, adicionar após o bloco de `createEventCard`:

```javascript
/* ========== Event filters ========== */

const EVENT_FILTERS_KEY = 'secur.eventFilters';

function readFilterState() {
  const url = new URLSearchParams(window.location.search);
  const state = {
    camera: url.get('camera') || '',
    zone: url.get('zone') || '',
    type: url.get('type') || '',
    since: url.get('since') || '',
    alerts: url.get('alerts') === '1',
  };
  if (Object.values(state).some(v => v !== '' && v !== false)) return state;
  try {
    const saved = JSON.parse(localStorage.getItem(EVENT_FILTERS_KEY) || 'null');
    if (saved) return { camera: '', zone: '', type: '', since: '', alerts: false, ...saved };
  } catch (e) { /* ignore */ }
  return state;
}

function saveFilterState(state) {
  try {
    localStorage.setItem(EVENT_FILTERS_KEY, JSON.stringify(state));
  } catch (e) { /* ignore */ }
}

function syncUrl(state) {
  const url = new URLSearchParams();
  if (state.camera) url.set('camera', state.camera);
  if (state.zone) url.set('zone', state.zone);
  if (state.type) url.set('type', state.type);
  if (state.since) url.set('since', state.since);
  if (state.alerts) url.set('alerts', '1');
  const qs = url.toString();
  history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
}

function applyEventFilters(events, alertTypes) {
  const state = readFilterState();
  const sinceHours = Number(state.since) || 0;
  const cutoff = sinceHours ? Date.now() - sinceHours * 3600 * 1000 : null;
  return events.filter(e => {
    if (state.camera && String(e.camera_id) !== state.camera) return false;
    if (state.zone && (e.zone || '') !== state.zone) return false;
    if (state.type && e.event_type !== state.type) return false;
    if (cutoff && new Date(e.timestamp).getTime() < cutoff) return false;
    if (state.alerts && !alertTypes.has(e.event_type)) return false;
    return true;
  });
}

function populateFilterOptions(events) {
  const cameraSelect = document.getElementById('filter-camera');
  const zoneSelect = document.getElementById('filter-zone');
  const typeSelect = document.getElementById('filter-type');
  const cameras = [...new Set(events.map(e => String(e.camera_id)))].sort();
  const zones = [...new Set(events.map(e => e.zone).filter(Boolean))].sort();
  const types = [...new Set(events.map(e => e.event_type))].sort();
  const state = readFilterState();

  if (cameraSelect && !cameraSelect.dataset.populated) {
    cameraSelect.dataset.populated = '1';
    cameras.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = `Câmera ${c}`;
      if (c === state.camera) opt.selected = true;
      cameraSelect.appendChild(opt);
    });
    zones.forEach(z => {
      const opt = document.createElement('option');
      opt.value = z;
      opt.textContent = z;
      if (z === state.zone) opt.selected = true;
      zoneSelect.appendChild(opt);
    });
    types.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t;
      if (t === state.type) opt.selected = true;
      typeSelect.appendChild(opt);
    });
  }
  const sinceSelect = document.getElementById('filter-since');
  if (sinceSelect) sinceSelect.value = state.since;
  const alertsCheck = document.getElementById('filter-alerts');
  if (alertsCheck) alertsCheck.checked = state.alerts;
}

function renderEventCards(events, alertTypes) {
  const grid = document.getElementById('events-grid');
  const empty = document.getElementById('events-empty');
  if (!grid) return;

  const filtered = applyEventFilters(events, alertTypes);
  if (!filtered.length) {
    grid.innerHTML = '';
    if (empty) empty.classList.remove('hidden-panel');
    return;
  }
  if (empty) empty.classList.add('hidden-panel');

  let pending = filtered.length;
  const cards = filtered.map((event, idx) => {
    const card = document.createElement('div');
    card.className = 'card event-card';
    const thumb = document.createElement('div');
    thumb.className = 'event-thumb event-thumb-empty';
    thumb.innerHTML = '&#x1F4F7;';
    card.appendChild(thumb);
    const body = document.createElement('div');
    body.className = 'event-card-body';
    body.innerHTML = `
      <div class="event-card-header">
        <span class="event-type">${event.event_type} ${event.event_type !== 'snapshot_info' ? '<span class="badge badge-alert">alerta</span>' : '<span class="badge badge-info">info</span>'}</span>
        <span class="event-time" data-ts="${new Date(event.timestamp).toISOString()}">${timeAgo(event.timestamp)}</span>
      </div>
      <p class="event-meta">Câmera ${event.camera_id || '-'}${event.zone ? ' · ' + event.zone : ''}</p>
      ${event.details ? `<p class="event-details">${event.details}</p>` : ''}
    `;
    card.appendChild(body);
    grid.appendChild(card);
    getCameraThumb(event.camera_id, event.timestamp).then(url => {
      if (url) {
        const img = document.createElement('img');
        img.className = 'event-thumb';
        img.src = url;
        img.alt = 'thumbnail';
        img.loading = 'lazy';
        thumb.replaceWith(img);
      }
    });
    return card;
  });

  // re-render relógio a cada 30s
  if (!window._eventTimeTimer) {
    window._eventTimeTimer = setInterval(() => {
      document.querySelectorAll('#events-grid .event-time[data-ts]').forEach(el => {
        el.textContent = timeAgo(el.dataset.ts);
      });
    }, 30000);
  }
}

async function renderEvents(events) {
  let alertTypes = new Set();
  try {
    const notif = await fetchData('/api/notifications');
    alertTypes = new Set((notif.events || [])
      .filter(e => e.category === 'alerta')
      .map(e => e.key));
  } catch (e) { /* sem categorias: "só alertas" vira no-op */ }
  populateFilterOptions(events);
  renderEventCards(events, alertTypes);
  return alertTypes;
}
```

Nota: `renderEvents` retorna `alertTypes` para o handler de mudança de filtro re-renderizar sem refetch.

- [ ] **Step 5:** Wire dos filtros**

Em `secur/static/dashboard.js`, adicionar após `renderEvents`:

```javascript
let lastEvents = [];
let lastAlertTypes = new Set();

function setupEventFilters() {
  const ids = ['filter-camera', 'filter-zone', 'filter-type', 'filter-since', 'filter-alerts'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => {
      const state = readFilterState();
      state.camera = document.getElementById('filter-camera').value;
      state.zone = document.getElementById('filter-zone').value;
      state.type = document.getElementById('filter-type').value;
      state.since = document.getElementById('filter-since').value;
      state.alerts = document.getElementById('filter-alerts').checked;
      saveFilterState(state);
      syncUrl(state);
      renderEventCards(lastEvents, lastAlertTypes);
    });
  });

  const clearButtons = ['filter-clear', 'events-clear-filters'];
  clearButtons.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', () => {
      const camera = document.getElementById('filter-camera');
      const zone = document.getElementById('filter-zone');
      const type = document.getElementById('filter-type');
      const since = document.getElementById('filter-since');
      const alerts = document.getElementById('filter-alerts');
      if (camera) camera.value = '';
      if (zone) zone.value = '';
      if (type) type.value = '';
      if (since) since.value = '';
      if (alerts) alerts.checked = false;
      saveFilterState({ camera: '', zone: '', type: '', since: '', alerts: false });
      syncUrl({ camera: '', zone: '', type: '', since: '', alerts: false });
      renderEventCards(lastEvents, lastAlertTypes);
    });
  });
}
```

- [ ] **Step 6:** Atualizar `renderDashboard` e o setup**

Em `secur/static/dashboard.js:1039-1040`, substituir:

```javascript
  const eventsTable = document.getElementById('events-table');
  eventsTable.innerHTML = events.map(createEventRow).join('');
```

por:

```javascript
  lastEvents = events;
  lastAlertTypes = await renderEvents(events);
```

Em `secur/static/dashboard.js:1149-1156` (fim do setup), após `setupSettings();` adicionar:

```javascript
setupEventFilters();
```

- [ ] **Step 7:** CSS dos cards e chips**

Adicionar ao final de `secur/static/style.css`:

```css
/* Event cards + filters (Fase 5) */
.chips-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.chip-select {
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  padding: 6px 12px;
  font-size: 0.78rem;
  color: var(--text);
  background: var(--surface);
  max-width: 180px;
}

#events-grid {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

.event-card {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.event-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
  background: var(--surface-2);
}

.event-thumb-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  color: var(--muted-subtle);
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
}

.event-card-body {
  padding: 10px 12px 12px;
}

.event-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.event-type {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text);
  word-break: break-word;
}

.event-time {
  font-size: 0.72rem;
  color: var(--muted-subtle);
  white-space: nowrap;
}

.event-meta {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 6px;
}

.event-details {
  font-size: 0.75rem;
  color: var(--muted-subtle);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

- [ ] **Step 8:** Verificação + commit**

Run: `node --check secur/static/dashboard.js && /tmp/secur-venv/bin/python -m pytest tests/ -q`
Expected: `node --check` sem output (OK) e `191 passed, 2 skipped` (regressão).

```bash
git add secur/templates/dashboard.html secur/static/dashboard.js secur/static/style.css
git commit -m "feat: dashboard event cards and filters"
```
