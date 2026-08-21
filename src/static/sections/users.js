// users.js — seção "Usuários"
const ROLES = [
  { value: 'admin', label: 'Admin (Síndico)', badge: 'badge-admin' },
  { value: 'chefe_seguranca', label: 'Chefe de Segurança', badge: 'badge-chefe' },
  { value: 'vigilante', label: 'Vigilante', badge: 'badge-vigilante' },
  { value: 'viewer', label: 'Morador (Viewer)', badge: 'badge-viewer' },
];
let currentUser = null;
let currentPermissions = null;
let users = [];
let editingUser = null;
let cameras = [];
let editingUserId = null;

async function init() {
  const meResp = await fetch('/api/auth/me');
  if (meResp.status === 401) { window.location.href = '/login'; return; }
  const me = await meResp.json();
  currentUser = me.user;
  currentPermissions = me.permissions || {};
  populateRoleSelect(document.getElementById('user-role'));
  const canCreate = currentPermissions.create_users;
  if (!canCreate) {
    const btn = document.getElementById('btn-open-create-user');
    if (btn) btn.style.display = 'none';
  }
  await loadUsers();
}

function populateRoleSelect(select) {
  select.innerHTML = '';
  ROLES.forEach(r => {
    if (currentUser.role === 'admin' || (currentUser.role === 'chefe_seguranca' && r.value !== 'admin')) {
      const opt = document.createElement('option');
      opt.value = r.value; opt.textContent = r.label;
      select.appendChild(opt);
    }
  });
}

async function loadUsers() {
  const resp = await fetch('/api/users');
  users = await resp.json();
  render();
}

function render() {
  const tbody = document.getElementById('users-table-body');
  const canManage = currentPermissions.manage_users;
  if (!users.length) {
    tbody.innerHTML = '<tr class="table-empty"><td colspan="5">Nenhum usuário cadastrado.</td></tr>';
    return;
  }
  tbody.innerHTML = users.map(u => {
    const roleInfo = ROLES.find(r => r.value === u.role) || { label: u.role, badge: '' };
    const isMe = u.id === currentUser.id;
    const isLastAdmin = u.role === 'admin' && users.filter(x => x.role === 'admin' && x.active).length <= 1;
    return `<tr>
      <td>${u.username} ${isMe ? '<span style="font-size:.75rem;color:var(--muted);">(você)</span>' : ''}</td>
      <td><span class="badge-role ${roleInfo.badge}">${roleInfo.label}</span></td>
      <td><span class="badge ${u.active ? 'on' : 'off'}">${u.active ? 'Ativo' : 'Inativo'}</span></td>
      <td>${u.created_at ? new Date(u.created_at).toLocaleDateString('pt-BR') : ''}</td>
      <td><div class="table-actions">
        ${u.role === 'viewer' && !isMe ? `<button class="button-mini" onclick="openCameras(${u.id}, '${u.username}')">Câmeras</button>` : ''}
        ${canManage ? `<button class="button-mini" onclick="openUserDialog(${u.id})">Editar</button>` : ''}
        ${!isMe && !isLastAdmin ? `<button class="button-mini" onclick="toggleUser(${u.id}, ${u.active ? 0 : 1})">${u.active ? 'Desativar' : 'Ativar'}</button>` : ''}
      </div></td>
    </tr>`;
  }).join('');
}

async function toggleUser(id, active) {
  if (!confirm('Tem certeza que deseja ' + (active ? 'ativar' : 'desativar') + ' este usuário?')) return;
  await fetch(`/api/users/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active }),
  });
  await loadUsers();
}

function openUserDialog(userId) {
  const errEl = document.getElementById('user-form-message');
  if (errEl) errEl.textContent = '';
  const pwRow = document.getElementById('user-password-row');
  const pwInput = document.getElementById('user-password');
  if (userId == null) {
    editingUser = null;
    document.getElementById('user-dialog-title').textContent = 'Adicionar usuário';
    document.getElementById('user-form').reset();
    pwRow.style.display = '';
    pwInput.required = true;
  } else {
    const u = users.find(x => x.id === userId);
    if (!u) return;
    editingUser = u.id;
    document.getElementById('user-dialog-title').textContent = 'Editar usuário';
    document.getElementById('user-username').value = u.username;
    document.getElementById('user-role').value = u.role;
    pwInput.value = '';
    pwRow.style.display = 'none';
    pwInput.required = false;
  }
  document.getElementById('user-dialog').classList.remove('hidden-panel');
}

function closeUserDialog() {
  document.getElementById('user-dialog').classList.add('hidden-panel');
  editingUser = null;
}

async function openCameras(userId, username) {
  editingUserId = userId;
  document.getElementById('cam-dialog-title').textContent = `Câmeras de ${username}`;
  const camResp = await fetch('/cameras');
  cameras = await camResp.json();
  const assignResp = await fetch(`/api/users/${userId}/cameras`);
  const assigned = await assignResp.json();
  const assignedIds = new Set(assigned.camera_ids || []);
  const list = document.getElementById('cam-list');
  if (!cameras.length) {
    list.innerHTML = '<p style="color:var(--muted);">Nenhuma câmera cadastrada</p>';
  } else {
    list.innerHTML = cameras.map(c =>
      `<label style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:.85rem;cursor:pointer;">
        <input type="checkbox" class="cam-check" value="${c.id}" ${assignedIds.has(c.id) ? 'checked' : ''}>
        <span>${c.name}</span>
        <span style="color:var(--muted);font-size:.75rem;">${c.zone || ''}</span>
      </label>`
    ).join('');
  }
  document.getElementById('cam-dialog').classList.remove('hidden-panel');
}

function closeCamDialog() {
  document.getElementById('cam-dialog').classList.add('hidden-panel');
  editingUserId = null;
}

async function saveCameras() {
  if (!editingUserId) return;
  const checked = [...document.querySelectorAll('.cam-check:checked')].map(cb => parseInt(cb.value));
  await fetch(`/api/users/${editingUserId}/cameras`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ camera_ids: checked }),
  });
  closeCamDialog();
}

// expõe handlers usados por onclick inline
window.openCameras = openCameras;
window.openUserDialog = openUserDialog;
window.toggleUser = toggleUser;
window.closeUserDialog = closeUserDialog;
window.closeCamDialog = closeCamDialog;
window.saveCameras = saveCameras;

export function initSection() {
  const form = document.getElementById('user-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const errEl = document.getElementById('user-form-message');
      errEl.textContent = '';
      const username = document.getElementById('user-username').value.trim();
      const password = document.getElementById('user-password').value;
      const role = document.getElementById('user-role').value;
      if (!username) { errEl.textContent = 'Preencha o usuário'; return; }
      if (editingUser == null) {
        if (!password) { errEl.textContent = 'Preencha a senha'; return; }
        if (password.length < 6) { errEl.textContent = 'Senha mínima: 6 caracteres'; return; }
        const resp = await fetch('/api/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password, role }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { errEl.textContent = data.error || 'Erro ao criar'; return; }
      } else {
        const resp = await fetch(`/api/users/${editingUser}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, role }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { errEl.textContent = data.error || 'Erro ao editar'; return; }
      }
      closeUserDialog();
      await loadUsers();
    });
  }

  const createBtn = document.getElementById('btn-open-create-user');
  if (createBtn) createBtn.addEventListener('click', () => openUserDialog(null));
  const cancelBtn = document.getElementById('cancel-user-edit');
  if (cancelBtn) cancelBtn.addEventListener('click', closeUserDialog);

  init();
}

export function teardownSection() {
  // handlers inline persistem via window; elementos são substituídos a cada load
}
