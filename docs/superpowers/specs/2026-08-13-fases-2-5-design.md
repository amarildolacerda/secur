# Secur — Spec Conjunta das Fases 2–5 (Alertas ricos, Comportamento, Privacidade, Integração)

Data: 2026-08-13
Projeto: secur (SecurityAI Dashboard)
Base: `docs/superpowers/specs/2026-08-13-secur-roadmap.md` (commitado em `512f0b5`)

## Objetivo

Definir o design unificado das fases 2–5 **antes** da implementação da Fase 1
(reduzir falsos positivos), para que as decisões de schema, worker, API e
dashboard da Fase 1 não criem retrabalho nas fases seguintes. Este documento é
a fonte de verdade de arquitetura para as fases 2–5; cada fase vira um plano de
implementação separado (ciclo spec → plan → implementação).

## Princípios transversais

- **Extensibilidade sem quebra**: toda mudança de schema usa o padrão
  `PRAGMA table_info` + `ALTER TABLE` (já usado para `thumbnail_path`); nunca
  recriar tabelas.
- **Payload de alerta extensível**: `AlertService.send()` já aceita kwargs
  opcionais (`identity`, `known`, `recognition_method`, `category`, `routing`);
  fases 2–5 adicionam campos sem alterar a assinatura.
- **Worker com pontos de extensão**: `CameraWorker.run()` ganha hooks para
  tracking (Fase 3) e buffer de frames (Fase 2) sem reescrever o loop.
- **TDD**: toda feature nova exige teste unitário; regra alterada → teste
  atualizado (AGENTS.md).
- **UI pt-BR**, seguindo os padrões existentes de `dashboard.html`/`dashboard.js`.

---

## 1. Arquitetura-alvo compartilhada

### 1.1 Schema SQLite (`secur/storage.py`)

Estado atual (âncora): tabelas `cameras`, `zones`, `events`, `identities`,
`identity_embeddings`, `camera_thumbnails`, `notification_routing`.

Evolução prevista pelas fases 2–5:

| Tabela / coluna | Fase | Descrição |
|---|---|---|
| `event_clips` (nova) | 2.2/2.4 | Clipe MP4 por evento: `id`, `camera_id`, `event_id`, `timestamp`, `path`, `duration_s` |
| `cameras.mask_polygons` (nova coluna, JSON) | 4.1 | Polígonos de mascaramento (blur) — **reusa o formato de `exclusion_zones` da Fase 1** |
| `zones.retention_policy` (nova coluna, JSON) | 4.2 | Política de retenção por zona: `{"thumbnails": N, "clips": N, "days": N}` |
| `events.thumbnail_path` (já existe) | 2.1 | Reaproveitado para anexo no Telegram |
| `events.clip_path` (nova coluna) | 2.2 | Link do clipe gravado para o evento |
| `settings` (nova tabela chave-valor) | 4.3/4.4 | Flags globais: `privacy_mode`, `local_only` |

Regras:
- `mask_polygons` e `retention_policy` seguem o mesmo padrão JSON das colunas
  novas da Fase 1 (`alert_classes`, `exclusion_zones`, `schedule`): `None`
  quando não configurado, parse com `json.loads` nos getters.
- `event_clips` espelha o padrão de `camera_thumbnails` (arquivo em disco +
  metadados no SQLite + `prune_*`).

### 1.2 CameraWorker (`secur/main.py`)

Pontos de extensão abertos na Fase 1 (sem implementar agora):

- **Buffer circular de frames** (Fase 2.2): anel de N frames (ex: 30s a ~5fps)
  mantido no worker; ao disparar alerta, grava MP4 com `cv2.VideoWriter` dos
  frames do buffer + frames seguintes (janela pré/pós evento).
- **Tracking por bbox** (Fase 3.1/3.2): estado por câmera mapeando detecções
  entre frames via IoU; alimenta eventos `loitering` e `direction_change`.
- **Máscara antes de salvar** (Fase 4.1): aplicar blur nos polígonos de
  `mask_polygons` no frame **antes** de salvar thumbnail/clipe/snapshot (nunca
  no frame de detecção — detecção usa o frame original).

A Fase 1 deve deixar o `run()` com estrutura clara (lookup de zona/config no
início, bloco de detecção isolado, bloco de thumbnail separado) para esses
hooks encaixarem sem refactor.

### 1.3 AlertService (`secur/alerts.py`)

- **Payload enriquecido** (2.3): `_format_message` passa a incluir zona +
  classificação + identidade + categoria + caminho do snapshot/clipe quando
  presentes. Campos já chegam no payload via `send()`.
- **Snapshot no Telegram** (2.1): `telegram_handler` ganha `sendPhoto` com o
  arquivo de `thumbnail_path` (baixado do disco local) quando o evento tem
  thumbnail e o routing permite.
- **Novo handler `siren_handler`** (5.1): canal `automation`, publica comando
  MQTT para dispositivo de sirene/áudio em eventos críticos
  (`intruder_detected`, `unknown_detected` em zona privativa/segurança).
- **Registro de handlers**: `register_handler` já é o mecanismo; novos handlers
  seguem o padrão `handler.channel = "..."` + routing por evento × canal.

### 1.4 API e dashboard (`secur/app.py`, `dashboard.html`, `dashboard.js`)

| Rota nova | Fase | Descrição |
|---|---|---|
| `GET /clips/<id>/video` | 2.4 | Stream do MP4 do evento |
| `GET /clips/<id>` | 2.4 | Metadados do clipe |
| `GET /api/export` | 5.4 | Download zip (eventos + thumbnails + clipes) |
| `PUT /api/settings` | 4.3/4.4 | Flags globais (`privacy_mode`, `local_only`) |
| `GET /api/settings` | 4.3/4.4 | Leitura das flags |

UI:
- **Revisão de clipes** (2.4): modal no card da câmera (padrão do histórico de
  thumbnails) com `<video>` player.
- **Máscara** (4.1): editor de polígonos no form da câmera (reusa o textarea
  JSON de `exclusion_zones` da Fase 1; mesma estrutura de dados).
- **Privacidade** (4.3/4.4): seção Config com toggle de modo privacidade +
  badge "100% local" estático no footer.

---

## 2. Detalhamento por fase

### Fase 2 — Alertas ricos (contexto = retenção de usuário)

#### 2.1 Snapshot anexado no Telegram
- **Encaixe**: `alerts.py` `telegram_handler` + `sendPhoto`.
- **Decisões**: enviar o thumbnail do evento (`events.thumbnail_path`) quando
  existir; fallback para mensagem de texto pura se não houver arquivo ou se o
  envio falhar (não derruba o alerta). Respeita routing por evento × canal.
- **Dependências**: Fase 1 (thumbnails já existem; nada novo no schema).
- **Testes**: handler com thumbnail presente/ausente; falha de upload não
  interrompe outros handlers.

#### 2.2 Clipe de vídeo por evento
- **Encaixe**: `main.py` `CameraWorker` (buffer circular) + `storage.py`
  (`event_clips`) + `alerts.py` (payload `clip_path`).
- **Decisões**: janela pré-evento (buffer) + pós-evento (gravação contínua por
  N segundos após o alerta); duração configurável (`CLIP_PRE_SECONDS`,
  `CLIP_POST_SECONDS` em `config.py`); codec MP4 (`mp4v`); retenção via
  `prune_event_clips` (padrão `camera_thumbnails`).
- **Dependências**: 2.4 (revisão) consome `event_clips`; 4.1 (máscara) aplica
  blur antes de gravar.
- **Testes**: buffer circular (tamanho fixo, descarta mais antigo); gravação
  gera arquivo válido; prune remove arquivo + registro.

#### 2.3 Notificação com contexto completo
- **Encaixe**: `alerts.py` `_format_message`.
- **Decisões**: incluir zona, classificação, identidade, categoria e caminho do
  snapshot/clipe quando presentes; manter escape Markdown existente.
- **Dependências**: nenhuma (payload já tem os campos).
- **Testes**: formatação com/sem cada campo opcional.

#### 2.4 Revisão de clipes no dashboard
- **Encaixe**: `app.py` (rotas `/clips/*`) + `dashboard.js` (modal).
- **Decisões**: modal no card da câmera listando clipes do evento (padrão do
  histórico de thumbnails); `<video controls>` com a rota de stream.
- **Dependências**: 2.2 (dados).
- **Testes**: rota retorna 404 para clipe inexistente; 200 com metadados.

### Fase 3 — Detecção de comportamento/anomalia

#### 3.1 Loitering
- **Encaixe**: `main.py` `CameraWorker` (tracking por IoU) + novo evento
  `loitering` em `decide_worker_event`.
- **Decisões**: tracking simples por bbox (IoU entre frames consecutivos);
  pessoa/veículo na mesma região por ≥ `LOITERING_SECONDS` (config) dispara
  `loitering`; cooldown por evento (reusa Fase 1.3).
- **Dependências**: Fase 1.3 (cooldown por evento); 3.2 (mesmo tracking).
- **Testes**: tracking associa bbox entre frames; evento dispara após o tempo
  limite; não dispara com movimento contínuo.

#### 3.2 Direção de movimento
- **Encaixe**: `main.py` `CameraWorker` (centroide entre frames) + evento
  `direction_change`.
- **Decisões**: comparar centroide da bbox rastreada entre frames; cruzar
  limite configurável (ex: linha vertical/horizontal da zona) dispara
  `direction_change` com direção (entrando/saindo).
- **Dependências**: 3.1 (mesmo tracker).
- **Testes**: centroide cruza o limite → evento com direção correta.

#### 3.3 Pessoa em zona restrita fora de horário
- **Encaixe**: `main.py` `decide_worker_event` + Fase 1.4 (schedule da zona).
- **Decisões**: combina 1.4 (horário) + identidade: pessoa **desconhecida** em
  zona privativa/segurança **fora do horário** → `intruder_detected` com
  prioridade; conhecida → `identity_recognized` normal.
- **Dependências**: Fase 1.4 (schedule), identidade existente.
- **Testes**: regra combinada (fora do horário + desconhecido → intruder).

#### 3.4 Detecção de queda / pessoa no chão
- **Encaixe**: `detector.py`/novo módulo (YOLO-pose) + evento `fall_detected`.
- **Decisões**: **avaliar viabilidade primeiro** (modelo de pose local, custo
  de inferência no hardware); se inviável, manter como backlog. Se viável:
  razão de aspecto da bbox + ângulo do torso → `fall_detected`.
- **Dependências**: nenhuma (feature isolada).
- **Testes**: fixture com pose sintética (em pé vs deitado).

### Fase 4 — Privacidade e robustez

#### 4.1 Mascaramento de regiões
- **Encaixe**: `storage.py` (`cameras.mask_polygons`) + `main.py` (blur antes
  de salvar) + `app.py`/dashboard (editor).
- **Decisões**: **reusa o formato de polígonos da Fase 1.2** (`exclusion_zones`)
  — mesma estrutura JSON, mesma validação; blur gaussiano nas regiões antes de
  salvar thumbnail/clipe/snapshot; detecção usa frame original.
- **Dependências**: Fase 1.2 (formato de polígonos), 2.2 (clipes mascarados).
- **Testes**: blur aplicado nas regiões; frame de detecção intacto.

#### 4.2 Retenção seletiva
- **Encaixe**: `storage.py` (`zones.retention_policy`) + `prune_*` existentes.
- **Decisões**: política por zona (`thumbnails`, `clips`, `days`); default
  mantém comportamento atual; `prune_camera_thumbnails`/`prune_event_clips`
  respeitam a política da zona da câmera.
- **Dependências**: 2.2 (clipes), Fase 1 (zona da câmera).
- **Testes**: política por zona aplicada no prune; default preservado.

#### 4.3 Modo privacidade
- **Encaixe**: `config.py` (flag global) + `main.py` (`identity_recognizer=None`)
  + `app.py`/dashboard (toggle).
- **Decisões**: flag global `PRIVACY_MODE` (env + `settings` table); quando
  ativo, reconhecimento de identidade desligado, movimento/objeto mantidos;
  toggle via API + dashboard.
- **Dependências**: 4.4 (indicador).
- **Testes**: com flag ativa, `recognize` não roda; eventos de identidade não
  são produzidos.

#### 4.4 Garantia 100% local
- **Encaixe**: dashboard (badge estático) + doc.
- **Decisões**: badge "100% local" no footer; documentar que nada sai do
  dispositivo (exceto canais configurados pelo usuário: Telegram/MQTT/HA).
- **Dependências**: nenhuma.
- **Testes**: nenhum (UI estática).

### Fase 5 — Integração e experiência

#### 5.1 Sirene/áudio externo
- **Encaixe**: `alerts.py` novo `siren_handler` (canal `automation`).
- **Decisões**: publica comando MQTT (`secur/siren/command`) em eventos
  críticos; config via env (`SIREN_TOPIC`, `SIREN_EVENTS`); respeita routing.
- **Dependências**: Fase 1.3 (cooldown por evento evita spam de sirene).
- **Testes**: handler publica comando nos eventos configurados; silencioso nos
  demais.

#### 5.2 Busca por linguagem natural
- **Encaixe**: novo módulo (LLM local opcional) + rota de busca.
- **Decisões**: **alto esforço** — avaliar viabilidade de LLM local no hardware;
  se inviável, backlog. Se viável: indexar eventos/thumbnails, query em
  português → filtros estruturados.
- **Dependências**: 2.2 (clipes indexáveis), 4.2 (retenção).
- **Testes**: query → filtros corretos.

#### 5.3 Cross-camera tracking
- **Encaixe**: `identity.py` (reusa ReID) + coordenação entre workers.
- **Decisões**: correlação temporal entre workers via tabela de "sessões" de
  identidade; reusa `IdentityRecognizer` e embeddings existentes.
- **Dependências**: identidade existente, 3.1 (tracking por câmera).
- **Testes**: mesma identidade em 2 câmeras → sessão única.

#### 5.4 Exportação/backup
- **Encaixe**: `app.py` (`GET /api/export`) + zip.
- **Decisões**: exporta eventos + thumbnails + clipes em zip; respeita 4.2
  (retenção) e 4.1 (máscara já aplicada nos arquivos).
- **Dependências**: 2.2 (clipes), 4.2.
- **Testes**: zip contém arquivos esperados; vazio quando não há dados.

---

## 3. Matriz de dependências entre fases

| Feature | Depende de | É dependida por |
|---|---|---|
| 2.1 Snapshot Telegram | — | — |
| 2.2 Clipes | — | 2.4, 4.1, 4.2, 5.4 |
| 2.3 Contexto completo | — | — |
| 2.4 Revisão clipes | 2.2 | — |
| 3.1 Loitering | Fase 1.3 (cooldown) | 3.2, 5.3 |
| 3.2 Direção | 3.1 | — |
| 3.3 Zona restrita + horário | Fase 1.4, identidade | — |
| 3.4 Queda | — (avaliar viabilidade) | — |
| 4.1 Máscara | Fase 1.2 (formato polígonos) | 2.2 (clipes mascarados), 5.4 |
| 4.2 Retenção seletiva | 2.2, Fase 1 (zona) | 5.4 |
| 4.3 Modo privacidade | — | 4.4 |
| 4.4 Badge local | 4.3 | — |
| 5.1 Sirene | Fase 1.3 | — |
| 5.2 Busca NL | 2.2, 4.2 | — |
| 5.3 Cross-camera | identidade, 3.1 | — |
| 5.4 Exportação | 2.2, 4.2 | — |

**Ordem sugerida de implementação**: Fase 2 (2.1→2.3→2.2→2.4) → Fase 4
(4.1→4.2→4.3→4.4) → Fase 3 (3.1→3.2→3.3; 3.4 avaliar) → Fase 5
(5.1→5.4→5.3; 5.2 avaliar). Fase 4 antes da 3 porque 4.1 reusa o formato da
Fase 1 e 4.2 protege o armazenamento que 2.2 cria.

---

## 4. Restrições para a Fase 1 (evitar retrabalho)

1. **Schema extensível**: colunas novas da Fase 1 (`alert_classes`,
   `exclusion_zones`, `schedule`) seguem o padrão JSON + `ALTER TABLE`; as
   fases 2–5 adicionam colunas/tabelas no mesmo padrão — não criar schema
   fechado.
2. **Formato de polígonos único**: `exclusion_zones` (Fase 1.2) e
   `mask_polygons` (4.1) usam **a mesma estrutura JSON** (lista de polígonos,
   cada um lista de `{"x","y"}`) — a Fase 1 define o formato e a validação que
   a 4.1 reaproveita.
3. **`AlertService.send()` intacto**: a Fase 1 não deve alterar a assinatura;
   fases 2–5 adicionam campos ao payload via kwargs opcionais.
4. **Worker com estrutura clara**: `CameraWorker.run()` da Fase 1 deve isolar
   lookup de config, bloco de detecção e bloco de thumbnail para os hooks de
   buffer (2.2) e tracking (3.1/3.2) encaixarem sem refactor.
5. **Cooldown por evento (1.3) é base**: 3.1 (loitering) e 5.1 (sirene) dependem
   do cooldown por evento — implementar com `get_cooldown_for_event` genérico.
6. **Não implementar nada das fases 2–5 agora**: este documento é design;
   execução só após a Fase 1 e aprovação de cada plano.

---

## Self-Review

1. **Cobertura**: todas as 16 features das fases 2–5 (2.1–2.4, 3.1–3.4, 4.1–4.4,
   5.1–5.4) têm decisões de design e encaixe no código atual. ✅
2. **Placeholders**: nenhum TBD/TODO; features de viabilidade incerta (3.4, 5.2)
   têm critério explícito de avaliação. ✅
3. **Consistência**: formato de polígonos único (1.2 = 4.1); payload de alerta
   extensível; schema segue padrão JSON + ALTER TABLE em todas as fases. ✅
4. **Escopo**: documento de design único; cada fase vira plano separado. ✅
5. **Ambiguidade**: retenção (4.2) e máscara (4.1) definem explicitamente onde
   se aplicam (prune; antes de salvar, nunca na detecção). ✅