# Arquitetura para 80 câmeras — condomínio (fibra óptica)

> **Data:** 2026-08-15
> **Status:** Proposta de dimensionamento (a validar com o projeto real do condomínio)
> **Objetivo:** dimensionar o Secur para um condomínio com 80 câmeras IP, rede em fibra óptica, **mantendo a gravação 24/7 nos NVRs existentes** — o Secur responde apenas pela análise.

---

## 1. Princípio de arquitetura

**A gravação contínua e a retenção ficam nos NVRs do condomínio** (responsabilidade e discos deles). O Secur **não grava 24/7** — ele consome sub-streams para análise (movimento → detecção IA → regras → eventos/alertas), guarda apenas **evidência curta por evento** (thumbnail + clipe de alguns segundos) e o banco de eventos, e integra com os NVRs para recuperar gravação completa quando necessário.

Consequências:
- **Rede:** o tráfego pesado de gravação (câmeras → NVR) não passa pelo backbone do Secur; o Secur só puxa sub-streams leves.
- **Armazenamento:** sem custo de 24/7 no Secur — thumbnails + clipes de evidência + DB (~1-5 TB/30d, não ~50-100 TB).
- **Computação:** análise pura, mais leve e mais barata.
- **Resiliência:** o NVR é o "gravador de verdade"; o Secur pode cair/reiniciar sem perder evidência contínua.

---

## 2. Arquitetura alvo

```
      Câmeras PoE (80) — switches PoE por andar/prédio (uplink fibra)
        │                                   │
        │ main-stream (gravação)            │ sub-stream (análise)
        ▼                                   ▼
   ┌──────────┐  (Rede interna,    ┌──────────────────┐
   │  NVR(s)  │   não cruza o      │ Nós de análise   │
   │ gravação │   backbone Secur)  │ Secur (4-6 nós,  │
   │ 24/7 +   │                    │ 8-16 câmeras c/  │
   │ retenção │                    │ movimento→IA→    │
   └──────────┘                    │ eventos)         │
                                   └────────┬─────────┘
                                            │ MQTT (eventos) + HTTPS (mídia)
                                            ▼
                                   ┌──────────────────┐
                                   │ Servidor central │
                                   │ Flask + Postgres │
                                   │ dashboard/alertas│
                                   └──────────────────┘
```

### Componentes

1. **NVRs (existentes)** — gravam 24/7 com retenção própria (ex.: 30 dias). Expõem RTSP (re-stream) e/ou ONVIF para o Secur consumir sub-streams. Sem mudança de responsabilidade.
2. **Nós de análise Secur** — puxam o **sub-stream** de cada câmera (640×360 @ 5 fps ≈ 0,3-0,5 Mbps) via RTSP do NVR ou direto da câmera; rodam o pipeline atual (movimento → detecção → tracking → regras); publicam eventos em MQTT e enviam thumbnail/clipe de evidência via HTTPS.
3. **Servidor central** — recebe eventos, persiste em PostgreSQL, serve dashboard/API, dispara notificações (Telegram/MQTT/HA), gerencia retenção da evidência curta.
4. **Integração com NVR** — API/ONVIF do NVR para: listar câmeras, consultar gravação e **exportar evidência sob demanda** (ex.: baixar o clipe do NVR para anexar a um alerta ou para o morador/síndico).

---

## 3. Dimensionamento de rede (fibra)

O tráfego do Secur é só o de análise:

| Plano | Bitrate/câmera | 80 câmeras | Observação |
|---|---|---|---|
| Sub-stream 640×360 @5fps H.264 | ~0,4 Mbps | **~32 Mbps** | Cabe em 1 Gbps |
| Sub-stream 720p @5fps H.264 | ~0,8-1 Mbps | **~64-80 Mbps** | Cabe em 1 Gbps |
| Sub-stream 1080p @5fps H.265 | ~1 Mbps | **~80 Mbps** | Cabe em 1 Gbps |

**Recomendação:**
- **Backbone fibra 1G é suficiente** para a análise do Secur (folga de 10x+); **10G no core** só se quiser sobra para 4K/mais streams ou tráfego de exportação pesado.
- O tráfego de gravação (câmeras → NVR) fica **local aos switches PoE/andar** e não cruza o backbone — projetar os uplinks dos switches PoE para os NVRs conforme os NVRs exigirem.
- **VLANs:** VLAN Câmeras (isolada, sem internet), VLAN NVR/Gravação, VLAN Secur/Análise, VLAN Gestão (dashboard). 
- **PoE:** somar potência das câmeras (ex.: 80 × 7W = 560W) → switches PoE+ com orçamento de energia e nobreak.

---

## 4. Dimensionamento de armazenamento (Secur)

Só evidência curta por evento + banco:

| Tipo | Volume estimado (80 câmeras, 30 dias) |
|---|---|
| Thumbnails (JPEG ~100 KB × eventos) | ~0,1-0,5 TB |
| Clipes de evidência (5-20 s @ 5 fps, H.264) | ~0,5-3 TB |
| Banco de eventos (PostgreSQL + índices) | < 0,1 TB |
| **Total** | **~1-4 TB** |

**Recomendação:** 1 SSD NVMe de 2-4 TB no servidor central (ou 2 em RAID-1) resolve. Exportações/permanentes (clipes baixados do NVR) em diretório separado fora da retenção. Nada de storage em camadas 24/7 — **isso fica nos NVRs**.

---

## 5. Dimensionamento de computação

### Análise (a parte do Secur)

Pipeline atual: movimento (barato) → detecção ONNX só quando há movimento. Com motion-gating, a maioria das câmeras fica ociosa.

- **CPU:** ~1-2 câmeras por core com detecção ativa a 5 fps. Um nó de 8-16 cores sustenta 10-20 câmeras.
- **80 câmeras → 4-6 nós de análise** (ex.: 1 por prédio/andar): mini-PC i5/i7, 16-32 GB RAM, SSD 512 GB-1 TB (buffer de pré-gravação + fila offline), 2×1G.
- **Alternativa centralizada:** 1 servidor com GPU (RTX 4060+) analisando as 80 câmeras, com workers "burros" só capturando; 2 servidores em HA se quiser redundância.

### Banco de dados

- SQLite não serve para múltiplos nós escrevendo → **PostgreSQL** no servidor central.
- Volume: 80 câmeras × 100-1000 eventos/dia = 8k-80k eventos/dia → 0,25-2,4M eventos/mês. Particionamento mensal + índices `(camera_id, timestamp)` resolve com folga.
- Thumbnails/clipes continuam como arquivos referenciados por path.

### Mensageria

- **MQTT** (já é dependência do projeto) como backbone de eventos: `secur/event/<camera_id>` com JSON + UUID.
- **Offline-first:** cada nó mantém fila local e reenvia quando a rede volta; central deduplica por `event_id`.

---

## 6. Mudanças no código (fases)

> Estratégia strangler: extrair, não reescrever.

### Fase A — Worker como processo autônomo
- Extrair `CameraWorker` de `main.py` para `secur/worker.py` executável (`python -m secur.worker --camera-id N --node-id X`).
- Config via API central (`GET /api/cameras` filtrado por node) com fallback local.
- Dashboard mostra nós (registro via `POST /api/nodes` + heartbeat).

### Fase B — Eventos via MQTT
- `AlertService` publica em MQTT estruturado (JSON + UUID); consumidor central persiste e notifica.
- Snapshots/clipes sobem via HTTPS `POST /api/events/<uuid>/media`.
- **Resultado:** N nós publicando, 1 central persistindo — sem SQLite compartilhado.

### Fase C — PostgreSQL
- Camada de storage plugável (`StorageBackend`: SQLite hoje, PostgreSQL amanhã).
- Migração com particionamento mensal; SQLite permanece para single-node/Pi.

### Fase D — Integração com NVR e evidência
- Descoberta de câmeras via **ONVIF** (listar dispositivos no NVR) e consumo de sub-stream RTSP.
- **Export sob demanda:** endpoint que solicita clipe ao NVR (API/ONVIF) e o anexa ao evento/alerta.
- Retenção por **espaço em disco** para a evidência curta (ex.: "use até 2TB") + exports fora da retenção.

### Fase E — Resiliência e operação
- Heartbeat/watchdog por nó remoto; fila offline + dedup (MQTT QoS 1).
- HA do servidor central (active/standby); backup do PostgreSQL + verificação de mídia.
- Monitoramento: métricas por nó (CPU, fila, fps, latência RTSP) no dashboard.

---

## 7. Hardware sugerido (3 perfis — sem storage 24/7)

| Perfil | Nós de análise (×5) | Servidor central | Armazenamento (central) | Custo relativo |
|---|---|---|---|---|
| **Enxuto (event-only)** | mini-PC i5, 16 GB, SSD 512 GB, 2×1G | i5/i7, 32 GB, SSD 1 TB | 1× SSD 2 TB | $ |
| **Equilibrado (análise + evidência)** | mini-PC i7, 32 GB, SSD 1 TB, 2×1G | i7, 64 GB, SSD 2 TB | 2× SSD 2 TB (RAID-1) | $$ |
| **Completo (centralizado c/ GPU)** | só captura (RPi/mini-PC leves) | 2× servidor HA + GPU (RTX 4060+), 64-128 GB | 2× SSD 4 TB (RAID-1) + NAS opcional p/ exports | $$$ |

Rede (todos): backbone fibra **1G core** (10G opcional), switches PoE+ por andar/prédio com uplink fibra, nobreak. Os **NVRs já existentes** seguem com seus discos e retenção.

---

## 8. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Dependência do NVR para evidência longa | Documentar contrato com o NVR (RTSP/ONVIF/API); testar export antes do go-live |
| Compatibilidade RTSP/ONVIF entre fabricantes (Intelbras, Hikvision, Dahua) | Camada de integração por fabricante; fallback para RTSP puro |
| Ponto único no servidor central | 2 servidores HA; nós continuam analisando e enfileirando offline |
| Banda para exportação pesada | Limitar concorrência de exports; fila; horários |
| LGPD/privacidade em condomínio | Modo privacidade + 100% local; política de acesso e retenção documentada |
| Manutenção de N nós | Config centralizada via API, heartbeat, atualização por pacote |

---

## 9. Próximos passos

1. **Levantar os NVRs do condomínio** (fabricante/modelo): RTSP de re-stream disponível? ONVIF? API de export?
2. Definir a topologia física: quantos prédios/andares, onde ficam os switches PoE e os NVRs, qual o caminho da fibra.
3. Validar resolução/fps dos sub-streams que os NVRs/câmeras conseguem fornecer para análise.
4. Detalhar a **Fase A** como plano de implementação (extração do worker + API de nós).
5. Definir o broker MQTT (ex.: Mosquitto no servidor central) e o formato dos eventos.
6. Orçar hardware conforme o perfil escolhido (sem storage 24/7).
