import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "events.db"

DEFAULT_CAMERAS = [
    {
        "name": "Camera 1",
        "source": "rtsp://admin:123456@192.168.1.104:554/stream",
        "zone": "entrada",
    }
]

MOTION_MIN_AREA = int(os.getenv("MOTION_MIN_AREA", "5000"))
FRAME_WAIT_SECONDS = float(os.getenv("FRAME_WAIT_SECONDS", "0.1"))
# Send a "sem movimento" alert after this many seconds without any occurrence (per camera)
NO_MOTION_ALERT_SECONDS = float(os.getenv("NO_MOTION_ALERT_SECONDS", "60"))
# Suppress repeated events of the same type within this window (per camera)
ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
DETECTOR_MODEL_PATH = os.getenv("DETECTOR_MODEL_PATH", "")
DETECTOR_CONFIDENCE = float(os.getenv("DETECTOR_CONFIDENCE", "0.25"))
DETECTOR_IOU = float(os.getenv("DETECTOR_IOU", "0.45"))
DETECTOR_CLASSES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "cat",
    "dog",
    "cow",
    "horse",
    "sheep",
    "bird",
]
IDENTITY_ENABLED = os.getenv("IDENTITY_ENABLED", "false").lower() in ("1", "true", "yes", "on")
IDENTITY_FACE_MODEL_PATH = os.getenv("IDENTITY_FACE_MODEL_PATH", "")
IDENTITY_REID_MODEL_PATH = os.getenv("IDENTITY_REID_MODEL_PATH", "")
IDENTITY_MATCH_THRESHOLD = float(os.getenv("IDENTITY_MATCH_THRESHOLD", "0.6"))
IDENTITY_EMBEDDINGS_DIR = DATA_DIR / "identities"
IDENTITY_EMBEDDINGS_DIR.mkdir(exist_ok=True)
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL", "http://192.168.1.12:8123")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")
HOME_ASSISTANT_EVENT_TYPE = os.getenv("HOME_ASSISTANT_EVENT_TYPE", "secur_alert")
MQTT_BROKER_URL = os.getenv("MQTT_BROKER_URL", "192.168.1.12")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "kzuca")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "123")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "homeassistant/secur/alert")

THUMBNAILS_DIR = DATA_DIR / "thumbnails"
THUMBNAILS_DIR.mkdir(exist_ok=True)
THUMBNAIL_INTERVAL_SECONDS = float(os.getenv("THUMBNAIL_INTERVAL_SECONDS", "10"))
THUMBNAIL_HISTORY_SIZE = int(os.getenv("THUMBNAIL_HISTORY_SIZE", "20"))
