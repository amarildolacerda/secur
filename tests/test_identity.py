import numpy as np
from secur.identity import (
    IdentityRecognizer,
    cosine_similarity,
    decide_event,
    RECOGNITION_LABELS,
)


def _stub_embedder(value):
    vec = np.array(value, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)
    return lambda img: vec


def test_cosine_similarity_basic():
    a = np.array([1.0, 0.0])
    b = np.array([1.0, 0.0])
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-6
    c = np.array([0.0, 1.0])
    assert abs(cosine_similarity(a, c)) < 1e-6


def test_recognize_known_and_unknown(tmp_path, monkeypatch):
    import secur.config as cfg
    monkeypatch.setattr(cfg, "IDENTITY_EMBEDDINGS_DIR", tmp_path / "emb")
    (tmp_path / "emb").mkdir(exist_ok=True)
    from secur.storage import EventStorage
    db = EventStorage(tmp_path / "events.db")
    rec = IdentityRecognizer(db, face_embedder=_stub_embedder([1, 0, 0]), reid_embedder=_stub_embedder([0, 1, 0]),
                             threshold=0.6, enabled=True)

    ident_id = rec.enroll("João", "person", [np.zeros((10, 10, 3), np.uint8)])
    assert ident_id == 1
    # same embedding -> known
    res = rec.recognize(np.zeros((10, 10, 3), np.uint8), "person")
    assert res["known"] is True and res["name"] == "João"
    # orthogonal embedding -> unknown
    rec2 = IdentityRecognizer(db, face_embedder=_stub_embedder([0, 0, 1]), reid_embedder=_stub_embedder([0, 1, 0]),
                              threshold=0.6, enabled=True)
    res2 = rec2.recognize(np.zeros((10, 10, 3), np.uint8), "person")
    assert res2["known"] is False and res2["name"] == "unknown"


def test_recognize_falls_back_to_reid():
    db = type("S", (), {"list_identities": lambda: [], "load_identity_embedding": lambda i: None})()
    rec = IdentityRecognizer(db, face_embedder=lambda img: None, reid_embedder=lambda img: np.array([1.0, 0.0]),
                             threshold=0.6, enabled=True)
    res = rec.recognize(np.zeros((10, 10, 3), np.uint8), "dog")
    assert res["method"] == "reid" and res["known"] is False


def test_decide_event_routing():
    known = {"name": "João", "known": True}
    intruder = {"name": "unknown", "known": False}
    kr = decide_event(known, "pública", "Cam1", "person")
    assert kr[0] == "identity_recognized" and kr[5] == "person"
    ir = decide_event(intruder, "privativa", "Cam1", "person")
    assert ir[0] == "intruder_detected" and ir[5] == "person"
    r = decide_event(intruder, "pública", "Cam1", "cow")
    assert r[0] == "unknown_detected"
    assert r[2] == "cow" and r[5] == "animal"
    v = decide_event(intruder, "pública", "Cam1", "car")
    assert v[0] == "unknown_detected" and v[5] == "vehicle"
    assert decide_event(None, "privativa", "Cam1", "person") is None
