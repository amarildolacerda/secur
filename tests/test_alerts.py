import json
import os
import pytest
from secur.alerts import AlertService, telegram_handler, mqtt_handler, home_assistant_handler


def test_alert_service_calls_handlers(monkeypatch):
    called = []

    def handler(payload):
        called.append(payload)

    service = AlertService()
    service.register_handler(handler)
    service.send("1", "entrada", "motion_detected", "teste")

    assert len(called) == 1
    assert called[0]["camera_id"] == "1"
    assert called[0]["event_type"] == "motion_detected"


def test_telegram_handler_skips_without_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def fake_post(*args, **kwargs):
        raise AssertionError("requests.post should not be called")

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({"camera_id": "1", "event_type": "motion_detected"})


def test_telegram_handler_sends_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    called = {}

    def fake_post(url, data=None, timeout=None):
        called["url"] = url
        called["data"] = data
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)

    telegram_handler({"camera_id": "1", "zone": "entrada", "event_type": "motion_detected", "details": "detalhe"})

    assert called["url"].startswith("https://api.telegram.org/bottoken123/sendMessage")
    assert called["data"]["chat_id"] == "chat123"
    assert "detalhe" in called["data"]["text"]
    assert called["data"]["parse_mode"] == "Markdown"
    assert called["timeout"] == 10


def test_mqtt_handler_publishes(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_URL", "test-broker")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1883")
    monkeypatch.setenv("MQTT_USERNAME", "user")
    monkeypatch.setenv("MQTT_PASSWORD", "pass")
    monkeypatch.setenv("MQTT_TOPIC", "test/topic")

    captured = {}

    def fake_publish_single(topic, payload=None, hostname=None, port=None, auth=None, qos=None, retain=None):
        captured["topic"] = topic
        captured["payload"] = payload
        captured["hostname"] = hostname
        captured["port"] = port
        captured["auth"] = auth
        captured["qos"] = qos
        captured["retain"] = retain

    monkeypatch.setattr("secur.alerts.publish.single", fake_publish_single)
    payload = {"camera_id": "1", "event_type": "motion_detected"}
    mqtt_handler(payload)

    assert captured["topic"] == "test/topic"
    assert json.loads(captured["payload"])["camera_id"] == "1"
    assert captured["hostname"] == "test-broker"
    assert captured["port"] == 1883
    assert captured["auth"] == {"username": "user", "password": "pass"}


def test_home_assistant_handler_skips_without_token(monkeypatch):
    monkeypatch.delenv("HOME_ASSISTANT_TOKEN", raising=False)

    def fake_post(*args, **kwargs):
        raise AssertionError("requests.post should not be called")

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    home_assistant_handler({"camera_id": "1", "event_type": "motion_detected"})


def test_home_assistant_handler_sends_event(monkeypatch):
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.local:8123")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "secret")
    monkeypatch.setenv("HOME_ASSISTANT_EVENT_TYPE", "secur_alert")

    called = {}

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_post(url, headers=None, json=None, timeout=None):
        called["url"] = url
        called["headers"] = headers
        called["json"] = json
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    payload = {"camera_id": "1", "event_type": "motion_detected"}
    home_assistant_handler(payload)

    assert called["url"] == "http://ha.local:8123/api/events/secur_alert"
    assert called["headers"]["Authorization"] == "Bearer secret"
    assert called["json"] == payload
    assert called["timeout"] == 10
