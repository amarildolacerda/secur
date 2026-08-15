# Histórico de Thumbnails por Câmera + Configuração de Notificações

Data: 2026-08-13
Projeto: secur (SecurityAI Dashboard)

## Objetivo

1. Guardar os últimos 20 thumbnails de cada câmera (capturados em movimento) e
   torná-los acessíveis ao clicar no card de status da câmera, substituindo o
   comportamento atual (que abre o player ao vivo).
2. Painel de configuração de quais tipos de alertas/infos são notificados em
   cada canal (Telegram, automação, futuros). `no_motion` deixa de ser enviado
   ao Telegram (default da config, não hardcode).

## Decisões

### Thumbnails
- **Gatilho de captura**: somente quando há movimento detectado.
- **Frequência**: no máximo 1 thumbnail a cada 10s durante movimento contínuo.
- **Retenção**: últimos 20 thumbnails por câmera; os mais antigos são apagados
  (arquivo + registro).
- **UI**: clique no preview do card abre o histórico (modal com grid); botão
  separado "Ao vivo" mantém o player existente (`openLivePlayer`).
- **Armazenamento**: arquivos JPEG em disco + metadados no SQLite (segue o
  padrão das thumbnails de identidade).

### Notificações
- **Escopo**: global por evento × canal (não por câmera).
- **Canais**: `telegram`, `automation` (MQTT+HA), futuros extensíveis via
  `register_handler` (padrão já existente).
- **UI**: seção "Notificações" na dashboard (sidebar), tabela evento × canal
  com toggles.
- **Persistência**: SQLite (tabela `notification_routing`).
- **Defaults**: comportamento atual + `no_motion` off no Telegram; gravados
  apenas se a tabela estiver vazia (permite evolução de defaults).

## Apanhado de eventos

| Evento | Origem | Categoria | Telegram (default) | Automação (default) |
|---|---|---|---|---|
| `motion_detected` | movimento sem objeto/identidade | alerta | ✅ | ✅ |
| `no_motion` | sem movimento há N s | info | ❌ | ✅ |
| `snapshot_info` | objetos detectados (info) | info | ❌ | ❌ |
| `identity_recognized` | pessoa/animal conhecido | info | ❌ | ✅ |
| `intruder_detected` | desconhecido em zona privativa/segurança | alerta | ✅ | ✅ |
| `unknown_detected` | não reconhecido em zona pública | alerta | ❌ | ✅ |
| `object_detected` | **legado** — não é mais produzido | alerta | ✅ | ✅ |

## Arquitetura

### 1. Storage (`secur/storage.py`)

Nova tabela:

```sql
CREATE TABLE IF NOT EXISTS camera_thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT,
    path TEXT NOT NULL
)
```

```sql
CREATE TABLE IF NOT EXISTS notification_routing (
    channel TEXT NOT NULL,
    event_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (channel, event_type)
)
```

Métodos novos (thumbnails):

- `add_camera_thumbnail(camera_id, path, event_type) -> int` — insere e retorna id.
- `list_camera_thumbnails(camera_id, limit=20)` — mais recentes primeiro
  (`ORDER BY id DESC`).
- `prune_camera_thumbnails(camera_id, keep=20)` — apaga do DB e do disco os
  registros excedentes (mais antigos).
- `remove_camera_thumbnails(camera_id)` — apaga todos os arquivos e registros
  da câmera (usado no DELETE de câmera).

Métodos novos (routing):

- `get_routing(channel)` -> dict {event_type: bool}
- `set_routing(channel, event_type, enabled)`
- `get_all_routing()` -> dict {channel: {event_type: bool}}
- `seed_default_routing(defaults)` — grava defaults apenas se a tabela estiver
  vazia.

Diretório de thumbnails: `data/thumbnails/cam<id>/<timestamp>.jpg`
(adicionar constante `THUMBNAILS_DIR` em `config.py`).

### 2. Registro de canais e eventos (`secur/notifications.py` — novo)

- `CHANNELS = [{"key": "telegram", "label": "Telegram"}, {"key": "automation", "label": "Automação"}]`
- `EVENT_TYPES` — registro canônico dos 7 tipos (key, label, categoria
  alerta/info, `legacy` flag para `object_detected`).
- `DEFAULT_ROUTING` — mapa canal → {event_type: bool} conforme tabela acima.
- Canais futuros: registrar handler via `register_handler` + entrada em
  `CHANNELS`.

### 3. Captura (`secur/main.py`, `CameraWorker.run()`)

No bloco de movimento (`motion_detected`):

- Se `time.time() - last_thumb_time >= 10.0`:
  - Codifica o frame atual em JPEG (`cv2.imencode`).
  - Salva em `data/thumbnails/cam<id>/<timestamp>.jpg`.
  - `storage.add_camera_thumbnail(camera_id, path, event_type)`.
  - `storage.prune_camera_thumbnails(camera_id, keep=20)`.
  - Atualiza `last_thumb_time`.
- Falha de encode/escrita: log warning e segue (não derruba o worker).

`event_type` registrado: o tipo do evento decidido no frame (ex:
`motion_detected`, `snapshot_info`, `identity_recognized`, etc.).

### 4. Dispatch (`secur/alerts.py`)

- `AlertService.send()` consulta `notification_routing` antes de chamar cada
  handler: `if not routing.is_enabled(channel, event_type): skip`.
- Handlers existentes mantêm a lógica interna (ex: HA ignora zona pública) — a
  config é uma camada adicional.
- O skip hardcode atual do Telegram (`snapshot_info`, `identity_recognized`,
  `unknown_detected`) é substituído pela config (defaults equivalentes).

### 5. API (`secur/app.py`)

Thumbnails:

- `GET /camera/<int:camera_id>/thumbnails` → JSON
  `[{id, timestamp, event_type, url: "/thumbnails/<id>/image"}]` (404 se a
  câmera não existir).
- `GET /thumbnails/<int:thumb_id>/image` → JPEG via `send_file` (404 se não
  existir).
- `DELETE /cameras/<int:camera_id>` → também chama
  `storage.remove_camera_thumbnails(camera_id)`.

Notificações:

- `GET /api/notifications` → `{channels: [{key, label}], events: [{key, label,
  category, legacy}], routing: {channel: {event: bool}}}`
- `PUT /api/notifications/routing` → body `{channel, event_type, enabled}`
- Atualizar `/docs` com os novos endpoints.

### 6. UI (`secur/templates/dashboard.html`, `secur/static/dashboard.js`, `secur/static/style.css`)

Thumbnails:

- Card de câmera (`createCameraCard`):
  - Clique no preview → `openThumbnailHistory(cameraId, cameraName)`.
  - Botão "Ao vivo" no card → `openLivePlayer(...)` (existente).
- Novo modal de histórico (reusa `.dialog-overlay`/`.dialog-card`):
  - Título com o nome da câmera.
  - Grid com os últimos 20 thumbnails (imagem + timestamp).
  - Carrega via `GET /camera/<id>/thumbnails` e renderiza as imagens.
- CSS: estilos para o grid de histórico no modal.

Notificações:

- Nova seção "Notificações" na sidebar (padrão das seções existentes).
- Tabela: linhas = eventos (label + categoria), colunas = canais, células =
  toggle.
- Salva via `PUT /api/notifications/routing` no toggle; feedback visual de
  salvamento.
- `object_detected` oculto (legacy).

## Testes

- `tests/test_storage.py`: add/list/prune/remove de thumbnails (inclui remoção
  de arquivo do disco); get/set/seed de routing.
- `tests/test_app.py`: rotas `/camera/<id>/thumbnails` (200/404),
  `/thumbnails/<id>/image` (200/404), `GET/PUT /api/notifications`.
- `tests/test_alerts.py`: dispatch respeita routing (telegram skip `no_motion`
  por config); MQTT/HA continuam publicando `no_motion`.
- `tests/test_main_identity.py` (ou novo): regra de intervalo de 10s via função
  auxiliar extraível (ex: `should_capture_thumbnail(last_thumb_time, now)`).

## Erros e casos de borda

- Encode/escrita falha → log warning, não interrompe o loop.
- Thumbnail apagado do disco mas presente no DB → rota de imagem retorna 404.
- Câmera excluída → thumbnails (arquivos + registros) removidos.
- DB antigo sem as tabelas → `CREATE TABLE IF NOT EXISTS` no `_create_tables`.
- Routing com evento desconhecido no PUT → 400.
- Canal desconhecido no PUT → 400.
- Tabela `notification_routing` vazia no boot → seed com defaults.