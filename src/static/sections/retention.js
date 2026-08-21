// retention.js — seção "Retenção"
import { fetchData, escapeHtml } from '../shared.js';

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

let eventRetentionSnapshot = null;

function retentionValue(v) {
  const n = Number(v);
  return Number.isFinite(n) ? String(n) : '';
}

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
  if (!body.dataset.rendered) {
    body.dataset.rendered = '1';
    body.innerHTML = buildRetentionTableHtml(pruning);
  }

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
      eventRetentionSnapshot = payload;
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

export function initSection() {
  setupEventRetention();
  renderEventRetentionSection();
}

export function teardownSection() {
  // listeners recriados a cada initSection
}
