import base64
import json

import numpy as np
import pytest

from secur.app import create_app
from secur.identity import IdentityRecognizer


def _stub_embedder(value):
    vec = np.array(value, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)
    return lambda img: vec


def _tiny_jpeg_b64():
    # 1x1 red JPEG encoded as base64
    import cv2
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[:, :] = (0, 0, 255)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


@pytest.fixture
def app(tmp_path, monkeypatch):
    import secur.config as cfg
    import secur.storage as storage_mod
    emb_dir = tmp_path / "emb"
    emb_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(cfg, "IDENTITY_EMBEDDINGS_DIR", emb_dir)
    monkeypatch.setattr(storage_mod, "IDENTITY_EMBEDDINGS_DIR", emb_dir)
    db_path = tmp_path / "events.db"
    monkeypatch.setattr(cfg, "DB_PATH", db_path)
    monkeypatch.setattr(storage_mod, "DB_PATH", db_path)
    app = create_app(db_path=db_path)
    app.config.update({"TESTING": True})
    app.recognizer_factory = lambda storage: IdentityRecognizer(
        storage,
        face_embedder=_stub_embedder([1, 0, 0]),
        reid_embedder=_stub_embedder([0, 1, 0]),
        threshold=0.6,
        enabled=True,
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_add_identity_success(client):
    resp = client.post(
        "/identities",
        data=json.dumps({"name": "João", "species": "person", "images": [_tiny_jpeg_b64()]}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json
    assert body["id"] == 1
    assert body["name"] == "João"
    assert body["species"] == "person"


def test_add_identity_rejects_invalid_species(client):
    resp = client.post(
        "/identities",
        data=json.dumps({"name": "X", "species": "alien", "images": [_tiny_jpeg_b64()]}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "species" in resp.json["error"]


def test_add_identity_requires_name_and_species(client):
    resp = client.post(
        "/identities",
        data=json.dumps({"images": [_tiny_jpeg_b64()]}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_list_identities(client):
    client.post(
        "/identities",
        data=json.dumps({"name": "João", "species": "person", "images": [_tiny_jpeg_b64()]}),
        content_type="application/json",
    )
    resp = client.get("/identities")
    assert resp.status_code == 200
    assert len(resp.json) == 1
    assert resp.json[0]["name"] == "João"


def test_delete_identity(client):
    client.post(
        "/identities",
        data=json.dumps({"name": "João", "species": "person", "images": [_tiny_jpeg_b64()]}),
        content_type="application/json",
    )
    resp = client.delete("/identities/1")
    assert resp.status_code == 200
    assert client.get("/identities").json == []


def test_delete_identity_not_found(client):
    resp = client.delete("/identities/9999")
    assert resp.status_code == 404


def test_import_identity(client):
    resp = client.post(
        "/identities/import",
        data=json.dumps({"name": "Importado", "species": "person", "thumbnail": _tiny_jpeg_b64()}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json["id"] == 1
    assert client.get("/identities").json[0]["name"] == "Importado"


def test_import_identity_rejects_invalid_species(client):
    resp = client.post(
        "/identities/import",
        data=json.dumps({"name": "X", "species": "alien"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_thumbnail_served_after_registration(client):
    client.post(
        "/identities",
        data=json.dumps({"name": "João", "species": "person", "images": [_tiny_jpeg_b64()]}),
        content_type="application/json",
    )
    resp = client.get("/identities/1/thumbnail")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_thumbnail_404_without_thumbnail(client):
    client.post(
        "/identities/import",
        data=json.dumps({"name": "SemThumb", "species": "person"}),
        content_type="application/json",
    )
    resp = client.get("/identities/1/thumbnail")
    assert resp.status_code == 404