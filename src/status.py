import os
import cv2
from .config import (
    DETECTOR_MODEL_PATH,
    IDENTITY_ENABLED,
    IDENTITY_FACE_MODEL_PATH,
    MOTION_MIN_AREA,
    APP_VERSION,
    HOME_ASSISTANT_URL,
    HOME_ASSISTANT_TOKEN,
)


def _probe_telegram(token):
    if not token:
        return False, "token não configurado"
    try:
        import urllib.request
        import json
        # urllib.request.Request NAO aceita timeout como kwarg — timeout vai
        # apenas em urlopen. Bug antigo: a chamada explodia antes de
        # efetivamente testar o bot, mostrando "Falha: ..." em vez de "ok".
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe"
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.load(r)
        if data.get("ok"):
            return True, f"bot @{data['result'].get('username', '?')}"
        return False, data.get("description", "erro Telegram")
    except Exception as e:
        return False, f"Falha: {e}"


def _probe_mqtt(broker, port):
    if not broker:
        return False, "broker não configurado"
    import socket
    try:
        with socket.create_connection((broker, int(port)), timeout=3):
            return True, f"TCP {broker}:{port} ok"
    except Exception as e:
        return False, f"Falha: {e}"


def _probe_ha(url, token):
    if not url:
        return False, "URL não configurada"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, f"Falha: {e}"


def build_system_status(camera_manager=None):
    opencv_ver = getattr(cv2, "__version__", "?")
    modules = []

    capture_items = [{
        "name": "Driver de captura (OpenCV)",
        "configured": True,
        "operational": True,
        "detail": f"OpenCV {opencv_ver}",
    }]
    workers = camera_manager.get_status() if camera_manager else []
    healthy = sum(1 for w in workers if w.get("healthy") is not False)
    capture_items.append({
        "name": "Workers de câmera",
        "configured": bool(camera_manager),
        "operational": healthy > 0,
        "detail": f"{healthy} ativo(s) / {len(workers)} total",
    })
    modules.append({"group": "Captura", "items": capture_items})

    det_items = [{
        "name": "Movimento",
        "configured": True,
        "operational": True,
        "detail": f"MOTION_MIN_AREA={MOTION_MIN_AREA}",
    }]
    model_cfg = bool(DETECTOR_MODEL_PATH) and os.path.exists(DETECTOR_MODEL_PATH)
    model_op = False
    if DETECTOR_MODEL_PATH:
        if os.path.exists(DETECTOR_MODEL_PATH):
            try:
                cv2.dnn.readNetFromONNX(DETECTOR_MODEL_PATH)
                model_op = True
                model_detail = f"{os.path.basename(DETECTOR_MODEL_PATH)} carregado"
            except Exception as e:
                model_detail = f"falha ao carregar: {e}"
        else:
            model_detail = "arquivo não encontrado"
    else:
        model_detail = "não configurado"
    det_items.append({
        "name": "Objetos (YOLO)",
        "configured": model_cfg,
        "operational": model_op,
        "detail": model_detail,
    })
    modules.append({"group": "Detecção", "items": det_items})

    id_cfg = bool(IDENTITY_ENABLED)
    id_op = (
        bool(IDENTITY_ENABLED)
        and bool(IDENTITY_FACE_MODEL_PATH)
        and os.path.exists(IDENTITY_FACE_MODEL_PATH)
    )
    modules.append({"group": "Identidade", "items": [{
        "name": "Reconhecimento",
        "configured": id_cfg,
        "operational": id_op,
        "detail": "IDENTITY_ENABLED=true" if id_cfg else "IDENTITY_ENABLED=false",
    }]})

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_op, tg_det = _probe_telegram(tg_token)
    mqtt_url = os.getenv("MQTT_BROKER_URL")
    mqtt_port = os.getenv("MQTT_BROKER_PORT", "1883")
    mq_op, mq_det = _probe_mqtt(mqtt_url, mqtt_port)
    ha_op, ha_det = _probe_ha(HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN)
    notif_items = [
        {"name": "Telegram", "configured": bool(tg_token), "operational": tg_op, "detail": tg_det},
        {"name": "MQTT", "configured": bool(mqtt_url), "operational": mq_op, "detail": mq_det},
        {"name": "Home Assistant", "configured": bool(HOME_ASSISTANT_URL) and bool(HOME_ASSISTANT_TOKEN), "operational": ha_op, "detail": ha_det},
    ]
    modules.append({"group": "Notificações", "items": notif_items})

    return {
        "backend": {"opencv_version": opencv_ver, "dnn_backend": "OpenCV DNN (ONNX)", "app_version": APP_VERSION},
        "modules": modules,
    }
