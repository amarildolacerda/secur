let cameraEditId = null;
let zoneEditId = null;
const appStartTime = Date.now();
// local thumbnails for recently captured images (id -> base64)
const localThumbnails = {};

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

function createSummaryCard(title, value, subtitle = "") {
  return `
    <div class="card">
      <h3>${title}</h3>
      <p class="summary-value">${value}</p>
      <p>${subtitle}</p>
    </div>
  `;
}

function setActiveSection(sectionId) {
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

function createCameraCard(camera) {
  const zoneLabel = camera.zone || '-';
  const imgId = `snapshot-${camera.id}`;

  return `
    <div class="card camera-card">
      <div class="camera-card-header">
        <strong>${camera.name}</strong>
        <span class="camera-badge">ID ${camera.id}</span>
      </div>
      <p>Zona: ${zoneLabel}</p>
      <p class="camera-source">Fonte: ${camera.source}</p>
      <div class="camera-preview-wrapper" onclick="openLivePlayer(${camera.id}, '${camera.name}', '${camera.source}')" style="cursor:pointer;">
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
    img.src = `/camera/${cameraId}/snapshot?ts=${Date.now()}`;
  }
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

function createCameraRow(camera) {
  return `
    <tr>
      <td>${camera.id}</td>
      <td>${camera.name}</td>
      <td>${camera.source}</td>
      <td>${camera.zone || '-'}</td>
      <td class="table-actions">
        <button class="button-secondary button-mini edit-camera" data-camera-id="${camera.id}">Editar</button>
        <button class="button-secondary button-mini delete-camera" data-camera-id="${camera.id}">Excluir</button>
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

function createEventRow(event) {
  const isInfo = event.event_type === 'snapshot_info';
  const badge = isInfo ? '<span class="badge-info">info</span>' : '';
  return `
    <tr class="${isInfo ? 'event-info' : ''}">
      <td>${event.id}</td>
      <td>${new Date(event.timestamp).toLocaleString()}</td>
      <td>${event.camera_id}</td>
      <td>${event.zone || "-"}</td>
      <td>${event.event_type} ${badge}</td>
      <td>${event.details || "-"}</td>
    </tr>
  `;
}

/* ========== Camera form ========== */

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

  if (message) {
    message.textContent = '';
    message.classList.remove('error');
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
  const cameraList = document.getElementById('camera-list');
  if (cameraList) delete cameraList.dataset.rendered;
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

/* ========== Footer ========== */

async function renderStatusFooter() {
  try {
    const status = await fetchData('/status');
    const health = document.getElementById('status-health');
    const cameras = document.getElementById('status-cameras');
    const workers = document.getElementById('status-workers');
    const recent = document.getElementById('status-recent');

    if (health) {
      health.textContent = `Status: ${status.status || 'ok'}`;
      health.className = status.status === 'ok' ? 'status-good' : 'status-bad';
    }
    if (cameras) {
      cameras.textContent = `Câmeras: ${status.camera_count ?? '—'}`;
    }
    if (workers) {
      workers.textContent = `Workers: ${status.active_workers ?? '—'}`;
    }
    if (recent) {
      recent.textContent = `Eventos recentes: ${status.recent_events ?? '—'}`;
    }

    const uptime = document.getElementById('status-uptime');
    if (uptime) {
      uptime.textContent = `Uptime: ${formatUptime(Date.now() - appStartTime)}`;
    }
  } catch (error) {
    const health = document.getElementById('status-health');
    if (health) {
      health.textContent = 'Status: indisponível';
      health.className = 'status-bad';
    }
  }
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

async function renderDashboard() {
  const cameras = await fetchData('/cameras');
  const events = await fetchData('/events');
  const zones = await fetchData('/zones');

  const summaryCards = document.getElementById('summary-cards');
  const lastEvent = events.length > 0 ? events[0] : null;
  const lastEventTime = lastEvent ? new Date(lastEvent.timestamp).toLocaleString() : 'Nenhum evento';

  summaryCards.innerHTML = [
    createSummaryCard('Câmeras conectadas', cameras.length, 'Fontes ativas de vídeo'),
    createSummaryCard('Zonas cadastradas', zones.length, 'Classificações de alerta'),
    createSummaryCard('Eventos recentes', events.length, 'Últimos 100 eventos carregados'),
    createSummaryCard('Último evento', lastEvent ? lastEvent.event_type : 'Nenhum', lastEventTime),
  ].join('');

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

  const eventsTable = document.getElementById('events-table');
  eventsTable.innerHTML = events.map(createEventRow).join('');

  renderCameraManagement(cameras);
  renderZoneManagement(zones);
  populateZoneDropdown(zones);

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

  await renderStatusFooter();
  try { await loadAndRenderIdentities(); } catch (e) { /* ignore */ }
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
setupCameraForm();
setupZoneForm();
  setupIdentityForm();
setInterval(() => {
  renderDashboard();
  renderStatusFooter();
}, 5000);
