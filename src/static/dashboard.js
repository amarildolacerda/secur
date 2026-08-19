let cameraEditId = null;
let zoneEditId = null;
const appStartTime = Date.now();
// local thumbnails for recently captured images (id -> base64)
const localThumbnails = {};
// Toggle "Ver offline" da overview: preferência da sessão (não resetada a
// cada render/poll — a visibilidade da seção offline é derivada dela).
let showOfflineCameras = false;

const SNAPSHOT_RETRY_INTERVAL_MS = CameraFault.FAULT_DEFAULTS.retryIntervalMs;
const SNAPSHOT_OFFLINE_RETRY_INTERVAL_MS = CameraFault.FAULT_DEFAULTS.offlineRetryIntervalMs;
const SNAPSHOT_OFFLINE_THRESHOLD_MS = CameraFault.FAULT_DEFAULTS.offlineThresholdMs;
// id -> { status:'retrying'|'offline', firstFailAt, timer }
const cameraFaultState = {};

function formatUptime(ms) {
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

async function fetchData(url) {
  const response = await fetch(url);
  return response.json();
}

const _apiCache = new Map(); // url -> { ts, promise }
async function fetchCached(url, ttlMs = 60000) {
  const cached = _apiCache.get(url);
  if (cached && (Date.now() - cached.ts) < ttlMs) return cached.promise;
  const promise = fetchData(url);
  _apiCache.set(url, { ts: Date.now(), promise });
  promise.catch(() => { const c = _apiCache.get(url); if (c && c.promise === promise) _apiCache.delete(url); });
  return promise;
}
function invalidateCache(url) {
  if (url) _apiCache.delete(url);
  else _apiCache.clear();
}

function createSummaryCard(title, value, subtitle = "") {
  return `
    <div class="card">
      <h3>${title}</h3>
      <p class="summary-value">${value}</p>
      <p>${subtitle}</p>
    </div>
  `;
}

// Seção ativa do sidebar (determina quais URLs o polling busca).
let currentSection = 'overview';
// True após o render inicial do boot; a partir daí, troca de seção
// renderiza imediatamente (polling scoped à seção ativa).
let dashboardReady = false;

function setActiveSection(sectionId) {
  const sectionChanged = sectionId !== currentSection;
  currentSection = sectionId;

  const panels = document.querySelectorAll('#page .panel, #page .dialog-overlay');
  panels.forEach(panel => {
    if (panel.id === 'camera-dialog' || panel.id === 'zone-dialog') return;
    panel.classList.toggle('hidden-panel', panel.id !== sectionId);
  });

  document.querySelectorAll('.nav-link, .nav-sublink[data-section]').forEach(link => {
    if (link.dataset.section) {
      link.classList.toggle('active', link.dataset.section === sectionId);
    }
  });

  // Troca de seção renderiza imediatamente (sem esperar o próximo poll de 5s).
  // Cobre nav links E botões de "Adicionar câmera/zona" (que chamam setActiveSection).
  if (sectionChanged) {
    // Re-renderiza a tabela de retenção na próxima visita à seção (o guard
    // evita que o polling de 5s destrua inputs em edição).
    const retentionBody = document.getElementById('retention-table-body');
    if (retentionBody) delete retentionBody.dataset.rendered;
    if (dashboardReady) {
      renderDashboard();
    }
  }
}

function toggleCrudNav() {
  const g = document.querySelector('.nav-group');
  if (g) g.classList.toggle('collapsed');
}

function setupSidebarNavigation() {
  document.querySelectorAll('.nav-link[data-section], .nav-sublink[data-section]').forEach(link => {
    link.addEventListener('click', () => {
      setActiveSection(link.dataset.section);
      if (link.dataset.section === 'overview') {
        hideCameraForm();
        hideZoneForm();
      }
    });
  });
}

function createCameraCard(camera, offline = false, lastEventTs = null, n0Count = 0) {
  const faultOffline = cameraFaultState[camera.id] && cameraFaultState[camera.id].status === 'offline';
  offline = offline || faultOffline;
  const zoneLabel = camera.zone || '-';
  const imgId = `snapshot-${camera.id}`;
  const offlineBadge = offline
    ? '<span class="badge-offline">Offline</span>'
    : '';
  const n0Badge = n0Count > 0
    ? `<span class="badge badge-info" title="Eventos N0 (captura) desta câmera">N0: ${n0Count}</span>`
    : '';
  const lastEventLabel = lastEventTs
    ? new Date(lastEventTs).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : 'Sem eventos';

  return `
    <div class="card camera-card${offline ? ' camera-card-offline' : ''}" data-camera-id="${camera.id}">
      <div class="camera-card-header">
        <strong>${camera.name}</strong>
        <span class="camera-badge">ID ${camera.id}</span> <span class="n0-badge-slot">${n0Badge}</span>
      </div>
      <p class="camera-zone">Zona: ${zoneLabel} ${offlineBadge}</p>
      <p class="camera-source">Fonte: ${camera.source}</p>
      <p class="camera-card-time">Último evento: ${lastEventLabel}</p>
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
          onload="onSnapshotLoad(${camera.id}, this)"
          onerror="onSnapshotError(${camera.id}, this)"
        />
        <span class="snapshot-age" data-camera-id="${camera.id}" hidden>--</span>
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

function retrySnapshot(cameraId) {
  const img = document.getElementById(`snapshot-${cameraId}`);
  if (img) {
    const wrapper = img.parentElement;
    wrapper.classList.add('loading');
    wrapper.classList.remove('error');
    img.style.display = '';
    img.nextElementSibling.style.display = 'none';
    fetchSnapshotWithHeader(cameraId, `/camera/${cameraId}/snapshot?ts=${Date.now()}`);
  }
}

function retrySnapshotNow(cameraId) {
  const img = document.getElementById(`snapshot-${cameraId}`);
  if (!img) return;
  const wrapper = img.parentElement;
  wrapper.classList.add('loading');
  wrapper.classList.remove('error');
  img.style.display = '';
  img.nextElementSibling.style.display = 'none';
  fetchSnapshotWithHeader(cameraId, `/camera/${cameraId}/snapshot?ts=${Date.now()}`);
}

function onSnapshotError(cameraId, el) {
  const wrapper = el.parentElement;
  wrapper.classList.remove('loading');
  wrapper.classList.add('error');
  el.dataset.loading = '';
  const img = el;
  img.style.display = 'none';
  // Falha no frame: a idade do anterior não é mais válida
  const ageSpan = wrapper.querySelector('.snapshot-age');
  if (ageSpan) ageSpan.hidden = true;
  img.nextElementSibling.style.display = 'flex';

  const prev = cameraFaultState[cameraId] || null;
  const { state } = CameraFault.transitionFault(prev, 'error', Date.now());
  cameraFaultState[cameraId] = state;
  scheduleSnapshotRetry(cameraId);
  refreshSnapshotFallback(cameraId);
}

// Snapshot ages: cameraId -> ISO timestamp de captura do último frame.
// Preenchido em onSnapshotLoad via XHR (XMLHttpRequest expõe getResponseHeader;
// o <img> em si não dá acesso). null = sem info ainda.
const snapshotTimes = {};

function ageLabelFromMs(ms) {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const seconds = Math.floor(ms / 1000);
  if (seconds < 5) return 'agora';
  if (seconds < 60) return `há ${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `há ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `há ${h}h`;
  const d = Math.floor(h / 24);
  return `há ${d}d`;
}

function ageLabel(capturedIso) {
  const captured = new Date(capturedIso).getTime();
  if (!Number.isFinite(captured)) return '—';
  return ageLabelFromMs(Date.now() - captured);
}

function refreshSnapshotAges() {
  document.querySelectorAll('.snapshot-age[data-camera-id]').forEach(span => {
    const id = span.dataset.cameraId;
    const ts = snapshotTimes[id];
    if (!ts) return;
    span.textContent = `📷 ${ageLabel(ts)}`;
    span.title = `Frame capturado em ${new Date(ts).toLocaleString('pt-BR')}`;
    span.hidden = false;
  });
}
// Tick único global — 1s é granular o bastante para o usuário não ver o número
// "parado" e barato o bastante para 80 câmeras.
if (!window._snapshotAgeTimer) {
  window._snapshotAgeTimer = setInterval(refreshSnapshotAges, 1000);
}

function fetchSnapshotTime(cameraId, srcUrl) {
  // XHR separado do <img> para ler o header X-Snapshot-Time. O <img> já
  // consumiu sua resposta sem expor headers; aqui só queremos o instante.
  try {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', srcUrl);
    xhr.onload = function () {
      const ts = xhr.getResponseHeader('X-Snapshot-Time');
      if (ts) {
        snapshotTimes[cameraId] = ts;
        refreshSnapshotAges();
      }
    };
    xhr.send();
  } catch (e) { /* sem header: span fica oculto */ }
}

async function fetchSnapshotWithHeader(cameraId, url) {
  try {
    const resp = await fetch(url);
    const img = document.getElementById(`snapshot-${cameraId}`);
    if (!resp.ok) { if (img) onSnapshotError(cameraId, img); return; }
    const ts = resp.headers.get('X-Snapshot-Time');
    if (ts) { snapshotTimes[cameraId] = ts; refreshSnapshotAges(); }
    const blob = await resp.blob();
    if (!img) return;
    const blobUrl = URL.createObjectURL(blob);
    img.src = blobUrl; // triggers onSnapshotLoad with blob: src
  } catch (e) {
    const img = document.getElementById(`snapshot-${cameraId}`);
    if (img) onSnapshotError(cameraId, img);
  }
}

function onSnapshotLoad(cameraId, el) {
  if (el.src && el.src.startsWith('blob:')) {
    const wrapper = el.parentElement;
    wrapper.classList.remove('loading');
    wrapper.classList.remove('error');
    const t = cameraFaultState[cameraId];
    if (t && t.timer) clearTimeout(t.timer);
    delete cameraFaultState[cameraId];
    refreshSnapshotFallback(cameraId);
    el.dataset.loading = '';
    return;
  }
  fetchSnapshotWithHeader(cameraId, el.currentSrc || el.src);
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

// Re-baixa o snapshot de uma camera so quando o frame ja e velho (>30s) ou
// o usuario fez hover pedindo frame fresco. Antes re-baixava TODAS as
// cameras a cada poll de 5s, causando:
//  - flick visual (imagem pisca a cada recarga)
//  - 'imagem some' quando o stream demora: <img> fica vazio entre o request
//    antigo e o novo, e o badge mostra 'agora' indefinidamente
//  - carga desnecessaria no servidor (openCV VideoCapture 80x a cada 5s)
const SNAPSHOT_MAX_AGE_MS = 30000;

function refreshSnapshot(cameraId, force = false) {
  const img = document.getElementById(`snapshot-${cameraId}`);
  if (!img || img.dataset.loading === '1') return;
  const wrapper = img.parentElement;
  if (wrapper.classList.contains('error')) return;
  const ts = snapshotTimes[String(cameraId)];
  if (!force && ts && (Date.now() - new Date(ts).getTime()) < SNAPSHOT_MAX_AGE_MS) return;
  img.dataset.loading = '1';
  img.src = `/camera/${cameraId}/snapshot?ts=${Date.now()}`;
}

// Poll: so re-baixa cameras com snapshot velho. Sem isso a imagem some.
function updateVisibleSnapshots(cameras) {
  cameras.forEach(camera => {
    const img = document.getElementById(`snapshot-${camera.id}`);
    if (!img || !img.dataset.loaded) return;
    const wrapper = img.parentElement;
    if (!wrapper || !wrapper.classList.contains('in-viewport')) return;
    if (wrapper.classList.contains('error')) return;
    refreshSnapshot(camera.id, false);
  });
}

// Hook de hover: usuario quer frame fresco ao interagir com o card.
function setupHoverFreshSnapshots() {
  if (window._hoverFreshWired) return;
  window._hoverFreshWired = true;
  document.addEventListener('mouseover', (e) => {
    const wrapper = e.target.closest('.camera-preview-wrapper');
    if (!wrapper) return;
    const cameraId = wrapper.dataset.cameraId;
    if (cameraId) refreshSnapshot(cameraId, true);
  });
}

/* ========== Ordenação por último evento ========== */

// Monta Map<camera_id, último timestamp de evento>. /events vem em ordem desc,
// mas o máximo (em vez do primeiro match) garante o mais recente mesmo se a
// ordem do endpoint mudar.
function buildLastEventMap(events) {
  const map = new Map();
  events.forEach(e => {
    if (e.camera_id == null) return;
    const ts = new Date(e.timestamp).getTime();
    if (!map.has(e.camera_id) || ts > map.get(e.camera_id)) map.set(e.camera_id, ts);
  });
  return map;
}

// Conta eventos por câmera (chaves normalizadas para string, pois /events
// devolve camera_id como string e /cameras como int). Usado no indicador N0.
function countEventsByCamera(events) {
  const map = new Map();
  events.forEach(e => {
    if (e.camera_id == null) return;
    const key = String(e.camera_id);
    map.set(key, (map.get(key) || 0) + 1);
  });
  return map;
}

// Ordena câmeras por último evento desc (mais recentes primeiro). Câmeras sem
// evento vão para o fim, preservando a ordem original entre elas (sort estável).
function sortCamerasByLastEvent(cameras, lastEventMap) {
  return [...cameras].sort((a, b) => (lastEventMap.get(b.id) || 0) - (lastEventMap.get(a.id) || 0));
}

function renderCameraTiles(cameras, workerStatus, lastEventMap = new Map(), n0ByCamera = new Map()) {
  const tilesContainer = document.getElementById('camera-tiles');
  const emptyState = document.getElementById('camera-empty-state');
  if (!tilesContainer) return;

  if (!cameras.length) {
    tilesContainer.innerHTML = '';
    updateOfflineSection([], null, lastEventMap, n0ByCamera);
    if (emptyState) emptyState.classList.remove('hidden-panel');
    return;
  }
  if (emptyState) emptyState.classList.add('hidden-panel');

  const activeIds = new Set((workerStatus || []).filter(w => w.healthy !== false).map(w => w.camera_id));
  const offlineCameras = workerStatus ? cameras.filter(c => !activeIds.has(c.id)) : [];
  const onlineCameras = workerStatus ? cameras.filter(c => activeIds.has(c.id)) : cameras;

  // Diff minimo: nao recriar cards que ja estao no DOM. innerHTML='' a cada
  // 5s causava flick do layout (recalculo de altura do grid), re-fetch do
  // snapshot (img novo) e re-animacao do loading pulse. Agora so atualizamos
  // os campos dinamicos (badges, texto) e mantemos o <img> existente.
  const existing = new Map();
  tilesContainer.querySelectorAll('.camera-card[data-camera-id]').forEach(el => {
    existing.set(String(el.dataset.cameraId), el);
  });
  const fragment = document.createDocumentFragment();
  onlineCameras.forEach(c => {
    const key = String(c.id);
    const n0Count = n0ByCamera.get(key) || 0;
    const existingEl = existing.get(key);
    if (existingEl) {
      // Atualiza so o que muda entre polls (N0 badge, offline badge, ultimo evento)
      updateCameraCard(existingEl, c, false, lastEventMap.get(c.id), n0Count);
      existing.delete(key);
      return;
    }
    const wrapper = document.createElement('div');
    wrapper.innerHTML = createCameraCard(c, false, lastEventMap.get(c.id), n0Count);
    fragment.appendChild(wrapper.firstElementChild);
  });
  // Reposiciona: ordem pode mudar (sortCamerasByLastEvent). Estrategia simples:
  // re-anexa na ordem correta, removendo os antigos do DOM antes.
  const newChildren = Array.from(fragment.children);
  tilesContainer.innerHTML = '';
  newChildren.forEach(el => tilesContainer.appendChild(el));
  // Cards que existiam mas nao estao mais online (viraram offline): mantemos
  // no DOM e marcamos como offline via updateCameraCard (updateOfflineSection
  // cuida deles separadamente).
  existing.forEach(el => tilesContainer.appendChild(el));

  updateOfflineSection(cameras, workerStatus, lastEventMap, n0ByCamera);
  observeSnapshots();
}

// Atualizacao incremental: badges, offline, ultimo evento. NAO toca no <img>
// nem recria o wrapper — preserva o snapshot carregado e evita flick a cada
// poll de 5s (sem isso, innerHTML='' destruiria todos os cards e re-dispararia
// fetch do snapshot + re-animacao do loading pulse).
function updateCameraCard(el, camera, offline, lastEventTs, n0Count) {
  const faultOffline = cameraFaultState[camera.id] && cameraFaultState[camera.id].status === 'offline';
  const isOffline = offline || faultOffline;
  el.classList.toggle('camera-card-offline', isOffline);

  // N0 badge (slot reservado no header)
  const n0Slot = el.querySelector('.n0-badge-slot');
  if (n0Slot) {
    n0Slot.innerHTML = n0Count > 0
      ? `<span class="badge badge-info" title="Eventos N0 (captura) desta câmera">N0: ${n0Count}</span>`
      : '';
  }

  // Offline badge (ao final do parágrafo de zona)
  const zoneP = el.querySelector('.camera-zone');
  if (zoneP) {
    let offlineBadge = zoneP.querySelector('.badge-offline');
    if (isOffline && !offlineBadge) {
      offlineBadge = document.createElement('span');
      offlineBadge.className = 'badge-offline';
      offlineBadge.textContent = 'Offline';
      zoneP.appendChild(document.createTextNode(' '));
      zoneP.appendChild(offlineBadge);
    } else if (!isOffline && offlineBadge) {
      offlineBadge.remove();
    }
  }

  const timeEl = el.querySelector('.camera-card-time');
  if (timeEl) {
    const label = lastEventTs
      ? new Date(lastEventTs).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
      : 'Sem eventos';
    timeEl.textContent = `Último evento: ${label}`;
  }
}

// Câmeras offline ocultas por padrão (otimização de espaço): aparece apenas o
// bar "Ver offline (N)" com switch quando há offline; o switch revela a lista
// em #camera-offline-section. Chamada a cada poll da overview (sem re-renderizar
// a grade, que tem guard de lazy-load) mantém contador e visibilidade em dia.
// A preferência do usuário (showOfflineCameras) é preservada na sessão.
function updateOfflineSection(cameras, workerStatus, lastEventMap = new Map(), n0ByCamera = new Map()) {
  const offlineBar = document.getElementById('camera-offline-bar');
  const offlineSection = document.getElementById('camera-offline-section');
  const offlineList = document.getElementById('camera-offline-list');
  const offlineLabel = document.getElementById('camera-offline-toggle-label');
  if (!offlineBar || !offlineSection) return;

  const activeIds = new Set((workerStatus || []).filter(w => w.healthy !== false).map(w => w.camera_id));
  const offlineCameras = workerStatus ? cameras.filter(c => !activeIds.has(c.id)) : [];

  if (offlineCameras.length) {
    if (offlineList) offlineList.innerHTML = offlineCameras.map(c => createCameraCard(c, true, lastEventMap.get(c.id), n0ByCamera.get(String(c.id)) || 0)).join('');
    if (offlineLabel) offlineLabel.textContent = `Ver offline (${offlineCameras.length})`;
    offlineBar.classList.remove('hidden-panel');
    offlineSection.classList.toggle('hidden-panel', !showOfflineCameras);
  } else {
    if (offlineList) offlineList.innerHTML = '';
    offlineBar.classList.add('hidden-panel');
    offlineSection.classList.add('hidden-panel');
  }
}

function setupOfflineToggle() {
  const toggle = document.getElementById('show-offline-cameras');
  if (!toggle) return;
  toggle.addEventListener('change', () => {
    showOfflineCameras = toggle.checked;
    const offlineSection = document.getElementById('camera-offline-section');
    if (offlineSection) offlineSection.classList.toggle('hidden-panel', !showOfflineCameras);
  });
}

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

/* ========== Live Player ========== */

let livePlayerInterval = null;

function openLivePlayer(cameraId, cameraName, source) {
  const overlay = document.getElementById('live-player-overlay');
  const title = document.getElementById('live-player-title');
  const videoEl = document.getElementById('live-video');
  const imgEl = document.getElementById('live-snapshot');
  const videoContainer = document.getElementById('live-video-container');
  const imgContainer = document.getElementById('live-snapshot-container');

  title.textContent = cameraName;
  overlay.classList.remove('hidden-panel');

  // Determine stream type
  const isHLS = source.endsWith('.m3u8') || source.includes('.m3u8');
  const isHTTP = source.startsWith('http') && !isHLS;

  if (isHLS && typeof Hls !== 'undefined' && Hls.isSupported()) {
    // HLS stream
    videoContainer.style.display = '';
    imgContainer.style.display = 'none';

    const hls = new Hls({ liveSyncDurationCount: 2, enableWorker: true });
    hls.loadSource(source);
    hls.attachMedia(videoEl);
    hls.on(Hls.Events.MANIFEST_PARSED, () => videoEl.play().catch(() => {}));
    overlay._hls = hls;
  } else if (isHLS && videoEl.canPlayType('application/vnd.apple.mpegurl')) {
    // Safari native HLS
    videoContainer.style.display = '';
    imgContainer.style.display = 'none';
    videoEl.src = source;
    videoEl.play().catch(() => {});
  } else if (isHTTP) {
    // Direct HTTP video
    videoContainer.style.display = '';
    imgContainer.style.display = 'none';
    videoEl.src = source;
    videoEl.play().catch(() => {});
  } else {
    // RTSP fallback: pseudo-live via snapshot loop
    videoContainer.style.display = 'none';
    imgContainer.style.display = '';
    imgEl.src = `/camera/${cameraId}/snapshot?ts=${Date.now()}`;
    livePlayerInterval = setInterval(() => {
      imgEl.src = `/camera/${cameraId}/snapshot?ts=${Date.now()}`;
    }, 500);
  }
}

function closeLivePlayer() {
  const overlay = document.getElementById('live-player-overlay');
  const videoEl = document.getElementById('live-video');

  overlay.classList.add('hidden-panel');

  // Stop HLS
  if (overlay._hls) {
    overlay._hls.destroy();
    overlay._hls = null;
  }

  // Stop video
  videoEl.pause();
  videoEl.src = '';

  // Stop snapshot loop
  if (livePlayerInterval) {
    clearInterval(livePlayerInterval);
    livePlayerInterval = null;
  }
}

/* ========== Thumbnail History ========== */

function thumbPhaseBadge(item) {
  if (item.dropped === true) return '<span class="thumb-phase-badge thumb-phase-dropped">descartado</span>';
  const lvl = item.level != null ? Number(item.level) : null;
  if (lvl === null || lvl === undefined) return '';
  const labels = ['N0', 'N1', 'N2', 'N3', 'N4'];
  const classes = ['thumb-phase-n0', 'thumb-phase-n1', 'thumb-phase-n2', 'thumb-phase-n3', 'thumb-phase-n4'];
  const label = labels[lvl] || ('N' + lvl);
  const cls = classes[lvl] || 'thumb-phase-n0';
  return `<span class="thumb-phase-badge ${cls}">${label}</span>`;
}

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
        <div class="thumb-history-item" onclick="openThumbDetail('${item.url}', '${item.timestamp}', '${item.event_type || ''}', '${item.level != null ? item.level : ''}', '${item.disposition || ''}', ${item.dropped === true})">
          <img src="${item.url}" alt="thumbnail" loading="lazy" />
          <span class="thumb-history-time">${new Date(item.timestamp).toLocaleString()} ${thumbPhaseBadge(item)}</span>
          <span class="thumb-history-event">${item.event_type || ''}</span>
        </div>
      `).join('');
    })
    .catch(() => {
      empty.textContent = 'Falha ao carregar histórico.';
      empty.style.display = '';
    });
}

// Estado do zoom/pan. Resetado a cada openThumbDetail para nao carregar
// zoom de um item antigo em outro.
const thumbZoomState = { scale: 1, x: 0, y: 0, dragging: false, dragStartX: 0, dragStartY: 0, originX: 0, originY: 0 };

function applyThumbZoom() {
  const img = document.getElementById('thumb-detail-img');
  const label = document.getElementById('thumb-detail-zoom-label');
  if (!img) return;
  img.style.transform = `translate(${thumbZoomState.x}px, ${thumbZoomState.y}px) scale(${thumbZoomState.scale})`;
  img.style.width = img.dataset.naturalWidth ? `${img.dataset.naturalWidth}px` : '';
  img.style.height = img.dataset.naturalHeight ? `${img.dataset.naturalHeight}px` : '';
  if (label) label.textContent = `${Math.round(thumbZoomState.scale * 100)}%`;
}

function resetThumbZoom() {
  thumbZoomState.scale = 1;
  thumbZoomState.x = 0;
  thumbZoomState.y = 0;
  applyThumbZoom();
}

function setupThumbDetailZoom() {
  const viewport = document.getElementById('thumb-detail-viewport');
  const img = document.getElementById('thumb-detail-img');
  const btnIn = document.getElementById('thumb-detail-zoom-in');
  const btnOut = document.getElementById('thumb-detail-zoom-out');
  const btnReset = document.getElementById('thumb-detail-zoom-reset');
  if (!viewport || !img) return;
  if (viewport._zoomWired) return; // evita re-bind a cada open
  viewport._zoomWired = true;

  // Wheel: zoom centrado no cursor. deltaY>0 afasta, <0 aproxima.
  viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = viewport.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
    const newScale = Math.max(0.2, Math.min(8, thumbZoomState.scale * factor));
    // Ajusta x/y para que o ponto sob o cursor nao "pule".
    const ratio = newScale / thumbZoomState.scale;
    thumbZoomState.x = cx - ratio * (cx - thumbZoomState.x);
    thumbZoomState.y = cy - ratio * (cy - thumbZoomState.y);
    thumbZoomState.scale = newScale;
    applyThumbZoom();
  }, { passive: false });

  // Drag pan: so ativo se scale > 1 (senao nao extrapola o viewport).
  viewport.addEventListener('mousedown', (e) => {
    if (thumbZoomState.scale <= 1) return;
    thumbZoomState.dragging = true;
    thumbZoomState.dragStartX = e.clientX;
    thumbZoomState.dragStartY = e.clientY;
    thumbZoomState.originX = thumbZoomState.x;
    thumbZoomState.originY = thumbZoomState.y;
    viewport.classList.add('grabbing');
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!thumbZoomState.dragging) return;
    thumbZoomState.x = thumbZoomState.originX + (e.clientX - thumbZoomState.dragStartX);
    thumbZoomState.y = thumbZoomState.originY + (e.clientY - thumbZoomState.dragStartY);
    applyThumbZoom();
  });
  window.addEventListener('mouseup', () => {
    thumbZoomState.dragging = false;
    viewport.classList.remove('grabbing');
  });

  // Duplo-clique: 1x se esta zoomed, senao 2x no ponto clicado.
  viewport.addEventListener('dblclick', (e) => {
    e.preventDefault();
    const rect = viewport.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    if (thumbZoomState.scale > 1) {
      resetThumbZoom();
    } else {
      const newScale = 2;
      const ratio = newScale / thumbZoomState.scale;
      thumbZoomState.x = cx - ratio * (cx - thumbZoomState.x);
      thumbZoomState.y = cy - ratio * (cy - thumbZoomState.y);
      thumbZoomState.scale = newScale;
      applyThumbZoom();
    }
  });

  // Botoes
  btnIn && btnIn.addEventListener('click', () => {
    const newScale = Math.min(8, thumbZoomState.scale * 1.2);
    thumbZoomState.x = viewport.clientWidth / 2 - (newScale / thumbZoomState.scale) * (viewport.clientWidth / 2 - thumbZoomState.x);
    thumbZoomState.y = viewport.clientHeight / 2 - (newScale / thumbZoomState.scale) * (viewport.clientHeight / 2 - thumbZoomState.y);
    thumbZoomState.scale = newScale;
    applyThumbZoom();
  });
  btnOut && btnOut.addEventListener('click', () => {
    const newScale = Math.max(0.2, thumbZoomState.scale / 1.2);
    const ratio = newScale / thumbZoomState.scale;
    thumbZoomState.x = viewport.clientWidth / 2 - ratio * (viewport.clientWidth / 2 - thumbZoomState.x);
    thumbZoomState.y = viewport.clientHeight / 2 - ratio * (viewport.clientHeight / 2 - thumbZoomState.y);
    thumbZoomState.scale = newScale;
    applyThumbZoom();
  });
  btnReset && btnReset.addEventListener('click', resetThumbZoom);
}

function openThumbDetail(url, timestamp, eventType, level, disposition, dropped, extra = {}) {
  const overlay = document.getElementById('thumb-detail-overlay');
  const title = document.getElementById('thumb-detail-title');
  const img = document.getElementById('thumb-detail-img');
  const meta = document.getElementById('thumb-detail-meta');

  // Atalhos de teclado: + zoom in, - zoom out, Esc fecha.
  // Registra uma vez por dialog aberto (overlay._keysWired) para nao empilhar.
  if (!overlay._keysWired) {
    overlay._keysWired = true;
    overlay.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeThumbDetail();
        return;
      }
      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        thumbZoomState.scale = Math.min(8, thumbZoomState.scale * 1.2);
        applyThumbZoom();
      } else if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        thumbZoomState.scale = Math.max(0.2, thumbZoomState.scale / 1.2);
        applyThumbZoom();
      } else if (e.key === '0') {
        e.preventDefault();
        resetThumbZoom();
      }
    });
  }
  // Garante que o overlay receba keydown (precisa de tabindex).
  if (!overlay.hasAttribute('tabindex')) overlay.setAttribute('tabindex', '-1');
  overlay.focus();

  title.textContent = extra.camera ? `${extra.camera} — Detalhe` : 'Detalhe do evento';
  img.src = url;
  // Dimensoes naturais para o zoom usar pixel-perfect (escala 1 = tamanho real)
  img.onload = () => {
    img.dataset.naturalWidth = img.naturalWidth;
    img.dataset.naturalHeight = img.naturalHeight;
    resetThumbZoom();
  };
  if (img.complete) {
    img.dataset.naturalWidth = img.naturalWidth;
    img.dataset.naturalHeight = img.naturalHeight;
    resetThumbZoom();
  }

  const lvl = level !== '' && level !== null && level !== undefined ? Number(level) : null;
  const lvlLabel = lvl !== null ? (['N0', 'N1', 'N2', 'N3', 'N4'][lvl] || ('N' + lvl)) : null;
  const dispLabel = disposition ? `<span class="badge badge-info">${disposition}</span>` : '';
  const droppedLabel = dropped ? '<span class="badge badge-off">descartado</span>' : '';
  const lvlBadge = lvlLabel ? `<span class="badge badge-info">${lvlLabel}</span>` : '';

  // Idade do evento ("uptime" da imagem): quanto tempo passou desde a
  // captura. Importante para o operador entender se o frame ainda
  // representa a realidade ou se ja e antigo.
  const ageMs = Date.now() - new Date(timestamp).getTime();
  const ageLabel = ageMs >= 0 ? ageLabelFromMs(ageMs) : '—';
  meta.innerHTML = `
    ${extra.camera ? `<span><strong>Câmera:</strong> ${extra.camera}</span>` : ''}
    ${extra.zone ? `<span><strong>Zona:</strong> ${extra.zone}</span>` : ''}
    <span><strong>Data:</strong> ${new Date(timestamp).toLocaleString()} <em>(${ageLabel})</em></span>
    ${eventType ? `<span><strong>Tipo:</strong> ${eventType}</span>` : ''}
    ${lvlBadge}
    ${dispLabel}
    ${droppedLabel}
    ${extra.details ? `<span><strong>Detalhes:</strong> ${extra.details}</span>` : ''}
  `;

  setupThumbDetailZoom();
  resetThumbZoom();
  overlay.classList.remove('hidden-panel');
}

function closeThumbDetail() {
  const overlay = document.getElementById('thumb-detail-overlay');
  if (overlay) overlay.classList.add('hidden-panel');
}

function closeThumbHistory() {
  const overlay = document.getElementById('thumb-history-overlay');
  if (overlay) overlay.classList.add('hidden-panel');
}

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

/* ========== Settings ========== */

async function renderSettings() {
  const toggle = document.getElementById('privacy-mode-toggle');
  if (!toggle) return;
  try {
    const data = await fetchData('/api/settings');
    toggle.checked = !!data.privacy_mode;
  } catch (e) { /* offline: mantém estado atual */ }
  renderSettingsConfig();
}

// Renderiza o valor de um parâmetro conforme o tipo:
// booleano → badge (Ativado/Desativado), número → tag mono, texto → elipse.
function appendConfigValue(dd, v) {
  const text = Array.isArray(v) ? v.join(', ') : String(v);
  dd.title = text;
  if (typeof v === 'boolean') {
    const badge = document.createElement('span');
    badge.className = 'config-value-badge ' + (v ? 'is-on' : 'is-off');
    badge.textContent = v ? 'Ativado' : 'Desativado';
    dd.appendChild(badge);
  } else if (typeof v === 'number') {
    const tag = document.createElement('span');
    tag.className = 'config-value-num';
    tag.textContent = text;
    dd.appendChild(tag);
  } else {
    const span = document.createElement('span');
    span.className = 'config-value-text';
    span.textContent = text;
    dd.appendChild(span);
  }
}

// Painel read-only "Configurações em uso" (collapsible). Busca /api/config
// e exibe os parâmetros efetivos agrupados por categoria.
function renderSettingsConfig() {
  const container = document.getElementById('settings-config');
  if (!container) return;
  fetch('/api/config')
    .then(r => r.json())
    .then(cfg => {
      container.innerHTML = '';
      const section = document.createElement('div');
      section.className = 'settings-config-sections';

      const groups = [
        { title: 'Movimento (N1)', data: cfg.motion, keys: ['min_area_px', 'frame_wait_seconds', 'worker_healthy_timeout_seconds'], labels: { min_area_px: 'Área mínima (px)', frame_wait_seconds: 'Espera frame (s)', worker_healthy_timeout_seconds: 'Timeout worker saudável (s)' } },
        { title: 'Alertas', data: cfg.alerts, keys: ['no_motion_alert_seconds', 'cooldown_seconds'], labels: { no_motion_alert_seconds: 'Sem movimento alerta (s)', cooldown_seconds: 'Cooldown padrão (s)' } },
        { title: 'Detector (YOLO)', data: cfg.detector, keys: ['model_path', 'confidence', 'iou'], labels: { model_path: 'Modelo', confidence: 'Confiança', iou: 'IoU' } },
        { title: 'Identidade', data: cfg.identity, keys: ['enabled', 'face_model_path', 'match_threshold'], labels: { enabled: 'Habilitado', face_model_path: 'Modelo face', match_threshold: 'Threshold match' } },
        { title: 'Thumbnails', data: cfg.thumbnails, keys: ['interval_seconds', 'diff_threshold', 'history_size'], labels: { interval_seconds: 'Intervalo (s)', diff_threshold: 'Threshold diff', history_size: 'Histórico' } },
        { title: 'Clips', data: cfg.clips, keys: ['pre_seconds', 'post_seconds', 'fps', 'history_size'], labels: { pre_seconds: 'Pré (s)', post_seconds: 'Pós (s)', fps: 'FPS', history_size: 'Histórico' } },
        { title: 'Tracking', data: cfg.tracking, keys: ['iou_threshold', 'max_age_seconds'], labels: { iou_threshold: 'IoU threshold', max_age_seconds: 'Max age (s)' } },
        { title: 'Comportamento', data: cfg.behavior, keys: ['loitering_seconds', 'loitering_max_distance', 'fall_aspect_ratio'], labels: { loitering_seconds: 'Loitering (s)', loitering_max_distance: 'Loitering dist. max', fall_aspect_ratio: 'Fall aspect ratio' } },
      ];

      groups.forEach(g => {
        if (!g.data) return;
        const groupDiv = document.createElement('div');
        groupDiv.className = 'config-module-group';
        const h4 = document.createElement('h4');
        h4.textContent = g.title;
        groupDiv.appendChild(h4);
        const dl = document.createElement('dl');
        dl.className = 'settings-config-list';
        g.keys.forEach(k => {
          const v = g.data[k];
          if (v === undefined || v === null) return;
          const dt = document.createElement('dt');
          dt.textContent = g.labels[k] || k;
          const dd = document.createElement('dd');
          appendConfigValue(dd, v);
          dl.appendChild(dt);
          dl.appendChild(dd);
        });
        if (dl.children.length) {
          groupDiv.appendChild(dl);
          const count = document.createElement('span');
          count.className = 'config-group-count';
          count.textContent = String(dl.children.length / 2);
          h4.appendChild(count);
        }
        if (groupDiv.children.length > 1) section.appendChild(groupDiv);
      });

      if (cfg.privacy_mode != null) {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'config-module-group';
        const h4 = document.createElement('h4');
        h4.textContent = 'Privacidade';
        groupDiv.appendChild(h4);
        const dl = document.createElement('dl');
        dl.className = 'settings-config-list';
        const dt = document.createElement('dt');
        dt.textContent = 'Modo privacidade';
        const dd = document.createElement('dd');
        appendConfigValue(dd, cfg.privacy_mode);
        dl.appendChild(dt);
        dl.appendChild(dd);
        groupDiv.appendChild(dl);
        const count = document.createElement('span');
        count.className = 'config-group-count';
        count.textContent = '1';
        h4.appendChild(count);
        section.appendChild(groupDiv);
      }

      // Botão para executar limpeza manual
      // (removido: a política de retenção agora é editável em Manutenção →
      // "Retenção de eventos", onde o botão "Aplicar" executa a limpeza.)

      if (!section.children.length) {
        container.textContent = 'Sem informações de configuração disponíveis.';
        return;
      }
      container.appendChild(section);
    })
    .catch(() => {
      container.textContent = 'Falha ao carregar configurações.';
    });
}

function setupSettings() {
  const configToggle = document.getElementById('settings-config-toggle');
  if (configToggle) {
    configToggle.addEventListener('click', () => {
      const panel = document.getElementById('settings-config');
      if (!panel) return;
      panel.classList.toggle('hidden-panel');
      const open = !panel.classList.contains('hidden-panel');
      configToggle.classList.toggle('is-open', open);
      configToggle.setAttribute('aria-expanded', String(open));
      if (open) {
        panel.classList.remove('animate-in');
        void panel.offsetWidth; // reinicia a animação de entrada
        panel.classList.add('animate-in');
      }
    });
  }
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
    } else {
      invalidateCache('/api/settings');
    }
  });
}

function createCameraRow(camera) {
  const classesText = camera.alert_classes && camera.alert_classes.length
    ? camera.alert_classes.join(', ')
    : 'todas';
  const exclusionsText = camera.exclusion_zones && camera.exclusion_zones.length
    ? `${camera.exclusion_zones.length} polígono(s)`
    : '—';
  const maskText = camera.mask_polygons && camera.mask_polygons.length
    ? `${camera.mask_polygons.length} polígono(s)`
    : '—';
  return `
    <tr>
      <td>${camera.id}</td>
      <td>${camera.name}</td>
      <td>${camera.source}</td>
      <td>${camera.zone || '-'}</td>
      <td>${classesText}</td>
      <td>${exclusionsText}</td>
      <td>${maskText}</td>
      <td class="table-actions">
        <button class="button-secondary button-mini edit-camera" data-camera-id="${camera.id}">Editar</button>
        <button class="button-secondary button-mini delete-camera" data-camera-id="${camera.id}">Excluir</button>
        <button class="button-secondary button-mini clips-camera" data-camera-id="${camera.id}">Clipes</button>
      </td>
    </tr>
  `;
}

function createZoneRow(zone) {
  const classLabel = {
    'privativa': 'Privativa',
    'segurança': 'Segurança',
    'pública': 'Pública'
  }[zone.classification] || zone.classification;

  return `
    <tr>
      <td>${zone.id}</td>
      <td>${zone.name}</td>
      <td>${classLabel}</td>
      <td class="table-actions">
        <button class="button-secondary button-mini edit-zone" data-zone-id="${zone.id}">Editar</button>
        <button class="button-secondary button-mini delete-zone" data-zone-id="${zone.id}">Excluir</button>
      </td>
    </tr>
  `;
}

/* ========== Event cards ========== */

function timeAgo(ts) {
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return 'agora';
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

const thumbCache = {};
const THUMB_CACHE_TTL_MS = 30000;
function _pickThumb(items, eventTs) {
  if (!items || !items.length) return null;
  let best = null, bestDiff = Infinity;
  items.forEach(item => {
    const diff = Math.abs(new Date(item.timestamp).getTime() - new Date(eventTs).getTime());
    if (diff < bestDiff) { bestDiff = diff; best = item; }
  });
  return best ? best.url : null;
}
function getCameraThumb(cameraId, eventTs) {
  if (!cameraId) return Promise.resolve(null);
  const cached = thumbCache[cameraId];
  if (cached && (Date.now() - cached.ts) < THUMB_CACHE_TTL_MS) {
    return cached.promise.then(items => _pickThumb(items, eventTs));
  }
  const promise = fetch(`/camera/${cameraId}/thumbnails`).then(r => r.ok ? r.json() : []).catch(() => []);
  thumbCache[cameraId] = { ts: Date.now(), promise };
  return promise.then(items => _pickThumb(items, eventTs));
}

function createEventCard(event, thumbUrl, alertTypes = new Set()) {
  const isAlert = alertTypes.has(event.event_type);
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

/* ========== Event filters ========== */

const EVENT_FILTERS_KEY = 'secur.eventFilters';

function readFilterState() {
  const url = new URLSearchParams(window.location.search);
  const state = {
    camera: url.get('camera') || '',
    zone: url.get('zone') || '',
    type: url.get('type') || '',
    level: url.get('level') || '',
    since: url.get('since') || '1',
    alerts: url.get('alerts') === '1',
    retained: url.get('retained') === '1',
  };
  // Filtros explícitos na URL têm precedência; caso contrário, tenta
  // localStorage. O default since='1' (última hora) não deve bloquear esse
  // fallback, então o guard olha os parâmetros da URL em vez dos valores.
  const hasUrlFilters = url.has('camera') || url.has('zone') || url.has('type') || url.has('level') || url.has('since') || url.has('alerts') || url.has('retained');
  if (hasUrlFilters) return state;
  try {
    const saved = JSON.parse(localStorage.getItem(EVENT_FILTERS_KEY) || 'null');
    if (saved) return { camera: '', zone: '', type: '', level: '', since: '', alerts: false, retained: false, ...saved };
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
  if (state.level) url.set('level', state.level);
  if (state.since) url.set('since', state.since);
  if (state.alerts) url.set('alerts', '1');
  if (state.retained) url.set('retained', '1');
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
    if (state.level && Number(e.level) !== Number(state.level)) return false;
    if (cutoff && new Date(e.timestamp).getTime() < cutoff) return false;
    if (state.alerts && !alertTypes.has(e.event_type)) return false;
    if (state.retained && !e.retained) return false;
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
  const levelSelect = document.getElementById('filter-level');
  if (levelSelect) levelSelect.value = state.level;
  const alertsCheck = document.getElementById('filter-alerts');
  if (alertsCheck) alertsCheck.checked = state.alerts;
  const retainedCheck = document.getElementById('filter-retained');
  if (retainedCheck) retainedCheck.checked = state.retained;
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

  // NOTA (fix Critical do review da Task 2): o grid DEVE ser limpo antes do
  // append — renderDashboard roda a cada 5s e sem isso os cards duplicariam
  // a cada poll (o brief original omitia a limpeza).
  grid.innerHTML = '';

  filtered.forEach((event) => {
    const card = document.createElement('div');
    const lvl = event.level != null ? Number(event.level) : 0;
    let cardClass = 'card event-card';
    if (lvl === 3) cardClass += ' event-card-n3';
    if (lvl === 4) cardClass += ' event-card-n4';
    card.className = cardClass;
    // Data-attrs para o click delegado (openEventThumbDialog) abrir o dialog
    // com metadados do evento. Sem isso, o dialog mostraria apenas a imagem.
    card.dataset.eventId = event.id;
    card.dataset.timestamp = event.timestamp;
    card.dataset.eventType = event.event_type || '';
    card.dataset.level = lvl;
    card.dataset.disposition = event.disposition || '';
    card.dataset.dropped = event.dropped ? '1' : '0';
    card.dataset.cameraId = event.camera_id || '';
    card.dataset.cameraName = event.camera_name || event.camera_id || '';
    card.dataset.zone = event.zone || '';
    card.dataset.details = event.details || '';
    card.dataset.retained = event.retained ? '1' : '0';
    const thumb = document.createElement('div');
    thumb.className = 'event-thumb event-thumb-empty';
    thumb.style.cursor = 'pointer';
    thumb.innerHTML = '&#x1F4F7;';
    card.appendChild(thumb);
    const body = document.createElement('div');
    body.className = 'event-card-body';
    const lvlLabel = ['N0', 'N1', 'N2', 'N3', 'N4'][lvl] || ('N' + lvl);
    const droppedBadge = event.dropped ? '<span class="badge badge-off">descartado N1</span>' : '';
    const retainedBadge = event.retained ? '<span class="badge badge-ok">retido</span>' : '';
    const levelBadge = `<span class="badge badge-info">${lvlLabel}</span>`;
    body.innerHTML = `
      <div class="event-card-header">
        <span class="event-type">${event.event_type} ${alertTypes.has(event.event_type) ? '<span class="badge badge-alert">alerta</span>' : '<span class="badge badge-info">info</span>'} ${levelBadge} ${droppedBadge} ${retainedBadge}</span>
        <span class="event-time" data-ts="${new Date(event.timestamp).toISOString()}">${timeAgo(event.timestamp)}</span>
        <label class="retain-checkbox" title="Marcar para não apagar no prune">
          <input type="checkbox" ${event.retained ? 'checked' : ''} data-event-id="${event.id}">
          <span class="checkbox-label">Reter</span>
        </label>
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
        img.style.cursor = 'zoom-in';
        // O <img> e inserido dentro do card; o listener delegado em
        // #events-grid (installado em setupEventCardThumbPreview) cuida
        // do click para abrir o dialog ampliado.
        thumb.replaceWith(img);
      }
    });
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
    const notif = await fetchCached('/api/notifications');
    alertTypes = new Set((notif.events || [])
      .filter(e => e.category === 'alerta')
      .map(e => e.key));
  } catch (e) { /* sem categorias: "só alertas" vira no-op */ }
  populateFilterOptions(events);
  renderEventCards(events, alertTypes);
  return alertTypes;
}

let lastEvents = [];
let lastAlertTypes = new Set();
let lastDashboardPayload = null;

function setupEventFilters() {
  const ids = ['filter-camera', 'filter-zone', 'filter-type', 'filter-level', 'filter-since', 'filter-alerts', 'filter-retained'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => {
      const state = readFilterState();
      state.camera = document.getElementById('filter-camera').value;
      state.zone = document.getElementById('filter-zone').value;
      state.type = document.getElementById('filter-type').value;
      state.level = document.getElementById('filter-level').value;
      state.since = document.getElementById('filter-since').value;
      state.alerts = document.getElementById('filter-alerts').checked;
      state.retained = document.getElementById('filter-retained').checked;
      saveFilterState(state);
      syncUrl(state);
      renderEventCards(lastEvents, lastAlertTypes);
    });
  });

  const clearButtons = ['filter-clear', 'events-clear-filters'];
  clearButtons.forEach(id => {
    const el = document.getElementById(id);
    if (el)     el.addEventListener('click', () => {
      const camera = document.getElementById('filter-camera');
      const zone = document.getElementById('filter-zone');
      const type = document.getElementById('filter-type');
      const level = document.getElementById('filter-level');
      const since = document.getElementById('filter-since');
      const alerts = document.getElementById('filter-alerts');
      const retained = document.getElementById('filter-retained');
      if (camera) camera.value = '';
      if (zone) zone.value = '';
      if (type) type.value = '';
      if (level) level.value = '';
      if (since) since.value = '';
      if (alerts) alerts.checked = false;
      if (retained) retained.checked = false;
      saveFilterState({ camera: '', zone: '', type: '', level: '', since: '', alerts: false, retained: false });
      syncUrl({ camera: '', zone: '', type: '', level: '', since: '', alerts: false, retained: false });
      renderEventCards(lastEvents, lastAlertTypes);
    });
  });
}

/* ========== Camera form ========== */

/* ---------- Preview de zonas de exclusão / máscara ----------
   Desenha os polígonos dos textareas sobre o frame atual da câmera
   (snapshot ?raw=1, sem máscara). Sem frame (modo adicionar ou câmera
   offline) usa um placeholder escuro com grade e ajusta os polígonos à
   área visível para dar noção da forma. */

const PREVIEW_DEBOUNCE_MS = 350;
// Estado do preview: frame carregado (edit) ou placeholder (add/offline).
let previewFrame = null;        // { img, width, height } | null
let previewLoadToken = 0;       // cancela loads obsoletos ao fechar/reabrir
let previewDebounceTimer = null;
let previewNote = 'add';        // 'add' | 'offline' | null (frame carregado)

function resetCameraPreview() {
  previewLoadToken += 1;
  clearTimeout(previewDebounceTimer);
  previewFrame = null;
  previewNote = 'add';
  const loading = document.getElementById('camera-preview-loading');
  if (loading) loading.hidden = true;
  const note = document.getElementById('camera-preview-note');
  if (note) {
    note.textContent = '';
    note.classList.remove('error');
  }
}

// Parseia o texto de um campo de polígonos. Aceita a lista de polígonos
// (formato oficial) e, de forma leniente, uma lista plana de pontos como
// um único polígono (ex.: o placeholder do textarea). Retorna
// { polygons, error } — error só para JSON inválido / não-lista.
function parsePolygonField(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return { polygons: [], error: null };
  let data;
  try {
    data = JSON.parse(trimmed);
  } catch (e) {
    return { polygons: null, error: 'JSON inválido.' };
  }
  if (!Array.isArray(data)) {
    return { polygons: null, error: 'Formato: lista de polígonos.' };
  }
  const isFlat = data.length > 0 && !Array.isArray(data[0]);
  const rawPolys = isFlat ? [data] : data;
  const polygons = [];
  for (const poly of rawPolys) {
    if (!Array.isArray(poly)) continue;
    const pts = [];
    for (const p of poly) {
      if (p && typeof p === 'object' && typeof p.x === 'number' && typeof p.y === 'number') {
        pts.push({ x: p.x, y: p.y });
      }
    }
    if (pts.length >= 3) polygons.push(pts);
  }
  return { polygons, error: null };
}

function drawPlaceholderGrid(ctx, w, h) {
  ctx.fillStyle = '#12141a';
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 40; x < w; x += 40) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
  for (let y = 40; y < h; y += 40) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
  ctx.stroke();
}

// Contorno escuro por baixo + cor por cima: visível em frames claros e escuros.
function strokeWithOutline(ctx, outlineColor, color, outlineWidth, width) {
  ctx.strokeStyle = outlineColor;
  ctx.lineWidth = outlineWidth;
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}

function drawExclusionPolygon(ctx, pts) {
  if (pts.length < 3) return;
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
  ctx.closePath();
  ctx.fillStyle = 'rgba(245, 158, 11, 0.22)';
  ctx.fill();
  strokeWithOutline(ctx, 'rgba(0,0,0,0.55)', '#f59e0b', 4, 2);
}

function drawMaskPolygon(ctx, pts) {
  if (pts.length < 3) return;
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
  ctx.closePath();
  ctx.fillStyle = 'rgba(10, 12, 16, 0.55)';
  ctx.fill();
  // Hachura diagonal sutil para sugerir "borrado".
  const pattern = document.createElement('canvas');
  pattern.width = 8;
  pattern.height = 8;
  const pctx = pattern.getContext('2d');
  pctx.strokeStyle = 'rgba(255,255,255,0.28)';
  pctx.lineWidth = 1;
  pctx.beginPath();
  pctx.moveTo(-4, 4); pctx.lineTo(4, -4);
  pctx.moveTo(0, 8); pctx.lineTo(8, 0);
  pctx.moveTo(4, 12); pctx.lineTo(12, 4);
  pctx.stroke();
  const hatch = ctx.createPattern(pattern, 'repeat');
  if (hatch) {
    ctx.fillStyle = hatch;
    ctx.fill();
  }
  strokeWithOutline(ctx, 'rgba(0,0,0,0.7)', 'rgba(255,255,255,0.65)', 3, 1.5);
}

function drawCameraPreview() {
  const canvas = document.getElementById('camera-preview-canvas');
  const note = document.getElementById('camera-preview-note');
  if (!canvas || !note) return;
  const ctx = canvas.getContext('2d');

  const exclusion = parsePolygonField(document.getElementById('camera-exclusion-zones').value);
  const mask = parsePolygonField(document.getElementById('camera-mask-polygons').value);
  const error = exclusion.error || mask.error;

  // Resolução interna: acompanha o frame (edit) ou 16:9 padrão (placeholder).
  let W, H;
  if (previewFrame) {
    W = previewFrame.width;
    H = previewFrame.height;
  } else {
    W = 960;
    H = 540;
  }
  const MAX_W = 960;
  if (W > MAX_W) {
    H = Math.round((H * MAX_W) / W);
    W = MAX_W;
  }
  if (canvas.width !== W) canvas.width = W;
  if (canvas.height !== H) canvas.height = H;

  if (previewFrame) {
    ctx.drawImage(previewFrame.img, 0, 0, W, H);
  } else {
    drawPlaceholderGrid(ctx, W, H);
  }

  // Escala: frame real usa coordenadas de pixel; placeholder ajusta o
  // conjunto de polígonos à área visível para dar noção da forma.
  let sx = 1, sy = 1, ox = 0, oy = 0;
  if (previewFrame) {
    sx = W / previewFrame.width;
    sy = H / previewFrame.height;
  } else {
    const all = [...(exclusion.polygons || []), ...(mask.polygons || [])].flat();
    if (all.length) {
      const minX = Math.min(...all.map(p => p.x));
      const maxX = Math.max(...all.map(p => p.x));
      const minY = Math.min(...all.map(p => p.y));
      const maxY = Math.max(...all.map(p => p.y));
      const bw = Math.max(maxX - minX, 1);
      const bh = Math.max(maxY - minY, 1);
      sx = sy = Math.min((W * 0.8) / bw, (H * 0.8) / bh);
      ox = (W - (minX + maxX) * sx) / 2;
      oy = (H - (minY + maxY) * sy) / 2;
    }
  }
  const map = pts => pts.map(p => ({ x: p.x * sx + ox, y: p.y * sy + oy }));

  (exclusion.polygons || []).forEach(poly => drawExclusionPolygon(ctx, map(poly)));
  (mask.polygons || []).forEach(poly => drawMaskPolygon(ctx, map(poly)));

  // Nota / erro inline (não interfere na validação do submit).
  if (error) {
    note.textContent = error;
    note.classList.add('error');
  } else if (previewNote === 'offline') {
    note.textContent = 'Câmera offline — preview sem frame, polígonos em escala aproximada.';
    note.classList.remove('error');
  } else if (previewNote === 'add') {
    note.textContent = 'Sem frame ainda — polígonos em escala aproximada. O preview do frame aparece ao editar uma câmera salva.';
    note.classList.remove('error');
  } else {
    note.textContent = 'Frame atual sem máscara aplicada; polígonos desenhados por cima.';
    note.classList.remove('error');
  }

  // Acessibilidade: descreve o conteúdo desenhado.
  const counts = [];
  if (exclusion.polygons && exclusion.polygons.length) counts.push(`${exclusion.polygons.length} zona(s) de exclusão`);
  if (mask.polygons && mask.polygons.length) counts.push(`${mask.polygons.length} máscara(s) de privacidade`);
  canvas.setAttribute('aria-label',
    `Prévia das zonas de exclusão e máscara de privacidade${previewFrame ? ' sobre o frame da câmera' : ''}.` +
    (counts.length ? ` ${counts.join(', ')}.` : ' Nenhum polígono definido.'));
}

function schedulePreviewRedraw() {
  clearTimeout(previewDebounceTimer);
  previewDebounceTimer = setTimeout(drawCameraPreview, PREVIEW_DEBOUNCE_MS);
}

async function loadPreviewFrame(cameraId) {
  const token = ++previewLoadToken;
  previewFrame = null;
  previewNote = null;
  const loading = document.getElementById('camera-preview-loading');
  if (loading) loading.hidden = false;
  try {
    const response = await fetch(`/camera/${cameraId}/snapshot?raw=1&ts=${Date.now()}`);
    if (token !== previewLoadToken) return;
    if (!response.ok) throw new Error('snapshot indisponível');
    const blob = await response.blob();
    if (token !== previewLoadToken) return;
    const url = URL.createObjectURL(blob);
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = url;
    });
    if (token !== previewLoadToken) {
      URL.revokeObjectURL(url);
      return;
    }
    previewFrame = { img, width: img.naturalWidth || 1920, height: img.naturalHeight || 1080 };
    URL.revokeObjectURL(url);
  } catch (e) {
    if (token !== previewLoadToken) return;
    previewNote = 'offline';
  } finally {
    if (token === previewLoadToken) {
      if (loading) loading.hidden = true;
      drawCameraPreview();
    }
  }
}

function setCameraFormMode(mode, camera = null) {
  const title = document.getElementById('camera-dialog-title');
  const submit = document.getElementById('camera-form-submit');
  const form = document.getElementById('camera-form');
  const nameInput = document.getElementById('camera-name');
  const sourceInput = document.getElementById('camera-source');
  const zoneInput = document.getElementById('camera-zone');
  const message = document.getElementById('camera-form-message');

  if (mode === 'edit' && camera) {
    cameraEditId = camera.id;
    title.textContent = 'Editar câmera';
    submit.textContent = 'Salvar alterações';
    nameInput.value = camera.name;
    sourceInput.value = camera.source;
    zoneInput.value = camera.zone || '';
  } else {
    cameraEditId = null;
    title.textContent = 'Adicionar câmera';
    submit.textContent = 'Adicionar câmera';
    form.reset();
  }

  populateAlertClasses(camera ? camera.alert_classes : null);
  const exclusionInput = document.getElementById('camera-exclusion-zones');
  if (exclusionInput) {
    exclusionInput.value = camera && camera.exclusion_zones ? JSON.stringify(camera.exclusion_zones) : '';
  }
  const maskInput = document.getElementById('camera-mask-polygons');
  if (maskInput) {
    maskInput.value = camera && camera.mask_polygons ? JSON.stringify(camera.mask_polygons) : '';
  }

  if (message) {
    message.textContent = '';
    message.classList.remove('error');
  }

  // Preview de zonas/máscara: frame real ao editar, placeholder no adicionar.
  resetCameraPreview();
  if (mode === 'edit' && camera) {
    loadPreviewFrame(camera.id);
  } else {
    drawCameraPreview();
  }
}

function showCameraForm(mode = 'add', camera = null) {
  const dialog = document.getElementById('camera-dialog');
  if (dialog) {
    setCameraFormMode(mode, camera);
    dialog.classList.remove('hidden-panel');
    document.getElementById('camera-dialog-title').textContent = mode === 'edit' ? 'Editar câmera' : 'Adicionar câmera';
  }
}

function hideCameraForm() {
  const dialog = document.getElementById('camera-dialog');
  if (dialog) {
    dialog.classList.add('hidden-panel');
    setCameraFormMode('add');
  }
}

function resetCameraList() {
  const cameraTiles = document.getElementById('camera-tiles');
  if (cameraTiles) delete cameraTiles.dataset.rendered;
}

async function submitCameraForm(event) {
  event.preventDefault();

  const nameInput = document.getElementById('camera-name');
  const sourceInput = document.getElementById('camera-source');
  const zoneInput = document.getElementById('camera-zone');
  const message = document.getElementById('camera-form-message');
  const submitBtn = document.getElementById('camera-form-submit');
  const cancelBtn = document.getElementById('cancel-camera-edit');

  const payload = {
    name: nameInput.value.trim(),
    source: sourceInput.value.trim(),
    zone: zoneInput.value || null,
  };

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

  if (!payload.name || !payload.source) {
    message.textContent = 'Nome e fonte são obrigatórios.';
    message.classList.add('error');
    return;
  }

  // Show loading state
  submitBtn.disabled = true;
  submitBtn.classList.add('button-loading');
  const originalText = submitBtn.textContent;
  submitBtn.innerHTML = '<span class="spinner"></span> Validando stream...';
  cancelBtn.disabled = true;
  message.textContent = '';
  message.classList.remove('error');

  let response;
  try {
    if (cameraEditId) {
      response = await fetch(`/cameras/${cameraEditId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } else {
      response = await fetch('/cameras', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }

    if (!response.ok) {
      const error = await response.json();
      message.textContent = error.error || 'Falha ao salvar câmera.';
      message.classList.add('error');
      return;
    }

    hideCameraForm();
    resetCameraList();
    renderDashboard();
  } finally {
    // Restore button state
    submitBtn.disabled = false;
    submitBtn.classList.remove('button-loading');
    submitBtn.textContent = originalText;
    cancelBtn.disabled = false;
  }
}

async function deleteCamera(cameraId) {
  if (!confirm('Tem certeza que deseja excluir esta câmera?')) return;
  const response = await fetch(`/cameras/${cameraId}`, {
    method: 'DELETE',
  });
  if (response.ok) {
    resetCameraList();
    renderDashboard();
  }
}

/* ========== Zone form ========== */

function setZoneFormMode(mode, zone = null) {
  const title = document.getElementById('zone-dialog-title');
  const submit = document.getElementById('zone-form-submit');
  const form = document.getElementById('zone-form');
  const nameInput = document.getElementById('zone-name');
  const classInput = document.getElementById('zone-classification');
  const message = document.getElementById('zone-form-message');

  if (mode === 'edit' && zone) {
    zoneEditId = zone.id;
    title.textContent = 'Editar zona';
    submit.textContent = 'Salvar alterações';
    nameInput.value = zone.name;
    classInput.value = zone.classification;
  } else {
    zoneEditId = null;
    title.textContent = 'Adicionar zona';
    submit.textContent = 'Adicionar zona';
    form.reset();
  }

  const startInput = document.getElementById('zone-schedule-start');
  const endInput = document.getElementById('zone-schedule-end');
  if (mode === 'edit' && zone) {
    startInput.value = (zone.schedule && zone.schedule.start) || '';
    endInput.value = (zone.schedule && zone.schedule.end) || '';
  } else {
    startInput.value = '';
    endInput.value = '';
  }

  const directionInput = document.getElementById('zone-direction-line');
  if (mode === 'edit' && zone) {
    directionInput.value = zone.direction_line ? JSON.stringify(zone.direction_line) : '';
  } else {
    directionInput.value = '';
  }

  if (message) {
    message.textContent = '';
    message.classList.remove('error');
  }
}

function showZoneForm(mode = 'add', zone = null) {
  const dialog = document.getElementById('zone-dialog');
  if (dialog) {
    setZoneFormMode(mode, zone);
    dialog.classList.remove('hidden-panel');
    document.getElementById('zone-dialog-title').textContent = mode === 'edit' ? 'Editar zona' : 'Adicionar zona';
  }
}

function hideZoneForm() {
  const dialog = document.getElementById('zone-dialog');
  if (dialog) {
    dialog.classList.add('hidden-panel');
    setZoneFormMode('add');
  }
}

async function submitZoneForm(event) {
  event.preventDefault();

  const nameInput = document.getElementById('zone-name');
  const classInput = document.getElementById('zone-classification');
  const message = document.getElementById('zone-form-message');

  const payload = {
    name: nameInput.value.trim(),
    classification: classInput.value,
  };

  const startInput = document.getElementById('zone-schedule-start');
  const endInput = document.getElementById('zone-schedule-end');
  let schedule = null;
  if (startInput.value || endInput.value) {
    schedule = { start: startInput.value || '00:00', end: endInput.value || '23:59' };
  }
  payload.schedule = schedule;

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

  if (!payload.name) {
    message.textContent = 'Nome é obrigatório.';
    message.classList.add('error');
    return;
  }

  let response;
  if (zoneEditId) {
    response = await fetch(`/zones/${zoneEditId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } else {
    response = await fetch('/zones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  if (!response.ok) {
    const error = await response.json();
    message.textContent = error.error || 'Falha ao salvar zona.';
    message.classList.add('error');
    return;
  }

  hideZoneForm();
  renderDashboard();
}

async function deleteZone(zoneId) {
  if (!confirm('Tem certeza que deseja excluir esta zona?')) return;
  const response = await fetch(`/zones/${zoneId}`, {
    method: 'DELETE',
  });
  if (response.ok) {
    renderDashboard();
  }
}

/* ========== Zone dropdown for camera form ========== */

function populateZoneDropdown(zones, selectedZone) {
  const select = document.getElementById('camera-zone');
  if (!select) return;

  const current = selectedZone || select.value;
  select.innerHTML = '<option value="">Nenhuma zona</option>';
  zones.forEach(zone => {
    const opt = document.createElement('option');
    opt.value = zone.name;
    opt.textContent = zone.name;
    if (zone.name === current) opt.selected = true;
    select.appendChild(opt);
  });
}

// Agrupa classes por categoria para paineis colapsaveis. Antes eram 80
// checkboxes em flex-wrap dentro do form (ocupavam a tela toda e nao cabiam
// no dialog de 500px). Agora: <details> por categoria, default expandido
// para as categorias mais relevantes (pessoas, veiculos, animais). Botoes
// de acao rapida: selecionar/limpar categoria, e busca por texto.
const ALERT_CLASS_GROUPS = [
  { key: 'all', label: 'Todas as classes (limpar filtro)', classes: null },
  { key: 'person', label: 'Pessoas', classes: ['person'] },
  { key: 'vehicle', label: 'Veículos', classes: ['bicycle','car','motorcycle','airplane','bus','train','truck','boat'] },
  { key: 'outdoor', label: 'Externo', classes: ['traffic light','fire hydrant','stop sign','parking meter','bench'] },
  { key: 'animal', label: 'Animais', classes: ['bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe'] },
  { key: 'accessory', label: 'Acessórios pessoais', classes: ['backpack','umbrella','handbag','tie','suitcase'] },
  { key: 'sports', label: 'Esportes', classes: ['frisbee','skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket'] },
  { key: 'food', label: 'Alimentos / cozinha', classes: ['bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich','orange','broccoli','carrot','hot dog','pizza','donut','cake'] },
  { key: 'furniture', label: 'Móveis / Eletro', classes: ['chair','couch','potted plant','bed','dining table','toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven','toaster','sink','refrigerator'] },
  { key: 'misc', label: 'Outros', classes: ['book','clock','vase','scissors','teddy bear','hair drier','toothbrush'] },
];

function _buildClassCheckbox(cls, selectedSet) {
  const checked = selectedSet.has(cls) ? 'checked' : '';
  const escaped = cls.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
  return `<label class="checkbox-inline"><input type="checkbox" value="${escaped}" ${checked} /> ${escaped}</label>`;
}

async function populateAlertClasses(selected) {
  const container = document.getElementById('camera-alert-classes');
  if (!container) return;
  let classes = [];
  try {
    const data = await fetchCached('/api/classes');
    classes = data.classes || [];
  } catch (e) { return; }
  const selectedSet = new Set(selected || []);

  // Agrupa pelo ALERT_CLASS_GROUPS; classes desconhecidas vao para "Outros".
  const knownKeys = new Set();
  ALERT_CLASS_GROUPS.forEach(g => g.classes && g.classes.forEach(c => knownKeys.add(c)));
  const miscClasses = classes.filter(c => !knownKeys.has(c));

  const sections = ALERT_CLASS_GROUPS
    .filter(g => !g.classes || g.classes.some(c => classes.includes(c)))
    .map((g, idx) => {
      // Primeira secao abre por default (pessoas + veiculos, os mais uteis).
      const open = idx === 1 || idx === 2 ? 'open' : '';
      const groupClasses = g.classes ? g.classes.filter(c => classes.includes(c)) : [];
      const checkboxes = groupClasses.map(c => _buildClassCheckbox(c, selectedSet)).join('');
      return `
        <details class="class-group" ${open}>
          <summary>
            <span class="class-group-label">${g.label}</span>
            <span class="class-group-count">${groupClasses.length}</span>
            <button type="button" class="button-mini class-group-toggle" data-group="${g.key}">inverter</button>
          </summary>
          <div class="class-group-body">${checkboxes}</div>
        </details>
      `;
    }).join('');

  // Classes que nao estao em nenhum grupo vao em uma secao "Nao categorizadas".
  const orphanSection = miscClasses.length
    ? `<details class="class-group"><summary><span class="class-group-label">Não categorizadas</span><span class="class-group-count">${miscClasses.length}</span></summary><div class="class-group-body">${miscClasses.map(c => _buildClassCheckbox(c, selectedSet)).join('')}</div></details>`
    : '';

  container.innerHTML = `
    <div class="class-filter-actions">
      <input type="search" id="class-filter-search" placeholder="Filtrar classes..." />
      <button type="button" class="button-mini" id="class-filter-all">Todas</button>
      <button type="button" class="button-mini" id="class-filter-none">Limpar</button>
    </div>
    ${sections}
    ${orphanSection}
  `;

  // Eventos dos botoes de acao rapida
  const allBtn = container.querySelector('#class-filter-all');
  const noneBtn = container.querySelector('#class-filter-none');
  const search = container.querySelector('#class-filter-search');
  allBtn && allBtn.addEventListener('click', () => {
    container.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = true; cb.dispatchEvent(new Event('change')); });
  });
  noneBtn && noneBtn.addEventListener('click', () => {
    container.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = false; cb.dispatchEvent(new Event('change')); });
  });
  search && search.addEventListener('input', () => {
    const term = search.value.trim().toLowerCase();
    container.querySelectorAll('.class-group').forEach(d => {
      const labels = d.querySelectorAll('label.checkbox-inline');
      let visibleCount = 0;
      labels.forEach(l => {
        const text = l.textContent.toLowerCase();
        const show = !term || text.includes(term);
        l.style.display = show ? '' : 'none';
        if (show) visibleCount++;
      });
      d.querySelector('.class-group-count').textContent = visibleCount;
      // Abre secoes com resultados
      d.style.display = visibleCount > 0 ? '' : 'none';
    });
  });
  // Botao "inverter" por secao
  container.querySelectorAll('.class-group-toggle').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const det = btn.closest('details');
      det.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); });
    });
  });
}

/* ========== Messages ========== */

function showMenuMessage(message, targetId = 'camera-form-message') {
  const messageContainer = document.getElementById(targetId);
  if (messageContainer) {
    messageContainer.textContent = message;
    messageContainer.classList.remove('error');
    setTimeout(() => {
      messageContainer.textContent = '';
    }, 5000);
  }
}

function scrollToSection(sectionId) {
  const section = document.getElementById(sectionId);
  if (section) {
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

/* ========== Maintenance menu ========== */

/* ========== Retenção de eventos (Manutenção) ========== */

// Rótulos amigáveis para tipos de evento conhecidos. Chaves fora deste mapa
// exibem o nome técnico como está.
const EVENT_RETENTION_LABELS = {
  motion_detected: 'Movimento detectado',
  capture: 'Captura (N0)',
  snapshot_info: 'Objetos detectados (info)',
  no_motion: 'Sem movimento',
  loitering: 'Permanência suspeita',
  suppressed: 'Suprimido (cooldown)',
  cooldown: 'Cooldown',
  identity_recognized: 'Identidade reconhecida',
  intruder_detected: 'Intruso em zona restrita',
  direction_change: 'Movimento em direção proibida',
  fall_detected: 'Possível queda',
  unknown_detected: 'Não reconhecido',
  object_detected: 'Objeto detectado (legado)',
};

// Última política de retenção carregada de /api/config — usada pelo botão
// "Restaurar" para reverter os inputs sem nova chamada de rede.
let eventRetentionSnapshot = null;

// Valor numérico seguro para o input ('' se ausente/NaN em vez de "NaN").
function retentionValue(v) {
  const n = Number(v);
  return Number.isFinite(n) ? String(n) : '';
}

// Linha de um tipo de evento: rótulo amigável + chave técnica (mono) + input.
function retentionTypeRow(type, label, days) {
  const key = type !== label ? `<code class="retention-key">${escapeHtml(type)}</code>` : '';
  return `
    <tr data-retention-type="${escapeHtml(type)}">
      <td>
        <span class="retention-label">${escapeHtml(label)}</span>
        ${key}
      </td>
      <td>
        <div class="retention-input-wrap">
          <input class="retention-input" type="number" min="0" step="any" inputmode="decimal"
                 data-retention-type="${escapeHtml(type)}" value="${retentionValue(days)}"
                 aria-label="${escapeHtml(label)} (dias)" />
          <span class="retention-unit">dias</span>
        </div>
      </td>
    </tr>
  `;
}

// Linha global (Retenção padrão / Idade máx. não retido): visualmente separada.
function retentionGlobalRow(role, label, hint, days) {
  return `
    <tr class="retention-global-row" data-retention-role="${role}">
      <td>
        <span class="retention-label">${escapeHtml(label)}</span>
        <span class="retention-hint">${escapeHtml(hint)}</span>
      </td>
      <td>
        <div class="retention-input-wrap">
          <input class="retention-input" type="number" min="0" step="any" inputmode="decimal"
                 data-retention-role="${role}" value="${retentionValue(days)}"
                 aria-label="${escapeHtml(label)} (dias)" />
          <span class="retention-unit">dias</span>
        </div>
      </td>
    </tr>
  `;
}

// Monta o HTML do tbody a partir da política de retenção (config ou snapshot).
function buildRetentionTableHtml(pruning) {
  const typeDays = pruning.type_days || {};
  const typeRows = Object.entries(typeDays).map(([type, days]) => {
    const label = EVENT_RETENTION_LABELS[type] || type;
    return retentionTypeRow(type, label, days);
  }).join('');
  const globalRows =
    retentionGlobalRow('default', 'Retenção padrão', 'tipos sem regra específica', pruning.default_days) +
    retentionGlobalRow('max_age', 'Idade máx. não retido', 'limite absoluto p/ eventos não retidos', pruning.max_age_days);
  return typeRows + globalRows;
}

async function renderEventRetentionSection() {
  const body = document.getElementById('retention-table-body');
  if (!body) return;
  let cfg;
  try {
    cfg = await fetchData('/api/config');
  } catch (e) {
    if (!body.dataset.rendered) {
      body.innerHTML = '<tr><td colspan="2">Falha ao carregar configuração.</td></tr>';
    }
    return;
  }
  const pruning = cfg.event_pruning || {};
  eventRetentionSnapshot = pruning;
  // O polling de 5s não pode recriar a tabela enquanto o usuário edita:
  // os inputs são montados apenas na primeira visita à seção (guard
  // resetado em setActiveSection ao trocar de seção).
  if (!body.dataset.rendered) {
    body.dataset.rendered = '1';
    body.innerHTML = buildRetentionTableHtml(pruning);
  }

  // Nota de status: limpeza automática ativa/desativada + intervalo.
  const statusEl = document.getElementById('retention-status');
  if (statusEl) {
    const enabled = pruning.enabled !== false;
    const interval = Number(pruning.interval_seconds) || 0;
    const intervalLabel = interval >= 3600 && interval % 3600 === 0
      ? `${interval / 3600}h`
      : `${interval}s`;
    statusEl.textContent = enabled
      ? `Limpeza automática ativa (a cada ${intervalLabel}). Eventos retidos (retained=1) nunca são removidos.`
      : `Limpeza automática desativada. A tabela abaixo permite executar a limpeza manualmente.`;
    statusEl.classList.toggle('is-warn', !enabled);
  }
}

// Lê os inputs da tabela e valida. Retorna null se algum valor for inválido.
function readRetentionInputs() {
  const typeDays = {};
  let valid = true;
  document.querySelectorAll('#retention-table-body input[data-retention-type]').forEach(input => {
    const value = parseFloat(input.value);
    if (Number.isNaN(value) || value < 0) { valid = false; return; }
    typeDays[input.dataset.retentionType] = value;
  });
  const defaultInput = document.querySelector('#retention-table-body input[data-retention-role="default"]');
  const maxAgeInput = document.querySelector('#retention-table-body input[data-retention-role="max_age"]');
  const defaultDays = defaultInput ? parseFloat(defaultInput.value) : NaN;
  const maxAgeDays = maxAgeInput ? parseFloat(maxAgeInput.value) : NaN;
  if (Number.isNaN(defaultDays) || defaultDays < 0 || Number.isNaN(maxAgeDays) || maxAgeDays < 0) {
    valid = false;
  }
  return valid ? { type_days: typeDays, default_days: defaultDays, max_age_days: maxAgeDays } : null;
}

async function applyEventRetention() {
  const btn = document.getElementById('retention-apply');
  const msg = document.getElementById('retention-message');
  if (!btn || !msg) return;

  const payload = readRetentionInputs();
  msg.classList.remove('error');
  if (!payload) {
    msg.textContent = 'Informe valores numéricos válidos (0 ou mais dias).';
    msg.classList.add('error');
    return;
  }

  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = 'Aplicando...';
  msg.textContent = '';

  try {
    const res = await fetch('/api/events/prune', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.textContent = data.error || `Falha ao aplicar (HTTP ${res.status}).`;
      msg.classList.add('error');
    } else {
      const deleted = Number(data.deleted) || 0;
      eventRetentionSnapshot = payload; // "Restaurar" volta para o que foi aplicado
      msg.textContent = deleted > 0
        ? `Política salva. Limpeza concluída: ${deleted} evento(s) removido(s).`
        : 'Política salva. Nenhum evento a remover.';
    }
  } catch (e) {
    msg.textContent = 'Falha de rede ao aplicar a retenção.';
    msg.classList.add('error');
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

function restoreEventRetention() {
  const body = document.getElementById('retention-table-body');
  if (!body || !eventRetentionSnapshot) return;
  body.innerHTML = buildRetentionTableHtml(eventRetentionSnapshot);
  const msg = document.getElementById('retention-message');
  if (msg) { msg.textContent = ''; msg.classList.remove('error'); }
}

function setupEventRetention() {
  const applyBtn = document.getElementById('retention-apply');
  if (applyBtn) applyBtn.addEventListener('click', applyEventRetention);
  const restoreBtn = document.getElementById('retention-restore');
  if (restoreBtn) restoreBtn.addEventListener('click', restoreEventRetention);
}

/* ========== Footer ========== */

async function renderStatusFooter() {
  let status = null;
  if (lastDashboardPayload) {
    status = {
      status: 'ok',
      camera_count: (lastDashboardPayload.cameras || []).length,
      recent_events: (lastDashboardPayload.events || []).length,
      active_workers: (lastDashboardPayload.worker_status || []).length,
    };
  } else {
    try { status = await fetchData('/status'); } catch (e) { status = null; }
  }
  if (!status) {
    const health = document.getElementById('status-health');
    if (health) { health.textContent = 'Status: indisponível'; health.className = 'status-bad'; }
    return;
  }
  const health = document.getElementById('status-health');
  const cameras = document.getElementById('status-cameras');
  const workers = document.getElementById('status-workers');
  const recent = document.getElementById('status-recent');
  if (health) { health.textContent = `Status: ${status.status || 'ok'}`; health.className = status.status === 'ok' ? 'status-good' : 'status-bad'; }
  if (cameras) cameras.textContent = `Câmeras: ${status.camera_count ?? '—'}`;
  if (workers) workers.textContent = `Workers: ${status.active_workers ?? '—'}`;
  if (recent) recent.textContent = `Eventos recentes: ${status.recent_events ?? '—'}`;
  const uptime = document.getElementById('status-uptime');
  if (uptime) uptime.textContent = `Uptime: ${formatUptime(Date.now() - appStartTime)}`;
}

/* ========== Render ========== */

function renderCameraManagement(cameras) {
  const body = document.getElementById('camera-table-body');
  if (body) {
    body.innerHTML = cameras.map(createCameraRow).join('');
  }
}

function renderZoneManagement(zones) {
  const body = document.getElementById('zone-table-body');
  if (body) {
    body.innerHTML = zones.map(createZoneRow).join('');
  }
}

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
      } else {
        invalidateCache('/api/notifications');
      }
    });
  });
}

/* ========== Identities management ========== */
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function fetchIdentitiesList() {
  try {
    return await fetchData('/identities');
  } catch (e) { return []; }
}

function renderIdentities(list) {
  const body = document.getElementById('identities-table-body');
  if (!body) return;
  body.innerHTML = list.map(i => {
    const serverThumb = i.thumbnail_url ? i.thumbnail_url : null;
    const localThumb = localThumbnails[i.id] ? `data:image/jpeg;base64,${localThumbnails[i.id]}` : null;
    const src = serverThumb || localThumb || '';
    const imgHtml = src ? `<img src="${escapeHtml(src)}" alt="thumb" style="width:48px;height:36px;object-fit:cover;border-radius:4px;margin-right:8px;vertical-align:middle;">` : '';
    return `
    <tr>
      <td>${escapeHtml(i.id)}</td>
      <td>${imgHtml}${escapeHtml(i.name)}</td>
      <td>${escapeHtml(i.species)}</td>
      <td>${escapeHtml(i.created_at)}</td>
      <td><a href="#" data-id="${escapeHtml(i.id)}" class="del-identity">Remover</a></td>
    </tr>
  `;
  }).join('');

  document.querySelectorAll('.del-identity').forEach(a => a.addEventListener('click', async (e) => {
    e.preventDefault();
    const id = a.dataset.id;
    await fetch(`/identities/${id}`, { method: 'DELETE' });
    await loadAndRenderIdentities();
  }));
}

async function loadAndRenderIdentities() {
  const list = await fetchIdentitiesList();
  renderIdentities(list);
}

function setupIdentityForm() {
  const addBtn = document.getElementById('add-identity-button');
  if (addBtn) addBtn.addEventListener('click', () => {
    // show the identity dialog from identities.html if present, otherwise prompt
    const dialog = document.getElementById('identity-dialog');
    if (dialog) dialog.classList.remove('hidden-panel');
  });

  // If the identities dialog exists, wire its form and inputs
  // maintain a list of selected/captured base64 images in memory
  window.identitySelected = window.identitySelected || [];
  const fileInput = document.getElementById('identity-images');
  const thumbsContainer = document.getElementById('identity-thumbnails');

  function renderIdentityThumbnails(){
    if (!thumbsContainer) return;
    thumbsContainer.innerHTML = '';
    window.identitySelected.forEach((b64, idx) => {
      const div = document.createElement('div');
      div.className = 'thumb-item';
      div.dataset.idx = idx;
      div.style.display = 'flex';
      div.style.alignItems = 'center';
      div.style.gap = '6px';
      const img = document.createElement('img');
      img.src = 'data:image/jpeg;base64,' + b64;
      img.style.width = '64px'; img.style.height = '48px'; img.style.objectFit = 'cover'; img.style.border = '1px solid #ddd';
      const btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'button-mini remove-thumb'; btn.textContent = '✕';
      btn.addEventListener('click', () => { window.identitySelected.splice(idx,1); renderIdentityThumbnails(); });
      div.appendChild(img); div.appendChild(btn);
      thumbsContainer.appendChild(div);
    });
  }

  if (fileInput){
    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(fileInput.files || []);
      for (const f of files){
        const data = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result.split(',')[1]); r.readAsDataURL(f); });
        window.identitySelected.push(data);
      }
      // clear file input so same file can be reselected later
      try{ fileInput.value = ''; }catch(e){}
      renderIdentityThumbnails();
    });
  }

  const form = document.getElementById('identity-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('identity-name').value;
      const species = document.getElementById('identity-species') ? document.getElementById('identity-species').value : 'person';
      const images = (window.identitySelected || []).slice();
      const res = await fetch('/identities', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name, species, images}) });
      if (res.status === 201) {
        const j = await res.json().catch(()=>null);
        const dialog = document.getElementById('identity-dialog');
        if (dialog) dialog.classList.add('hidden-panel');
        try{
          if (j && j.id){
            // attach local thumbnail if we have one
            if (window.identitySelected.length>0){ localThumbnails[j.id] = window.identitySelected[0]; }
            window.identitySelected = [];
            renderIdentityThumbnails();
          }
        }catch(e){}
        await loadAndRenderIdentities();
      } else {
        const j = await res.json();
        const msg = document.getElementById('identity-message');
        if (msg) msg.textContent = j.error || 'Erro';
      }
    });
  }

  // dialog controls: close/cancel
  const closeBtn = document.getElementById('identity-dialog-close');
  if (closeBtn) closeBtn.addEventListener('click', () => { const d = document.getElementById('identity-dialog'); if (d) d.classList.add('hidden-panel'); });
  const cancelBtn = document.getElementById('identity-cancel');
  if (cancelBtn) cancelBtn.addEventListener('click', () => { const d = document.getElementById('identity-dialog'); if (d) d.classList.add('hidden-panel'); });

  // capture button in dialog
  const captureBtn = document.getElementById('identity-capture');
  if (captureBtn) captureBtn.addEventListener('click', captureFromCamera);
}

async function captureFromCamera(){
  const status = document.getElementById('capture-status');
  if (status) status.textContent = 'Aguardando permissão...';
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:true});
    const video = document.createElement('video');
    video.srcObject = stream;
    await video.play();
    await new Promise(res=>setTimeout(res, 200));
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    ctx.drawImage(video, 0, 0, w, h);
    const data = c.toDataURL('image/jpeg').split(',')[1];
    const preview = document.getElementById('capture-preview');
    const previewArea = document.getElementById('capture-preview-area');
    if (preview) preview.src = 'data:image/jpeg;base64,' + data;
    if (previewArea) previewArea.style.display = '';
    if (preview) preview.dataset.last = data;
    if (status) status.textContent = 'Imagem capturada (aguardando aprovação)';
    stream.getTracks().forEach(t=>t.stop());
    video.remove();
    setTimeout(()=>{ if (status) status.textContent=''; }, 3000);
  }catch(err){
    if (status) status.textContent = 'Erro: ' + (err.message || err);
    setTimeout(()=>{ if (status) status.textContent=''; }, 4000);
  }
}

// approve / recapture for embedded dialog
document.addEventListener('click', function(e){
  if (e.target && e.target.id === 'approve-capture'){
    const preview = document.getElementById('capture-preview');
    if (preview && preview.dataset.last){
      // push into selected list and render thumbs
      window.identitySelected = window.identitySelected || [];
      window.identitySelected.push(preview.dataset.last);
      renderIdentityThumbnails();
      // also keep hidden textarea for backwards compatibility
      const b64ta = document.getElementById('identity-images-b64');
      if (b64ta) b64ta.value = (b64ta.value ? b64ta.value + '\n' : '') + preview.dataset.last;
      // hide preview but keep dialog open
      const previewArea = document.getElementById('capture-preview-area');
      if (previewArea) previewArea.style.display = 'none';
      delete preview.dataset.last;
    }
  }
  if (e.target && e.target.id === 'recapture'){
    // start a new camera capture without closing the dialog
    captureFromCamera();
  }
  // remove thumb buttons
  if (e.target && e.target.classList && e.target.classList.contains('remove-thumb')){
    const btn = e.target;
    const idx = Number(btn.parentElement.dataset.idx);
    if (!isNaN(idx)){
      window.identitySelected.splice(idx,1);
      renderIdentityThumbnails();
    }
  }
});

/* ========== Dashboard dispatcher ========== */
// Polling scoped à seção ativa: cada render só busca/renderiza os dados que
// contribuem para a seção em evidência. Mapa seção → URLs:
//   overview              /cameras /events /zones (+ /status 1x p/ grade offline)
//   recent-events         /events + /api/notifications (alertTypes p/ filtros)
//   notifications         /api/notifications
//   settings              /api/settings
//   camera-management     /cameras + /zones (dropdown de zona do form)
//   zones-management      /zones
//   identities-management /identities
const SECTION_RENDERERS = {
  'overview': renderOverviewSection,
  'recent-events': renderEventsSection,
  'notifications': renderNotifications,
  'settings': renderSettings,
  'camera-management': renderCameraManagementSection,
  'zones-management': renderZoneManagementSection,
  'event-retention': renderEventRetentionSection,
  'identities-management': loadAndRenderIdentities,
  'users-management': renderUsersSection,
  'permissions-management': renderPermissionsSection,
  'audit-log': loadAuditLog,
};

// ── Users Management ──
const USER_ROLES = [
  {value:'admin', label:'Admin (Síndico)', badge:'badge-admin'},
  {value:'chefe_seguranca', label:'Chefe de Segurança', badge:'badge-chefe'},
  {value:'vigilante', label:'Vigilante', badge:'badge-vigilante'},
  {value:'viewer', label:'Morador (Viewer)', badge:'badge-viewer'},
];
let _usersCurrentUser = null;

async function renderUsersSection() {
  try {
    const meResp = await fetch('/api/auth/me');
    if (meResp.status === 401) { window.location.href = '/login'; return; }
    const me = await meResp.json();
    _usersCurrentUser = me.user;
    // Populate role select
    const roleSelect = document.getElementById('new-role');
    if (roleSelect && roleSelect.options.length === 0) {
      USER_ROLES.forEach(r => {
        if (me.user.role === 'admin' || (me.user.role === 'chefe_seguranca' && r.value !== 'admin')) {
          const opt = document.createElement('option');
          opt.value = r.value; opt.textContent = r.label;
          roleSelect.appendChild(opt);
        }
      });
    }
    // Show/hide create button
    const createBtn = document.getElementById('btn-create-user');
    if (createBtn) createBtn.style.display = me.permissions?.create_users ? '' : 'none';
    await _loadUsers();
  } catch(e) { console.error('renderUsersSection:', e); }
}

async function _loadUsers() {
  try {
    const resp = await fetch('/api/users');
    const users = await resp.json();
    const grid = document.getElementById('users-grid');
    if (!grid) return;
    grid.innerHTML = users.map(u => {
      const ri = USER_ROLES.find(r => r.value === u.role) || {label:u.role, badge:''};
      const isMe = u.id === _usersCurrentUser?.id;
      const isLastAdmin = u.role === 'admin' && users.filter(x => x.role === 'admin' && x.active).length <= 1;
      return `<div class="user-card-inline">
        <div class="user-info">
          <h3>${u.username} ${isMe ? '<span style="font-size:.75rem;color:var(--muted);">(você)</span>' : ''}</h3>
          <p><span class="badge-role ${ri.badge}">${ri.label}</span> · ${u.active ? 'Ativo' : 'Inativo'}</p>
        </div>
        <div style="display:flex;gap:4px;">
          ${u.role==='viewer' && !isMe ? `<button class="button-mini" onclick="_openCamDialog(${u.id},'${u.username}')">Câmeras</button>` : ''}
          ${!isMe && !isLastAdmin ? `<button class="button-mini" onclick="_toggleUser(${u.id},${u.active?0:1})">${u.active?'Desativar':'Ativar'}</button>` : ''}
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.error('_loadUsers:', e); }
}

async function _toggleUser(id, active) {
  await fetch(`/api/users/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({active})});
  await _loadUsers();
}

let _camDialogUserId = null;
async function _openCamDialog(userId, username) {
  _camDialogUserId = userId;
  const camResp = await fetch('/cameras');
  const cameras = await camResp.json();
  const assignResp = await fetch(`/api/users/${userId}/cameras`);
  const assigned = await assignResp.json();
  const assignedIds = new Set(assigned.camera_ids || []);
  const list = document.getElementById('cam-dialog-list');
  list.innerHTML = cameras.length ? cameras.map(c =>
    `<label style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:.85rem;cursor:pointer;">
      <input type="checkbox" class="cam-check" value="${c.id}" ${assignedIds.has(c.id)?'checked':''}>
      <span>${c.name}</span><span style="color:var(--muted);font-size:.75rem;">${c.zone||''}</span>
    </label>`
  ).join('') : '<p style="color:var(--muted);">Nenhuma câmera</p>';
  document.getElementById('cam-dialog-title').textContent = `Câmeras — ${username}`;
  document.getElementById('cam-dialog').classList.remove('hidden-panel');
}
function _closeCamDialog() { document.getElementById('cam-dialog').classList.add('hidden-panel'); }
async function _saveCamDialog() {
  if (!_camDialogUserId) return;
  const ids = [...document.querySelectorAll('.cam-check:checked')].map(cb=>parseInt(cb.value));
  await fetch(`/api/users/${_camDialogUserId}/cameras`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({camera_ids:ids})});
  _closeCamDialog();
}

document.addEventListener('DOMContentLoaded', () => {
  const createBtn = document.getElementById('btn-create-user');
  if (createBtn) createBtn.addEventListener('click', () => {
    const form = document.getElementById('create-user-form');
    if (form.style.display === 'none') {
      document.getElementById('new-username').value = '';
      document.getElementById('new-password').value = '';
      form.style.display = 'block';
    } else {
      form.style.display = 'none';
    }
  });
  const confirmBtn = document.getElementById('btn-confirm-create');
  if (confirmBtn) confirmBtn.addEventListener('click', async () => {
    const errEl = document.getElementById('create-user-error');
    errEl.textContent = '';
    const username = document.getElementById('new-username').value.trim();
    const password = document.getElementById('new-password').value;
    const role = document.getElementById('new-role').value;
    if (!username || !password) { errEl.textContent = 'Preencha todos os campos'; return; }
    if (password.length < 6) { errEl.textContent = 'Senha mínima: 6 caracteres'; return; }
    const resp = await fetch('/api/users', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username,password,role})});
    const data = await resp.json();
    if (!resp.ok) { errEl.textContent = data.error || 'Erro'; return; }
    document.getElementById('new-username').value = '';
    document.getElementById('new-password').value = '';
    document.getElementById('create-user-form').style.display = 'none';
    await _loadUsers();
  });
});

// ── Permissions Management ──
const PERM_CATEGORIES = {
  'Monitoramento': ['view_live','view_events','view_clips','view_snapshots','view_dashboard'],
  'Eventos': ['dismiss_event','retain_event','delete_event','prune_events'],
  'Operação': ['arm_disarm'],
  'Sistema': ['manage_cameras','manage_zones','manage_identities','manage_notifications','manage_settings','manage_retention'],
  'Usuários': ['manage_users','create_users','view_users','manage_permissions'],
  'Auditoria': ['view_audit_log'],
};

async function renderPermissionsSection() {
  try {
    const meResp = await fetch('/api/auth/me');
    const me = await meResp.json();
    if (!me.permissions?.manage_permissions) {
      document.getElementById('perm-body').innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);">Sem permissão</td></tr>';
      return;
    }
    const [permsResp, defsResp] = await Promise.all([fetch('/api/permissions'), fetch('/api/permissions/definitions')]);
    const permissions = await permsResp.json();
    const definitions = await defsResp.json();
    const roles = ['admin','chefe_seguranca','vigilante','viewer'];
    let html = '';
    for (const [cat, perms] of Object.entries(PERM_CATEGORIES)) {
      html += `<tr><td colspan="5" style="font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;background:var(--bg);padding:.3rem .6rem;">${cat}</td></tr>`;
      for (const perm of perms) {
        html += `<tr><td title="${perm}" style="text-align:left;">${definitions[perm]||perm}</td>`;
        for (const role of roles) {
          const checked = permissions[role]?.[perm] ? 'checked' : '';
          const disabled = role==='admin' ? 'disabled' : '';
          html += `<td><input type="checkbox" class="perm-toggle" data-role="${role}" data-perm="${perm}" ${checked} ${disabled}></td>`;
        }
        html += '</tr>';
      }
    }
    document.getElementById('perm-body').innerHTML = html;
    // Save button
    document.getElementById('btn-save-perms').onclick = async () => {
      const status = document.getElementById('perm-status');
      const toggles = document.querySelectorAll('.perm-toggle');
      const updates = [];
      toggles.forEach(t => { if (!t.disabled) updates.push({role:t.dataset.role, permission:t.dataset.perm, enabled:t.checked}); });
      const resp = await fetch('/api/permissions', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({permissions:updates})});
      status.textContent = resp.ok ? '✓ Salvo' : 'Erro ao salvar';
      status.style.color = resp.ok ? 'var(--primary)' : 'var(--danger)';
      setTimeout(()=>{ status.textContent=''; }, 3000);
    };
  } catch(e) { console.error('renderPermissionsSection:', e); }
}

// ── Audit Log ──
const AUDIT_ACTION_LABELS = {login:'Login',create_user:'Criar usuário',update_user:'Editar usuário',create_api_key:'Criar API key',delete_api_key:'Deletar API key',update_permissions:'Atualizar permissões',setup_create_admin:'Setup'};
const AUDIT_ACTION_CLASSES = {login:'action-login',create_user:'action-create',create_api_key:'action-create',update_user:'action-update',update_permissions:'action-update',delete_api_key:'action-delete'};

async function loadAuditLog() {
  try {
    const actionFilter = document.getElementById('audit-action-filter')?.value || '';
    const params = new URLSearchParams({limit:50});
    if (actionFilter) params.set('action', actionFilter);
    const resp = await fetch('/api/audit?' + params.toString());
    const entries = await resp.json();
    const tbody = document.getElementById('audit-body');
    if (!tbody) return;
    if (!entries.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:1rem;">Nenhum registro</td></tr>'; return; }
    tbody.innerHTML = entries.map(e => {
      const label = AUDIT_ACTION_LABELS[e.action] || e.action;
      const cls = AUDIT_ACTION_CLASSES[e.action] || '';
      const date = new Date(e.created_at).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'});
      return `<tr><td style="white-space:nowrap;font-size:.8rem;">${date}</td><td>${e.user_id||'—'}</td><td><span class="action-badge ${cls}">${label}</span></td><td>${e.target_type||'—'} ${e.target_id||''}</td><td>${e.ip_address||'—'}</td></tr>`;
    }).join('');
  } catch(e) { console.error('loadAuditLog:', e); }
}

async function renderDashboard() {
  const renderer = SECTION_RENDERERS[currentSection];
  if (!renderer) return;
  try {
    await renderer();
  } catch (error) {
    // Falha de uma seção não pode matar o polling nem as demais seções.
  }
}

async function renderOverviewSection() {
  let payload;
  try {
    payload = await fetchData('/api/dashboard');
  } catch (e) { return; }
  lastDashboardPayload = payload;
  const cameras = payload.cameras || [];
  const events = payload.events || [];
  const zones = payload.zones || [];
  const n0events = payload.n0_events || [];
  const n0ByCamera = countEventsByCamera(n0events);
  const summaryCards = document.getElementById('summary-cards');
  const lastEvent = events.length > 0 ? events[0] : null;
  const lastEventTime = lastEvent ? new Date(lastEvent.timestamp).toLocaleString() : 'Nenhum evento';
  summaryCards.innerHTML = [
    createSummaryCard('Câmeras conectadas', cameras.length, 'Fontes ativas de vídeo'),
    createSummaryCard('Zonas cadastradas', zones.length, 'Classificações de alerta'),
    createSummaryCard('Eventos recentes', events.length, 'Últimos 100 eventos carregados'),
    createSummaryCard('Último evento', lastEvent ? lastEvent.event_type : 'Nenhum', lastEventTime),
  ].join('');
  const lastEventMap = buildLastEventMap(events);
  const sortedCameras = sortCamerasByLastEvent(cameras, lastEventMap);
  const cameraTiles = document.getElementById('camera-tiles');
  const workerStatus = payload.worker_status || null;
  if (!cameraTiles.dataset.rendered) {
    if (sortedCameras.length > 0) {
      cameraTiles.dataset.rendered = '1';
      renderCameraTiles(sortedCameras, workerStatus, lastEventMap, n0ByCamera);
    }
    // if no cameras yet, leave dataset.rendered unset so next poll retries
  } else {
    updateOfflineSection(sortedCameras, workerStatus, lastEventMap, n0ByCamera);
  }
  updateVisibleSnapshots(sortedCameras);
}

async function renderEventsSection() {
  const state = readFilterState();
  const params = new URLSearchParams();
  if (state.level) params.set('level', state.level);
  // Retidos são protegidos do prune e não podem ficar fora do corte de 100:
  // com o filtro ativo o servidor retorna todos (limite 1000).
  if (state.retained) params.set('retained', '1');
  const events = await fetchData('/events?' + params.toString());
  lastEvents = events;
  lastAlertTypes = await renderEvents(events);
}

async function renderCameraManagementSection() {
  const cameras = await fetchData('/cameras');
  const zones = await fetchData('/zones');
  renderCameraManagement(cameras);
  populateZoneDropdown(zones);
  bindCameraManagementActions(cameras, zones);
}

async function renderZoneManagementSection() {
  const zones = await fetchData('/zones');
  renderZoneManagement(zones);
  bindZoneManagementActions(zones);
}

// Listeners re-bindados apenas na seção renderizada (camera-management):
// a tabela é recriada a cada render (innerHTML), então os botões novos
// precisam de bind — sem duplicação porque os nós antigos são descartados.
function bindCameraManagementActions(cameras, zones) {
  document.querySelectorAll('.delete-camera').forEach(button => {
    button.addEventListener('click', () => {
      deleteCamera(button.dataset.cameraId);
    });
  });

  document.querySelectorAll('.edit-camera').forEach(button => {
    button.addEventListener('click', async () => {
      const cameraId = Number(button.dataset.cameraId);
      const camera = cameras.find(cam => cam.id === cameraId);
      if (camera) {
        populateZoneDropdown(zones, camera.zone);
        showCameraForm('edit', camera);
      }
    });
  });

  document.querySelectorAll('.clips-camera').forEach(button => {
    button.addEventListener('click', () => {
      const cameraId = button.dataset.cameraId;
      const camera = cameras.find(c => String(c.id) === String(cameraId));
      openClipHistory(cameraId, camera ? camera.name : 'Câmera');
    });
  });
}

function bindZoneManagementActions(zones) {
  document.querySelectorAll('.delete-zone').forEach(button => {
    button.addEventListener('click', () => {
      deleteZone(button.dataset.zoneId);
    });
  });

  document.querySelectorAll('.edit-zone').forEach(button => {
    button.addEventListener('click', async () => {
      const zoneId = Number(button.dataset.zoneId);
      const zone = zones.find(z => z.id === zoneId);
      if (zone) {
        showZoneForm('edit', zone);
      }
    });
  });
}

/* ========== Setup ========== */

function setupCameraForm() {
  const form = document.getElementById('camera-form');
  form.addEventListener('submit', submitCameraForm);

  const addButton = document.getElementById('add-camera-button');
  if (addButton) {
    addButton.addEventListener('click', () => {
      setActiveSection('camera-management');
      showCameraForm('add');
    });
  }

  const cancelButton = document.getElementById('cancel-camera-edit');
  if (cancelButton) {
    cancelButton.addEventListener('click', () => {
      hideCameraForm();
    });
  }

  const closeButton = document.getElementById('camera-dialog-close');
  if (closeButton) {
    closeButton.addEventListener('click', () => {
      hideCameraForm();
    });
  }

  // Preview ao vivo dos polígonos enquanto o usuário digita (debounced).
  ['camera-exclusion-zones', 'camera-mask-polygons'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', schedulePreviewRedraw);
  });
}

function setupZoneForm() {
  const form = document.getElementById('zone-form');
  form.addEventListener('submit', submitZoneForm);

  const addButton = document.getElementById('add-zone-button');
  if (addButton) {
    addButton.addEventListener('click', () => {
      setActiveSection('zones-management');
      showZoneForm('add');
    });
  }

  const cancelButton = document.getElementById('cancel-zone-edit');
  if (cancelButton) {
    cancelButton.addEventListener('click', () => {
      hideZoneForm();
    });
  }

  const closeButton = document.getElementById('zone-dialog-close');
  if (closeButton) {
    closeButton.addEventListener('click', () => {
      hideZoneForm();
    });
  }
}

setActiveSection('overview');
setupSidebarNavigation();
renderDashboard();
renderStatusFooter(); // footer fixo global: renderiza no boot (render por seção não busca /status)
dashboardReady = true;
setupCameraForm();
setupZoneForm();
setupSettings();
setupEventRetention();
setupEventFilters();
setupOfflineToggle();
setupSystemStatusLink();
setupIdentityForm();
const emptyAddCamera = document.getElementById('empty-add-camera');
if (emptyAddCamera) {
  emptyAddCamera.addEventListener('click', () => {
    setActiveSection('camera-management');
    showCameraForm('add');
  });
}
document.getElementById('clip-history-close').addEventListener('click', closeClipHistory);
// Delegated click: ao clicar no .event-thumb dentro de #events-grid,
// abre o mesmo dialog usado pelo historico de thumbnails da camera. Reaproveita
// openThumbDetail para mostrar a imagem com zoom/pan e os metadados do evento.
function setupEventCardThumbPreview() {
  const grid = document.getElementById('events-grid');
  if (!grid || grid._thumbPreviewWired) return;
  grid._thumbPreviewWired = true;
  grid.addEventListener('click', (e) => {
    const thumb = e.target.closest('.event-thumb');
    if (!thumb || !thumb.tagName || thumb.tagName.toLowerCase() !== 'img') return;
    const card = thumb.closest('.event-card');
    if (!card) return;
    // Recupera os dados do card. Foi salvo como data-attrs no card durante
    // renderEventCards; se nao estiver (createEventCard legado), busca do
    // card-content textual como fallback.
    openEventThumbDialog(card, thumb.src);
  });

  // Retain checkbox handler (delegated)
  grid.addEventListener('change', async (e) => {
    const checkbox = e.target.closest('.retain-checkbox input[type="checkbox"]');
    if (!checkbox) return;
    const eventId = checkbox.dataset.eventId;
    if (!eventId) return;
    const retain = checkbox.checked;
    try {
      const res = await fetch(`/api/events/${eventId}/retain`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ retain })
      });
      const data = await res.json();
      if (!res.ok) {
        checkbox.checked = !retain; // revert on error
        alert(data.error || 'Erro ao atualizar');
      } else {
        // Update UI
        const card = checkbox.closest('.event-card');
        if (card) {
          card.dataset.retained = retain ? '1' : '0';
          const badge = card.querySelector('.badge-ok');
          if (retain && !badge) {
            // Add retained badge
            const header = card.querySelector('.event-card-header .event-type');
            if (header) {
              const badgeEl = document.createElement('span');
              badgeEl.className = 'badge badge-ok';
              badgeEl.textContent = 'retido';
              header.appendChild(badgeEl);
            }
          } else if (!retain && badge) {
            badge.remove();
          }
        }
      }
    } catch (e) {
      checkbox.checked = !retain;
      alert('Erro ao atualizar');
    }
  });
}
function openEventThumbDialog(card, imgSrc) {
  const meta = {
    camera: card.dataset.cameraName || card.dataset.cameraId || '',
    zone: card.dataset.zone || '',
    details: card.dataset.details || '',
  };
  openThumbDetail(
    imgSrc,
    card.dataset.timestamp || new Date().toISOString(),
    card.dataset.eventType || '',
    card.dataset.level != null ? Number(card.dataset.level) : null,
    card.dataset.disposition || '',
    card.dataset.dropped === '1',
    meta,
  );
}
setupEventCardThumbPreview();
setupHoverFreshSnapshots();

setInterval(() => {
  renderDashboard();
  renderStatusFooter();
}, 5000);
