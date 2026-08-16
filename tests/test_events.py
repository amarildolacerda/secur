from src.event_rules import decide_worker_event, _unpack_worker_decision


def test_decide_fall():
    et, det, *_ = decide_worker_event([], None, "public", "cam1", fall=True, now=1.0)
    assert et == "fall_detected"


def test_unpack_none():
    assert _unpack_worker_decision(None) == (None,) * 6


def test_events_level_columns(tmp_path):
    from src.storage import EventStorage
    s = EventStorage(str(tmp_path / "t.db"))
    eid = s.add_event("1", "z", "motion", "d", level=0, source="local", dropped=False)
    assert eid > 0
    s.update_event_level(eid, 4, event_type="motion", disposition="alert")
    rows = s.list_events(level=4)
    assert len(rows) == 1 and rows[0]["source"] == "local" and rows[0]["dropped"] == 0
    assert s.list_events(level=9) == []


def test_local_queue_delivers():
    from src.events import LocalEventQueue, CameraEvent
    q = LocalEventQueue()
    received = []
    q.subscribe(lambda e: received.append(e))
    q.start()
    ev = CameraEvent(camera_id="1", source="local")
    q.enqueue(ev)
    import time; time.sleep(0.2)
    assert received and received[0].camera_id == "1"


def test_worker_emits_not_alerts():
    import src.events as ev_mod
    sent = []
    class FakeBus:
        def enqueue(self, e): sent.append(e)
        def subscribe(self, h): pass
        def start(self): pass
    # usa CameraWorker com stubs; verifica que enfileira e NÃO chama alerts.send
    from src.main import CameraWorker
    cam = {"id": "1", "name": "cam1", "alert_classes": ["person"]}
    alerts_spy = {"called": False}
    class FakeAlerts:
        def send(self, *a, **k): alerts_spy["called"] = True
    w = CameraWorker.__new__(CameraWorker)
    w.camera = cam
    w.event_bus = FakeBus()
    w.alerts = FakeAlerts()
    ce = w.build_candidate_event([{"label": "person"}], None, None, "zone", "public",
                                 None, 1.0, False, None, None, None, no_motion=False)
    assert ce.source == "local" and ce.level == 1 and ce.dropped is False
    assert alerts_spy["called"] is False

