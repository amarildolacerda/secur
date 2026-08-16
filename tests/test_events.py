from src.event_rules import decide_worker_event, _unpack_worker_decision


def test_decide_fall():
    et, det, *_ = decide_worker_event([], None, "public", "cam1", fall=True, now=1.0)
    assert et == "fall_detected"


def test_unpack_none():
    assert _unpack_worker_decision(None) == (None,) * 6
