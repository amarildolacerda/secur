import json
import pytest
from secur.app import create_app
from secur.camera import CameraStream


@pytest.fixture
def app():
    app = create_app()
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
