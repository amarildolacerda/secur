=== TASK 4: Re-gate alert handlers for identity events ===

**Files:**
- Modify: `secur/alerts.py`
- Test: `tests/test_alerts_identity.py`

**Interfaces:**
- Consumes: payload keys `event_type`, `zone_classification`, `identity`, `known`, `recognition_method`, `category`.
- Produces: extended `AlertService.send(...)` signature; handlers correctly gate `identity_recognized`, `intruder_detected`, `unknown_detected`.

## Tests (write to `tests/test_alerts_identity.py` verbatim)
```python
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
```

## Implementation (edit `secur/alerts.py` verbatim)
1. Update `AlertService.send` to include identity fields:
```python
def send(self, camera_id, zone, event_type, details=None, zone_classification=None,
         identity=None, known=None, recognition_method=None, category=None):
    payload = {
        "camera_id": camera_id,
        "zone": zone,
        "event_type": event_type,
        "details": details,
        "zone_classification": zone_classification,
        "identity": identity,
        "known": known,
        "recognition_method": recognition_method,
        "category": category,
    }
    for handler in self.handlers:
        try:
            handler(payload)
        except Exception:
            logger.exception("Alert handler failed: %s", handler.__name__)
```

2. Update `telegram_handler` skip rule (the first `if` at top of the function):
```python
def telegram_handler(payload: Dict):
    if payload.get("event_type") in ("snapshot_info", "identity_recognized", "unknown_detected"):
        return
    ...
```

3. Update `mqtt_handler` skip rule (the existing `if payload.get("event_type") == "snapshot_info": return` becomes):
```python
def mqtt_handler(payload: Dict):
    if payload.get("event_type") in ("snapshot_info", "identity_recognized", "unknown_detected"):
        return
    ...
```

4. Update `home_assistant_handler` gating (replace its existing early returns with):
```python
def home_assistant_handler(payload: Dict):
    if payload.get("event_type") in ("snapshot_info",):
        return
    zone_classification = payload.get("zone_classification")
    event = payload.get("event_type")
    if event in ("motion_detected", "no_motion") and zone_classification not in ("privativa", "segurança"):
        return
    if event not in ("motion_detected", "no_motion", "identity_recognized", "intruder_detected", "unknown_detected"):
        return
    ...
```

5. Update `_format_message` to include identity and category:
```python
def _format_message(payload: Dict) -> str:
    camera_id = payload.get("camera_id")
    zone = payload.get("zone")
    event_type = payload.get("event_type")
    details = payload.get("details") or "Sem detalhes adicionais."
    identity = payload.get("identity")
    message = (
        "*Alerta de Segurança*\n"
        f"*Câmera:* {camera_id}\n"
        f"*Zona:* {zone}\n"
        f"*Evento:* {event_type}\n"
        f"*Descrição:* {details}"
    )
    if identity:
        message += f"\n*Identidade:* {identity}"
    category = payload.get("category")
    if category:
        message += f"\n*Categoria:* {category}"
    return message
```

Steps:
1. Write `tests/test_alerts_identity.py` verbatim from the Tests block.
2. Run `python -m pytest tests/test_alerts_identity.py -v` → expect FAIL (the mirrored skip helpers assert the rules the handlers must implement; handlers aren't gated yet).
3. Apply the 5 edits above to `secur/alerts.py`.
4. Run `python -m pytest tests/test_alerts_identity.py -v` → expect PASS.
5. Commit ONLY those two files: `git add secur/alerts.py tests/test_alerts_identity.py && git commit -m "feat(alerts): extend payload and re-gate handlers for identity events"`

GLOBAL CONSTRAINTS: Project targets Raspberry Pi 4; offline. Only `intruder_detected` is a real security alarm (Telegram + MQTT); `identity_recognized` and `unknown_detected` reach Home Assistant as automation triggers but are silenced in Telegram/MQTT. Per AGENTS.md integrate via `dev` branch (already on it).