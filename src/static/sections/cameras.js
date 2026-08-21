// cameras.js — seção "Câmeras"
import { fetchData, fetchCached, invalidateCache, escapeHtml, showMenuMessage } from '../shared.js';

const PREVIEW_DEBOUNCE_MS = 350;
let previewFrame = null;
let previewLoadToken = 0;
let previewDebounceTimer = null;
let previewNote = 'add';
let cameraEditId = null;

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
    if (response.status === 401) { window.location.href = '/login'; return; }
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
    refreshCameras();
  } finally {
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
    refreshCameras();
  }
}

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

  const knownKeys = new Set();
  ALERT_CLASS_GROUPS.forEach(g => g.classes && g.classes.forEach(c => knownKeys.add(c)));
  const miscClasses = classes.filter(c => !knownKeys.has(c));

  const sections = ALERT_CLASS_GROUPS
    .filter(g => !g.classes || g.classes.some(c => classes.includes(c)))
    .map((g, idx) => {
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
      d.style.display = visibleCount > 0 ? '' : 'none';
    });
  });
  container.querySelectorAll('.class-group-toggle').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const det = btn.closest('details');
      det.querySelectorAll('input[type=checkbox]').forEach(cb => { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); });
    });
  });
}

function renderCameraManagement(cameras) {
  const body = document.getElementById('camera-table-body');
  if (body) {
    body.innerHTML = cameras.map(createCameraRow).join('');
  }
}

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

function setupCameraForm() {
  const form = document.getElementById('camera-form');
  if (form) form.addEventListener('submit', submitCameraForm);

  const addButton = document.getElementById('add-camera-button');
  if (addButton) {
    addButton.addEventListener('click', () => {
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

  ['camera-exclusion-zones', 'camera-mask-polygons'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', schedulePreviewRedraw);
  });
}

async function refreshCameras() {
  const [cameras, zones] = await Promise.all([
    fetchData('/cameras'),
    fetchData('/zones'),
  ]);
  renderCameraManagement(cameras);
  populateZoneDropdown(zones);
  bindCameraManagementActions(cameras, zones);
}

export function initSection() {
  setupCameraForm();
  refreshCameras();
}

export function teardownSection() {
  // listeners são recriados a cada initSection (elementos substituídos via innerHTML)
}
