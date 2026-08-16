# Fila de Eventos e Fases N0–N4 (captura → alerta/avaliação) — Design

> Status: design aprovado (2026-08-16). Pronto para `writing-plans`.
> Projeto: Secur/Tucuxi. Backend Flask + OpenCV; dashboard JS. Alvo de escala: 80 câmeras (condomínio, fibra) — ver `docs/architecture-80-cameras.md` e `docs/roadmap.md` (Fases A–E, funil N0–N4).

## Objetivo

Separar a **captura/emissão de eventos (N0)** de uma **decisão de alerta/avaliação (N2–N4)** num serviço dedicado, preparando o código para ser quebrado em fases de escalabilidade. Hoje tudo ocorre dentro de `CameraWorker.run` (emite e já chama `alerts.send`). O resultado desta mudança:

- `CameraWorker` (N0, borda) **emite eventos** e **não gera alertas**.
- Um consumidor (`AlertRuleEngine`, fases N2–N4) decide se o evento vira alerta ou disparo no Home Assistant.
- Eventos trafegam por uma **fila** (`EventQueue`) — local hoje, Redis no futuro.
- Dispositivos de borda remotos entram via **`POST /api/ingest`** já em N1.

## Princípio norteador (regras para fases futuras)

Estas regras DEVEM ser respeitadas por qualquer implementação futura que expanda as fases:

1. **N0 entrega, não decide.** Quem captura (câmera local ou borda remota) só produz eventos-candidato. Nunca dispara alerta/HA.
2. **A decisão "evento → alerta" ou "evento → disparo HA" é das fases N2–N4**, nunca do N0.
3. **N1 tria na borda.** Filtros simples descartam ruído (ex.: vegetação balançando) antes de submeter a avaliação pesada. Só o que vale a pena segue.
4. **Níveis são acumulativos.** Um evento sobe N0→N1→N2→N3→N4; o nível armazenado reflete o maior nível alcançado.
5. **Transporte é trocável.** Produtores e consumidores falam só a interface `EventQueue` (`enqueue`/`subscribe`); a implementação (Local ↔ Redis) troca sem tocá-los.
6. **Origem é registrada.** `source = local | edge` distingue o que veio da captura local do que veio de borda remota.
7. **Evidência (clipe) é NVR/armazenamento** na arquitetura 80-câmeras (Fase D). No box local, o worker grava clipe sob demanda do consumidor; borda remota usará NVR depois.

## Modelo de evento (níveis N0–N4)

`CameraEvent` (dataclass em `src/events.py`):

| campo | tipo | descrição |
|-------|------|-----------|
| `event_id` | str | gerado no produtor (UUID); permite escalar o mesmo evento |
| `camera_id` | str | |
| `zone` | str\|None | |
| `zone_classification` | str\|None | |
| `timestamp` | float | |
| `level` | int (0–4) | nível atual/alcançado |
| `source` | `local`\|`edge` | origem |
| `event_type` | str\|None | tipo já classificado (pessoa, queda, loitering, …) ou None |
| `details` | str\|None | |
| `identity_name` | str\|None | |
| `known` | bool | |
| `category` | str\|None | |
| `recognition_method` | str\|None | |
| `thumbnail_path` | str\|None | |
| `no_motion` | bool | evento "sem movimento" |
| `detections` | list | resultado bruto da inferência (para o consumidor decidir) |
| `dropped` | bool | descartado em N1 (ruído) |

### Semântica de nível

- **N0 — Captura (somente câmeras locais):** worker local emite captura bruta/movimento. Armazenado em N0.
- **N1 — Triagem na borda:**
  - Câmera local: estágio `triage_n1(event)` decide manter×descartar. Descartado → `dropped=true`, não escala (visível em N0 como "descartado em N1"). Mantido → sobe a N1.
  - Borda remota: o próprio dispositivo já fez N0+N1; o pacote chega na API **em N1** (`/api/ingest` cria `CameraEvent` com `level=1`, `source=edge`). Não há descarte do nosso lado.
- **N2 — Detecção/classificação:** `event_type` determinado (pessoa, veículo, animal…).
- **N3 — Análise:** loitering, queda, direção, identidade.
- **N4 — Providência (decisão):** informar / alertar / perigo eminente → `alerts.send` (Telegram/MQTT/HA) e solicita clipe.

Escalonamento é feito pelo consumidor ao processar o evento (ver abaixo).

## Arquitetura de componentes

### `src/events.py` — `EventQueue` + `CameraEvent`
- `EventQueue` (Protocol): `enqueue(event)`, `subscribe(handler)`, `start()`.
- `LocalEventQueue`: `queue.Queue` + thread consumer que entrega a cada handler registrado. Usado hoje.
- `RedisEventQueue`: **interface compatível, não implementada** (futuro). Comentar o contrato (host/port, stream key, serialização JSON) para a Fase B do roadmap.
- `CameraEvent` dataclass (schema acima).

### Produtor A — `CameraWorker` (N0, local)
- `run()` segue fazendo movimento + inferência na borda, mas **emite `CameraEvent`** via `event_bus.enqueue(...)` e **deixa de chamar `alerts.send` / iniciar clipe direto**.
- Antes de emitir, aplica `triage_n1` (filtro simples); se descartar, emite mesmo assim com `dropped=true` (para o overview mostrar a chegada N0) — ou omite; decidir no plan. Recomendado: emitir `dropped=true` para auditabilidade do N0.
- "Sem movimento" vira `CameraEvent(no_motion=True, level=0)`.

### Produtor B — `POST /api/ingest` (`src/app.py`)
- Recebe JSON de borda (campos do `CameraEvent`), valida mínimo (`camera_id`), constrói `CameraEvent(level=1, source=edge)` e enfileira.
- Sem auth nesta fase (anotar token de borda como fase futura).
- É produtor alternativo, mesmo barramento.

### Consumidor — `AlertRuleEngine` (`src/alert_rules.py`)
- Assina a fila. Por evento recebido:
  1. **Armazena N0/N1** (`storage.add_event(..., level=event.level, source=event.source)`) → obtém `event_id`.
  2. Se `dropped` → não processa (fim).
  3. **N2/N3:** roda `decide_worker_event` (já existe) sobre `detections`/identidade → define `event_type`, `details`, categoria; `update_event_level(event_id, 2 ou 3)`.
  4. **N4:** se `event_type` e cooldown ok → `alerts.send(...)` (agora **só notificação**, não persiste) + `camera_manager.request_clip(camera_id, event_id)` (workers locais; borda remota usa NVR depois) + `update_event_level(event_id, 4, disposition)`.
- `decide_worker_event` sai do worker e passa a viver em `alert_rules.py` (ou `events_rules.py`); o worker só emite o candidato.

### `alerts.send` (contrato novo)
- Deixa de persistir evento; passa a ser **só notificação** (Telegram/MQTT/HA). Quem persiste é o `AlertRuleEngine`.

### `src/main.py`
- Cria `event_bus = LocalEventQueue()`, registra `AlertRuleEngine(event_bus, alerts, storage, camera_manager)`, injeta `event_bus` nos workers.

## Storage (`src/storage.py`)
- `events` ganha colunas `level` (INT, default 0), `dropped` (INT/bool, default 0), `source` (TEXT, default `'local'`). Migração SQL.
- `add_event(camera_id, zone, event_type, details, level=0, source='local', dropped=False)` → retorna `id`.
- `update_event_level(event_id, level, disposition=None)` → `UPDATE events SET level=?, disposition=? WHERE id=?`.
- `list_events(limit=100, level=None, camera_id=None, source=None)` → inclui novas colunas no SELECT/WHERE.
- `update_event_clip_path` mantém-se.

## Dashboard (Visão geral + Eventos)
- **Visão geral:** card da câmera mostra indicador de **chegada N0** (contagem de eventos N0 daquela câmera, via `list_events(level=0, camera_id)`).
- **Eventos:** cada linha mostra **badge de nível** (N0–N4) e marca "descartado" se `dropped`. Filtro por **nível** (Todos / N0 / N1 / N2 / N3 / N4) nos filtros existentes (`src/static/dashboard.js` + endpoint de eventos passa `level`).
- Endpoint de eventos (`/api/events` ou existente) retorna `level`, `source`, `dropped`.

## Tratamento de erro
- Handler do consumidor isolado: exceção não derruba o worker nem a fila (bus captura por handler).
- Worker mantém `try/except` por frame.
- Evento inválido em `/api/ingest` → 400; ausência de `camera_id` → 400.

## Testes (`tests/test_events.py`)
- `LocalEventQueue` entrega evento a handler registrado.
- `AlertRuleEngine` aplica cooldown e chama `alerts` mock; não persiste duplicado; descarta `dropped`.
- `CameraWorker` (dummy) enfileira e **não** chama `alerts.send` (mock).
- `/api/ingest` enfileira com payload válido; rejeita sem `camera_id`.
- `storage` `add_event`/`update_event_level`/`list_events(level=...)` funcionam.

## Fora de escopo (anotado para fases futuras)
- **RedisEventQueue** (transporte Fase B): implementar `EventQueue` sobre Redis Streams; sem mudança em produtores/consumidores.
- **Autenticação de borda** em `/api/ingest` (token por dispositivo).
- **HA como assinante separado**: hoje o `AlertRuleEngine` dispara HA; no futuro, HA vira assinante próprio da fila (N4) — a interface já permite.
- **NVR / clipe remoto (Fase D):** borda remota não grava clipe local; export sob demanda do NVR.
- **N2–N4 distribuídos**: central de análise consome a fila e decide providência (funil N0–N4 do `architecture-80-cameras.md`).
- **Atualização de `SPEC.md` §7 e `README.md`**: refletir a fronteira N0↔N2–N4 e a fila (regra 5 do `AGENTS.md`) — tarefa do plano de implementação.

## Não-objetivos
- Não distribuir inferência/identidade para fora do worker nesta mudança (fronteira mínima).
- Não implementar Redis nem autenticação de borda agora.
- Não remover funcionalidade de alerta existente: comportamento visível se mantém.
