# Integração MQTT — Spec de funcionamento

**Data:** 2026-08-21
**Status:** Documentado (comportamento atual do código)
**Escopo:** Publicação de alertas/estado em MQTT e descoberta automática no Home Assistant.

> Complementa o aprendizado da limpeza de tópicos órfãos (ver seção 7 e 8).

## 1. Propósito

O Secur integra com Home Assistant (HA) por **dois caminhos independentes**:

1. **MQTT auto-discovery** — cria entidades de dispositivo no HA (binary_sensor de
   motion/alert, camera de snapshot) publicando configs no namespace `homeassistant/...`.
2. **Eventos REST (webhook)** — `home_assistant_handler` faz POST em
   `HA_URL/api/events/<event_type>` para disparar automações no HA (não passa por MQTT).

O `mqtt_handler` publica alertas/estado em tópicos MQTT para consumo genérico (HA ou
outros) e para alimentar o estado das entidades criadas pela descoberta.

## 2. Configuração (env vars, em `config.py`)

| Var | Default | Uso |
|-----|---------|-----|
| `MQTT_BROKER_URL` | `192.168.1.12` | Host do broker |
| `MQTT_BROKER_PORT` | `1883` | Porta |
| `MQTT_USERNAME` | `kzuca` | Auth |
| `MQTT_PASSWORD` | `123` | Auth |
| `MQTT_TOPIC` | `homeassistant/secur/alert` | Tópico "principal" de alerta (não retido) |
| `HOME_ASSISTANT_URL` | `http://192.168.1.12:8123` | REST do HA |
| `HOME_ASSISTANT_TOKEN` | (vazio) | Bearer token do HA |
| `HOME_ASSISTANT_EVENT_TYPE` | `secur_alert` | Tipo de evento REST |

Se `MQTT_BROKER_URL` vazio → `mqtt_handler` e `mqtt_register_device` são pulados.
Se `HOME_ASSISTANT_TOKEN` vazio → `home_assistant_handler` é pulado.

## 3. Dois caminhos de integração

### 3.1 MQTT auto-discovery (`mqtt_register_device`, `alerts.py:267`)
Executado **uma vez no startup** (`main.py:667-669`):
```python
cameras = storage.list_cameras()
mqtt_register_device(cameras)
```
Para cada câmera publica 3 configs retidos (`retain=True`):
- `homeassistant/binary_sensor/secur_cam{id}_motion/config`
- `homeassistant/binary_sensor/secur_cam{id}_alert/config`
- `homeassistant/camera/secur_cam{id}_snapshot/config`

`safe_id = f"secur_cam{camera_id}"` (id vindo do banco).

### 3.2 Eventos REST (`home_assistant_handler`, `alerts.py:175`)
Independente de MQTT. Faz `POST {HA_URL}/api/events/{EVENT_TYPE}` com o payload do
evento. Só dispara para eventos de motion/no_motion em zonas **não** `pública`, ou
`identity_recognized`/`intruder_detected`/`unknown_detected`/`object_detected`.

## 4. Referência de tópicos (publicados por evento — `mqtt_handler`, `alerts.py:103`)

`safe_id = secur_cam{camera_id}`. Quando `MQTT_TOPIC` está definido (caminho principal):

| Tópico | Conteúdo | Retido? |
|--------|----------|---------|
| `secur/{safe_id}/alert_state` | JSON do evento | não |
| `secur/{safe_id}/alert` | JSON do evento | não |
| `secur/{safe_id}/state` | `motion` / `idle` | **não** (publish.single sem retain) |
| `homeassistant/secur/alert` (=`MQTT_TOPIC`) | JSON do evento | não |

No **fallback** (sem `MQTT_TOPIC`): usa `mqtt.Client()` e publica `secur/{safe_id}/state`
com `retain=True`. Ou seja, o estado só fica retido se `MQTT_TOPIC` **não** estiver setado.

> Consequência: com a config padrão, `secur/secur_cam{id}/state` **não persiste** após
> restart — só aparece no próximo evento.

## 5. Ciclo de vida dos handlers

`AlertService` (`main.py:634-637`) registra `telegram_handler`, `mqtt_handler`,
`home_assistant_handler`. O roteamento (`storage.get_all_routing()`) decide quais
canais disparam por regra. `mqtt_handler.channel = "automation"` → só dispara se a
regra tiver `"mqtt"` em `then.alert`.

## 6. Namespaces e `safe_id`

- Atual: `secur_cam{id}` (consistente entre `mqtt_handler` e `mqtt_register_device`).
- **Legado (não existe mais no código, mas pode sobrar no broker):**
  `homeassistant/secur/cam{id}/...` e `homeassistant/camera/secur/snapshot/config`
  (entidade global órfã). Esses são lixo acumulado de versões anteriores.

## 7. Gotchas operacionais (aprendido na limpeza)

1. **Descoberta HA NÃO remove órfãos.** Apagar uma câmera do banco **não** apaga seus
   tópicos `homeassistant/.../secur_cam{id}/.../config` retidos. Eles ficam como entidades
   fantasma no HA para sempre, a menos que sejam limpos manualmente.
2. **Reset do app não limpa tópicos antigos.** `mqtt_register_device` só *republish* as
   câmeras atuais; não faz `retain=False` nas ausentes. Por isso um `docker restart`
   sozinho não remove entidades órfãs.
3. **Estado não retido no caminho padrão** (ver seção 4) — não confundir "sumiu o estado"
   com "quebrou".
4. **Probe de status só checa TCP.** `status.py:_probe_mqtt` faz `socket.connect` no
   broker; `operational: true` significa "TCP alcançável", **não** que auth/publicação
   funcionem.
5. **`mosquitto_sub` não está instalado** no ambiente. Para inspecionar o broker, usar
   `paho` dentro do container `security_app` (que tem a lib e acesso de rede).

## 8. Procedimento de limpeza (reset de tópicos "Secur*")

Quando há entidades órfãs no HA (câmeras removidas do banco, ou tópicos legados):

1. Listar câmeras existentes no banco:
   `SELECT id FROM cameras` → conjunto de IDs válidos (ex.: `{2}`).
2. Dentro do container, subscrever `homeassistant/#` e `secur/#` (paho), coletar retidos.
3. Para cada tópico que casar `secur_cam(\d+)` com id **fora** do banco, publicar
   payload vazio com `retain=True` (isso apaga a retenção):
   `client.publish(topic, b"", qos=0, retain=True)`.
4. Também limpar o órfão global `homeassistant/camera/secur/snapshot/config`.
5. **Não** tocar em `homeassistant/light/gw_*` / `homeassistant/sensor/gw_*` — são de
   outro integrador (gateway Zigbee), não do Secur.
6. `docker restart security_app` para re-registrar as câmeras válidas (recria os
   `homeassistant/.../secur_cam{id}/.../config` das câmeras que sobraram).
7. Re-verificar: só devem restar os tópicos das câmeras do banco + dispositivos `gw_*`.

> Exemplo real (2026-08-21): banco tinha só `Entrada` (id=2); broker acumulava 46
> tópicos de `secur_cam1`–`13`,`15`. Limpeza removeu 40 órfãos, mantendo `cam2` + `gw_*`.

## 9. Segurança

- Credenciais MQTT vêm de env (`.env`), não hardcoded no código (exceto defaults de
  desenvolvimento em `config.py`). Em produção, definir `MQTT_PASSWORD` real.
- Tópicos não usam ACL por câmera; qualquer cliente autenticado no broker lê todos os
  alertas. Se necessário, restringir por usuário no broker.
