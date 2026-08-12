import cv2
from flask import Flask, jsonify, render_template, request, Response
from .camera import CameraStream
from .storage import EventStorage


def create_app(camera_manager=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    storage = EventStorage()

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/status")
    def status():
        cameras = storage.list_cameras()
        events = storage.list_events(limit=10)
        status_payload = {
            "status": "ok",
            "camera_count": len(cameras),
            "recent_events": len(events),
            "cameras": cameras,
        }

        if camera_manager is not None:
            status_payload["worker_status"] = camera_manager.get_status()
            status_payload["active_workers"] = len(status_payload["worker_status"])

        return jsonify(status_payload)

    @app.route("/workers")
    def workers():
        return jsonify({
            "workers": camera_manager.get_status() if camera_manager is not None else [],
            "active_workers": len(camera_manager.get_status()) if camera_manager is not None else 0,
        })

    @app.route("/camera/<int:camera_id>/snapshot")
    def camera_snapshot(camera_id):
        import logging
        import threading
        log = logging.getLogger(__name__)

        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404

        source = camera["source"]
        log.info("Snapshot requested for camera %s (source=%s)", camera_id, source)

        result = {"frame": None, "error": None}

        def capture_frame():
            try:
                cap = cv2.VideoCapture(source)
                if not cap.isOpened():
                    result["error"] = "Não foi possível abrir a fonte de vídeo"
                    return

                is_network = source.startswith("http") or source.startswith("rtsp") or source.endswith(".m3u8")
                if is_network:
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                    # Skip buffered/garbage frames
                    for _ in range(3):
                        cap.read()

                success, frame = cap.read()
                cap.release()

                if not success or frame is None:
                    result["error"] = "Não foi possível capturar o frame"
                else:
                    result["frame"] = frame
            except Exception as e:
                result["error"] = f"Exceção: {e}"

        thread = threading.Thread(target=capture_frame, daemon=True)
        thread.start()
        thread.join(timeout=10)

        if thread.is_alive():
            log.warning("Snapshot timed out for camera %s (source=%s)", camera_id, source)
            return jsonify({"error": "Timeout ao capturar frame (stream inacessível)"}), 504

        if result["error"]:
            log.warning("Snapshot failed for camera %s: %s", camera_id, result["error"])
            return jsonify({"error": result["error"]}), 502

        success, jpg = cv2.imencode(".jpg", result["frame"])
        if not success:
            return jsonify({"error": "Falha ao codificar imagem"}), 500

        log.info("Snapshot OK for camera %s", camera_id)
        return Response(jpg.tobytes(), mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.route("/docs")
    def docs():
        api_docs = [
            {"path": "/", "method": "GET", "description": "Dashboard HTML"},
            {"path": "/health", "method": "GET", "description": "Service health check"},
            {"path": "/status", "method": "GET", "description": "Service and worker summary"},
            {"path": "/workers", "method": "GET", "description": "Current worker status"},
            {"path": "/camera/<id>/snapshot", "method": "GET", "description": "Capture a current frame preview"},
            {"path": "/cameras", "method": "GET", "description": "List cameras"},
            {"path": "/cameras", "method": "POST", "description": "Add a new camera"},
            {"path": "/cameras/<id>", "method": "PUT", "description": "Update a camera"},
            {"path": "/cameras/<id>", "method": "DELETE", "description": "Remove a camera"},
            {"path": "/zones", "method": "GET", "description": "List zones"},
            {"path": "/zones", "method": "POST", "description": "Add a new zone"},
            {"path": "/zones/<id>", "method": "PUT", "description": "Update a zone"},
            {"path": "/zones/<id>", "method": "DELETE", "description": "Remove a zone"},
            {"path": "/events", "method": "GET", "description": "Recent event history"},
        ]
        return render_template("docs.html", api_docs=api_docs)

    @app.route("/cameras")
    def cameras():
        return jsonify(storage.list_cameras())

    @app.route("/cameras", methods=["POST"])
    def add_camera():
        payload = request.get_json() or {}
        name = payload.get("name")
        source = payload.get("source")
        zone = payload.get("zone")

        if not name or not source:
            return jsonify({"error": "name and source são obrigatórios"}), 400

        if not CameraStream.validate_source(source):
            return jsonify({"error": "source inválido ou stream inacessível"}), 400

        camera_id = storage.add_camera(name, source, zone)
        return jsonify({"id": camera_id, "name": name, "source": source, "zone": zone}), 201

    @app.route("/cameras/<int:camera_id>", methods=["PUT"])
    def update_camera(camera_id):
        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404

        payload = request.get_json() or {}
        name = payload.get("name")
        source = payload.get("source")
        zone = payload.get("zone")

        if not name or not source:
            return jsonify({"error": "name and source são obrigatórios"}), 400

        if not CameraStream.validate_source(source):
            return jsonify({"error": "source inválido ou stream inacessível"}), 400

        storage.update_camera(camera_id, name, source, zone)
        updated_camera = storage.get_camera(camera_id)
        return jsonify(updated_camera), 200

    @app.route("/cameras/<int:camera_id>", methods=["DELETE"])
    def delete_camera(camera_id):
        removed = storage.remove_camera(camera_id)
        if not removed:
            return jsonify({"error": "Câmera não encontrada"}), 404
        return jsonify({"status": "removido"}), 200

    @app.route("/events")
    def events():
        items = storage.list_events(limit=100)
        return jsonify(items)

    @app.route("/zones")
    def zones():
        return jsonify(storage.list_zones())

    @app.route("/zones", methods=["POST"])
    def add_zone():
        payload = request.get_json() or {}
        name = payload.get("name")
        classification = payload.get("classification", "pública")

        if not name:
            return jsonify({"error": "name é obrigatório"}), 400

        if classification not in ('privativa', 'segurança', 'pública'):
            return jsonify({"error": "classification deve ser: privativa, segurança ou pública"}), 400

        existing = storage.list_zones()
        if any(z["name"] == name for z in existing):
            return jsonify({"error": "Zona com esse nome já existe"}), 400

        zone_id = storage.add_zone(name, classification)
        return jsonify({"id": zone_id, "name": name, "classification": classification}), 201

    @app.route("/zones/<int:zone_id>", methods=["PUT"])
    def update_zone(zone_id):
        zone = storage.get_zone(zone_id)
        if not zone:
            return jsonify({"error": "Zona não encontrada"}), 404

        payload = request.get_json() or {}
        name = payload.get("name")
        classification = payload.get("classification")

        if not name or not classification:
            return jsonify({"error": "name e classification são obrigatórios"}), 400

        if classification not in ('privativa', 'segurança', 'pública'):
            return jsonify({"error": "classification deve ser: privativa, segurança ou pública"}), 400

        storage.update_zone(zone_id, name, classification)
        updated_zone = storage.get_zone(zone_id)
        return jsonify(updated_zone), 200

    @app.route("/zones/<int:zone_id>", methods=["DELETE"])
    def delete_zone(zone_id):
        removed = storage.remove_zone(zone_id)
        if not removed:
            return jsonify({"error": "Zona não encontrada"}), 404
        return jsonify({"status": "removido"}), 200

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app
