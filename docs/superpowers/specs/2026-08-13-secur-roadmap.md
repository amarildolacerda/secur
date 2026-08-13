# Secur — Roadmap de Novos Requisitos (2026-08-13)

## Contexto

Levantamento baseado em pesquisa web (2024-2026) de três frentes:
1. **Usuários** — fóruns (Reddit r/homesecurity, r/smarthome, r/homeassistant), reviews (Ring, Wyze, Eufy, Reolink, Arlo, Nest), feature requests (Aqara).
2. **Indústria** — relatórios (Parks Associates, Axis Perspectives 2026, Gartner), ISC West 2026, lançamentos (Arlo+Origin AI, Xiaomi, Hikvision).
3. **Ciência** — papers CVPR/ICCV/WACV/NeurIPS 2025 (VAD, action recognition, person re-ID, zero-shot anomaly detection, privacy-preserving).

## Estado atual do projeto (âncora)

Já implementado no `secur`:
- Detecção de movimento (`motion.py` — `MotionDetector`)
- Detecção de objetos (`detector.py` — `ObjectDetector`, YOLO)
- Reconhecimento de identidade (`identity.py` — face + ReID)
- Zonas com classificação (privativa/segurança/pública)
- Thumbnails por câmera (20, intervalo 10s) + histórico no dashboard
- Notificações Telegram/MQTT/Home Assistant com routing por evento × canal
- Dashboard responsivo (cards, preview, Ao vivo, histórico, seção Notificações)
- Cooldown de alertas, `no_motion`, `snapshot_info`, `intruder_detected`, `unknown_detected`, `object_detected`

## Critério de priorização

**Valor para o usuário** — ordenar pelo que mais resolve as queixas reais dos usuários (falsos positivos é a queixa nº 1 em todas as fontes).

## Fases

### Fase 1 — Reduzir falsos positivos (queixa nº 1)

| # | Feature | Valor | Esforço | Encaixe |
|---|---------|-------|---------|---------|
| 1.1 | **Filtro por classe de objeto** — alertar só para pessoa/carro/animal/pacote selecionados por câmera | Alto | Baixo | `detector.py` já retorna `label`; adicionar config por câmera + filtro no `decide_worker_event` |
| 1.2 | **Zonas de exclusão por câmera** — ignorar regiões do frame (rua, árvore, janela vizinho) | Alto | Médio | Novo campo na tabela `cameras` (JSON de polígonos); aplicar no `MotionDetector`/`ObjectDetector` |
| 1.3 | **Cooldown configurável por evento** — hoje global (`ALERT_COOLDOWN_SECONDS`); permitir por tipo | Médio | Baixo | `config.py` + `last_alert_time` em `main.py` |
| 1.4 | **Horário de alerta por zona** — ex: zona privativa só alerta 22h-6h | Médio | Médio | Campo `schedule` na tabela `zones`; checagem no `CameraWorker` |

### Fase 2 — Alertas ricos (contexto = retenção de usuário)

| # | Feature | Valor | Esforço | Encaixe |
|---|---------|-------|---------|---------|
| 2.1 | **Snapshot anexado no Telegram** — enviar o thumbnail junto com o alerta | Alto | Baixo | `alerts.py` `telegram_handler` + `sendPhoto`; thumbnail já existe |
| 2.2 | **Clipe de vídeo por evento** — salvar N segundos (MP4) além do thumbnail | Alto | Médio | Novo buffer circular de frames no `CameraWorker`; tabela `event_clips` |
| 2.3 | **Notificação com contexto completo** — zona + classificação + identidade + categoria no texto | Médio | Baixo | `_format_message` em `alerts.py` (payload já tem tudo) |
| 2.4 | **Revisão de clipes no dashboard** — player de vídeo do evento | Médio | Médio | Rota `/clips/<id>/video` + modal no dashboard |

### Fase 3 — Detecção de comportamento/anomalia (indústria + ciência)

| # | Feature | Valor | Esforço | Encaixe |
|---|---------|-------|---------|---------|
| 3.1 | **Loitering** — pessoa parada/andando na mesma área por Xs | Alto | Médio | Tracking simples por bbox (IoU) no `CameraWorker`; novo evento `loitering` |
| 3.2 | **Direção de movimento** — pessoa entrando/saindo da zona | Médio | Médio | Centroide de bbox entre frames; novo evento `direction_change` |
| 3.3 | **Pessoa em zona restrita fora de horário** — combina 1.4 + identidade | Alto | Médio | Regra em `decide_worker_event` |
| 3.4 | **Detecção de queda / pessoa no chão** — útil para idosos | Médio | Alto | Modelo de pose/action recognition; avaliar viabilidade com YOLO-pose |

### Fase 4 — Privacidade e robustez

| # | Feature | Valor | Esforço | Encaixe |
|---|---------|-------|---------|---------|
| 4.1 | **Mascaramento de regiões** — blur de áreas sensíveis (janelas vizinhos) nos thumbnails/snapshots/preview | Alto | Médio | Máscara por câmera (reusa 1.2); aplicar blur no frame antes de salvar |
| 4.2 | **Retenção seletiva** — política por zona/evento (ex: não gravar zona pública, reter menos) | Médio | Baixo | `prune_camera_thumbnails` + config por zona |
| 4.3 | **Modo privacidade** — desativa reconhecimento de identidade, mantém movimento/objeto | Médio | Baixo | Flag global em `config.py`; `identity_recognizer=None` |
| 4.4 | **Garantia 100% local** — indicador no dashboard de que nada sai do dispositivo | Baixo | Baixo | Badge estático + doc |

### Fase 5 — Integração e experiência

| # | Feature | Valor | Esforço | Encaixe |
|---|---------|-------|---------|---------|
| 5.1 | **Sirene/áudio externo** — acionar dispositivo via MQTT/HA em evento crítico | Médio | Baixo | Novo handler no `AlertService` (routing `automation`) |
| 5.2 | **Busca por linguagem natural** — "eventos de pessoa na entrada ontem à noite" | Médio | Alto | LLM local opcional; indexar eventos/thumbnails |
| 5.3 | **Cross-camera tracking** — seguir pessoa entre câmeras (person re-ID leve) | Médio | Alto | Reusa `identity.py`; correlação temporal entre workers |
| 5.4 | **Exportação/backup** — exportar eventos + thumbnails + clipes | Médio | Médio | Rota de download + zip |

## Regras de decisão (do AGENTS.md do projeto)

- **Shared vs individual**: se a feature for reaproveitada em várias implementações, vai para `shared/`; senão, individual.
- **Clean architecture**: evitar acoplamentos; separar types/defines compartilhados e locais.
- **TDD**: toda feature nova exige teste unitário; se alterar regra existente, atualizar o teste.
- **Loop non-blocking**: nada de `delay()` bloqueante em `loop()`.
- **PROGMEM/memória**: páginas grandes em chunks de 256 bytes; manter enxutas (<8KB) quando possível.

## Próximos passos

Cada fase vira uma spec → plano → implementação (ciclo brainstorming → writing-plans). Recomenda-se começar pela **Fase 1** (maior valor, menor esforço, encaixe natural no código atual).