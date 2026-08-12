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
        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404

        capture = cv2.VideoCapture(camera["source"])
        if not capture.isOpened():
            capture.release()
            return jsonify({"error": "Não foi possível abrir a fonte de vídeo"}), 502

        success, frame = capture.read()
        capture.release()
        if not success or frame is None:
            return jsonify({"error": "Não foi possível capturar o frame"}), 502

        success, jpg = cv2.imencode(".jpg", frame)
        if not success:
            return jsonify({"error": "Falha ao codificar imagem"}), 500

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
            {"path": "/cameras/<id>", "method": "DELETE", "description": "Remove a camera"},
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

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app
