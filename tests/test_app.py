import json
import pytest
from secur.app import create_app
from secur.camera import CameraStream


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    app = create_app(db_path=db_path)
    app.config.update({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_route(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_docs_route(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert b"Secur API Documentation" in response.data
    assert b"/status" in response.data
    assert b"/workers" in response.data


def test_status_route(client):
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json
    assert body["status"] == "ok"
    assert "camera_count" in body
    assert "recent_events" in body
    assert "cameras" in body
    assert isinstance(body["cameras"], list)


def test_workers_route(client):
    response = client.get("/workers")
    assert response.status_code == 200
    body = response.json
    assert body["active_workers"] == 0
    assert body["workers"] == []


def test_cameras_route_initial_empty(client):
    response = client.get("/cameras")
    assert response.status_code == 200
    assert isinstance(response.json, list)


def test_add_camera_rejects_invalid_source(client, monkeypatch):
    def fake_validate_source(source):
        return False

    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(fake_validate_source))
    response = client.post(
        "/cameras",
        data=json.dumps({"name": "Test Camera", "source": "invalid-source", "zone": "test"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json["error"] == "source inválido ou stream inacessível"


def test_add_camera_accepts_valid_source(client, monkeypatch):
    def fake_validate_source(source):
        return True

    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(fake_validate_source))
    response = client.post(
        "/cameras",
        data=json.dumps({"name": "Test Camera", "source": "valid-source", "zone": "test"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["name"] == "Test Camera"
    assert response.json["source"] == "valid-source"
    assert response.json["zone"] == "test"


def test_camera_thumbnails_route(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    resp = client.post("/cameras", json={"name": "Cam", "source": "source://x", "zone": "entrada"})
    assert resp.status_code == 201
    cam_id = resp.json["id"]

    # no thumbnails yet
    resp = client.get(f"/camera/{cam_id}/thumbnails")
    assert resp.status_code == 200
    assert resp.json == []


def test_camera_thumbnails_route_404(client):
    resp = client.get("/camera/999/thumbnails")
    assert resp.status_code == 404


def test_thumbnail_image_route_404(client):
    resp = client.get("/thumbnails/999/image")
    assert resp.status_code == 404


def test_notifications_get(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    body = resp.json
    assert [c["key"] for c in body["channels"]] == ["telegram", "automation"]
    assert "motion_detected" in [e["key"] for e in body["events"]]
    assert "routing" in body


def test_notifications_put(client):
    resp = client.put("/api/notifications/routing", json={"channel": "telegram", "event_type": "no_motion", "enabled": True})
    assert resp.status_code == 200
    body = client.get("/api/notifications").json
    assert body["routing"]["telegram"]["no_motion"] is True


def test_notifications_put_invalid(client):
    resp = client.put("/api/notifications/routing", json={"channel": "nope", "event_type": "no_motion", "enabled": True})
    assert resp.status_code == 400
    resp = client.put("/api/notifications/routing", json={"channel": "telegram", "event_type": "nope", "enabled": True})
    assert resp.status_code == 400


def test_add_camera_with_alert_classes(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    response = client.post(
        "/cameras",
        data=json.dumps({
            "name": "Cam", "source": "valid-source", "zone": "entrada",
            "alert_classes": ["person", "car"],
            "exclusion_zones": [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]],
        }),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["alert_classes"] == ["person", "car"]
    assert response.json["exclusion_zones"] == [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]


def test_add_camera_rejects_invalid_alert_classes(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    response = client.post(
        "/cameras",
        data=json.dumps({"name": "Cam", "source": "valid-source", "alert_classes": "person"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_api_classes(client):
    response = client.get("/api/classes")
    assert response.status_code == 200
    assert "person" in response.json["classes"]


def test_camera_clips_route(client, monkeypatch):
    from secur.camera import CameraStream
    monkeypatch.setattr(CameraStream, "validate_source", staticmethod(lambda s: True))
    resp = client.post("/cameras", json={"name": "Cam", "source": "source://x", "zone": "entrada"})
    cam_id = resp.json["id"]

    resp = client.get(f"/camera/{cam_id}/clips")
    assert resp.status_code == 200
    assert resp.json == []


def test_camera_clips_route_404(client):
    resp = client.get("/camera/999/clips")
    assert resp.status_code == 404


def test_clip_metadata_route_404(client):
    resp = client.get("/clips/999")
    assert resp.status_code == 404


def test_clip_video_route_404(client):
    resp = client.get("/clips/999/video")
    assert resp.status_code == 404
