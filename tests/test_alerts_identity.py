import secur.alerts as alerts


def _payload(event_type, zone_classification="privativa", identity="João", known=True, category="person"):
    return {
        "camera_id": "1", "zone": "Entrada", "event_type": event_type,
        "details": "x", "zone_classification": zone_classification,
        "identity": identity, "known": known, "recognition_method": "face",
        "category": category,
    }


def test_telegram_skips_known_unknown_and_snapshot(monkeypatch):
    calls = []
    def fake_post(url, data=None, timeout=None, json=None):
        calls.append((url, data, json))
        class R:
            def raise_for_status(self): pass
        return R()
    monkeypatch.setattr(alerts.requests, "post", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
    for skipped in ("snapshot_info", "identity_recognized", "unknown_detected"):
        alerts.telegram_handler(_payload(skipped))
    assert calls == [], "telegram must skip snapshot/identity/unknown"
    calls.clear()
    alerts.telegram_handler(_payload("intruder_detected"))
    assert len(calls) == 1, "telegram must alarm on intruder"
    calls.clear()
    alerts.telegram_handler(_payload("motion_detected"))
    assert len(calls) == 1, "telegram must alarm on motion"


def test_mqtt_only_intruder(monkeypatch):
    import paho.mqtt.client as mqtt_mod

    instances = []
    class FakeClient:
        def __init__(self, *a, **k):
            self.published = []
            instances.append(self)
        def username_pw_set(self, *a, **k): pass
        def connect_async(self, *a, **k): pass
        def loop_start(self): pass
        def loop_stop(self): pass
        def is_connected(self): return True
        def publish(self, topic, payload, *a, **k):
            self.published.append((topic, payload))
            return None
        def disconnect(self): pass

    monkeypatch.setattr(mqtt_mod, "Client", FakeClient)
    monkeypatch.setenv("MQTT_BROKER_URL", "broker")
    instances.clear()
    alerts.mqtt_handler(_payload("intruder_detected"))
    assert instances and instances[-1].published, "intruder must publish to MQTT"
    instances.clear()
    alerts.mqtt_handler(_payload("identity_recognized"))
    assert not (instances and instances[-1].published), "identity must NOT publish to MQTT"
    instances.clear()
    alerts.mqtt_handler(_payload("unknown_detected"))
    assert not (instances and instances[-1].published), "unknown_detected must NOT publish to MQTT"


def test_ha_receives_all_identity_events(monkeypatch):
    calls = []
    def fake_post(url, data=None, timeout=None, json=None, **kwargs):
        calls.append((url, json))
        class R:
            def raise_for_status(self): pass
        return R()
    monkeypatch.setattr(alerts.requests, "post", fake_post)
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "tok")
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha")

    for ev in ("identity_recognized", "intruder_detected", "unknown_detected"):
        calls.clear()
        alerts.home_assistant_handler(_payload(ev))
        assert calls, f"HA must receive {ev}"

    calls.clear()
    alerts.home_assistant_handler(_payload("snapshot_info"))
    assert calls == [], "HA must skip snapshot_info"

    calls.clear()
    alerts.home_assistant_handler(_payload("motion_detected", zone_classification="pública"))
    assert calls == [], "HA must skip public motion"

    calls.clear()
    alerts.home_assistant_handler(_payload("motion_detected", zone_classification="privativa"))
    assert calls, "HA must send private motion"
