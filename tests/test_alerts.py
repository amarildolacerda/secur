import json
import os
import pytest
import requests
from secur.alerts import AlertService, telegram_handler, mqtt_handler, home_assistant_handler
from secur.notifications import CHANNELS, EVENT_TYPES, DEFAULT_ROUTING, is_enabled


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


def test_notifications_registry():
    assert [c["key"] for c in CHANNELS] == ["telegram", "automation"]
    keys = [e["key"] for e in EVENT_TYPES]
    assert "motion_detected" in keys
    assert "no_motion" in keys
    assert "intruder_detected" in keys
    assert "loitering" in keys
    assert "direction_change" in keys
    assert "fall_detected" in keys
    assert "object_detected" in keys
    legacy = [e for e in EVENT_TYPES if e.get("legacy")]
    assert [e["key"] for e in legacy] == ["object_detected"]


def test_behavior_events_are_alerts():
    categories = {e["key"]: e["category"] for e in EVENT_TYPES}
    assert categories["loitering"] == "alerta"
    assert categories["direction_change"] == "alerta"
    assert categories["fall_detected"] == "alerta"


def test_default_routing_no_motion_off_telegram():
    assert DEFAULT_ROUTING["telegram"]["no_motion"] is False
    assert DEFAULT_ROUTING["telegram"]["motion_detected"] is True
    assert DEFAULT_ROUTING["automation"]["no_motion"] is True
    assert DEFAULT_ROUTING["automation"]["snapshot_info"] is False


def test_default_routing_behavior_events():
    # Telegram: loitering/direction off (verboso), queda on (emergência)
    assert DEFAULT_ROUTING["telegram"]["loitering"] is False
    assert DEFAULT_ROUTING["telegram"]["direction_change"] is False
    assert DEFAULT_ROUTING["telegram"]["fall_detected"] is True
    # Automation: todos os eventos de comportamento on
    assert DEFAULT_ROUTING["automation"]["loitering"] is True
    assert DEFAULT_ROUTING["automation"]["direction_change"] is True
    assert DEFAULT_ROUTING["automation"]["fall_detected"] is True


def test_is_enabled_defaults_true():
    assert is_enabled({}, "telegram", "motion_detected") is True
    assert is_enabled({"telegram": {"motion_detected": False}}, "telegram", "motion_detected") is False
    assert is_enabled({"telegram": {"motion_detected": False}}, "telegram", "no_motion") is True


def test_alert_service_respects_routing(monkeypatch):
    called = []

    def handler(payload):
        called.append(payload)
    handler.channel = "telegram"

    service = AlertService()
    service.register_handler(handler)
    routing = {"telegram": {"motion_detected": False}}
    service.send("1", "entrada", "motion_detected", "teste", routing=routing)
    assert called == []

    service.send("1", "entrada", "no_motion", "teste", routing=routing)
    assert len(called) == 1
    assert called[0]["event_type"] == "no_motion"


def test_alert_service_skips_no_motion_for_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    def fake_post(*args, **kwargs):
        raise AssertionError("requests.post should not be called for no_motion")

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)

    service = AlertService()
    service.register_handler(telegram_handler)
    service.routing = {"telegram": {"no_motion": False}}
    service.send("1", "entrada", "no_motion", "teste")


def test_event_store_handler_records_event(monkeypatch):
    from secur.alerts import event_store_handler

    recorded = {}

    class FakeStorage:
        def add_event(self, camera_id, zone, event_type, details=None):
            recorded["camera_id"] = camera_id
            recorded["zone"] = zone
            recorded["event_type"] = event_type
            recorded["details"] = details

    handler = event_store_handler(FakeStorage())
    payload = {
        "camera_id": "1",
        "zone": "entrada",
        "event_type": "motion_detected",
        "details": "Movimento detectado",
        "identity": "João",
        "known": True,
        "category": "person",
    }
    handler(payload)

    assert recorded["camera_id"] == "1"
    assert recorded["zone"] == "entrada"
    assert recorded["event_type"] == "motion_detected"
    assert recorded["details"] == "Movimento detectado"


def test_alert_service_with_storage_registers_store_handler(monkeypatch):
    recorded = []

    class FakeStorage:
        def add_event(self, camera_id, zone, event_type, details=None):
            recorded.append((camera_id, zone, event_type, details))

    service = AlertService(storage=FakeStorage())
    service.send("1", "entrada", "no_motion", "Sem movimento")

    assert len(recorded) == 1
    assert recorded[0][0] == "1"
    assert recorded[0][2] == "no_motion"


def test_alert_service_payload_includes_optional_paths(monkeypatch):
    called = []

    def handler(payload):
        called.append(payload)

    service = AlertService()
    service.register_handler(handler)
    service.send(
        "1", "entrada", "motion_detected", "teste",
        thumbnail_path="/tmp/thumb.jpg", clip_path="/tmp/clip.mp4",
    )

    assert called[0]["thumbnail_path"] == "/tmp/thumb.jpg"
    assert called[0]["clip_path"] == "/tmp/clip.mp4"


def test_alert_service_returns_event_id(monkeypatch):
    class FakeStorage:
        def add_event(self, camera_id, zone, event_type, details=None):
            return 42

    service = AlertService(storage=FakeStorage())
    event_id = service.send("1", "entrada", "motion_detected", "teste")
    assert event_id == 42


def test_alert_service_returns_none_without_store_handler():
    service = AlertService()
    service.register_handler(lambda payload: None)
    assert service.send("1", "entrada", "motion_detected") is None


def test_format_message_full_context():
    from secur.alerts import _format_message
    payload = {
        "camera_id": "1",
        "zone": "Sala",
        "event_type": "intruder_detected",
        "details": "Pessoa detectada",
        "zone_classification": "privativa",
        "identity": "João",
        "known": True,
        "recognition_method": "face",
        "category": "person",
        "thumbnail_path": "/tmp/thumb.jpg",
        "clip_path": "/tmp/clip.mp4",
    }
    text = _format_message(payload)
    assert "privativa" in text
    assert "João" in text
    assert "face" in text
    assert "person" in text
    assert "thumb.jpg" in text
    assert "clip.mp4" in text


def test_format_message_minimal():
    from secur.alerts import _format_message
    text = _format_message({"camera_id": "1", "zone": "entrada", "event_type": "motion_detected"})
    assert "Sem detalhes adicionais" in text
    assert "privativa" not in text
    assert "Identidade" not in text


def test_telegram_handler_sends_photo(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"jpegdata")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    called = {}

    def fake_post(url, data=None, files=None, timeout=None):
        called["url"] = url
        called["data"] = data
        called["files"] = files
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({
        "camera_id": "1", "zone": "entrada", "event_type": "motion_detected",
        "details": "detalhe", "thumbnail_path": str(thumb),
    })

    assert called["url"].startswith("https://api.telegram.org/bottoken123/sendPhoto")
    assert called["data"]["chat_id"] == "chat123"
    assert "photo" in called["files"]
    assert called["timeout"] == 10


def test_telegram_handler_falls_back_to_text_when_thumbnail_missing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    called = {}

    def fake_post(url, data=None, files=None, timeout=None):
        called["url"] = url
        called["data"] = data
        called["files"] = files
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({
        "camera_id": "1", "zone": "entrada", "event_type": "motion_detected",
        "details": "detalhe", "thumbnail_path": "/tmp/nao-existe.jpg",
    })

    assert called["url"].startswith("https://api.telegram.org/bottoken123/sendMessage")
    assert called["files"] is None


def test_telegram_handler_photo_failure_falls_back_to_text(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"jpegdata")

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    calls = []

    def fake_post(url, data=None, files=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError("upload failed")
        return DummyResponse()

    monkeypatch.setattr("secur.alerts.requests.post", fake_post)
    telegram_handler({
        "camera_id": "1", "zone": "entrada", "event_type": "motion_detected",
        "details": "detalhe", "thumbnail_path": str(thumb),
    })

    assert len(calls) == 2
    assert calls[1].startswith("https://api.telegram.org/bottoken123/sendMessage")
