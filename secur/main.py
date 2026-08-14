import json
import logging
import time
import threading
import cv2
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
    NO_MOTION_ALERT_SECONDS,
    ALERT_COOLDOWN_SECONDS,
    ALERT_COOLDOWN_BY_EVENT,
    THUMBNAILS_DIR,
    THUMBNAIL_INTERVAL_SECONDS,
    THUMBNAIL_HISTORY_SIZE,
    CLIP_PRE_SECONDS,
    CLIP_POST_SECONDS,
    CLIP_FPS,
    CLIPS_DIR,
    CLIP_HISTORY_SIZE,
)
from .camera import CameraStream
from .detector import ObjectDetector
from .motion import MotionDetector
from .geometry import bbox_center_in_polygons
from .alerts import AlertService, telegram_handler, mqtt_handler, home_assistant_handler, mqtt_register_device
from .app import create_app
from .storage import EventStorage
from .identity import IdentityRecognizer, decide_event, RECOGNITION_LABELS, build_recognizer
from .notifications import DEFAULT_ROUTING

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class CameraWorker:
    def __init__(self, camera, storage: EventStorage, alerts: AlertService, object_detector: ObjectDetector, identity_recognizer=None):
        self.camera = camera
        self.storage = storage
        self.alerts = alerts
        self.object_detector = object_detector
        self.identity_recognizer = identity_recognizer
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
        last_motion_time = None
        no_motion_alerted = False
        last_alert_time = {}
        last_thumb_time = None
        frame_buffer = CircularFrameBuffer(maxlen=max(1, int(CLIP_PRE_SECONDS * CLIP_FPS)))
        clip_writer = None
        clip_end_time = 0.0
        clip_event_id = None
        clip_path = None

        while not self.stop_event.is_set():
            frame = camera_stream.read()
            if frame is None:
                time.sleep(1)
                continue

            frame_buffer.push(frame)

            # Finalize clip recording after the post-event window
            if clip_writer is not None:
                if time.time() < clip_end_time:
                    clip_writer.write(frame)
                else:
                    clip_writer.release()
                    clip_writer = None
                    if clip_event_id is not None:
                        try:
                            self.storage.update_event_clip_path(clip_event_id, clip_path)
                        except Exception:
                            logger.warning("Falha ao linkar clipe ao evento (câmera %s)", self.camera.get("name"))
                    try:
                        self.storage.prune_event_clips(self.camera["id"], keep=CLIP_HISTORY_SIZE)
                    except Exception:
                        logger.warning("Falha ao podar clipes (câmera %s)", self.camera.get("name"))

            # Look up zone classification and schedule (once)
            zone_name = self.camera.get("zone")
            zone_classification = None
            zone_schedule = None
            if zone_name:
                zones = self.storage.list_zones()
                zone_obj = next((z for z in zones if z["name"] == zone_name), None)
                if zone_obj:
                    zone_classification = zone_obj.get("classification")
                    zone_schedule = zone_obj.get("schedule")

            exclusion_polygons = self.camera.get("exclusion_zones") or []
            motion_detected = motion_detector.detect(frame, exclusion_polygons=exclusion_polygons)
            if motion_detected:
                last_motion_time = time.time()
                no_motion_alerted = False

                try:
                    detections = self.object_detector.detect(frame)
                    detections = filter_detections_by_classes(detections, self.camera.get("alert_classes"))
                    if exclusion_polygons:
                        detections = [d for d in detections if not bbox_center_in_polygons(d["bbox"], exclusion_polygons)]

                    identity_info = None
                    identity_label = None
                    if detections and self.identity_recognizer is not None:
                        for det in detections:
                            if det["label"] in RECOGNITION_LABELS:
                                bbox = det["bbox"]
                                x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
                                crop = frame[y:y + h, x:x + w]
                                if crop.size > 0:
                                    identity_info = self.identity_recognizer.recognize(crop, det["label"])
                                    identity_label = det["label"]
                                    break

                    event_type, details, identity_name, known, _label, category = decide_worker_event(
                        detections, identity_info, zone_classification, self.camera["name"], identity_label
                    )

                    alert_classes = self.camera.get("alert_classes")
                    if alert_classes and not detections:
                        logger.debug(
                            "Evento suprimido (filtro de classes) câmera=%s",
                            self.camera.get("name"),
                        )
                    else:
                        thumb_path = None
                        if should_capture_thumbnail(last_thumb_time, time.time(), THUMBNAIL_INTERVAL_SECONDS):
                            try:
                                cam_dir = THUMBNAILS_DIR / f"cam{self.camera['id']}"
                                cam_dir.mkdir(parents=True, exist_ok=True)
                                filename = f"{int(time.time() * 1000)}.jpg"
                                path = cam_dir / filename
                                ok, jpg = cv2.imencode(".jpg", frame)
                                if ok:
                                    path.write_bytes(jpg.tobytes())
                                    self.storage.add_camera_thumbnail(self.camera["id"], str(path), event_type)
                                    self.storage.prune_camera_thumbnails(self.camera["id"], keep=THUMBNAIL_HISTORY_SIZE)
                                    last_thumb_time = time.time()
                                    thumb_path = str(path)
                            except Exception:
                                logger.warning("Falha ao capturar thumbnail (câmera %s)", self.camera.get("name"))
                        now = time.time()
                        if not is_within_schedule(zone_schedule, now):
                            logger.debug(
                                "Evento suprimido (fora do horário) câmera=%s evento=%s",
                                self.camera.get("name"), event_type,
                            )
                        elif now - last_alert_time.get(event_type, 0.0) >= get_cooldown_for_event(event_type):
                            last_alert_time[event_type] = now
                            event_id = self.alerts.send(
                                self.camera["id"], zone_name, event_type, details, zone_classification,
                                identity=identity_name, known=known, category=category,
                                recognition_method=identity_info.get("method") if identity_info else None,
                                thumbnail_path=thumb_path,
                            )
                            # Start clip recording: pre-event buffer + post-event frames
                            # Guard: only start a new recording if no clip is already active;
                            # otherwise the active writer/path/event would be overwritten
                            # without releasing the previous writer.
                            if clip_writer is not None:
                                logger.debug(
                                    "Clipe já ativo (câmera %s) — pulando gravação deste alerta",
                                    self.camera.get("name"),
                                )
                            else:
                                try:
                                    cam_dir = CLIPS_DIR / f"cam{self.camera['id']}"
                                    cam_dir.mkdir(parents=True, exist_ok=True)
                                    clip_path = cam_dir / f"{int(now * 1000)}.mp4"
                                    writer = cv2.VideoWriter(
                                        str(clip_path),
                                        cv2.VideoWriter_fourcc(*"mp4v"),
                                        CLIP_FPS,
                                        (frame.shape[1], frame.shape[0]),
                                    )
                                    for buf_frame in frame_buffer.frames():
                                        writer.write(buf_frame)
                                    clip_writer = writer
                                    clip_end_time = now + CLIP_POST_SECONDS
                                    clip_event_id = event_id
                                    self.storage.add_event_clip(self.camera["id"], event_id, str(clip_path), CLIP_PRE_SECONDS + CLIP_POST_SECONDS)
                                except Exception:
                                    logger.warning("Falha ao iniciar gravação de clipe (câmera %s)", self.camera.get("name"))
                        else:
                            logger.debug(
                                "Evento suprimido (cooldown %ss) câmera=%s evento=%s",
                                get_cooldown_for_event(event_type), self.camera.get("name"), event_type,
                            )
                except Exception:
                    logger.exception("Erro no processamento do frame (câmera %s)", self.camera.get("name"))
                    time.sleep(1)
                    continue

                # Thumbnail history: capture at most 1 per interval during continuous motion
                now_thumb = time.time()
                if should_capture_thumbnail(last_thumb_time, now_thumb, THUMBNAIL_INTERVAL_SECONDS):
                    try:
                        cam_dir = THUMBNAILS_DIR / f"cam{self.camera['id']}"
                        cam_dir.mkdir(parents=True, exist_ok=True)
                        filename = f"{int(now_thumb * 1000)}.jpg"
                        path = cam_dir / filename
                        ok, jpg = cv2.imencode(".jpg", frame)
                        if ok:
                            path.write_bytes(jpg.tobytes())
                            self.storage.add_camera_thumbnail(self.camera["id"], str(path), event_type)
                            self.storage.prune_camera_thumbnails(self.camera["id"], keep=THUMBNAIL_HISTORY_SIZE)
                            last_thumb_time = now_thumb
                    except Exception:
                        logger.warning("Falha ao capturar thumbnail (câmera %s)", self.camera.get("name"))
            else:
                # No motion: after NO_MOTION_ALERT_SECONDS without any occurrence, send "sem movimento"
                if (last_motion_time is not None
                        and not no_motion_alerted
                        and (time.time() - last_motion_time) >= NO_MOTION_ALERT_SECONDS):
                    details = f"Sem movimento há {int(NO_MOTION_ALERT_SECONDS)}s na câmera {self.camera['name']}"
                    self.alerts.send(
                        self.camera["id"], zone_name, "no_motion",
                        details, zone_classification,
                    )
                    no_motion_alerted = True

            time.sleep(FRAME_WAIT_SECONDS)


def decide_worker_event(detections, identity_info, zone_classification, camera_name, label=None):
    if identity_info is not None:
        decision = decide_event(identity_info, zone_classification, camera_name, label)
        if decision is not None:
            return decision
    if detections:
        return ("snapshot_info", format_detections(detections), None, None, None, None)
    return ("motion_detected", f"Movimento detectado na câmera {camera_name}", None, None, None, None)


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


def filter_detections_by_classes(detections, alert_classes):
    """Mantém apenas detecções cujo label está em alert_classes.
    alert_classes None/vazio = todas as classes."""
    if not alert_classes:
        return detections
    allowed = set(alert_classes)
    return [d for d in detections if d["label"] in allowed]


def is_within_schedule(schedule, now=None):
    """True se `now` (epoch) está dentro do schedule {"start": "HH:MM", "end": "HH:MM"}.
    Sem schedule → sempre True. Suporta virada de meia-noite (start > end)."""
    if not schedule:
        return True
    start = schedule.get("start")
    end = schedule.get("end")
    if not start or not end:
        return True
    now = now if now is not None else time.time()
    current = time.strftime("%H:%M", time.localtime(now))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def get_cooldown_for_event(event_type):
    """Cooldown específico por evento, com fallback para o global."""
    return ALERT_COOLDOWN_BY_EVENT.get(event_type, ALERT_COOLDOWN_SECONDS)


class CircularFrameBuffer:
    """Buffer circular de frames (janela pré-evento). Descarta o mais antigo."""

    def __init__(self, maxlen: int):
        self.maxlen = maxlen
        self._items = []

    def push(self, frame):
        self._items.append(frame)
        if len(self._items) > self.maxlen:
            self._items.pop(0)

    def frames(self):
        return list(self._items)


def should_capture_thumbnail(last_thumb_time, now, interval):
    if last_thumb_time is None:
        return True
    return (now - last_thumb_time) >= interval


class CameraManager:
    def __init__(self, storage: EventStorage, alerts: AlertService, object_detector: ObjectDetector, identity_recognizer=None):
        self.storage = storage
        self.alerts = alerts
        self.object_detector = object_detector
        self.identity_recognizer = identity_recognizer
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
                        worker = CameraWorker(camera, self.storage, self.alerts, self.object_detector, self.identity_recognizer)
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
    storage.seed_default_routing(DEFAULT_ROUTING)
    alerts = AlertService(storage=storage)
    alerts.register_handler(telegram_handler)
    alerts.register_handler(mqtt_handler)
    alerts.register_handler(home_assistant_handler)
    alerts.routing = storage.get_all_routing()

    object_detector = ObjectDetector(
        model_path=DETECTOR_MODEL_PATH,
        confidence_threshold=DETECTOR_CONFIDENCE,
        iou_threshold=DETECTOR_IOU,
        classes=DETECTOR_CLASSES,
    )

    identity_recognizer = build_recognizer(storage)
    camera_manager = CameraManager(storage, alerts, object_detector, identity_recognizer)
    camera_manager.start()

    # Register device with HA via MQTT auto-discovery
    cameras = storage.list_cameras()
    mqtt_register_device(cameras)

    storage.seed_zones([
        {"name": "Entrada", "classification": "pública"},
        {"name": "Estacionamento", "classification": "pública"},
        {"name": "Corredor", "classification": "pública"},
        {"name": "Sala de servidores", "classification": "privativa"},
        {"name": "Recepção", "classification": "segurança"},
    ])

    app = create_app(camera_manager=camera_manager)
    app.run(host=SERVER_HOST, port=SERVER_PORT)
