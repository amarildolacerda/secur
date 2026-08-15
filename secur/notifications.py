"""Registro canônico de canais de notificação e tipos de evento."""

CHANNELS = [
    {"key": "telegram", "label": "Telegram"},
    {"key": "automation", "label": "Automação"},
]

EVENT_TYPES = [
    {"key": "motion_detected", "label": "Movimento detectado", "category": "alerta", "legacy": False},
    {"key": "no_motion", "label": "Sem movimento", "category": "info", "legacy": False},
    {"key": "snapshot_info", "label": "Objetos detectados (info)", "category": "info", "legacy": False},
    {"key": "identity_recognized", "label": "Identidade reconhecida", "category": "info", "legacy": False},
    {"key": "intruder_detected", "label": "Intruso em zona restrita", "category": "alerta", "legacy": False},
    {"key": "loitering", "label": "Permanência suspeita", "category": "alerta", "legacy": False},
    {"key": "direction_change", "label": "Movimento em direção proibida", "category": "alerta", "legacy": False},
    {"key": "fall_detected", "label": "Possível queda", "category": "alerta", "legacy": False},
    {"key": "unknown_detected", "label": "Não reconhecido", "category": "alerta", "legacy": False},
    {"key": "object_detected", "label": "Objeto detectado (legado)", "category": "alerta", "legacy": True},
]

DEFAULT_ROUTING = {
    "telegram": {
        "motion_detected": True,
        "no_motion": False,
        "snapshot_info": False,
        "identity_recognized": False,
        "intruder_detected": True,
        "loitering": False,
        "direction_change": False,
        "fall_detected": True,
        "unknown_detected": False,
        "object_detected": True,
    },
    "automation": {
        "motion_detected": True,
        "no_motion": True,
        "snapshot_info": False,
        "identity_recognized": True,
        "intruder_detected": True,
        "loitering": True,
        "direction_change": True,
        "fall_detected": True,
        "unknown_detected": True,
        "object_detected": True,
    },
}


def is_enabled(routing: dict, channel: str, event_type: str) -> bool:
    """True se o canal não tem config para o evento (default permissivo)."""
    channel_routing = routing.get(channel)
    if channel_routing is None:
        return True
    return channel_routing.get(event_type, True)
