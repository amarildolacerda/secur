// audit.js — seção "Auditoria"
const ACTION_LABELS = {
  login: 'Login',
  create_user: 'Criar usuário',
  update_user: 'Editar usuário',
  create_api_key: 'Criar API key',
  delete_api_key: 'Deletar API key',
  update_permissions: 'Atualizar permissões',
  setup_create_admin: 'Setup inicial',
};
const ACTION_CLASSES = {
  login: 'action-login',
  create_user: 'action-create', create_api_key: 'action-create',
  update_user: 'action-update', update_permissions: 'action-update',
  delete_user: 'action-delete', delete_api_key: 'action-delete',
};
let allUsers = [];
let currentPage = 0;
const PAGE_SIZE = 50;

async function init() {
  const meResp = await fetch('/api/auth/me');
  if (meResp.status === 401) { window.location.href = '/login'; return; }
  try {
    const usersResp = await fetch('/api/users');
    if (usersResp.ok) allUsers = await usersResp.json();
  } catch (e) {}
  const userSelect = document.getElementById('filter-user');
  if (userSelect) {
    allUsers.forEach(u => {
      const opt = document.createElement('option');
      opt.value = u.id; opt.textContent = u.username;
      userSelect.appendChild(opt);
    });
  }
  await loadEntries();
}

async function loadEntries() {
  const action = document.getElementById('filter-action').value;
  const userId = document.getElementById('filter-user').value;
  const params = new URLSearchParams({ limit: PAGE_SIZE, offset: currentPage * PAGE_SIZE });
  if (action) params.set('action', action);
  if (userId) params.set('user_id', userId);
  const resp = await fetch('/api/audit?' + params.toString());
  const entries = await resp.json();
  render(entries);
}

function render(entries) {
  const tbody = document.getElementById('audit-body');
  if (!tbody) return;
  if (!entries.length) {
    tbody.innerHTML = '<tr class="table-empty"><td colspan="6">Nenhum registro encontrado</td></tr>';
    return;
  }
  tbody.innerHTML = entries.map(e => {
    const user = allUsers.find(u => u.id === e.user_id);
    const username = user ? user.username : (e.user_id ? `#${e.user_id}` : '—');
    const actionLabel = ACTION_LABELS[e.action] || e.action;
    const actionClass = ACTION_CLASSES[e.action] || '';
    const target = e.target_type ? `${e.target_type}${e.target_id ? ' #' + e.target_id : ''}` : '—';
    const details = e.details ? (typeof e.details === 'object' ? JSON.stringify(e.details) : e.details) : '—';
    const date = new Date(e.created_at).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
    return `<tr>
      <td class="audit-date">${date}</td>
      <td>${username}</td>
      <td><span class="action-badge ${actionClass}">${actionLabel}</span></td>
      <td>${target}</td>
      <td class="audit-details" title="${details.replace(/"/g, '&quot;')}">${details}</td>
      <td>${e.ip_address || '—'}</td>
    </tr>`;
  }).join('');
}

export function initSection() {
  currentPage = 0;
  const filterBtn = document.getElementById('btn-filter');
  if (filterBtn) filterBtn.addEventListener('click', () => { currentPage = 0; loadEntries(); });
  const actionSel = document.getElementById('filter-action');
  if (actionSel) actionSel.addEventListener('change', () => { currentPage = 0; loadEntries(); });
  const userSel = document.getElementById('filter-user');
  if (userSel) userSel.addEventListener('change', () => { currentPage = 0; loadEntries(); });
  init();
}

export function teardownSection() {
  // listeners recriados a cada initSection
}
