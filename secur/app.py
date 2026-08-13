import cv2
import os
from flask import Flask, jsonify, render_template, request, Response, send_file
from .camera import CameraStream
from .storage import EventStorage
from .notifications import CHANNELS, EVENT_TYPES
import base64
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)

try:
    from .identity import build_recognizer, IdentityRecognizer
except Exception:
    build_recognizer = None
    IdentityRecognizer = None


def create_app(camera_manager=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    storage = EventStorage()
    # recognizer_factory hook: tests or callers may set app.recognizer_factory = lambda storage: recognizer
    def _make_recognizer() -> Optional[object]:
        # Prefer the shared recognizer used by the camera workers so cache
        # refreshes (enroll/remove/import) propagate to live recognition.
        if camera_manager is not None and getattr(camera_manager, "identity_recognizer", None) is not None:
            return camera_manager.identity_recognizer
        if hasattr(app, "recognizer_factory") and callable(app.recognizer_factory):
            return app.recognizer_factory(storage)
        if build_recognizer is None:
            return None
        return build_recognizer(storage)

    app.recognizer_factory_internal = _make_recognizer

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

    @app.route("/camera/<int:camera_id>/thumbnails")
    def camera_thumbnails(camera_id):
        camera = storage.get_camera(camera_id)
        if not camera:
            return jsonify({"error": "Câmera não encontrada"}), 404
        items = storage.list_camera_thumbnails(camera_id, limit=20)
        out = []
        for it in items:
            out.append({
                "id": it["id"],
                "timestamp": it["timestamp"],
                "event_type": it["event_type"],
                "url": f"/thumbnails/{it['id']}/image",
            })
        return jsonify(out)

    @app.route("/thumbnails/<int:thumb_id>/image")
    def thumbnail_image(thumb_id):
        item = storage.get_camera_thumbnail(thumb_id)
        if not item:
            return jsonify({"error": "Thumbnail não encontrado"}), 404
        path = item["path"]
        if not os.path.exists(path):
            return jsonify({"error": "Thumbnail não encontrado"}), 404
        return send_file(path, mimetype="image/jpeg")

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
            {"path": "/camera/<id>/thumbnails", "method": "GET", "description": "Lista os últimos thumbnails da câmera"},
            {"path": "/thumbnails/<id>/image", "method": "GET", "description": "Imagem JPEG de um thumbnail"},
            {"path": "/api/notifications", "method": "GET", "description": "Canais, eventos e routing de notificações"},
            {"path": "/api/notifications/routing", "method": "PUT", "description": "Atualiza routing de um evento em um canal"},
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
        storage.remove_camera_thumbnails(camera_id)
        return jsonify({"status": "removido"}), 200

    @app.route("/events")
    def events():
        items = storage.list_events(limit=100)
        return jsonify(items)

    @app.route("/zones")
    def zones():
        return jsonify(storage.list_zones())

    @app.route("/api/notifications")
    def notifications_get():
        routing = storage.get_all_routing()
        return jsonify({
            "channels": CHANNELS,
            "events": EVENT_TYPES,
            "routing": routing,
        })

    @app.route("/api/notifications/routing", methods=["PUT"])
    def notifications_put():
        payload = request.get_json() or {}
        channel = payload.get("channel")
        event_type = payload.get("event_type")
        enabled = payload.get("enabled")
        if enabled is None:
            return jsonify({"error": "enabled é obrigatório"}), 400
        valid_channels = {c["key"] for c in CHANNELS}
        valid_events = {e["key"] for e in EVENT_TYPES}
        if channel not in valid_channels:
            return jsonify({"error": "canal inválido"}), 400
        if event_type not in valid_events:
            return jsonify({"error": "evento inválido"}), 400
        storage.set_routing(channel, event_type, bool(enabled))
        return jsonify({"status": "ok"}), 200


    # ========== Identity endpoints ==========
    @app.route("/identities", methods=["GET"])
    def list_identities():
        items = storage.list_identities()
        out = []
        for it in items:
            thumb = it.get('thumbnail_path')
            if thumb:
                it['thumbnail_url'] = f"/identities/{it['id']}/thumbnail"
            else:
                it['thumbnail_url'] = None
            out.append(it)
        return jsonify(out)

    @app.route("/identities", methods=["POST"])
    def add_identity():
        payload = request.get_json() or {}
        name = payload.get("name")
        species = payload.get("species")
        images_b64 = payload.get("images", [])

        if not name or not species:
            return jsonify({"error": "name and species are required"}), 400
        # validate species against recognizer labels
        try:
            from .identity import RECOGNITION_LABELS
            allowed = set(RECOGNITION_LABELS.values())
        except Exception:
            allowed = set(("person", "animal"))
        if species not in allowed:
            return jsonify({"error": f"species must be one of: {', '.join(sorted(allowed))}"}), 400

        images = []
        for s in images_b64:
            try:
                raw = base64.b64decode(s)
                arr = np.frombuffer(raw, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    images.append(img)
            except Exception:
                continue

        recognizer = app.recognizer_factory_internal()
        if recognizer is None:
            # fallback: save mean embedding directly via storage if no recognizer available
            return jsonify({"error": "identity recognizer not configured"}), 503

        try:
            ident_id = recognizer.enroll(name, species, images)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        # persist thumbnail (first provided base64) if available
        try:
            if images_b64:
                thumb_b64 = images_b64[0]
                thumb_path = storage.save_identity_thumbnail(name, thumb_b64)
                if thumb_path:
                    storage.update_identity_thumbnail(ident_id, thumb_path)
                else:
                    logger.warning("Falha ao salvar thumbnail para identidade %s", name)
        except Exception:
            logger.exception("Falha ao persistir thumbnail para identidade %s", name)

        return jsonify({"id": ident_id, "name": name, "species": species}), 201

    @app.route('/identities/<int:identity_id>/thumbnail')
    def identity_thumbnail(identity_id: int):
        ident = storage.get_identity(identity_id)
        if not ident or not ident.get('thumbnail_path'):
            return jsonify({'error': 'Thumbnail not found'}), 404
        try:
            from flask import send_file
            return send_file(ident['thumbnail_path'], mimetype='image/jpeg')
        except Exception:
            return jsonify({'error': 'Failed to serve thumbnail'}), 500

    @app.route("/identities/<int:identity_id>", methods=["DELETE"])
    def delete_identity(identity_id):
        recognizer = app.recognizer_factory_internal()
        if recognizer is not None and hasattr(recognizer, "remove_identity"):
            removed = recognizer.remove_identity(identity_id)
        else:
            removed = storage.remove_identity(identity_id)
        if not removed:
            return jsonify({"error": "Identity not found"}), 404
        return jsonify({"status": "removido"}), 200

    @app.route('/identities/import', methods=['POST'])
    def import_identity():
        """Create an identity directly with a thumbnail (bypass recognizer). Useful for testing."""
        payload = request.get_json() or {}
        name = payload.get('name')
        species = payload.get('species')
        thumb_b64 = payload.get('thumbnail')

        if not name or not species:
            return jsonify({'error': 'name and species are required'}), 400

        # validate species against recognizer labels
        try:
            from .identity import RECOGNITION_LABELS
            allowed = set(RECOGNITION_LABELS.values())
        except Exception:
            allowed = set(("person", "animal"))
        if species not in allowed:
            return jsonify({'error': f"species must be one of: {', '.join(sorted(allowed))}"}), 400

        # create a placeholder embedding file with the real embedder dimension
        try:
            import numpy as _np
            recognizer = app.recognizer_factory_internal()
            dim = 128
            if recognizer is not None:
                for embedder in (getattr(recognizer, "face_embedder", None), getattr(recognizer, "reid_embedder", None)):
                    if embedder is None:
                        continue
                    try:
                        probe = embedder(_np.zeros((32, 32, 3), dtype=_np.uint8))
                        if probe is not None and probe.size > 0:
                            dim = int(probe.size)
                            break
                    except Exception:
                        continue
            emb = _np.zeros((dim,), dtype=_np.float32)
            emb_path = storage.save_identity_embedding(name, emb)
            ident_id = storage.add_identity(name, species, emb_path)
            if thumb_b64:
                thumb_path = storage.save_identity_thumbnail(name, thumb_b64)
                if thumb_path:
                    storage.update_identity_thumbnail(ident_id, thumb_path)
            if recognizer is not None and hasattr(recognizer, "refresh_cache"):
                recognizer.refresh_cache()
            return jsonify({'id': ident_id, 'name': name, 'species': species}), 201
        except Exception as e:
            logger.exception("Falha ao importar identidade")
            return jsonify({'error': 'falha ao importar identidade'}), 500

    @app.route("/identities/view")
    def identities_view():
        # derive species options from recognizer labels
        try:
            from .identity import RECOGNITION_LABELS
            species_vals = sorted(set(RECOGNITION_LABELS.values()))
        except Exception:
            species_vals = ["person", "animal"]

        def label_for(s):
            return {"person": "Pessoa", "animal": "Animal", "vehicle": "Veículo"}.get(s, s.capitalize())

        species_options = [{"value": s, "label": label_for(s)} for s in species_vals]
        return render_template("identities.html", species_options=species_options)

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
