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


def test_camera_thumbnails_crud_and_prune(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    # create fake thumbnail files on disk
    files = []
    for i in range(3):
        p = tmp_path / f"thumb_{i}.jpg"
        p.write_bytes(b"jpegdata")
        files.append(str(p))
        storage.add_camera_thumbnail(cam_id, str(p), "motion_detected")

    thumbs = storage.list_camera_thumbnails(cam_id)
    assert len(thumbs) == 3
    # most recent first
    assert thumbs[0]["path"] == files[2]
    assert thumbs[0]["event_type"] == "motion_detected"

    # prune keeps only the newest 2
    storage.prune_camera_thumbnails(cam_id, keep=2)
    thumbs = storage.list_camera_thumbnails(cam_id)
    assert len(thumbs) == 2
    assert thumbs[0]["path"] == files[2]
    assert not Path(files[0]).exists()  # oldest file deleted from disk

    # remove all
    storage.remove_camera_thumbnails(cam_id)
    assert storage.list_camera_thumbnails(cam_id) == []
    assert not Path(files[1]).exists()
    assert not Path(files[2]).exists()
    storage.close()


def test_notification_routing_seed_and_update(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    defaults = {
        "telegram": {"motion_detected": True, "no_motion": False},
        "automation": {"motion_detected": True, "no_motion": True},
    }
    storage.seed_default_routing(defaults)
    assert storage.get_routing("telegram") == {"motion_detected": True, "no_motion": False}

    # seeding again does not overwrite
    storage.seed_default_routing({"telegram": {"motion_detected": False}})
    assert storage.get_routing("telegram")["motion_detected"] is True

    storage.set_routing("telegram", "no_motion", True)
    assert storage.get_routing("telegram")["no_motion"] is True

    all_routing = storage.get_all_routing()
    assert all_routing["automation"]["no_motion"] is True
    storage.close()
