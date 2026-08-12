let cameraEditId = null;
let zoneEditId = null;
const appStartTime = Date.now();

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

  return `
    <div class="card camera-card">
      <div class="camera-card-header">
        <strong>${camera.name}</strong>
        <span class="camera-badge">ID ${camera.id}</span>
      </div>
      <p>Zona: ${zoneLabel}</p>
      <p class="camera-source">Fonte: ${camera.source}</p>
      <img
        class="camera-preview"
        src="/camera/${camera.id}/snapshot?ts=${Date.now()}"
        alt="Preview da câmera"
        onerror="this.style.display='none'"
      />
    </div>
  `;
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
  return `
    <tr>
      <td>${event.id}</td>
      <td>${new Date(event.timestamp).toLocaleString()}</td>
      <td>${event.camera_id}</td>
      <td>${event.zone || "-"}</td>
      <td>${event.event_type}</td>
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

async function submitCameraForm(event) {
  event.preventDefault();

  const nameInput = document.getElementById('camera-name');
  const sourceInput = document.getElementById('camera-source');
  const zoneInput = document.getElementById('camera-zone');
  const message = document.getElementById('camera-form-message');

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

  let response;
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
  renderDashboard();
}

async function deleteCamera(cameraId) {
  if (!confirm('Tem certeza que deseja excluir esta câmera?')) return;
  const response = await fetch(`/cameras/${cameraId}`, {
    method: 'DELETE',
  });
  if (response.ok) {
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

  const cameraList = document.getElementById('camera-list');
  cameraList.innerHTML = cameras.map(createCameraCard).join('');

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
setInterval(() => {
  renderDashboard();
  renderStatusFooter();
}, 5000);
