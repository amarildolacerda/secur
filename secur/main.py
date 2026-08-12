import json
import logging
import time
import threading
from .config import (
    DEFAULT_CAMERAS,
    DETECTOR_CLASSES,
    DETECTOR_CONFIDENCE,
    DETECTOR_IOU,
    DETECTOR_MODEL_PATH,
    FRAME_WAIT_SECONDS,
    SERVER_HOST,
    SERVER_PORT,
    MOTION_MIN_AREA,
)
from .camera import CameraStream
from .detector import ObjectDetector
from .motion import MotionDetector
from .alerts import AlertService, telegram_handler, mqtt_handler, home_assistant_handler
from .app import create_app
from .storage import EventStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class CameraWorker:
    def __init__(self, camera, storage: EventStorage, alerts: AlertService, object_detector: ObjectDetector):
        self.camera = camera
        self.storage = storage
        self.alerts = alerts
        self.object_detector = object_detector
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def is_running(self):
        return self.thread.is_alive()

    def status(self):
        return {
            "camera_id": self.camera.get("id"),
            "name": self.camera.get("name"),
            "zone": self.camera.get("zone"),
            "source": self.camera.get("source"),
            "running": self.thread.is_alive(),
        }

    def run(self):
        camera_stream = CameraStream(self.camera["source"])
        motion_detector = MotionDetector(min_area=MOTION_MIN_AREA)

        while not self.stop_event.is_set():
            frame = camera_stream.read()
            if frame is None:
                time.sleep(1)
                continue

            motion_detected = motion_detector.detect(frame)
            if motion_detected:
                detections = self.object_detector.detect(frame)
                if detections:
                    event_type = "object_detected"
                    details = format_detections(detections)
                else:
                    event_type = "motion_detected"
                    details = f"Movimento detectado na câmera {self.camera['name']}"

                self.storage.add_event(self.camera["id"], self.camera.get("zone"), event_type, details)
                self.alerts.send(self.camera["id"], self.camera.get("zone"), event_type, details)

            time.sleep(FRAME_WAIT_SECONDS)


def format_detections(detections):
    if not detections:
        return None

    labels = [d["label"] for d in detections]
    details = json.dumps(
        [
            {
                "label": d["label"],
                "confidence": round(d["confidence"], 2),
                "bbox": d["bbox"],
            }
            for d in detections
        ]
    )
    return f"Objetos detectados: {', '.join(labels)} | detalhes: {details}"


class CameraManager:
    def __init__(self, storage: EventStorage, alerts: AlertService, object_detector: ObjectDetector):
        self.storage = storage
        self.alerts = alerts
        self.object_detector = object_detector
        self.workers = {}
        self.lock = threading.Lock()
        self.monitor_thread = threading.Thread(target=self.monitor_cameras, daemon=True)

    def start(self):
        self.storage.seed_cameras(DEFAULT_CAMERAS)
        self.monitor_thread.start()

    def monitor_cameras(self):
        while True:
            with self.lock:
                cameras = self.storage.list_cameras()
                active_ids = set(self.workers.keys())
                camera_ids = set(camera["id"] for camera in cameras)

                for camera in cameras:
                    if camera["id"] not in active_ids:
                        worker = CameraWorker(camera, self.storage, self.alerts, self.object_detector)
                        worker.start()
                        self.workers[camera["id"]] = worker

                for camera_id in list(active_ids - camera_ids):
                    worker = self.workers.pop(camera_id, None)
                    if worker:
                        worker.stop()

            time.sleep(10)

    def get_status(self):
        with self.lock:
            return [worker.status() for worker in self.workers.values()]


def main():
    storage = EventStorage()
    alerts = AlertService()
    alerts.register_handler(telegram_handler)
    alerts.register_handler(mqtt_handler)
    alerts.register_handler(home_assistant_handler)

    object_detector = ObjectDetector(
        model_path=DETECTOR_MODEL_PATH,
        confidence_threshold=DETECTOR_CONFIDENCE,
        iou_threshold=DETECTOR_IOU,
        classes=DETECTOR_CLASSES,
    )

    camera_manager = CameraManager(storage, alerts, object_detector)
    camera_manager.start()

    app = create_app(camera_manager=camera_manager)
    app.run(host=SERVER_HOST, port=SERVER_PORT)
