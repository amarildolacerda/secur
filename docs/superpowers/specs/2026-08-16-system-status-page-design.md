# Design: Página de Status do Sistema (embedada no dashboard)

**Data:** 2026-08-16
**Status:** Aprovado (abordagem A, versão embedada no main page)
**Contexto:** Secur / Tucuxi — dashboard web (`src/static/dashboard.js`, `src/templates/dashboard.html`, `src/app.py`)

## Objetivo

Adicionar, no **rodapé da versão** (`vX.Y.Z` na sidebar), um link que revela uma **seção de Status do Sistema embedada dentro do dashboard principal** (não uma página separada/navegação externa). A seção lista os módulos/drivers/serviços ativos e seu estado, combinando:
- **Configurado/Ativado**: se o módulo está habilitado (config/env/modelo presente).
- **Operacional (checagem ao vivo)**: quando viável, uma verificação leve confirma que funciona de fato.

Módulos exibidos (todos): câmeras/workers, detecção de objetos, detecção de movimento, identidade, notificações (Telegram, MQTT, Home Assistant), e o "driver" de captura/inferência (backend OpenCV/DNN).

## Abordagem

**A) Seção embedada no dashboard, alimentada por endpoint JSON.**
- Backend: `GET /api/system-status` retorna um dict estruturado (`build_system_status()` em novo `src/status.py`).
- Frontend: nova `<section id="system-status" class="panel hidden-panel">` dentro de `#page`, populada por JS que busca `/api/system-status` e renderiza cards com badges. O rodapé vira link que chama `setActiveSection('system-status')`.
- Checagens ao vivo com timeout curto e degradação graciosa ("não verificado" em falha).

Isolado do poll de 5s da Visão geral (a seção só atualiza quando visível).

## Modelo de dados (`build_system_status`)

Retorna:
```json
{
  "backend": { "opencv_version": "4.x", "dnn_backend": "OpenCV DNN (ONNX)" },
  "modules": [
    {
      "group": "Captura",
      "items": [
        { "name": "Driver de captura (OpenCV)", "configured": true, "operational": true, "detail": "OpenCV 4.x" },
        { "name": "Workers de câmera", "configured": true, "operational": true, "detail": "3 ativos / 0 offline" }
      ]
    },
    {
      "group": "Detecção",
      "items": [
        { "name": "Movimento", "configured": true, "operational": true, "detail": "MOTION_MIN_AREA=5000" },
        { "name": "Objetos (YOLO)", "configured": true, "operational": true, "detail": "yolov8n.onnx carregado" }
      ]
    },
    {
      "group": "Identidade",
      "items": [
        { "name": "Reconhecimento", "configured": false, "operational": false, "detail": "IDENTITY_ENABLED=false" }
      ]
    },
    {
      "group": "Notificações",
      "items": [
        { "name": "Telegram", "configured": true, "operational": true, "detail": "token ok (getMe)" },
        { "name": "MQTT", "configured": true, "operational": false, "detail": "broker não respondeu" },
        { "name": "Home Assistant", "configured": false, "operational": false, "detail": "URL não configurada" }
      ]
    }
  ]
}
```

### Regras de cada item
- **configured**: derivado de config/env (ex.: `DETECTOR_MODEL_PATH` existe; `IDENTITY_ENABLED`; `TELEGRAM_BOT_TOKEN` set; `MQTT_BROKER_URL`; `HOME_ASSISTANT_URL`).
- **operational**:
  - Workers de câmera: `healthy` em `worker_status` (já existe em `/status`).
  - Detecção de objetos: modelo carrega via `cv2.dnn.readNetFromONNX` (com cache de sucesso).
  - Identidade: recognizer inicializado (se `IDENTITY_ENABLED` e modelo presente).
  - Telegram: `GET https://api.telegram.org/bot<token>/getMe` (timeout 3s).
  - MQTT: `connect` + ping (timeout 3s), via `paho.mqtt` se disponível.
  - Home Assistant: `GET <url>/api/` com header `Authorization: Bearer <token>` (timeout 3s).
- Falha/timeout de checagem externa → `operational=false`, `detail` explica (não quebra a página).

## Backend (`src/status.py` + `src/app.py`)

- **Criar** `src/status.py`: função `build_system_status(camera_manager=None)` que monta o dict acima. Importa `src.config` para ler envs e `camera_manager` (já usado em `/status`) para workers. Checagens externas em funções auxiliares com `try/except` e `socket.setdefaulttimeout`/timeout de requests.
- **Modificar** `src/app.py`:
  - `GET /api/system-status` → `jsonify(build_system_status(camera_manager))`.
  - (Opcional) manter `GET /system-status` renderizando `system-status.html` como fallback — mas o alvo é embedar no dashboard, então o essencial é o endpoint JSON.

## Frontend (`src/templates/dashboard.html` + `src/static/dashboard.js`)

- **`dashboard.html`**: dentro de `#page`, adicionar:
  ```html
  <section class="panel hidden-panel" id="system-status">
    <h2>Status do sistema</h2>
    <div id="system-status-cards" class="grid"></div>
  </section>
  ```
  No rodapé da sidebar (`<div class="footer-nav">v0.2.0</div>`), transformar em link:
  ```html
  <div class="footer-nav"><a href="#" id="nav-system-status">v0.2.0</a></div>
  ```
- **`dashboard.js`**:
  - `setupSystemStatusLink()`: `nav-system-status` → `setActiveSection('system-status')`.
  - `renderSystemStatus()`: `fetch('/api/system-status')` → monta cards por grupo com badges (`badge-ok`, `badge-warn`, `badge-error`, `badge-off`) conforme `configured`/`operational`.
  - Atualizar ao abrir a seção e, enquanto visível, a cada ~15s (timer próprio, limpo ao sair).

## Estados visuais (badges)
- **Operacional** (configured && operational): verde.
- **Configurado, não operacional** (ex.: Telegram cfg mas falhou ping): amarelo ("Configurado").
- **Não configurado**: cinza ("Inativo").
- **Erro de checagem** (exceção): vermelho ("Erro").
- Reuso das variáveis CSS existentes (`--success`, `--warning`, `--danger`, `--muted`) e padrão de `.card`/`.badge-*`.

## Fora de escopo
- Não altera `/status` do dashboard nem o poll de 5s da Visão geral.
- Não implementa ações (ex.: "testar agora") além da checagem automática ao abrir/atualizar.
- Não persiste histórico de status.

## Verificação
- **Teste unitário** `tests/test_status.py`: `build_system_status()` com config mockada e probes mockados (sem rede) → cobre os grupos e estados.
- **Manual**: clicar no link da versão → seção abre no dashboard com cards/badges; derrubar Telegram/MQTT e reabrir → badge amarelo/vermelho conforme checagem.
