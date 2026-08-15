# Dashboard Redesign — Fase 5 (Front-end puro)

Data: 2026-08-14
Branch: `dev`
Status: Aprovado pelo usuário (brainstorming)
Referência de UX: dashboard do [frigate](https://github.com/amarildolacerda/frigate/tree/dev) (mapeado em 2026-08-14)

## Contexto

O dashboard atual (`secur/templates/dashboard.html` + `secur/static/dashboard.js` + `secur/static/style.css`) tem:
- Sidebar com 7 seções (Visão geral, Câmeras, Eventos, Notificações, Configurações, Manutenção)
- Visão geral: 4 summary cards + grade pequena de câmeras com snapshot
- Eventos: tabela (ID/timestamp/câmera/zona/tipo/detalhes) sem filtros
- URL NÃO é estado (seções via JS `hidden-panel`), sem filtros, sem empty states ricos, timestamps absolutos

O frigate (React/TypeScript) tem padrões aplicáveis a um dashboard server-rendered (Flask/Jinja2/vanilla JS):
- URL como estado (query params — linkável, sobrevive refresh)
- Chips de filtro persistentes (localStorage)
- Grade CSS responsiva com aspect-ratio + lazy-load via IntersectionObserver
- Card padrão: thumb + time-ago + badges + ações
- Empty states com CTA, toasts de feedback

## Decisões do usuário (brainstorming)

1. **Objetivo**: Visão geral/grade de câmeras + Eventos com filtros
2. **Escopo**: Redesenhar Visão geral (grade como estrela) + Consistência global
3. **Visão geral**: Grade de câmeras como estrela + Agrupar câmeras offline + Resumo compacto no topo
4. **Eventos**: Cards com thumbnail (em vez de tabela)
5. **Filtros**: Câmera + zona + tipo + período + só alertas + persistência URL/localStorage
6. **Abordagem**: A — Front-end puro (zero mudanças em Python; filtros client-side sobre os 100 eventos carregados; thumbnails via rota existente `/camera/<id>/thumbnails`)

## Design

### Seção 1 — Visão geral (grade como estrela)

- **Resumo compacto no topo**: os 4 cards atuais (Câmeras conectadas, Zonas cadastradas, Eventos recentes, Último evento) mantidos em linha compacta, mesmo estilo.
- **Grade de câmeras em destaque**: grid responsivo (`auto-fill minmax ~260px`) com preview 16:9 (`aspect-ratio` CSS), nome + badge da zona; ações no card mantidas (Ao vivo, clicar no preview → histórico, Clipes).
- **Lazy-load real**: IntersectionObserver — snapshots só são carregados/atualizados (polling 5s existente) para tiles visíveis no viewport.
- **Agrupamento offline**: câmeras sem worker ativo (fonte: `/status` → `cameras` vs `worker_status`) vão para seção "Offline" separada abaixo da grade, com badge visual; se `/status` não informar worker_status, fallback para grade única.
- **Empty state**: sem câmeras → ícone + texto + CTA "Adicionar câmera".

### Seção 2 — Eventos (cards com filtros)

- **Cards em vez de tabela**: cada card com thumbnail (casado com o thumbnail mais próximo da mesma câmera via `/camera/<id>/thumbnails`, cache em memória; placeholder com ícone quando não houver), badge do tipo (alerta/info — reusar `.badge-alert`/`.badge-info`), time-ago (atualiza a cada 30s), câmera + zona + detalhes.
- **Chips de filtro persistentes**: câmera, zona, tipo (multi), período (1h/24h/7d/tudo) e toggle "só alertas".
- **URL como estado**: `?camera=&zone=&type=&since=&alerts=1` — aplicado no load, compartilhável; localStorage guarda os últimos filtros para a próxima sessão.
- **Empty state com CTA** "Limpar filtros" quando o filtro não retorna nada.

### Seção 3 — Consistência global + infra

- **CSS único**: novos componentes (`.chip`, `.chip.active`, `.event-card`, `.event-thumb`, `.empty-state`, `.camera-tile`, seção offline, toasts) adicionados ao `style.css` existente, usando as variáveis atuais (`--primary`, `--danger`, `--radius`, etc.) — `docs.html` e `identities.html` herdam automaticamente.
- **JS**: helpers `timeAgo()`, `applyEventFilters()`, `syncUrl()`/`applyUrl()` em `dashboard.js`.
- **Validação**: `node --check` no JS + suíte Python como regressão (nenhuma mudança em Python).

## Fora de escopo (YAGNI)

- Filtros server-side no `/events` (abordagem B) — filtros client-side sobre 100 eventos são suficientes
- Página própria de Review/Explore/Export (frigate) — não faz sentido no escopo atual
- Drag-and-drop de tiles (react-grid-layout do frigate)
- Player multi-protocolo com fallback automático (o player atual já tem fallback RTSP→snapshot)
- Atalhos de teclado, i18n, dark mode

## Arquivos afetados

- `secur/templates/dashboard.html` — Visão geral (grade com lazy-load + seção offline), aba Eventos (chips de filtro + grid de cards)
- `secur/static/dashboard.js` — lazy-load, filtros + URL/localStorage, timeAgo, renderização de cards
- `secur/static/style.css` — novos componentes, todos seguindo as variáveis existentes

## Testes/verificação

- `node --check secur/static/dashboard.js`
- Suíte completa Python como regressão (não deve haver mudança em Python)
- Manual: navegação Visão geral → grade com lazy-load, seção offline, eventos com filtros, URL compartilhável
