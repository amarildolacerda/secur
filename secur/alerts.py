import logging
from typing import Dict
import json
import os
import requests
import paho.mqtt.publish as publish

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self):
        self.handlers = []

    def register_handler(self, handler):
        self.handlers.append(handler)

    def send(self, camera_id: str, zone: str, event_type: str, details: str = None, zone_classification: str = None):
        payload = {
            "camera_id": camera_id,
            "zone": zone,
            "event_type": event_type,
            "details": details,
            "zone_classification": zone_classification,
        }
        for handler in self.handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception("Alert handler failed: %s", handler.__name__)


def telegram_handler(payload: Dict):
    if payload.get("event_type") == "snapshot_info":
        return
    api_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not api_token or not chat_id:
        logger.debug("Telegram handler skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured")
        return

    text = _format_message(payload)
    url = f"https://api.telegram.org/bot{api_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        logger.info("Telegram alert sent for camera_id=%s event=%s", payload.get("camera_id"), payload.get("event_type"))
    except Exception:
        logger.exception("Telegram alert failed for camera_id=%s", payload.get("camera_id"))


def mqtt_handler(payload: Dict):
    if payload.get("event_type") == "snapshot_info":
        return
    broker = os.getenv("MQTT_BROKER_URL", "192.162.1.12")
    port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    username = os.getenv("MQTT_USERNAME", "kzuca")
    password = os.getenv("MQTT_PASSWORD", "123")
    topic = os.getenv("MQTT_TOPIC", "homeassistant/secur/alert")

    if not broker:
        logger.debug("MQTT handler skipped: MQTT_BROKER_URL not configured")
        return

    import paho.mqtt.client as mqtt

    client = mqtt.Client()
    if username and password:
        client.username_pw_set(username, password)

    try:
        client.connect_async(broker, port, keepalive=10)
        client.loop_start()
        import time
        deadline = time.time() + 3
        while time.time() < deadline and not client.is_connected():
            time.sleep(0.1)
        client.loop_stop()

        if not client.is_connected():
            logger.warning("MQTT connection timeout (broker %s:%s)", broker, port)
            return

        client.publish(topic, json.dumps(payload), qos=0, retain=False)
        logger.info("MQTT alert published to topic=%s camera_id=%s", topic, payload.get("camera_id"))
    except Exception as e:
        logger.warning("MQTT alert failed (broker %s:%s): %s", broker, port, e)
    finally:
        try:
            client.loop_stop()
        except Exception:
            pass


def home_assistant_handler(payload: Dict):
    if payload.get("event_type") == "snapshot_info":
        return
    url = os.getenv("HOME_ASSISTANT_URL", "http://192.162.1.12:8123")
    token = os.getenv("HOME_ASSISTANT_TOKEN")
    event_type = os.getenv("HOME_ASSISTANT_EVENT_TYPE", "secur_alert")

    if not token:
        logger.debug("Home Assistant handler skipped: HOME_ASSISTANT_TOKEN not configured")
        return

    # Only trigger for motion/no_motion events in private/security zones
    zone_classification = payload.get("zone_classification")
    event = payload.get("event_type")
    if event in ("motion_detected", "no_motion") and zone_classification not in ("privativa", "segurança"):
        logger.debug("Home Assistant skipped: %s in zone classification '%s'", event, zone_classification)
        return

    event_url = f"{url.rstrip('/')}/api/events/{event_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(event_url, headers=headers, json=payload, timeout=(3, 5))
        response.raise_for_status()
        logger.info("Home Assistant event sent event_type=%s camera_id=%s", event_type, payload.get("camera_id"))
    except requests.exceptions.ConnectTimeout:
        logger.warning("Home Assistant offline (timeout 3s): %s", url)
    except requests.exceptions.ConnectionError:
        logger.warning("Home Assistant connection refused: %s", url)
    except Exception:
        logger.warning("Home Assistant event failed for event_type=%s", event_type)


def _format_message(payload: Dict) -> str:
    camera_id = payload.get("camera_id")
    zone = payload.get("zone")
    event_type = payload.get("event_type")
    details = payload.get("details") or "Sem detalhes adicionais."

    message = (
        "*Alerta de Segurança*\n"
        f"*Câmera:* {camera_id}\n"
        f"*Zona:* {zone}\n"
        f"*Evento:* {event_type}\n"
        f"*Descrição:* {details}"
    )
    return message
