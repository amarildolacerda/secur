// permissions.js — seção "Permissões"
const ROLES = ['admin', 'chefe_seguranca', 'vigilante', 'viewer'];
const ROLE_LABELS = { admin: 'Admin', chefe_seguranca: 'Chefe Seg.', vigilante: 'Vigilante', viewer: 'Morador' };
const CATEGORIES = {
  'Monitoramento': ['view_live', 'view_events', 'view_clips', 'view_snapshots', 'view_dashboard'],
  'Eventos': ['dismiss_event', 'retain_event', 'delete_event', 'prune_events'],
  'Operação': ['arm_disarm'],
  'Sistema': ['manage_cameras', 'manage_zones', 'manage_identities', 'manage_notifications', 'manage_settings', 'manage_retention'],
  'Usuários': ['manage_users', 'create_users', 'view_users', 'manage_permissions'],
  'Auditoria': ['view_audit_log'],
};
let permissions = {};
let definitions = {};

async function init() {
  const meResp = await fetch('/api/auth/me');
  if (meResp.status === 401) { window.location.href = '/login'; return; }
  const me = await meResp.json();
  if (!me.permissions?.manage_permissions) {
    const panel = document.getElementById('permissions-management');
    if (panel) panel.innerHTML = '<div class="form-message error" style="padding:2rem;">Sem permissão para acessar esta página.</div>';
    return;
  }
  const [permsResp, defsResp] = await Promise.all([
    fetch('/api/permissions'),
    fetch('/api/permissions/definitions'),
  ]);
  permissions = await permsResp.json();
  definitions = await defsResp.json();
  render();
}

function render() {
  const tbody = document.getElementById('perm-body');
  if (!tbody) return;
  let html = '';
  for (const [cat, perms] of Object.entries(CATEGORIES)) {
    html += `<tr class="perm-category"><td colspan="5">${cat}</td></tr>`;
    for (const perm of perms) {
      const label = definitions[perm] || perm;
      html += `<tr><td title="${perm}">${label}</td>`;
      for (const role of ROLES) {
        const checked = permissions[role]?.[perm] ? 'checked' : '';
        const disabled = role === 'admin' ? 'disabled' : '';
        html += `<td><input type="checkbox" class="perm-toggle" data-role="${role}" data-perm="${perm}" ${checked} ${disabled}></td>`;
      }
      html += '</tr>';
    }
  }
  tbody.innerHTML = html;
}

export function initSection() {
  const saveBtn = document.getElementById('btn-save');
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const status = document.getElementById('save-status');
      status.className = ''; status.textContent = 'Salvando...';
      const toggles = document.querySelectorAll('.perm-toggle');
      const updates = [];
      for (const t of toggles) {
        if (t.disabled) continue;
        updates.push({
          role: t.dataset.role,
          permission: t.dataset.perm,
          enabled: t.checked,
        });
      }
      try {
        const resp = await fetch('/api/permissions', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ permissions: updates }),
        });
        if (resp.ok) {
          status.className = 'form-message'; status.textContent = '✓ Salvo';
        } else {
          const data = await resp.json();
          status.className = 'form-message error'; status.textContent = data.error || 'Erro';
        }
      } catch (e) {
        status.className = 'form-message error'; status.textContent = 'Erro de conexão';
      }
    });
  }
  init();
}

export function teardownSection() {
  // listeners recriados a cada initSection
}
