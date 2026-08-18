# Descrição do Banco de Dados (Secur)

Banco SQLite local (`data/events.db`), acessado via `EventStorage` (`src/storage.py`).
Local do arquivo: `data/events.db` (volume montado, persiste entre reinícios).

Convenções:
- `timestamp` e datas são armazenados em **ISO 8601 com timezone UTC** (`datetime.now(timezone.utc).isoformat()`).
- Colunas `INTEGER` booleanas usam `0`/`1` (ex.: `dropped`, `retained`, `enabled`).
- `camera_id` na tabela `events` é **TEXT** (id da câmera como string); em `cameras`/`camera_thumbnails`/`event_clips` é **INTEGER** (PK autoincrement da tabela `cameras`). O join entre `events.camera_id` (texto) e `cameras.id` (inteiro) é feito por conversão de tipo nas queries.

---

## Tabelas

### `events`
Registro de cada evento de segurança produzido pelo pipeline (N0–N4).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK AUTOINCREMENT | Identificador do evento. |
| `timestamp` | TEXT NOT NULL | Momento do evento (ISO 8601 UTC). |
| `camera_id` | TEXT NOT NULL | Id da câmera de origem (string). |
| `zone` | TEXT | Zona classificada onde ocorreu. |
| `event_type` | TEXT NOT NULL | Tipo do evento (ver abaixo). |
| `details` | TEXT | Detalhes livres (JSON ou texto). |
| `level` | INTEGER DEFAULT 0 | Nível N0–N4 (classificação de decisão). |
| `dropped` | INTEGER DEFAULT 0 | `1` se descartado na triagem N1 (ruído). |
| `source` | TEXT DEFAULT 'local' | Origem (`local`, borda remota, etc.). |
| `disposition` | TEXT | Desfecho da regra (`suppressed`, `cooldown`, `alert`, NULL). |
| `clip_path` | TEXT | Caminho do clipe de vídeo associado (se houver). |
| `retained` | INTEGER DEFAULT 0 | `1` = protegido contra prune (nunca apagado). |

**`event_type` (valores observados):** `motion_detected`, `capture`, `snapshot_info`, `no_motion`, `loitering`, `alert`, `suppressed`, `cooldown`.

**`level` (N0–N4):**
- `0` — evento base (produzido na borda, antes da decisão).
- `1` — mantido na triagem N1 (movimento real).
- `2` — detecção (N2).
- `3` — análise/supressão (N3): `disposition` em `('suppressed','cooldown')`.
- `4` — alerta normal (N4).

**`dropped`:** definido em `main.py` como `dropped = not kept`, onde `kept = triage_n1(detections, no_motion)`. Vira `1` quando **não é `no_motion` e não há detecções** (ruído descartado na borda). Eventos `dropped=1` não escalam para alerta.

**Relacionamentos:** `camera_thumbnails.event_id` e `event_clips.event_id` referenciam `events.id` (cascade manual no prune).

---

### `cameras`
Câmeras configuradas.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK AUTOINCREMENT | Id interno. |
| `name` | TEXT NOT NULL | Nome da câmera. |
| `source` | TEXT NOT NULL | Fonte de vídeo (ex.: `rtsp://...`, `source://...`). |
| `zone` | TEXT | Zona padrão. |
| `alert_classes` | TEXT | Classes de detecção habilitadas (JSON/lista). |
| `exclusion_zones` | TEXT | Polígonos de exclusão (JSON). |
| `mask_polygons` | TEXT | Máscaras de região (JSON, coluna de migração). |

---

### `zones`
Zonas de classificação.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK AUTOINCREMENT | Id interno. |
| `name` | TEXT NOT NULL UNIQUE | Nome da zona. |
| `classification` | TEXT DEFAULT 'pública' | Classificação (ex.: pública, privada). |
| `schedule` | TEXT | Janela de horário `{"start":"HH:MM","end":"HH:MM"}` (JSON). |
| `retention_policy` | TEXT | Política de retenção por zona (JSON, migração). |
| `direction_line` | TEXT | Linha de direção para contagem (JSON, migração). |

---

### `known_identities`
Identidades conhecidas para reconhecimento.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK AUTOINCREMENT | Id interno. |
| `name` | TEXT NOT NULL | Nome da identidade. |
| `species` | TEXT DEFAULT 'person' | Espécie/classe (`person`, `animal`, etc.). |
| `created_at` | TEXT NOT NULL | Data de cadastro (ISO 8601). |
| `embedding_path` | TEXT NOT NULL | Caminho do embedding salvo. |
| `thumbnail_path` | TEXT | Miniatura da identidade (coluna de migração). |

---

### `camera_thumbnails`
Miniaturas de frames por câmera (usadas no dashboard/overview).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK AUTOINCREMENT | Id interno. |
| `camera_id` | INTEGER NOT NULL | FK → `cameras.id`. |
| `timestamp` | TEXT NOT NULL | Momento do frame. |
| `event_type` | TEXT | Tipo de evento associado (se houver). |
| `path` | TEXT NOT NULL | Caminho do arquivo de imagem. |
| `event_id` | TEXT | FK → `events.id` (quando a miniatura pertence a um evento). |

---

### `event_clips`
Clipes de vídeo de eventos.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK AUTOINCREMENT | Id interno. |
| `camera_id` | INTEGER NOT NULL | FK → `cameras.id`. |
| `event_id` | INTEGER | FK → `events.id`. |
| `timestamp` | TEXT NOT NULL | Momento do clipe. |
| `path` | TEXT NOT NULL | Caminho do arquivo de vídeo. |
| `duration_s` | REAL | Duração em segundos. |

---

### `notification_routing`
Roteamento de notificações por canal × tipo de evento.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `channel` | TEXT NOT NULL | Canal (`telegram`, `mqtt`, `ha`). |
| `event_type` | TEXT NOT NULL | Tipo de evento. |
| `enabled` | INTEGER DEFAULT 1 | `1` se habilitado. |

PK composta: `(channel, event_type)`.

---

### `settings`
Configurações globais chave-valor (persistidas em runtime, ex.: `privacy_mode`).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `key` | TEXT PK | Nome da configuração. |
| `value` | TEXT NOT NULL | Valor (sempre string). |

---

## Política de Prune (limpeza automática)

O prune (`EventStorage.prune_events`) roda no scheduler (`EVENT_PRUNE_INTERVAL_SECONDS`, padrão 120s) e sob demanda (`POST /api/events/prune`). Regras (em `config.py`, env `EVENT_PRUNE_*`):

1. **Por tipo de evento** — ignora `level`. Cada `event_type` tem retenção em dias (`EVENT_PRUNE_TYPE_DAYS`); `0` = remove todos imediatamente, `<0` = nunca podar por tipo, fração permitida (ex.: `0.5` = 12h). Tipos não previstos usam `EVENT_PRUNE_DEFAULT_DAYS`.
2. **Idade Máxima** (`EVENT_PRUNE_MAX_AGE_DAYS`) — rede de segurança final: qualquer evento **não retido** mais antigo que o limite é removido, independente do tipo.
3. **Retidos preservados** — eventos com `retained = 1` **nunca** são removidos.
4. **Garantia de análise** — eventos ainda em voo (`disposition IS NULL` **e** `dropped = 0`) **nunca** são removidos, independente da idade. O `AlertRuleEngine` só define `disposition` após analisar e disparar os handlers de notificação (Telegram/MQTT/Home Assistant), então a automação é sempre notificada antes do prune. Eventos dropados (`dropped = 1`, triados como ruído na N1) e analisados (`disposition` definido) podem ser podados normalmente.

Ao remover eventos, o prune também apaga em cascata as miniaturas (`camera_thumbnails`) e clipes (`event_clips`) associados (e seus arquivos em disco).

> Nota: o flag `dropped` não é mais usado pelo prune (era o padrão N1 antigo). Eventos dropados são podados pela retenção do seu `event_type`.
