# Arquitetura para 80 câmeras — condomínio (fibra óptica)

> **Data:** 2026-08-15
> **Status:** Proposta de dimensionamento (a validar com o projeto real do condomínio)
> **Objetivo:** dimensionar o Secur para um condomínio com 80 câmeras IP, cabeamento estruturado em fibra óptica, identificando gargalos da arquitetura atual e o caminho de evolução em fases.

---

## 1. Contexto

- Hoje o Secur roda em **processo único** com **1 thread por câmera** (`CameraWorker` em `main.py`), SQLite local, thumbnails/clipes em disco local e Flask in-process.
- Projetado para até 8 câmeras (roadmap atual).
- **Cenário real:** condomínio com **80 câmeras IP**, rede cabeada em **fibra óptica** (backbone), câmeras PoE distribuídas em prédios/áreas comuns.

**80 câmeras não é "mais do mesmo" — é mudança de arquitetura.** Os gargalos do modelo atual:

| Gargalo | Motivo |
|---|---|
| **GIL / threads** | Detecção ONNX roda na mesma thread do loop; com muitas câmeras a inferência serializa no GIL |
| **RTSP por thread** | Cada worker abre 1+ stream; 80 streams num só processo = instabilidade e CPU/IO concentrados |
| **SQLite** | Escrita concorrente de vários nós trava/degrada; sem suporte a múltiplos escritores remotos |
| **Disco único** | Thumbnails + clipes + DB no mesmo disco do nó; sem camadas quente/frio |
| **Config em env** | Sem API de registro/descoberta para nós distribuídos |
| **Single point of failure** | Um processo = se cair, caem todas as câmeras |

---

## 2. Arquitetura alvo (distribuída)

```
                    ┌─────────────────────────────────────────────┐
                    │            REDE (fibra óptica)              │
                    │  Backbone 10G core / 1G acesso  + VLANs     │
                    └───────┬──────────────┬─────────────┬────────┘
                            │              │             │
              ┌─────────────▼───┐  ┌───────▼──────┐  ┌───▼─────────────┐
              │ Nó de captura 1 │  │ Nó de captura│  │ Nó de captura N │
              │ (8-16 câmeras)  │  │ 2 (8-16)     │  │ (8-16 câmeras)  │
              │ worker.py       │  │              │  │                 │
              │ detect+clips    │  │              │  │                 │
              └───────┬─────────┘  └──────┬───────┘  └───────┬─────────┘
                      │  MQTT (eventos)   │                 │
                      │  HTTPS (snap/clip)│                 │
              ┌───────▼───────────────────▼─────────────────▼─────────┐
              │               SERVIDOR CENTRAL (1-2 nós)              │
              │  Flask API + Dashboard │ PostgreSQL │ MQTT broker     │
              │  Storage tier: SSD (quente) + HDD/NAS (arquivo)       │
              └───────────────────────────────────────────────────────┘
```

### Componentes

1. **Nós de captura/detecção (workers)** — mini-PCs/servidores de borda, 1 por agrupamento físico de câmeras (ex.: 1 por prédio/andar). Cada nó:
   - Puxa **apenas o sub-stream** das suas câmeras (640×360 @ 5 fps ≈ 0,3-0,5 Mbps) para detecção/movimento;
   - Roda o pipeline atual (movimento → detecção → tracking → regras) **sem mudar a lógica**;
   - Publica **eventos em MQTT** (JSON: câmera, tipo, timestamp, metadados) e envia snapshot/clipe via HTTPS para o servidor central;
   - Mantém buffer de pré-gravação local (10s) e grava clipe localmente se a rede cair (modo offline + fila).

2. **Servidor central** — recebe eventos, persiste em PostgreSQL, serve dashboard/API, gerencia retenção e notificações (Telegram/MQTT/HA). Armazena mídia em camadas: SSD (últimos dias) → HDD/NAS (arquivo).

3. **MQTT broker** — backbone de eventos (já usado no Secur para HA). Workers publicam; central consome; também serve para comandos (armar/desarmar, reconfigurar).

4. **Rede** — fibra no backbone, switches PoE na borda, VLANs separando câmeras de outros tráfegos (e da internet), sub-stream para detecção + main-stream só quando necessário (gravação/visualização).

---

## 3. Dimensionamento de rede (fibra)

| Plano | Bitrate/câmera | 80 câmeras | Observação |
|---|---|---|---|
| Detecção (sub-stream 640×360 @5fps H.264) | ~0,4 Mbps | **~32 Mbps** | Cabe folgado em 1 Gbps |
| Gravação por evento (clipes curtos) | ~1-2 Mbps | **~80-160 Mbps** | Picos durante eventos |
| Gravação 24/7 1080p @15fps H.264 | ~2-4 Mbps | **~160-320 Mbps** | Cabe em backbone 1G; confortável em 10G core |
| Gravação 24/7 4K | ~8 Mbps | **~640 Mbps** | Exige backbone 10G + uplinks dedicados |

**Recomendação:** backbone de fibra **10G no core** (switches core com SFP+) e **1G de acesso** (switches PoE por andar/prédio, uplink em fibra). Isso dá folga de 5-10x para o pior cenário (24/7 1080p) e permite crescer.

- **VLANs:** VLAN Câmeras (isolada, sem internet), VLAN Gestão (NVR/workers), VLAN Usuários (dashboard). 
- **PoE:** somar potência das câmeras (ex.: 80 × 7W = 560W) → dimensionar switches PoE+ com orçamento de energia e nobreak.

---

## 4. Dimensionamento de armazenamento

Fórmula: `armazenamento = câmeras × bitrate × horas/dia × dias retenção` (VBR varia com a cena).

| Cenário | GB/dia por câmera | 80 câmeras/dia | 30 dias |
|---|---|---|---|
| Event-only (atual: thumbnails + clipes curtos) | ~0,5-2 GB | ~40-160 GB | **1,2-4,8 TB** |
| 24/7 sub-stream (640×360 @0,4 Mbps) | ~4,3 GB | ~345 GB | **~10 TB** |
| 24/7 1080p H.264 @2 Mbps | ~21,6 GB | ~1,7 TB | **~52 TB** |
| 24/7 1080p H.265 @1,2 Mbps | ~13 GB | ~1 TB | **~31 TB** |
| 24/7 4K H.265 @4 Mbps | ~43 GB | ~3,4 TB | **~103 TB** |

**Recomendação (custo-benefício):**
- **Camada quente (SSD, 7 dias):** clipes/thumbnails recentes + DB. ~2-4 TB NVMe.
- **Camada fria (HDD/NAS, 30-60 dias):** gravação 24/7 de sub-stream ou 1080p H.265. ~32-64 TB (4-8 discos de 8-16 TB em RAID-5/6) — viável em NAS com 2×10G.
- **Exportações/permanentes:** diretório separado fora da retenção (recurso "exports" do roadmap).

> Nota: para o condomínio, a norma e a prática BR pedem retenção de **30 dias** como padrão; definir política por zona (áreas comuns vs. portaria vs. garagem).

---

## 5. Dimensionamento de computação

### Detecção (a parte cara)

Pipeline atual: movimento (barato) → detecção ONNX só quando há movimento. Com motion-gating, a maioria das câmeras fica ociosa na maior parte do tempo.

- **CPU:** ~1-2 câmeras por core com detecção ativa a 5 fps (modelo YOLO-tiny/ONNX). Com gating por movimento, um nó de **8-16 cores** sustenta **10-20 câmeras** confortavelmente.
- **80 câmeras → 4-6 nós de captura** (ex.: 1 por prédio), cada um mini-PC/servidor com i5/i7 ou Xeon E-2xxx, 16-32 GB RAM, SSD 512GB-1TB, 2×1G ou 1×10G.
- **Alternativa centralizada:** 1 servidor grande (2×Xeon 16-24 cores, 128 GB) com GPU (ex.: RTX 4060/4070 ou Intel Arc) rodando detecção para 80 câmeras, com workers "burros" só capturando. Mais barato de manter, porém ponto único — usar 2 servidores em HA.

### Banco de dados

- SQLite **não serve** para múltiplos nós escrevendo. Migrar para **PostgreSQL** no servidor central.
- Volume estimado: 80 câmeras × 100-1000 eventos/dia = 8k-80k eventos/dia → ~0,25-2,4M eventos/mês. PostgreSQL com índices em `(camera_id, timestamp)` e **particionamento por mês** resolve com folga.
- Thumbnails/clipes continuam como **arquivos**, referenciados por path no banco (como hoje).

### Mensageria

- **MQTT já é dependência do projeto** → natural para o backbone de eventos entre nós e central.
- Workers publicam `secur/event/<camera_id>` com payload JSON; central consome e persiste.
- Comandos: `secur/cmd/<node>` para armar/desarmar, reconfigurar, reiniciar.
- **Offline-first:** cada nó mantém fila local (arquivo/SQLite local) e reenvia quando a rede volta; central deduplica por `event_id` (UUID).

---

## 6. Mudanças no código (fases)

> Ordem pensada para manter o sistema funcionando a cada passo (estratégia strangler: extrair, não reescrever).

### Fase A — Worker como processo autônomo
- Extrair `CameraWorker` de `main.py` para `secur/worker.py` executável (`python -m secur.worker --camera-id N --node-id X`).
- Worker busca sua config na API central (`GET /api/cameras` filtrado por node) em vez de env vars; mantém fallback para config local.
- Dashboard mostra **nós** (registrados via `POST /api/nodes` com heartbeat).

### Fase B — Eventos via MQTT
- `AlertService` ganha publicador MQTT estruturado (`secur/event/<id>` JSON com UUID).
- Novo consumidor no servidor central persiste eventos no banco e dispara notificações.
- Snapshots/clipes sobem via HTTPS `POST /api/events/<uuid>/media` (multipart).
- **Resultado:** N nós publicando, 1 central persistindo — sem SQLite compartilhado.

### Fase C — PostgreSQL
- Camada de storage com dialeto plugável: `StorageBackend` (SQLite hoje, PostgreSQL amanhã).
- Migração: script de export/import + particionamento mensal.
- Manter SQLite como opção para instalação single-node (dev/Pi).

### Fase D — Storage em camadas e retenção por espaço
- Diretórios por camada (SSD/HDD) com política de migração quente→frio (por idade).
- Retenção por **espaço em disco** (ex.: "use até 3TB") além de dias — item do roadmap.
- Exports (clipes permanentes) fora da retenção.

### Fase E — Resiliência e operação
- Heartbeat + watchdog por nó (já existe `/workers` no dashboard — estender para nós remotos).
- Fila offline + dedup (MQTT QoS 1 + `event_id`).
- Backup do PostgreSQL + rotina de verificação de integridade de mídia.
- Monitoramento: métricas por nó (CPU, fila, frames/s, latência RTSP) expostas no dashboard.

---

## 7. Hardware sugerido (3 perfis)

| Perfil | Nós de captura (×5) | Servidor central | Armazenamento | Custo relativo |
|---|---|---|---|---|
| **Enxuto (event-only)** | mini-PC i5, 16 GB, SSD 512 GB, 2×1G | i5/i7, 32 GB, SSD 1 TB | NAS 2×8 TB (RAID-1) | $ |
| **Equilibrado (24/7 sub + eventos)** | mini-PC i7, 32 GB, SSD 1 TB, 1×10G | Xeon E-2xxx/i7, 64 GB, SSD 2 TB | NAS 4×8 TB (RAID-5) | $$ |
| **Completo (24/7 1080p + IA)** | servidor 1U Xeon 16c, 64 GB, SSD 1 TB | 2× servidor HA + GPU (RTX 4060+) | NAS 8×16 TB (RAID-6) ou SAN | $$$ |

Rede (todos): switch core 10G (SFP+) + switches PoE+ por andar/prédio com uplink fibra + nobreak dimensionado.

---

## 8. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Ponto único no servidor central | 2 servidores HA (active/standby), workers continuam gravando offline |
| Banda da rede interna | VLANs + sub-stream para detecção; main-stream só sob demanda |
| Custo de armazenamento 24/7 | H.265, retenção em camadas, 24/7 só de sub-stream ou zonas críticas |
| Detecção IA em 80 streams | Motion-gating (já existe) + nós distribuídos; GPU opcional |
| LGPD/privacidade em condomínio | Já temos modo privacidade + 100% local; documentar política de acesso e retenção |
| Manutenção de N nós | Config centralizada via API, heartbeat, atualização por pacote |

---

## 9. Próximos passos

1. Validar com o projeto real do condomínio: número de câmeras por prédio/andar, resolução, retenção exigida (30 dias?), orçamento.
2. Detalhar a **Fase A** como plano de implementação (extração do worker + API de nós).
3. Definir o broker MQTT (ex.: Mosquitto no servidor central) e o formato dos eventos.
4. Decidir o modelo de detecção: nós de borda (4-6) vs. centralizado com GPU.
5. Orçar hardware conforme o perfil escolhido.
