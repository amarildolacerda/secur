# Dashboard: Lazy-load de seções no `#main-page`

**Data:** 2026-08-21
**Status:** Design aprovado (pendente de revisão do usuário antes do plano de implementação)
**Tipo:** Refatoração de arquitetura de frontend (sem mudança de backend/storage)

## Problema

O dashboard atual é um SPA monolítico:

- `src/templates/dashboard.html` contém **11 seções** como `<section class="panel hidden-panel">` (overview, camera-management, zones-management, recent-events, notifications, settings, identities-management, event-retention, users-management, permissions-management, audit-log) mais todos os seus dialogs, tudo no HTML estático.
- `src/static/dashboard.js` (~3256 linhas) manipula todas as seções; é baixado e parseado por completo a cada carregamento.

Consequência: todo o HTML e JS são transferidos/parseados mesmo quando o uso diário envolve apenas **Visão geral + Eventos + Câmeras**. As páginas de manutenção (Usuários, Permissões, Auditoria, Zonas, Identidades, Notificações, Configurações, Retenção) são raramente usadas, mas pesam no carregamento inicial.

Há ainda **duplicação**: já existem templates separados (`users.html`, `permissions.html`, `audit.html`, `identities.html`) que a sidebar não utiliza (aponta para seções duplicadas dentro do SPA).

## O que já existe

- `dashboard.html`: shell + 11 seções + dialogs; sidebar usa botões `data-section` que alternam painéis via `setActiveSection`.
- `dashboard.js`: núcleo (init, checagem de sessão, `fetchData`, polling) + funções de cada seção.
- Templates separados órfãos da sidebar: `users.html`, `permissions.html`, `audit.html`, `identities.html`.
- Rotas de API existentes (`/api/*`). Rotas `GET /zones`, `/notifications`, `/settings` hoje retornam JSON (não template).
- Padrão de dialog já alinhado em `users.html` (criar/editar via `#user-dialog`); câmeras/zonas/identidades também usam dialog.

## O que construir

### 1. Shell estável (`dashboard.html`)
`dashboard.html` passa a conter apenas:
- sidebar (com botões `data-section` que disparam lazy-load),
- `<div id="main-page">` (único local de apresentação),
- footer + user-bar + checagem de sessão.

As 11 seções deixam de existir no HTML estático.

### 2. Partials por seção
Cada seção vira um **fragmento HTML** em `src/templates/sections/<nome>.html` (ex: `overview.html`, `cameras.html`, `events.html`, `zones.html`, `identities.html`, `users.html`, `permissions.html`, `audit.html`, `notifications.html`, `settings.html`, `retention.html`). Cada partial contém apenas o conteúdo da seção (panel + dialogs). Os partials são majoritariamente markup estático; dados dinâmicos são buscados via `/api/*` pelo JS da seção (evita precisar de contexto server-side no partial).

### 3. Rota de partials
Adicionar em `app.py`:
```
GET /section/<nome>  -> render_template("sections/<nome>.html")
```
Retorna o fragmento HTML. Rotas `/api/*` existentes permanecem. (`/zones`, `/notifications`, `/settings` GET que hoje retornam JSON podem ser mantidas como API ou removidas se não usadas — decisão deixada para o plano, sem impacto no frontend.)

### 4. Lazy-loader no núcleo JS
Núcleo (`src/static/core.js` ou equivalente) com:
- `loadSection(name)`: `fetch('/section/'+name)` → injeta HTML em `#main-page` → carrega sob demanda `src/static/sections/<nome>.js` (dynamic `import`/script tag, uma vez) → chama `initSection()` para ligar eventos.
- **Cache em memória** das seções já carregadas (não refaz fetch ao reabrir).
- **Gestão de polling**: ao trocar de seção, parar o polling/intervalos da seção anterior para evitar vazamento/requisições órfãs.
- Item ativo da sidebar destacado.

### 5. Módulos JS por seção + `shared.js`
- **`src/static/shared.js`** (carregado uma vez, parte do núcleo): utilidades comuns usadas por múltiplas seções — `fetchData`/`fetchCached`, `formatUptime`, `escapeHtml`, helpers de mensagem/toast, abertura/fechamento genérico de dialog, formatação de datas, constantes compartilhadas (ex: `CameraFault.FAULT_DEFAULTS`), e qualquer outra função de uso comum. **Fonte única de verdade**: corrigir em um só lugar, reflete em todas as seções.
- **`src/static/sections/*.js`** (um por seção): `overview.js`, `cameras.js`, `events.js`, `zones.js`, `identities.js`, `users.js`, `permissions.js`, `audit.js`, `notifications.js`, `settings.js`, `retention.js`. Cada módulo **importa de `shared.js`** (e do núcleo) as utilidades comuns, em vez de duplicá-las, e exporta `initSection()` (e `teardownSection()` se necessário). O núcleo carrega ~poucos KB; cada módulo de seção só quando usado.

### 6. Dialog nos auxiliares
Manter/garantir que as seções auxiliares (Usuários, Permissões, Auditoria, Zonas, Identidades, Notificações, Configurações, Retenção) usem **dialog** para criar/editar, seguindo o padrão já aplicado em `users.html` (`#user-dialog`: `.dialog-overlay` → `.dialog-card` → `.dialog-header` + `<form>` com `.form-row`, `.form-actions` `button-primary`/`button-secondary`, `.form-message`).

### 7. Sidebar
Itens viram botões `data-section` que chamam `loadSection(name)`, mantendo `#main-page` como local único de apresentação (sem reload, sem páginas separadas de fato). Itens sem permissão podem ser ocultados conforme `me.permissions`.

## Modelo de dados
Sem mudança no backend/storage. É apenas fragmentação da camada de apresentação.

## Rotas
- **Nova:** `GET /section/<nome>` → fragmento HTML da seção.
- **Mantidas:** todas as rotas `/api/*` (proteção por `require_permission` já existe).
- **Ajuste opcional:** `/zones`, `/notifications`, `/settings` GET (JSON) — manter como API ou remover se órfãs.

## Segurança
- `before_request` já redireciona não autenticados para `/login` (corrigido previamente).
- Partials e módulos JS são públicos (static), mas dados sensíveis vêm das rotas `/api/*` protegidas por sessão/permissão; o lazy-load não expõe dados por si.
- Cada seção busca seus dados via `/api/*` com a sessão do usuário; permissões por seção já são aplicadas nas APIs.

## Riscos
- **Complexidade do loader:** cache, re-bind de eventos, e principalmente parar o polling da seção anterior ao trocar de seção (vazamento de requisições/intervalos).
- **Navegação SPA:** botão "voltar" do browser não reflete seções; decidir se usa hash routing (`#cameras`) — opcional, fora do escopo inicial.
- **Regression:** funcionalidades existentes (câmeras ao vivo, eventos, dialogs) devem continuar idênticas. O plano deve incluir verificação manual de cada seção após migração.
- **Ambiente de execução:** subagentes de implementação estão indisponíveis no ambiente atual (modelo `deepseek-v4-flash-free` inexistente); a implementação pode exigir execução direta ou ajuste de modelo.

## Plano de implementação (resumo — detalhado em writing-plans)
1. Criar shell mínimo (`dashboard.html` com `#main-page`) + núcleo JS (loader lazy, navegação, sessão, `fetchData`, polling genérico) **+ `shared.js` com as utilidades comuns**. **Carregar somente "Visão geral" no boot**; Eventos, Câmeras e todas as demais seções são lazy. Prova de conceito = Visão geral carregando via lazy-loader.
2. Extrair, uma seção por vez, para partial + módulo JS: overview, events, cameras (já cobertos no passo 1), depois zones, identities, users, permissions, audit, notifications, settings, retention. Garantir dialog nos auxiliares.
3. Ajustar sidebar (`loadSection`) e remover seções hardcoded do `dashboard.html` original.
4. Verificar no browser (login → navegar por todas as seções → criar/editar via dialog → permissões por role).
5. Limpeza: remover `dashboard.js` monolítico e templates órfãos duplicados (`users.html` etc. se absorvidos pelos partials ou mantidos conforme decisão de estrutura).

## Decisões (registradas)
- **Boot vs lazy (DEFINIDO):** somente **"Visão geral"** é carregada no boot. Todo o resto — Eventos, Câmeras, Zonas, Identidades, Usuários, Permissões, Auditoria, Notificações, Configurações, Retenção — é **lazy** (buscado/injetado sob demanda ao clicar na sidebar).
- **Mecanismo de carga do JS (default):** `dynamic import()` de ES modules (`src/static/sections/<nome>.js`), cacheável pelo browser e executado uma única vez por seção. Ajustável no plano se houver incompatibilidade.
- **Templates órfãos (default):** absorver `users.html`, `permissions.html`, `audit.html`, `identities.html` como os partials dessas seções (reaproveitar em vez de descartar), removendo as seções duplicadas do SPA monolítico. Ajustável no plano.
