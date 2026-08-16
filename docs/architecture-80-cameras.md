# Arquitetura para 80 câmeras — condomínio (fibra óptica)

> **Data:** 2026-08-15
> **Status:** Proposta de dimensionamento (a validar com o projeto real do condomínio)
> **Objetivo:** dimensionar o Secur para um condomínio com 80 câmeras IP, rede em fibra óptica.
> **Princípios:**
> 1. **A gravação 24/7 e a retenção ficam nos NVRs existentes** — o Secur não grava contínuo.
> 2. **A borda só faz triagem leve** (movimento + separação de potenciais pontos de análise) — **nenhum processamento pesado** (IA/classificação) na borda.
> 3. **A central de análise recebe os candidatos e decide a providência** (informar, alertar, perigo eminente).

---

## 1. Modelo de processamento: borda leve → central de análise

```
   Câmeras PoE (80) — switches PoE por andar/prédio (uplink fibra)
     │                                   │
     │ main-stream (gravação)            │ sub-stream (triagem)
     ▼                                   ▼
┌──────────┐                      ┌───────────────────────┐
│  NVR(s)  │  grava 24/7,         │  Nós de BORDA (leves) │
│ gravação │  retenção própria    │  só triagem:          │
│          │                      │  • movimento (OpenCV) │
└──────────┘                      │  • zonas/exclusão     │
                                  │  • captura SELETIVA   │
                                  │    de frames candid.  │
                                  │  • NENHUMA IA pesada  │
                                  └──────────┬────────────┘
                                             │ frames candidatos + eventos
                                             │ (MQTT + HTTPS/multipart)
                                             ▼
                              ┌────────────────────────────────┐
                              │    CENTRAL DE ANÁLISE          │
                              │  • fila de análise             │
                              │  • detecção IA (ONNX/YOLO)     │
                              │  • tracking / comportamento    │
                              │  • identidade                  │
                              │  • regras + classificação      │
                              │  • DECISÃO DE PROVIDÊNCIA      │
                              └───────┬────────────┬───────────┘
                                      │            │
                      ┌───────────────▼──┐  ┌──────▼──────────────┐
                      │  PROVIDÊNCIAS    │  │  Banco + Dashboard  │
                      │  informar /      │  │  Postgres + Flask   │
                      │  alertar /       │  │  + notificações     │
                      │  perigo eminente │  │  (Telegram/MQTT/HA) │
                      └──────────────────┘  └─────────────────────┘
```

### Por que esse modelo?

| Aspecto | Borda com IA (antes) | Borda leve + central (agora) |
|---|---|---|
| Custo do nó de borda | mini-PC i5/i7 (R$ 2-5k) | RPi/mini-PC fraco (R$ 300-1k) |
| Modelo de IA | 1 por nó, redundante | **1 centralizado** (GPU ou CPU forte) — mais barato de manter/atualizar |
| Banda | sub-stream contínuo sobe | **só frames candidatos sobem** (pico de movimento) |
| Latência de decisão | local (mais rápido) | rede LAN fibra (poucos ms) — aceitável |
| Resiliência | nó decide sozinho | nó enfileira offline; central deduplica |

**O ponto-chave:** movimento + ROI (região de interesse) é barato (OpenCV, µs-ms por frame). IA pesada (detecção, identidade, tracking) roda **uma vez**, na central, só quando há candidato — e o volume de candidatos é uma fração do tempo total (motion-gating).

### 1.1 Triagem em níveis (funil de pesca) — separar situações em potencial

O pipeline separa situações em potencial em **5 níveis de triagem**, do mais barato ao mais caro. Os níveis rasos **"pescam" sem se importar muito com o quê** — o objetivo é só ir limpando a lâmina d'água: coletar tudo que tem potencial e descartar o obviamente irrelevante, sem medo de puxar lixo junto. O que passa é que vira candidato sério para os níveis profundos (mais precisos e mais caros):

| Nível | Onde roda | O que faz | Custo | Taxa de passagem (aprox.) |
|---|---|---|---|---|
| **N0 — Captura e movimento (pesca grossa)** | borda | sub-stream + motion-gating OpenCV — pega tudo que mexe, sem critério | µs-ms/frame | 100% frames → ~5-15% com movimento |
| **N1 — Pré-seleção (pesca fina)** | borda | heurísticas leves: área do blob, posição (ROI/zonas), duração mínima, exclusões/máscaras — descarta o óbvio, mantém o duvidoso | ~ms | → ~1-5% candidatos reais |
| **N2 — Detecção rápida** | central | YOLO-tiny/ONNX no ROI; só classifica (pessoa/veículo/animal/etc.), sem tracking | ~5-20 ms/frame | → ~0,5-2% detecções de interesse |
| **N3 — Análise completa** | central | tracking, comportamento (loitering/direção/queda), identidade, regras de zona/schedule | ~20-100 ms/evento | → situações confirmadas |
| **N4 — Decisão** | central | classifica providência (informar/alertar/perigo eminente) + roteia notificação + evidência | ~ms | → poucos eventos/min |

**Exemplo com 80 câmeras a 5 fps:**
- N0 processa ~400 fps de movimento (trivial para a borda);
- N1 reduz para ~20-60 fps de candidatos;
- N2 analisa ~2-8 fps de ROIs (folga enorme — GPU nem é obrigatória);
- N3/N4 tratam poucos eventos por minuto.

**Regras do funil:**
- **Sem falso negativo crítico:** N1 é propositalmente permissivo (deixa passar falso positivo para não perder evento real); N2/N3 refinam. Thresholds configuráveis por câmera/zona.
- **Backpressure:** se a central saturar, a borda reduz fps de candidato ou marca/descarta com prioridade (nunca bloqueia a captura).
- **Prioridade na fila:** candidatos de zonas críticas (portaria, garagem, áreas privativas) sobem na frente — relevante para "perigo eminente".
- **Evidência acompanha o nível:** a borda anexa ROI/frame + metadados (bbox de movimento, timestamp, câmera) a cada candidato; a central anexa o resultado de cada nível ao evento — dá rastreabilidade ("por que este evento?").

> Isso é o padrão Frigate (motion → detection → tracking) formalizado, e casa com o que o Secur já tem (motion-gating + detecção ONNX + tracking).

### 1.2 Matriz de situações monitoráveis (além de intrusão)

O Secur monitora **situações**, não só presença/intrusão. Cada situação tem uma fonte (visão e/ou sensor), um nível de detecção no funil e uma providência padrão:

| Situação | Fonte | Detecção (nível) | Evento Secur | Providência padrão |
|---|---|---|---|---|
| Presença / intrusão (já existe) | visão | N2-N4 | `intruder_detected`, `motion_detected`, `identity_recognized` | alertar / perigo |
| **Alagamento / vazamento** | **sensores** (bóia, umidade, condutivo) + visão (opcional) | sensor → direto na central (N4); visão → N2 | `flooding_detected`, `water_leak` | alertar (vazamento); **perigo eminente** (subida rápida em garagem/subsolo) |
| **Fogo / fumaça** | **visão** (YOLO fire/smoke) + sensores (fumaça/calor via MQTT/HA) | N2 (visão) ou sensor direto | `fire_detected`, `smoke_detected` | **perigo eminente** (notificação prioritária + export de evidência + opção de alarme) |
| **Objeto abandonado em área de circulação** (ex.: carrinho) | visão (stationary objects + zona/ROI proibido) | N3 (tempo parado > threshold + zona) | `object_left_behind`, `obstruction_detected` | informar; **alertar** se bloquear rota de fuga / área crítica |
| Queda de pessoa (já existe) | visão | N3 | `fall_detected` | **perigo eminente** |
| Aglomeração / multidão em área comum | visão (contagem de pessoas) | N3 | `crowd_detected` | informar; alertar acima de limite |
| Veículo parado / obstruindo em local proibido | visão (stationary + zona) | N3 | `vehicle_blocking` | alertar |
| Pichação / vandalismo suspeito | visão (motion + stationary + zona) | N3 | `vandalism_suspected` | alertar |
| Porta/janela aberta fora de horário | visão (mudança de cena) ou sensor | N2/N3 ou sensor direto | `door_open` | alertar |
| Animal (já existe) | visão | N2 | (labels animal) | informar |
| Câmera offline / queda de energia | infra (health) | monitor | `camera_offline` | alertar |

**Como sensores entram no funil:** sensores (alagamento, fumaça, calor, CO, porta) são **fontes externas de alto nível** — chegam via MQTT/Home Assistant e **entram direto na central como candidatos já confirmados** (pulam N0-N2; o N4 decide a providência e cruza com contexto de visão quando houver). Ex.: sensor de fumaça dispara → central cruza com câmera da área → se visão confirma fogo → **perigo eminente** + evidência.

**Regras de negócio por situação (configuráveis):**
- Thresholds por situação e zona (ex.: tempo parado do carrinho, nível de água, limite de pessoas).
- Providência ajustável por área: carrinho no corredor de fuga = alertar; carrinho em depósito = informar.
- Cooldown por situação (reaproveita o mecanismo de cooldown atual por evento).

### 1.3 Situações ampliadas — condomínio, shopping, rodoviária/terminal, varejo

Pesquisa de desejos em [docs/research-monitoring-venues.md](docs/research-monitoring-venues.md). A maioria reusa o **mesmo funil N0-N4** — muda apenas o *analisador* na central (N2/N3) e a saída (alerta vs. analytics). A borda continua pescando movimento/ROI igual.

| Situação | Ambiente | Fonte | Nível | Providência padrão |
|---|---|---|---|---|
| **Bagagem/objeto abandonado** (sem dono > threshold) | rodoviária, shopping, aeroporto, condomínio | visão (stationary + owner association) | N3 | alertar (área crítica); informar |
| **Aglomeração/densidade** (capacidade excedida) | shopping, terminal, salão de festas, piscina | visão (contagem/densidade) | N3 | alertar |
| **Filas (tempo de espera)** | loja, caixa, portaria, guichê | visão (contagem + throughput) | N3 | informar (operacional); alertar se longa |
| **Fluxo/contagem de pessoas (footfall)** | loja, shopping, terminal | visão (counting) | N2/N3 | informar (analytics) |
| **Queda em escada/elevador** | terminal, shopping, condomínio | visão (fall + localização) | N3 | **perigo eminente** |
| **Superlotação de elevador** | condomínio, shopping | visão (contagem) | N3 | informar; alertar se risco |
| **Furto na portaria / encomenda** | condomínio | visão (loitering + zona portaria) | N3 | alertar |
| **Movimento suspeito na garagem** (loitering perto de veículo, mexer no veículo) | condomínio, shopping | visão (loitering + veículo) | N3 | alertar |
| **Veículo parado/obstruindo** (roadmap) | garagem, shopping, rua | visão (stationary + zona) | N3 | alertar |
| **Vandalismo/pichação** (roadmap) | shopping, condomínio, terminal | visão (stationary + zona) | N3 | alertar |
| **Carrinho abandonado em circulação** (roadmap) | shopping, condomínio | visão (stationary + zona) | N3 | informar; alertar se bloqueia rota |
| **Self-checkout/caixa fraud** | loja | visão (área de caixa) + POS | N3 | alertar (prevenção de perdas) |
| Fogo/fumaça, alagamento, porta aberta (roadmap) | todos | visão + sensores | N2-N4 | perigo/alertar |

**Analytics como saída:** footfall, filas, heat maps, contagem são casos *operacionais* — mesma infraestrutura, saída para dashboard/BI em vez de alerta. Amplia o público do Secur (operação + segurança) sem mudar a arquitetura.

**Casos mais complexos (exigem avanço de N3):**
- **Bagagem abandonada:** associação objeto-dono (owner association) — além do stationary simples.
- **Contagem/densidade em alta circulação:** modelo dedicado (YOLO conta pessoas; densidade por grid).
- **Queda em escada/elevador:** fall detection em contexto específico (escada/elevador) — já existe heurística de queda no Secur.

---





## 2. Dimensionamento do tráfego de candidatos (central)

A borda só envia frames quando há movimento relevante (após exclusões/máscaras). Estimativa:

| Cenário | Suposição | Frames/s na central | Banda |
|---|---|---|---|
| Conservador | 80 câmeras, 10% do tempo com movimento, 5 fps de candidato | ~40 fps | ~2 MB/s (~16 Mbps) @ 640×360 JPEG |
| Típico | 5% do tempo ativo | ~20 fps | ~1 MB/s (~8 Mbps) |
| Agressivo (eventos densos) | 20% ativo | ~80 fps | ~4 MB/s (~32 Mbps) |

- **Backbone fibra 1G sobra** (folga 30-100x).
- Cada frame candidato: JPEG 640×360 (~30-60 KB) ou ROI recortado menor.
- **Diminui-se ainda mais** enviando só o **ROI** do movimento (crop) em vez do frame inteiro.

---

## 3. Dimensionamento da central de análise

### Fila de análise
- Entrada: frames candidatos + metadados (câmera, timestamp, bbox de movimento, ROI).
- Fila em memória (Redis) ou disco (bounded); consumidor processa em ordem.
- **Backpressure:** se a central não acompanhar, a borda reduz fps de candidato ou descarta com marcação (política configurável).

### Detecção IA centralizada
- **40 fps** de inferência (conservador). 
  - **CPU 8-16 cores**: YOLO-tiny/ONNX ~50-100 fps → aguenta.
  - **GPU (RTX 4060+/Arc)**: centenas de fps → folga enorme.
- Modelo único, atualizável em um lugar.

### Tracking / comportamento / identidade
- Tudo na central, com o estado por câmera (tracking já existe por worker → passa a ser por câmera na central).
- Identidade (embeddings) também centralizada — 1 modelo, 1 base de identidades.

### Decisão de providência (classificação de severidade)
A central classifica cada evento em **3 níveis** (mapeia para as categorias atuais do Secur):

| Nível | Significado | Exemplos | Ação padrão |
|---|---|---|---|
| **Informar** | Contexto, sem ação | objeto detectado, sem movimento, identidade reconhecida em área pública | log + dashboard; notificação opcional (info) |
| **Alertar** | Atenção necessária | intruso em zona privativa/segurança, loitering, direção proibida, não reconhecido | notificação imediata (Telegram/MQTT/HA) + snapshot |
| **Perigo eminente** | Ação urgente | queda detectada, intruso + zona privativa + identidade desconhecida, padrão de arrombamento | notificação prioritária + export de evidência do NVR + opção de acionar sirene/automação |

> Isso **estende** o modelo atual do Secur (categorias `info`/`alerta` em `notifications.py`) com um nível **crítico/perigo iminente** — e deixa a **decisão** concentrada na central, não na borda.

---

## 4. Dimensionamento de rede (fibra)

| Tráfego | Volume | Onde trafega |
|---|---|---|
| Câmera → NVR (gravação) | 80 × 2-8 Mbps = 160-640 Mbps | Local aos switches PoE/andar (não cruza o backbone Secur) |
| Câmera → borda (triagem) | 80 × 0,4-1 Mbps = 32-80 Mbps | Rede local |
| Borda → central (candidatos) | ~8-32 Mbps | Backbone fibra — **1G sobra** |
| Central → NVR (export evidência) | picos (ex.: clipe de 10-60s) | Backbone — agendar/limitar |

- **Backbone fibra 1G** suficiente; **10G** só para sobra/expansão.
- **VLANs:** Câmeras (isolada), NVR/Gravação, Secur (borda+central), Gestão.
- **PoE:** 80 × ~7W ≈ 560W → switches PoE+ com orçamento e nobreak.

---

## 5. Dimensionamento de armazenamento (Secur)

Só evidência curta + banco (o 24/7 fica no NVR):

| Tipo | Volume (80 câmeras, 30 dias) |
|---|---|
| Thumbnails (~100 KB × eventos) | ~0,1-0,5 TB |
| Clipes de evidência (5-20 s) | ~0,5-3 TB |
| Banco (PostgreSQL) | < 0,1 TB |
| **Total** | **~1-4 TB** → 1 SSD NVMe 2-4 TB (ou 2 em RAID-1) |

Exports/permanentes em diretório separado, fora da retenção.

---

## 6. Computação (resumo)

| Componente | Hardware sugerido |
|---|---|
| **Nó de borda** (×5-8, 10-16 câmeras cada) | RPi 4/5 ou mini-PC fraco (Celeron/i3), 4-8 GB RAM, SSD/eMMC 64-128 GB (fila offline), 1×1G |
| **Central de análise** | 1 servidor: i7/Xeon 8-16c, 64 GB, SSD 2 TB; **GPU opcional** (RTX 4060+/Arc) para folga; 2 em HA se quiser redundância |
| **Banco/dashboard** | Na central (mesmo host ou VM) — Postgres + Flask |

---

## 7. Mudanças no código (fases)

> Estratégia strangler: extrair, não reescrever. Cada fase mantém o sistema funcionando.

### Fase A — Worker de borda (triagem leve: N0-N1)
- Extrair `CameraWorker` para `src/worker.py` executável em **modo borda**: movimento (N0) + pré-seleção heurística (N1: área do blob, posição, duração, exclusões/máscaras) + captura seletiva de frames candidatos (ROI), **sem detecção IA**.
- Envia candidatos via MQTT/HTTPS para a central (ou enfileira local se offline).
- Config via API central (`GET /api/cameras` por node); registro de nós com heartbeat.

### Fase B — Transporte de candidatos
- Formato de evento com **UUID** (`secur/event/<camera_id>` MQTT) + upload de frame/ROI via HTTPS multipart.
- Fila offline local (arquivo/SQLite) + reenvio; central deduplica por `event_id`.

### Fase C — Central de análise e decisão (N2-N4)
- **Fila de análise** (Redis ou bounded) + consumidor que roda: detecção rápida (N2) → tracking/comportamento/identidade/regras (N3) → **classificação de providência (informar/alertar/perigo eminente)** (N4).
- **PostgreSQL** (particionamento mensal, índices `(camera_id, timestamp)`); camada de storage plugável (SQLite para single-node/Pi).
- Categorias de notificação ganham o nível **crítico/perigo eminente**.

### Fase D — Integração com NVR e evidência
- Descoberta de câmeras via **ONVIF** + sub-stream RTSP do NVR para a borda.
- **Export sob demanda:** central solicita clipe ao NVR e anexa ao evento/alerta (sobretudo para "perigo eminente").
- Retenção por **espaço em disco** para evidência curta; exports fora da retenção.

### Fase E — Resiliência e operação
- Heartbeat/watchdog por nó remoto; fila offline + dedup (MQTT QoS 1).
- HA da central (active/standby); backup do Postgres + verificação de mídia.
- Monitoramento: métricas por nó (CPU, fila, fps de candidato, latência) e por central (fila de análise, fps de inferência) no dashboard.

---

## 8. Hardware sugerido (3 perfis)

| Perfil | Borda | Central | Armazenamento | Custo relativo |
|---|---|---|---|---|
| **Enxuto** | RPi 5 / mini-PC i3 (×5-8) | i7 8c, 32-64 GB, SSD 2 TB | 1× SSD 2 TB | $ |
| **Equilibrado** | mini-PC i3/i5 (×5-8) | Xeon/i7 12-16c, 64 GB, SSD 2 TB + GPU entry (RTX 4060) | 2× SSD 2 TB (RAID-1) | $$ |
| **Completo (HA)** | mini-PC i5 (×5-8) | 2× servidor HA + GPU (RTX 4070+/Arc A770), 128 GB | 2× SSD 4 TB (RAID-1) + NAS p/ exports | $$$ |

Rede: backbone fibra 1G core, switches PoE+ por andar/prédio (uplink fibra), nobreak. NVRs existentes seguem com discos/retenção próprios.

---

## 9. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Dependência da rede entre borda e central | LAN fibra 1G + fila offline na borda; candidatos não se perdem |
| Central sobrecarregada (pico de movimento) | Backpressure: borda reduz fps/descarta com marcação; fila bounded + alerta de saturação |
| Latência de decisão (borda→central) | LAN de poucos ms; aceitável para alerta; "perigo eminente" pode priorizar na fila |
| Compatibilidade NVR (Intelbras/Hikvision/Dahua) | Camada de integração por fabricante; fallback RTSP puro |
| Ponto único na central | HA (2 servidores) para o perfil completo; borda continua triando offline |
| LGPD/privacidade em condomínio | Modo privacidade + 100% local; política de acesso/retenção documentada |
| Custo de banda de exportação | Limitar concorrência, fila, horários |

---

## 10. Próximos passos

1. **Levantar os NVRs do condomínio** (fabricante/modelo): RTSP de re-stream? ONVIF? API de export?
2. Definir topologia física: prédios/andares, switches PoE, NVRs, caminho da fibra.
3. Validar resolução/fps dos **sub-streams** disponíveis para a triagem.
4. Detalhar a **Fase A** (worker de borda leve) e a **Fase C** (central de análise + decisão de providência) como planos de implementação.
5. Definir o formato dos candidatos (MQTT + HTTPS) e o broker (Mosquitto na central).
6. Orçar hardware conforme o perfil escolhido.
