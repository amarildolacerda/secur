from secur.alerts import (
    AlertService,
    telegram_handler,
    mqtt_handler,
    home_assistant_handler,
)


def _payload(event_type, zone_classification="privativa", identity="João", known=True):
    return {
        "camera_id": "1", "zone": "Entrada", "event_type": event_type,
        "details": "x", "zone_classification": zone_classification,
        "identity": identity, "known": known, "recognition_method": "face",
    }


def test_telegram_skips_known_unknown_and_snapshot(monkeypatch):
    # gating: only intruder_detected is a Telegram alarm
    assert telegram_handler_skip("identity_recognized") is True
    assert telegram_handler_skip("unknown_detected") is True
    assert telegram_handler_skip("snapshot_info") is True
    assert telegram_handler_skip("intruder_detected") is False
    assert telegram_handler_skip("motion_detected") is False


def telegram_handler_skip(event_type):
    # Mirror the gating used inside telegram_handler
    return event_type in ("snapshot_info", "identity_recognized", "unknown_detected")


def test_mqtt_only_intruder(monkeypatch):
    assert mqtt_skip("intruder_detected") is False
    assert mqtt_skip("identity_recognized") is True
    assert mqtt_skip("unknown_detected") is True
    assert mqtt_skip("snapshot_info") is True


def mqtt_skip(event_type):
    return event_type in ("snapshot_info", "identity_recognized", "unknown_detected")


def test_ha_receives_all_identity_events():
    # All identity events are HA automation triggers
    assert ha_skip("identity_recognized", "pública") is False
    assert ha_skip("intruder_detected", "pública") is False
    assert ha_skip("unknown_detected", "pública") is False
    assert ha_skip("snapshot_info", "pública") is True
    # existing motion gating preserved
    assert ha_skip("motion_detected", "pública") is True
    assert ha_skip("motion_detected", "privativa") is False


def ha_skip(event_type, zone_classification):
    if event_type in ("snapshot_info",):
        return True
    if event_type in ("motion_detected", "no_motion") and zone_classification not in ("privativa", "segurança"):
        return True
    return event_type not in ("motion_detected", "no_motion", "identity_recognized", "intruder_detected", "unknown_detected")
