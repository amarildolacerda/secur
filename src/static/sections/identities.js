// identities.js — seção "Identidades"
import { fetchData, escapeHtml } from '../shared.js';

let localThumbnails = {};
let identitySelected = [];

function fetchIdentitiesList() {
  try {
    return fetchData('/identities');
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

function renderIdentityThumbnails() {
  const thumbsContainer = document.getElementById('identity-thumbnails');
  if (!thumbsContainer) return;
  thumbsContainer.innerHTML = '';
  identitySelected.forEach((b64, idx) => {
    const div = document.createElement('div');
    div.className = 'thumb-item';
    div.dataset.idx = idx;
    div.style.display = 'flex';
    div.style.alignItems = 'center';
    div.style.gap = '6px';
    const img = document.createElement('img');
    img.src = 'data:image/jpeg;base64,' + b64;
    img.style.width = '64px'; img.style.height = '48px'; img.style.objectFit = 'cover'; img.style.border = '1px solid var(--border)';
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'button-mini remove-thumb'; btn.textContent = '✕';
    btn.addEventListener('click', () => { identitySelected.splice(idx, 1); renderIdentityThumbnails(); });
    div.appendChild(img); div.appendChild(btn);
    thumbsContainer.appendChild(div);
  });
}

function setupIdentityForm() {
  const addBtn = document.getElementById('add-identity-button');
  if (addBtn) addBtn.addEventListener('click', () => {
    const dialog = document.getElementById('identity-dialog');
    if (dialog) dialog.classList.remove('hidden-panel');
  });

  const fileInput = document.getElementById('identity-images');
  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(fileInput.files || []);
      for (const f of files) {
        const data = await new Promise((res) => {
          const r = new FileReader();
          r.onload = () => res(r.result.split(',')[1]);
          r.readAsDataURL(f);
        });
        identitySelected.push(data);
      }
      try { fileInput.value = ''; } catch (e) {}
      renderIdentityThumbnails();
    });
  }

  const form = document.getElementById('identity-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('identity-name').value;
      const species = document.getElementById('identity-species') ? document.getElementById('identity-species').value : 'person';
      const images = identitySelected.slice();
      const res = await fetch('/identities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, species, images })
      });
      if (res.status === 201) {
        const j = await res.json().catch(() => null);
        const dialog = document.getElementById('identity-dialog');
        if (dialog) dialog.classList.add('hidden-panel');
        try {
          if (j && j.id && identitySelected.length > 0) {
            localThumbnails[j.id] = identitySelected[0];
          }
        } catch (e) {}
        identitySelected = [];
        renderIdentityThumbnails();
        await loadAndRenderIdentities();
      } else {
        const j = await res.json();
        const msg = document.getElementById('identity-message');
        if (msg) msg.textContent = j.error || 'Erro';
      }
    });
  }

  const closeBtn = document.getElementById('identity-dialog-close');
  if (closeBtn) closeBtn.addEventListener('click', () => {
    const d = document.getElementById('identity-dialog');
    if (d) d.classList.add('hidden-panel');
  });
  const cancelBtn = document.getElementById('identity-cancel');
  if (cancelBtn) cancelBtn.addEventListener('click', () => {
    const d = document.getElementById('identity-dialog');
    if (d) d.classList.add('hidden-panel');
  });

  const captureBtn = document.getElementById('identity-capture');
  if (captureBtn) captureBtn.addEventListener('click', captureFromCamera);
}

async function captureFromCamera() {
  const status = document.getElementById('capture-status');
  if (status) status.textContent = 'Aguardando permissão...';
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    const video = document.createElement('video');
    video.srcObject = stream;
    await video.play();
    await new Promise(res => setTimeout(res, 200));
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
    stream.getTracks().forEach(t => t.stop());
    video.remove();
    setTimeout(() => { if (status) status.textContent = ''; }, 3000);
  } catch (err) {
    if (status) status.textContent = 'Erro: ' + (err.message || err);
    setTimeout(() => { if (status) status.textContent = ''; }, 4000);
  }
}

function captureClickHandler(e) {
  if (e.target && e.target.id === 'approve-capture') {
    const preview = document.getElementById('capture-preview');
    if (preview && preview.dataset.last) {
      identitySelected.push(preview.dataset.last);
      renderIdentityThumbnails();
      const b64ta = document.getElementById('identity-images-b64');
      if (b64ta) b64ta.value = (b64ta.value ? b64ta.value + '\n' : '') + preview.dataset.last;
      const previewArea = document.getElementById('capture-preview-area');
      if (previewArea) previewArea.style.display = 'none';
      delete preview.dataset.last;
    }
  }
  if (e.target && e.target.id === 'recapture') {
    captureFromCamera();
  }
  if (e.target && e.target.classList && e.target.classList.contains('remove-thumb')) {
    const btn = e.target;
    const idx = Number(btn.parentElement.dataset.idx);
    if (!isNaN(idx)) {
      identitySelected.splice(idx, 1);
      renderIdentityThumbnails();
    }
  }
}

export function initSection() {
  identitySelected = [];
  setupIdentityForm();
  loadAndRenderIdentities();
  document.addEventListener('click', captureClickHandler);
}

export function teardownSection() {
  document.removeEventListener('click', captureClickHandler);
}
