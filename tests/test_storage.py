from pathlib import Path
from secur.storage import EventStorage


def test_storage_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    camera_id = storage.add_camera("Camera Test", "source://test", "entrada")
    assert camera_id == 1

    cameras = storage.list_cameras()
    assert len(cameras) == 1
    assert cameras[0]["name"] == "Camera Test"
    assert cameras[0]["zone"] == "entrada"

    event_id = storage.add_event(camera_id, "entrada", "motion_detected", "detected")
    assert event_id == 1

    events = storage.list_events(limit=10)
    assert len(events) == 1
    assert events[0]["event_type"] == "motion_detected"
    assert events[0]["camera_id"] == str(camera_id)

    assert storage.remove_camera(camera_id) is True
    assert storage.get_camera(camera_id) is None

    storage.close()


def test_seed_cameras_runs_once(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    default_cameras = [
        {"name": "Seed Cam", "source": "source://seed", "zone": "entrada"}
    ]
    storage.seed_cameras(default_cameras)
    assert len(storage.list_cameras()) == 1

    storage.seed_cameras(default_cameras)
    assert len(storage.list_cameras()) == 1

    storage.close()
