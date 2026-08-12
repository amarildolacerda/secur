import json
import pytest
from secur.app import create_app
from secur.storage import EventStorage


@pytest.fixture
def app():
    app = create_app()
    app.config.update({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def storage(app):
    return EventStorage()


# ========== Zone CRUD ==========


def test_list_zones_initial_empty(client):
    response = client.get("/zones")
    assert response.status_code == 200
    assert isinstance(response.json, list)


def test_add_zone(client):
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Entrada", "classification": "pública"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["name"] == "Entrada"
    assert response.json["classification"] == "pública"
    assert "id" in response.json


def test_add_zone_privativa(client):
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Sala servidores", "classification": "privativa"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["classification"] == "privativa"


def test_add_zone_seguranca(client):
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Recepção", "classification": "segurança"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json["classification"] == "segurança"


def test_add_zone_requires_name(client):
    response = client.post(
        "/zones",
        data=json.dumps({"classification": "pública"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "name" in response.json["error"]


def test_add_zone_invalid_classification(client):
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Teste", "classification": "invalida"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "classification" in response.json["error"]


def test_add_zone_duplicate_name(client):
    client.post(
        "/zones",
        data=json.dumps({"name": "Duplicada", "classification": "pública"}),
        content_type="application/json",
    )
    response = client.post(
        "/zones",
        data=json.dumps({"name": "Duplicada", "classification": "pública"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "já existe" in response.json["error"]


def test_update_zone(client):
    res = client.post(
        "/zones",
        data=json.dumps({"name": "Original", "classification": "pública"}),
        content_type="application/json",
    )
    zone_id = res.json["id"]

    response = client.put(
        f"/zones/{zone_id}",
        data=json.dumps({"name": "Atualizada", "classification": "privativa"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["name"] == "Atualizada"
    assert response.json["classification"] == "privativa"


def test_update_zone_not_found(client):
    response = client.put(
        "/zones/9999",
        data=json.dumps({"name": "X", "classification": "pública"}),
        content_type="application/json",
    )
    assert response.status_code == 404


def test_delete_zone(client):
    res = client.post(
        "/zones",
        data=json.dumps({"name": "Para deletar", "classification": "pública"}),
        content_type="application/json",
    )
    zone_id = res.json["id"]

    response = client.delete(f"/zones/{zone_id}")
    assert response.status_code == 200
    assert response.json["status"] == "removido"


def test_delete_zone_not_found(client):
    response = client.delete("/zones/9999")
    assert response.status_code == 404


# ========== Alert zone classification ==========


def test_home_assistant_fires_for_privativa_motion():
    from secur.alerts import home_assistant_handler

    fired = []

    def fake_post(url, headers=None, json=None, timeout=None):
        class FakeResponse:
            status_code = 200
            def raise_for_status(self):
                pass
        fired.append(json)
        return FakeResponse()

    import secur.alerts as alerts_mod
    original = alerts_mod.requests.post
    alerts_mod.requests.post = fake_post
    try:
        payload = {
            "camera_id": "1",
            "zone": "Sala servidores",
            "event_type": "motion_detected",
            "details": "test",
            "zone_classification": "privativa",
        }
        home_assistant_handler(payload)
        assert len(fired) == 1
        assert fired[0]["zone_classification"] == "privativa"
    finally:
        alerts_mod.requests.post = original


def test_home_assistant_fires_for_seguranca_motion():
    from secur.alerts import home_assistant_handler

    fired = []

    def fake_post(url, headers=None, json=None, timeout=None):
        class FakeResponse:
            status_code = 200
            def raise_for_status(self):
                pass
        fired.append(json)
        return FakeResponse()

    import secur.alerts as alerts_mod
    original = alerts_mod.requests.post
    alerts_mod.requests.post = fake_post
    try:
        payload = {
            "camera_id": "2",
            "zone": "Recepção",
            "event_type": "motion_detected",
            "details": "test",
            "zone_classification": "segurança",
        }
        home_assistant_handler(payload)
        assert len(fired) == 1
    finally:
        alerts_mod.requests.post = original


def test_home_assistant_skips_publica_motion():
    from secur.alerts import home_assistant_handler

    fired = []

    def fake_post(url, headers=None, json=None, timeout=None):
        class FakeResponse:
            status_code = 200
            def raise_for_status(self):
                pass
        fired.append(json)
        return FakeResponse()

    import secur.alerts as alerts_mod
    original = alerts_mod.requests.post
    alerts_mod.requests.post = fake_post
    try:
        payload = {
            "camera_id": "3",
            "zone": "Entrada",
            "event_type": "motion_detected",
            "details": "test",
            "zone_classification": "pública",
        }
        home_assistant_handler(payload)
        assert len(fired) == 0
    finally:
        alerts_mod.requests.post = original


def test_home_assistant_fires_object_detected_any_zone():
    from secur.alerts import home_assistant_handler

    fired = []

    def fake_post(url, headers=None, json=None, timeout=None):
        class FakeResponse:
            status_code = 200
            def raise_for_status(self):
                pass
        fired.append(json)
        return FakeResponse()

    import secur.alerts as alerts_mod
    original = alerts_mod.requests.post
    alerts_mod.requests.post = fake_post
    try:
        payload = {
            "camera_id": "4",
            "zone": "Entrada",
            "event_type": "object_detected",
            "details": "test",
            "zone_classification": "pública",
        }
        home_assistant_handler(payload)
        assert len(fired) == 1
    finally:
        alerts_mod.requests.post = original
