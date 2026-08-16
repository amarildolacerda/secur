/*
SINOPSE:
   - arquivo de notas de tarefas a serem observados/implementados;
   - tratou uma nota, ele é removido da lista de notas
*/

## Tarefas para refazer após rollback para origin/dev

### Backend (fix-4 + fix-2)
- [ ] `CameraManager.get_latest_frame(camera_id)` em `src/main.py` — retorna frame em memória + timestamp
- [ ] `GET /camera/<id>/snapshot` em `src/app.py` — serve frame em memória do worker (com `X-Snapshot-Time`), fallback para VideoCapture direto
- [ ] `GET /api/dashboard` em `src/app.py` — payload agregado: `{cameras, events, zones, n0_events, worker_status}`
- [ ] Documentação da rota `/api/dashboard` em `/docs` (app.py)
- [ ] Fallback `_latest_thumbnail_path()` no `CameraWorker` (main.py) — para Telegram quando dedup bloqueia thumbnail
- [ ] Mudanças em `src/storage.py` (dedup thumbnails, 27 linhas)
- [ ] Mudanças em `src/config.py` e `src/alert_rules.py`
- [ ] Testes: `tests/test_thumbnail_dedup.py` (4 testes novos), `tests/test_events.py` (adições)

### Frontend (fix-5 + fix-3 + filtro 1h)
- [ ] `fetchCached(url, ttlMs=60000)` + `invalidateCache(url)` — cache TTL para `/api/settings`, `/api/notifications`, `/api/classes`
- [ ] `onSnapshotLoad` com guard `blob:` + `fetchSnapshotWithHeader` (P0) — fetch único lê header `X-Snapshot-Time` e troca `img.src` para blob URL
- [ ] `renderOverviewSection` usa `/api/dashboard` (P2) — **corrigir**: não setar `dataset.rendered='1'` se `cameras` vazio; remover guard ou validar dados antes
- [ ] `renderStatusFooter` reusa `lastDashboardPayload` (P3) — fallback para `/status` se overview não rodou
- [ ] `renderSettingsConfig()` — collapsible "Configurações em uso" (somente leitura, busca `/api/system-status`)
- [ ] Filtro eventos default `since: '1'` (última 1h) — em `readFilterState()` e `dashboard.html` option selected
- [ ] `renderEvents` usa `fetchCached('/api/notifications')`
- [ ] `populateAlertClasses` usa `fetchCached('/api/classes')`
- [ ] Invalidação de cache em PUTs: `/api/settings`, `/api/notifications`

### Correções necessárias (baseado nas regressões)
- [ ] **Sintoma 1** (eventos sem imagem): `thumbCache` nunca invalida — adicionar invalidação ou TTL; verificar se `getCameraThumb` falha silenciosamente
- [ ] **Sintoma 2** (overview sem câmera): `dataset.rendered` setado antes de validar `cameras` — mover guard para depois da validação ou remover
- [ ] **Sintoma 3** (dialog não abre): verificar se `onSnapshotLoad`/`fetchSnapshotWithHeader` interfere em imagens de eventos (cards usam `getCameraThumb`, não snapshot) — isolar escopo do blob-swap

### Verificação
- [ ] `/tmp/secur-venv/bin/python -m pytest tests/ -q` → 243 passed, 2 skipped
- [ ] `node --check src/static/dashboard.js` → OK
- [ ] Smoke test manual: overview mostra câmeras, eventos mostram thumbnails, click abre dialog