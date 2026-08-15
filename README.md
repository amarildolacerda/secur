# Secur

Sistema de vigilância inteligente para câmeras IP, com desenvolvimento inicial em Linux e deploy final planejado para Raspberry Pi.

## Visão geral

O projeto captura vídeo de câmeras IP, realiza detecção de movimento e classificação de objetos em tempo real usando IA, e gera alertas configuráveis para eventos de segurança.

## Escopo do MVP

- Captura de vídeo de até 4 câmeras IP simultâneas.
- Detecção de movimento e classificação básica de objetos.
- Definição de zonas de interesse e regras configuráveis.
- Alertas por Telegram.
- Dashboard web simples para visualização e histórico.

## Requisitos

### Funcionais
- Capturar streams RTSP/HTTP de câmeras IP.
- Detectar movimento em cada stream.
- Classificar objetos em pessoas, veículos e animais.
- Configurar zonas de interesse e horários sensíveis.
- Gerar alertas quando regras de segurança forem violadas.
- Registrar eventos com timestamp, câmera, tipo de evento e imagem de evidência.
- Expor dashboard web para monitoramento em tempo real.

### Não funcionais
- Processamento em tempo real com latência baixa (<2s de atraso aceitável no MVP).
- Uso eficiente de CPU/RAM para funcionar em Raspberry Pi 4.
- Modularidade para trocar modelos de IA e adicionar canais de alerta.
- Operação local sem depender exclusivamente da nuvem.
- Persistência de eventos em banco leve para buscas rápidas.

## Arquitetura proposta

- Captura de vídeo: OpenCV + ffmpeg/RTSP.
- IA: modelo YOLOv5/YOLOv8 ou TensorFlow Lite para inferência de objetos.
- Orquestração de câmeras: multiprocessing ou asyncio para cada stream.
- Persistência: SQLite para eventos; opcional InfluxDB para séries temporais.
- Backend: Flask ou FastAPI para APIs e dashboard.
- Frontend: interface web leve com gráficos e visualização de câmeras.
- Alertas: Telegram (e-mail/webhook em melhorias futuras) e integração futura com Home Assistant.

## Requisitos de sistema

### Hardware recomendado
- PC/Linux para desenvolvimento inicial.
- Raspberry Pi 4 com 4GB ou 8GB de RAM para deploy final.
- Módulo de armazenamento rápido (SSD USB ou cartão microSD de alta classe).
- Fonte de energia adequada para Pi e periféricos.
- Rede estável via Ethernet preferencialmente; Wi-Fi como alternativa.
- Câmeras IP com RTSP/HTTP e resolução compatível (720p recomendado).

### Software recomendado
- Linux (Ubuntu, Debian, Fedora) para desenvolvimento inicial.
- Raspberry Pi OS 64-bit para o deploy final.
- Python 3.11+.
- OpenCV.
- PyTorch, TensorFlow Lite ou ONNX Runtime.
- Flask ou FastAPI.
- SQLite.

## Como rodar

### Com Docker

1. Certifique-se de que o Docker Desktop está instalado e o daemon está rodando.
2. Construa a imagem:
   ```bash
   docker build -t secur-app .
   ```
3. Execute o container:
   ```bash
   docker run --rm -p 8000:8000 -v "${PWD}:/app" -v "${PWD}/data:/app/data" \
     -e SERVER_HOST=0.0.0.0 \
     -e SERVER_PORT=8000 \
     -e TELEGRAM_BOT_TOKEN=your_bot_token \
     -e TELEGRAM_CHAT_ID=your_chat_id \
     -e HOME_ASSISTANT_URL=http://192.162.1.12:8123 \
     -e HOME_ASSISTANT_TOKEN=your_ha_token \
     -e HOME_ASSISTANT_EVENT_TYPE=secur_alert \
     secur-app
   ```
4. Opcionalmente, use docker compose:
   ```bash
   docker compose up --build
   ```
5. Acesse:
   - `http://localhost:8000/health`   - `http://localhost:8000/status`   - `http://localhost:8000/cameras`
   - `http://localhost:8000/events`

### Localmente

1. Instale dependências:
   ```bash
   py -m pip install -r requirements.txt
   ```
2. Baixe um vídeo de teste:
   ```bash
   py scripts/download_sample_video.py
   ```
   Ou execute o arquivo de atalho:
   ```bash
   download_sample_video.bat
   ```
   Se ainda houver erro HTTP 403, baixe manualmente um MP4 de exemplo para `data/sample.mp4`.
3. Configure as câmeras no dashboard usando o arquivo local:
   - `source`: `C:\\git\\secur\\data\\sample.mp4` (Windows)
   - ou `/path/to/project/data/sample.mp4` (Linux)
4. Defina o caminho do modelo de detecção de objetos (opcional) em `DETECTOR_MODEL_PATH`.
5. Configure as variáveis de ambiente do Telegram:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Configure o MQTT do Home Assistant (inicial):
   - `MQTT_BROKER_URL` (padrão: `192.162.1.12`)
   - `MQTT_BROKER_PORT` (padrão: `1883`)
   - `MQTT_USERNAME` (padrão: `kzuca`)
   - `MQTT_PASSWORD` (padrão: `123`)
   - `MQTT_TOPIC` (padrão: `homeassistant/secur/alert`)
7. Configure as variáveis de ambiente do Home Assistant HTTP opcional:
   - `HOME_ASSISTANT_URL` (ex: `http://192.162.1.12:8123`)
   - `HOME_ASSISTANT_TOKEN`
   - `HOME_ASSISTANT_EVENT_TYPE` (opcional, padrão `secur_alert`)
8. Inicie o servidor:
   ```bash
   python run.py
   ```
9. Alternativa com instalação do pacote:
   ```bash
   python -m pip install .
   secur
   ```
10. Acesse:
    - `http://localhost:8000/`
    - `http://localhost:8000/health`
    - `http://localhost:8000/status`
    - `http://localhost:8000/workers`
    - `http://localhost:8000/docs`
    - `http://localhost:8000/cameras`
    - `http://localhost:8000/events`

### Com Makefile

- Instalar dependências:
  ```bash
  make install
  ```
- Executar localmente:
  ```bash
  make run
  ```
- Executar testes unitários e de integração:
  ```bash
  make test
  ```
- Executar toda a verificação do projeto (build Docker + teste):
  ```bash
  make check
  ```
- Executar todos os passos de verificação e build:
  ```bash
  make all
  ```
- Construir imagem Docker:
  ```bash
  make docker-build
  ```
- Subir container Docker:
  ```bash
  make docker-up
  ```
- Parar container Docker:
  ```bash
  make docker-down
  ```

## Funcionalidades principais

- Detecção de movimento por câmera.
- Classificação de objetos em categorias chave.
- Zonas de interesse personalizáveis (entrada, quintal, garagem).
- Regras de alerta baseadas em área, categoria e horário.
- Visualização de câmeras ao vivo e histórico de eventos.
- Exportação básica de logs e imagens de evidência.

## Privacidade

- **100% local**: todo o processamento (detecção, reconhecimento, gravação) roda no dispositivo; nada sai dele, exceto pelos canais que você configurar explicitamente (Telegram, MQTT, Home Assistant).
- **Mascaramento de regiões**: configure polígonos de máscara por câmera (formato JSON igual ao das zonas de exclusão) no dashboard; o blur é aplicado antes de salvar thumbnail, clipe e snapshot — a detecção usa sempre o frame original.
- **Modo privacidade**: desliga o reconhecimento de identidade (movimento e objetos continuam ativos). Ative via env `PRIVACY_MODE=true`, pela API `PUT /api/settings` ou pelo toggle no dashboard (Configurações).
- **Retenção seletiva**: política por zona (`retention_policy` JSON com `thumbnails`, `clips` e `days`) controla o prune de thumbnails e clipes.

## Comportamento e anomalias (Fase 3)

- **Loitering**: pessoa/veículo na mesma região por ≥ `LOITERING_SECONDS` (default 30s) dispara o evento `loitering` (cooldown próprio, env `ALERT_COOLDOWN_LOITERING`).
- **Direção de movimento**: configure uma linha virtual por zona (`direction_line` JSON: `{"axis":"vertical"|"horizontal","position":0-1}`) — cruzá-la dispara `direction_change` com a direção (entrando/saindo).
- **Zona restrita fora de horário**: desconhecido em zona privativa/segurança fora do schedule da zona → `intruder_detected` (prioridade); pessoa conhecida → `identity_recognized`.
- **Queda (heurística)**: pessoa com bbox deitada (`w/h ≥ FALL_ASPECT_RATIO`, default 1.2) → `fall_detected`. O ângulo do torso por modelo de pose local fica como backlog (custo de inferência no hardware).

## Casos de perigo

- Pessoa em área restrita.
- Veículo em área privada.
- Animal grande em local proibido.
- Movimento fora de horário autorizado.
- Intrusão em porteiro automático ou portão.

## Roadmap

### 1. MVP ✅
- [x] Conectar 1 câmera IP
- [x] Detectar movimento com OpenCV
- [x] Exibir stream e gerar evento básico

### 2. IA de detecção ✅
- [x] Integrar YOLO para reconhecimento de pessoas, carros e animais
- [ ] Validar acurácia e desempenho no Raspberry Pi

### 3. Multi-câmeras ✅
- [x] Suportar 4 câmeras simultâneas
- [x] Melhorar paralelismo e estabilidade

### 4. Alertas e dashboard ✅
- [x] Notificações via Telegram
- [x] Integração MQTT
- [x] Integração Home Assistant (HTTP events)
- [x] Dashboard web com histórico
- [x] CRUD de câmeras (adicionar/editar/excluir)
- [x] CRUD de zonas com classificação (pública/segurança/privativa)
- [x] Severidade de alertas baseada na classificação da zona
- [x] Evento `no_motion` após 60s sem movimento (todas as zonas, configurável via `NO_MOTION_ALERT_SECONDS`)
- [x] Estilo adaptado (ESP-NOW Hub pattern)

### 5. Expansão
- [ ] Suportar até 8 câmeras
- [ ] Treinamentos customizados de modelos
- [ ] Integração com automação residencial (já parcial com HA)

### Melhorias futuras
- [ ] **Snapshot inteligente** — usar snapshots capturados para identificar pessoas, animais e veículos de forma amigável; notificar informações sem gerar alertas de segurança
- [ ] Armazenamento em nuvem para backup e análise
- [ ] Notificações push via e-mail
- [ ] Detecção de comportamentos e anomalias
- [ ] Módulo móvel para notificações e controle remoto
- [ ] Validação completa de performance em Raspberry Pi
### 6. Recursos candidatos (inspirados no Frigate NVR)
> Backlog avaliado a partir do [Frigate](https://github.com/amarildolacerda/frigate)
> e da [pesquisa de desejos de usuários](docs/research-user-wants.md).
> Marque os que deseja implementar em uma próxima fase. CPU-leve = adequado ao Raspberry Pi.

#### Alta prioridade (CPU-leve, encaixe direto no pipeline atual)
- [ ] Filtros de objeto por score (min_score/threshold com mediana) — suprime falsos positivos
- [ ] Máscaras de movimento vs. máscaras de filtro de objeto por classe (bottom-center)
- [ ] Objetos estacionários — pausar detecção em objeto parado (~10s) para economizar CPU
- [ ] Re-streaming RTSP — reduz número de conexões à câmera (importante com 4-8 câmeras)
- [ ] Exportação de clipes permanentes (fora da retenção)

#### Alta prioridade — promovidos pela pesquisa de usuários
- [ ] Gravação contínua 24/7 com retenção em camadas (ex.: tudo 3d, movimento 7d, alertas 30d)
- [ ] Pré-gravação (pre-roll) — contexto antes do evento (ex.: 10s antes da detecção)
- [ ] PWA — dashboard instalável como app + notificações push (manifest + service worker)
- [ ] Retenção por espaço em disco (ex.: "use até 3TB") + múltiplos locais de armazenamento

#### Média prioridade (bom valor, custo moderado)
- [ ] Timeline de revisão agrupando eventos sobrepostos (review items)
- [ ] UI de revisão simplificada ("por que este evento?") + ações em lote (multiselect/delete)
- [ ] Armar/desarmar câmera/zona por horário (ex.: desarmar quando estou em casa)
- [ ] Permissões/roles — modo visualização (view-only) para não-admin
- [ ] Birdseye — visão geral que mostra apenas câmeras com atividade
- [ ] Detecção de áudio (sirene, alarme, vidro quebrando) — leve na CPU

#### Backlog (dependem de hardware/infra)
- [ ] Autotracking PTZ via ONVIF
- [ ] Reconhecimento de placas (LPR) — OCR local
- [ ] Face recognition dedicada (sub_label em pessoa conhecida)
- [ ] WebRTC/MSE live view de baixa latência (via go2rtc)
- [ ] Áudio bidirecional (two-way) em doorbell
- [ ] Integração com portaria remota / app do morador (contexto Brasil)
- [ ] Semantic search (embeddings locais) — requer 8GB+ RAM e AVX2; não roda no Pi
### 7. Escala 80 câmeras (condomínio — fibra óptica)
> Projeto real: condomínio com 80 câmeras IP em rede de fibra óptica.
> **A gravação 24/7 fica nos NVRs; a borda só faz triagem leve (movimento); a central de análise decide a providência (informar/alertar/perigo eminente).**
> Triagem em níveis (funil N0-N4): borda separa candidatos (movimento + heurísticas); central decide.
> Proposta completa em [docs/architecture-80-cameras.md](docs/architecture-80-cameras.md).

#### Fase A — Nó de borda (triagem leve N0-N1)
- [ ] N0: movimento (OpenCV) + N1: pré-seleção heurística (área/posição/duração/exclusões)
- [ ] Captura seletiva de frames/ROI candidatos; envio MQTT/HTTPS; fila offline; heartbeat

#### Fase B — Transporte de candidatos
- [ ] Eventos com UUID (MQTT) + upload de frame/ROI via HTTPS multipart
- [ ] Consumidor central deduplica por event_id; prioridade na fila p/ zonas críticas

#### Fase C — Central de análise e decisão (N2-N4)
- [ ] N2: detecção rápida (YOLO-tiny/ONNX no ROI) → N3: tracking/comportamento/identidade/regras
- [ ] N4: classificação de providência: informar / alertar / perigo eminente (novo nível crítico)
- [ ] PostgreSQL central (particionamento mensal); storage plugável (SQLite p/ single-node)

#### Fase D — Integração com NVR e evidência
- [ ] Descoberta de câmeras via ONVIF + sub-stream RTSP do NVR para a borda
- [ ] Export sob demanda: central baixa clipe do NVR e anexa ao evento/alerta
- [ ] Retenção por espaço em disco para evidência curta; exports fora da retenção

#### Fase E — Resiliência e operação
- [ ] Heartbeat/watchdog por nó remoto; fila offline + dedup (MQTT QoS 1)
- [ ] HA da central (active/standby); backup do banco e verificação de mídia
### 8. Situações monitoráveis (além de intrusão)
> O Secur monitora **situações**, não só presença/intrusão — via visão (funil N0-N4) e/ou sensores (MQTT/Home Assistant).
> Matriz completa em [docs/architecture-80-cameras.md](docs/architecture-80-cameras.md) (seção 1.2).

#### Visão (central de análise N2-N4)
- [ ] Fogo/fumaça (modelo YOLO fire/smoke) — perigo eminente
- [ ] Objeto abandonado em área de circulação (stationary + zona) — ex.: carrinho
- [ ] Aglomeração/multidão em área comum (contagem de pessoas)
- [ ] Veículo parado/obstruindo em local proibido
- [ ] Pichação/vandalismo suspeito
- [ ] Porta/janela aberta fora de horário

#### Sensores (via MQTT/Home Assistant — entram direto na central)
- [ ] Alagamento/vazamento (bóia, umidade, condutivo) — alerta imediato
- [ ] Fumaça/calor/CO (reforço ao fogo por visão)
- [ ] Porta/janela (contato) — cruzar com horário
- [ ] Qualquer sensor MQTT como "candidato já confirmado" no N4

#### Regras de negócio
- [ ] Thresholds e providência configuráveis por situação + zona
- [ ] Cooldown por situação (reaproveitar mecanismo atual)
#### Alta circulação (shopping, rodoviária/terminal, varejo)
- [ ] Bagagem/objeto abandonado (stationary + owner association) — alertar em área crítica
- [ ] Aglomeração/densidade (capacidade excedida) — alertar
- [ ] Filas e tempo de espera (caixa, portaria, guichê) — operacional
- [ ] Fluxo/contagem de pessoas (footfall) — analytics
- [ ] Queda em escada/elevador — perigo eminente
- [ ] Superlotação de elevador — informar/alertar
- [ ] Furto na portaria/encomenda (loitering + zona) — alertar
- [ ] Movimento suspeito na garagem (loitering perto de veículo) — alertar
- [ ] Self-checkout/caixa fraud (área de caixa + POS) — alertar (prevenção de perdas)

> Pesquisa completa: [docs/research-monitoring-venues.md](docs/research-monitoring-venues.md).
#### Prioridade recomendada (valor para o usuário)
1. **Alagamento/vazamento via sensores MQTT** — custo ~zero (já há MQTT/HA), impacto altíssimo (garagem subterrânea), entrega rápida
2. **Fogo/fumaça por visão** — maior impacto (vidas+patrimônio), modelo YOLO fire/smoke maduro, complementa sensores obrigatórios
3. **Objetos estacionários** — multiplicador: desbloqueia carrinho abandonado, veículo obstruindo, bagagem, vandalismo
4. **Loitering contextual (portaria/garagem)** — furto é a dor nº1 em condomínio BR; `check_loitering` já existe no código
5. Aglomeração/footfall/filas — só quando entrar em shopping/terminal (outro público)





