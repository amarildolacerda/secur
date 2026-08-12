import numpy as np
from secur.main import decide_worker_event


def test_decide_worker_event_known():
    dets = [{"label": "person", "bbox": {"x": 0, "y": 0, "w": 5, "h": 5}, "confidence": 0.9}]
    ident = {"identity_id": 1, "name": "João", "known": True, "method": "face", "confidence": 0.9}
    event_type, details, identity_name, known, _label, category = decide_worker_event(dets, ident, "privativa", "Cam1", "person")
    assert event_type == "identity_recognized"
    assert identity_name == "João" and known is True and category == "person"


def test_decide_worker_event_intruder():
    dets = [{"label": "person", "bbox": {"x": 0, "y": 0, "w": 5, "h": 5}, "confidence": 0.9}]
    ident = {"identity_id": None, "name": "unknown", "known": False, "method": "reid", "confidence": 0.3}
    event_type, details, identity_name, known, _label, category = decide_worker_event(dets, ident, "privativa", "Cam1", "person")
    assert event_type == "intruder_detected"
