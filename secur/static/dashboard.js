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

function createCameraCard(camera) {
  return `
    <div class="card camera-card">
      <strong>${camera.name}</strong>
      <p>ID: ${camera.id}</p>
      <p>Zona: ${camera.zone || '-'}</p>
      <p>Fonte: ${camera.source}</p>
      <img
        class="camera-preview"
        src="/camera/${camera.id}/snapshot?ts=${Date.now()}"
        alt="Preview da câmera"
        onerror="this.style.display='none'"
      />
      <button class="button-secondary delete-camera" data-camera-id="${camera.id}">Remover</button>
    </div>
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

async function addCamera(event) {
  event.preventDefault();

  const nameInput = document.getElementById('camera-name');
  const sourceInput = document.getElementById('camera-source');
  const zoneInput = document.getElementById('camera-zone');
  const message = document.getElementById('camera-form-message');

  const payload = {
    name: nameInput.value.trim(),
    source: sourceInput.value.trim(),
    zone: zoneInput.value.trim(),
  };

  if (!payload.name || !payload.source) {
    message.textContent = 'Nome e fonte são obrigatórios.';
    message.classList.add('error');
    return;
  }

  const response = await fetch('/cameras', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json();
    message.textContent = error.error || 'Falha ao adicionar câmera.';
    message.classList.add('error');
    return;
  }

  nameInput.value = '';
  sourceInput.value = '';
  zoneInput.value = '';
  message.textContent = 'Câmera adicionada com sucesso.';
  message.classList.remove('error');
  renderDashboard();
}

async function deleteCamera(cameraId) {
  const response = await fetch(`/cameras/${cameraId}`, {
    method: 'DELETE',
  });
  if (response.ok) {
    renderDashboard();
  }
}

async function renderDashboard() {
  const cameras = await fetchData('/cameras');
  const events = await fetchData('/events');

  const summaryCards = document.getElementById('summary-cards');
  const lastEvent = events.length > 0 ? events[0] : null;
  const lastEventTime = lastEvent ? new Date(lastEvent.timestamp).toLocaleString() : 'Nenhum evento';

  summaryCards.innerHTML = [
    createSummaryCard('Câmeras conectadas', cameras.length, 'Fontes ativas de vídeo'),
    createSummaryCard('Eventos recentes', events.length, 'Últimos 100 eventos carregados'),
    createSummaryCard('Último evento', lastEvent ? lastEvent.event_type : 'Nenhum', lastEventTime),
  ].join('');

  const cameraList = document.getElementById('camera-list');
  cameraList.innerHTML = cameras.map(createCameraCard).join('');

  const eventsTable = document.getElementById('events-table');
  eventsTable.innerHTML = events.map(createEventRow).join('');

  document.querySelectorAll('.delete-camera').forEach(button => {
    button.addEventListener('click', () => {
      deleteCamera(button.dataset.cameraId);
    });
  });
}

function setupForm() {
  const form = document.getElementById('camera-form');
  form.addEventListener('submit', addCamera);
}

renderDashboard();
setupForm();
setInterval(renderDashboard, 5000);
