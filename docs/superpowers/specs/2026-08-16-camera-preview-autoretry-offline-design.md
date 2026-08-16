# Design: Auto-retry de preview e badge "Offline" na Visão geral

**Data:** 2026-08-16
**Status:** Aprovado (abordagem A — frontend)
**Contexto:** Secur / Tucuxi — dashboard web (`src/static/dashboard.js`)

## Objetivo

Na Visão geral, quando o preview de uma câmera (`/camera/<id>/snapshot`) falha ao
carregar, hoje aparece o fallback "Falha ao carregar preview" + botão **Tentar
novamente** (manual). Queremos que o sistema:

1. Tente novamente sozinho após um tempo (auto-retry), sem exigir clique.
2. Se ficar sem resposta por muito tempo (~5 min), marque a câmera como **Offline**.
3. Volte sozinho para o estado normal se o preview voltar a funcionar (auto-recuperação).

O "offline de fato" (seção "Câmeras offline") continua sendo decidido no backend
via `worker_status` (`healthy`). Esta mudança é **puramente frontend** e não altera
o backend.

## Abordagem

**A) Rastreio de falha no frontend (escolhida).** Um mapa de estado em
`dashboard.js` acompanha por câmera o resultado do carregamento do preview e agenda
retries com timers. Sem mudança em `src/main.py`, `src/app.py` ou qualquer endpoint.

## Modelo de estado e constantes

No topo de `src/static/dashboard.js`:

```js
const SNAPSHOT_RETRY_INTERVAL_MS = 15000;          // tenta a cada 15s enquanto "retrying"
const SNAPSHOT_OFFLINE_RETRY_INTERVAL_MS = 30000;  // sonda a cada 30s quando "offline" (auto-recupera)
const SNAPSHOT_OFFLINE_THRESHOLD_MS = 300000;      // 5min sem resposta -> Offline
const cameraFaultState = {}; // id -> { status: 'retrying' | 'offline', firstFailAt: number, timer: Timeout | null }
```

## Integração no card (`createCameraCard`)

- Lê `cameraFaultState[camera.id]?.status === 'offline'` e passa como `offline` para
  `createCameraCard`, aplicando `camera-card-offline` + badge "Offline" **no mesmo
  card** (a câmera permanece na grade, não é movida para a seção offline).
- `onload`/`onerror` da `<img>` passam a chamar `onSnapshotLoad(id, el)` /
  `onSnapshotError(id, el)` em vez do manipulador inline atual.

## Handlers e timers

- `onSnapshotError(id)`: se não houver estado ou for `'ok'`, cria estado
  `retrying` com `firstFailAt = Date.now()`. Agenda `scheduleSnapshotRetry(id)`.
- `scheduleSnapshotRetry(id)`: um único timer por câmera (guarda em
  `state.timer` para não duplicar). Ao disparar:
  - se ainda não `offline` e já se passaram `SNAPSHOT_OFFLINE_THRESHOLD_MS` desde
    `firstFailAt` → `markSnapshotOffline(id)` (que reagenda no intervalo lento);
  - senão recarrega `img.src = /camera/<id>/snapshot?ts=<agora>` e reagenda.
- `markSnapshotOffline(id)`: estado `offline`, reaplica classe/badge e reagenda no
  intervalo lento (`SNAPSHOT_OFFLINE_RETRY_INTERVAL_MS`) para permitir auto-recuperação.
- `onSnapshotLoad(id)`: limpa estado e timer, remove badge/classe de erro
  (auto-recuperação).

## Sobrevivência aos polls (re-render a cada ~5s)

`renderCameraTiles` relê `cameraFaultState`: câmeras com falha crônica
(`fault-offline`) são renderizadas **na grade online** recebendo `offline=true` em
`createCameraCard` (badge "Offline" no próprio card), e NÃO são movidas para a seção
offline. O estado persiste em `cameraFaultState` (não no DOM), então o re-render
reconstrói o card correto. Cards em estado `ok` continuam iguais. A seção offline
existente (dirigida por `worker_status`) permanece inalterada e continua agrupando
apenas câmeras que o backend marca como unhealthy.

## Estados visuais

- `ok`: imagem normal.
- `retrying` (0–5min): fallback "Tentando novamente…" + botão "Tentar novamente"
  (manual) disponível.
- `offline` (após 5min): fallback "Sem resposta — Offline" + badge "Offline" no
  card + botão manual; sonda a cada 30s e volta sozinho se carregar.

## Fora de escopo

- Não muda backend, `/status`, `worker_status` nem alertas.
- Não move o card para a seção "Câmeras offline" (decisão do usuário: badge no mesmo card).
- Não persiste o estado de falha entre recarregamentos de página (limitado à sessão do cliente).

## Verificação

- Manual: derrubar a fonte de uma câmera → ver "Tentando novamente…" → após 5min
  badge "Offline" → restabelecer a fonte → card volta sozinho.
- Checar que o re-render periódico (poll de 5s) não zera o estado nem duplica timers.
- Confirmar que câmeras com `worker_status` healthy continuam na grade normal quando
  o snapshot funciona.
