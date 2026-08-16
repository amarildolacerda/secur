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
