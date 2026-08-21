// zones.js — seção "Zonas"
import { fetchData, showMenuMessage } from '../shared.js';

let zoneEditId = null;

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
  refreshZones();
}

async function deleteZone(zoneId) {
  if (!confirm('Tem certeza que deseja excluir esta zona?')) return;
  const response = await fetch(`/zones/${zoneId}`, { method: 'DELETE' });
  if (response.ok) {
    refreshZones();
  }
}

function renderZoneManagement(zones) {
  const body = document.getElementById('zone-table-body');
  if (body) {
    body.innerHTML = zones.map(createZoneRow).join('');
  }
}

function bindZoneManagementActions(zones) {
  document.querySelectorAll('.delete-zone').forEach(button => {
    button.addEventListener('click', () => {
      deleteZone(button.dataset.zoneId);
    });
  });

  document.querySelectorAll('.edit-zone').forEach(button => {
    button.addEventListener('click', () => {
      const zoneId = Number(button.dataset.zoneId);
      const zone = zones.find(z => z.id === zoneId);
      if (zone) showZoneForm('edit', zone);
    });
  });
}

function setupZoneForm() {
  const form = document.getElementById('zone-form');
  if (form) form.addEventListener('submit', submitZoneForm);

  const addButton = document.getElementById('add-zone-button');
  if (addButton) {
    addButton.addEventListener('click', () => {
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

async function refreshZones() {
  const zones = await fetchData('/zones');
  renderZoneManagement(zones);
  bindZoneManagementActions(zones);
}

export function initSection() {
  setupZoneForm();
  refreshZones();
}

export function teardownSection() {
  // listeners recriados a cada initSection
}
