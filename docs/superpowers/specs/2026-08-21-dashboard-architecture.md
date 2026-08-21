# Arquitetura do Dashboard (referência pós-implementação)

**Data:** 2026-08-21
**Status:** Implementado e validado em browser
**Escopo:** Frontend do dashboard — shell + lazy-load de seções (sem mudança de backend/storage)

> Doc de referência para não se perder em trabalhos futuros. O racional de design
> está em `2026-08-21-dashboard-lazy-sections-design.md`; este arquivo descreve o
> estado **final** e como estender.

## Visão geral

O dashboard deixou de ser um SPA monolítico. Agora só **"Visão geral"** carrega no
boot; todas as outras seções são buscadas e injetadas sob demanda ao clicar na sidebar.

Fluxo: clique na sidebar → `loadSection(name)` → `GET /section/<name>` (HTML parcial)
→ injetado em `#main-page` → `import()` do módulo JS da seção (uma vez) → `initSection()`.

## Mapa de arquivos

```
src/templates/dashboard.html        # SHELL: sidebar + #main-page + #app-footer + user-bar
src/templates/sections/*.html       # 11 partials de seção + _dialogs.html (compartilhado)
src/static/core.js                  # loader lazy, navegação, sessão, footer de status
src/static/shared.js                # utilidades + dialogs compartilhados (window-attached)
src/static/camera_fault.js          # global CameraFault (script clássico, NÃO module)
src/static/sections/*.js            # 11 módulos de seção (ES modules)
src/app.py                          # GET /section/<name> (whitelist)
```

Seções: `overview, events, cameras, zones, identities, users, permissions, audit,
notifications, settings, retention`.

## Responsabilidades

- **`dashboard.html` (shell):** sidebar com botões `data-section`; `<div id="main-page">`
  (único local de apresentação); `<footer id="app-footer">` (status); user-bar + logout.
  Carrega (ordem): `hls.js` (CDN) → `camera_fault.js` (clássico, define `window.CameraFault`)
  → `shared.js` (module) → `core.js` (module).
- **`core.js`:** `SECTION_MODULES` (mapa nome→import), `loadSection(name)` (fetch + inject +
  dynamic import + init/teardown), `setupSidebarNavigation()`, `bootDashboard()` (checa
  sessão via `/api/auth/me`, preenche user-bar, logout, `startFooter()`, `loadSection('overview')`),
  `renderStatusFooter()` + `startFooter()` (polling `/status` a cada 5s). `nav-system-status`
  → `loadSection('overview')`.
- **`shared.js`:** `fetchData`, `fetchCached`, `invalidateCache`, `escapeHtml`, `formatUptime`,
  `timeAgo`, `showMenuMessage`, `ageLabelFromMs`, e os dialogs compartilhados
  (live player, thumb history/detail, clip history, zoom). Os dialogs são **anexados a
  `window`** para funcionar com `onclick` inline nos partials.
- **`src/static/sections/<nome>.js`:** cada módulo importa o que usa de `shared.js` (e
  `core.js` quando precisa de `loadSection`) e exporta `initSection()` / `teardownSection()`.
- **`src/templates/sections/<nome>.html`:** partial com só o conteúdo da seção (panel + dialogs).
  `_dialogs.html` é incluído via `{% include "sections/_dialogs.html" %}` por overview e events.

## Convenções e armadilhas

1. **`onclick` inline nos partials** precisa de função em `window`. `shared.js` anexa os
   dialogs; `overview.js` anexa `retrySnapshot/onSnapshotLoad/onSnapshotError`; `users.js`
   anexa `openCameras/openUserDialog/toggleUser/closeUserDialog/closeCamDialog/saveCameras`.
   Ao adicionar handler inline, anexe-o a `window` no módulo correspondente.
2. **Não redefinir `CameraFault`.** Ele é global (vem de `camera_fault.js`). Usar
   `window.CameraFault` direto.
3. **Estado de módulo + timers:** `overview.js` gerencia `_overviewTimer`/`_statusTimer` e os
   limpa em `teardownSection()`. `identities.js` anexa um `document` click handler e o remove
   em `teardownSection()`. Sempre limpar listeners/timers da seção anterior ao trocar de seção
   (o `core.js` chama `teardownSection` da seção anterior antes de injetar a nova).
4. **Re-bind de eventos:** como o HTML da seção é re-injetado a cada `loadSection`, os
   listeners devem ser (re)atachados dentro de `initSection()`, não no topo do módulo.
5. **Footer de status:** fica no shell (`#app-footer`), atualizado por `core.js`, não por seção.
6. **Sidebar com scroll:** `nav` tem `overflow-y: auto` + `min-height: 0`; `.footer-nav` é
   `flex: none` (fica no fluxo, fixo na base da sidebar). Não remover essas propriedades.

## Como adicionar uma nova seção

1. Criar `src/templates/sections/<nome>.html` (panel + dialogs; usar CSS vars/classes do style guide).
2. Criar `src/static/sections/<nome>.js` exportando `initSection()` / `teardownSection()`,
   importando utilidades de `shared.js`.
3. Registrar em `SECTION_MODULES` (`core.js`) e na whitelist de `GET /section/<name>` (`app.py`).
4. Adicionar botão `data-section="<nome>"` na sidebar de `dashboard.html` (grupo "Manutenção"
   se for de manutenção).

## Notas de limpeza (decisões tomadas)

- **Removido:** `src/static/dashboard.js` (monólito) e `src/templates/identities.html`
  (standalone, dependia de `dashboard.js` e virou seção lazy).
- **Mantido como acesso direto** (redundante com as seções lazy, mas inofensivo):
  `users.html`, `permissions.html`, `audit.html` — servidos em `/users`, `/permissions`,
  `/audit`. Têm scripts próprios e não dependem de `dashboard.js`. Podem ser removidos no
  futuro para consolidação total.
- **Rota removida:** `GET /identities/view` (agora coberta pela seção lazy `identities`).
