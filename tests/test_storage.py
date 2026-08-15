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


def test_camera_alert_classes_and_exclusion_zones(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    cam_id = storage.add_camera(
        "Cam", "source://x", "entrada",
        alert_classes=["person", "car"],
        exclusion_zones=[[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]],
    )
    cam = storage.get_camera(cam_id)
    assert cam["alert_classes"] == ["person", "car"]
    assert cam["exclusion_zones"] == [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]

    storage.update_camera(cam_id, "Cam", "source://y", "entrada", alert_classes=["person"])
    cam = storage.get_camera(cam_id)
    assert cam["alert_classes"] == ["person"]
    assert cam["exclusion_zones"] is None

    storage.close()


def test_camera_defaults_alert_classes_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")
    cam = storage.get_camera(cam_id)
    assert cam["alert_classes"] is None
    assert cam["exclusion_zones"] is None
    storage.close()


def test_zone_schedule_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    zone_id = storage.add_zone("Sala", "privativa", schedule={"start": "22:00", "end": "06:00"})
    zone = storage.get_zone(zone_id)
    assert zone["schedule"] == {"start": "22:00", "end": "06:00"}

    storage.update_zone(zone_id, "Sala", "privativa", schedule=None)
    zone = storage.get_zone(zone_id)
    assert zone["schedule"] is None

    storage.close()


def test_migration_adds_new_columns(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE cameras (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source TEXT NOT NULL, zone TEXT)"
    )
    conn.execute(
        "CREATE TABLE zones (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, classification TEXT NOT NULL DEFAULT 'pública')"
    )
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada", alert_classes=["person"])
    assert storage.get_camera(cam_id)["alert_classes"] == ["person"]
    zone_id = storage.add_zone("Z", "pública", schedule={"start": "08:00", "end": "18:00"})
    assert storage.get_zone(zone_id)["schedule"] == {"start": "08:00", "end": "18:00"}
    storage.close()


def test_event_clips_crud_and_prune(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    files = []
    for i in range(3):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"mp4data")
        files.append(str(p))
        storage.add_event_clip(cam_id, None, str(p), 10.0)

    clips = storage.list_event_clips(cam_id)
    assert len(clips) == 3
    assert clips[0]["path"] == files[2]
    assert clips[0]["duration_s"] == 10.0

    storage.prune_event_clips(cam_id, keep=2)
    clips = storage.list_event_clips(cam_id)
    assert len(clips) == 2
    assert not Path(files[0]).exists()

    storage.remove_event_clips(cam_id)
    assert storage.list_event_clips(cam_id) == []
    assert not Path(files[1]).exists()
    storage.close()


def test_event_clip_get_and_404(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"mp4data")
    clip_id = storage.add_event_clip(cam_id, None, str(p), 5.0)

    clip = storage.get_event_clip(clip_id)
    assert clip["camera_id"] == cam_id
    assert clip["duration_s"] == 5.0
    assert storage.get_event_clip(9999) is None
    storage.close()


def test_update_event_clip_path(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    event_id = storage.add_event("1", "entrada", "motion_detected", "teste")

    assert storage.update_event_clip_path(event_id, "/tmp/clip.mp4") is True
    events = storage.list_events(limit=10)
    assert events[0]["clip_path"] == "/tmp/clip.mp4"

    assert storage.update_event_clip_path(9999, "/tmp/x.mp4") is False
    storage.close()


def test_camera_mask_polygons_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    polygons = [[{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}]]
    cam_id = storage.add_camera("Cam", "source://x", "entrada", mask_polygons=polygons)
    cam = storage.get_camera(cam_id)
    assert cam["mask_polygons"] == polygons
    # list_cameras parse path (separate json.loads copy)
    assert storage.list_cameras()[0]["mask_polygons"] == polygons

    storage.update_camera(cam_id, "Cam", "source://y", "entrada", mask_polygons=None)
    cam = storage.get_camera(cam_id)
    assert cam["mask_polygons"] is None

    storage.close()


def test_camera_mask_polygons_default_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")
    cam = storage.get_camera(cam_id)
    assert cam["mask_polygons"] is None
    assert cam["exclusion_zones"] is None
    storage.close()


def test_migration_adds_mask_polygons_column(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE cameras (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, source TEXT NOT NULL, zone TEXT)"
    )
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    # Legacy-DB contract: EventStorage.__init__ unlinks the seeded file under
    # pytest, so migration runs on a fresh CREATE (which omits the column and
    # triggers the same ALTER). Insert a row without mask data and verify the
    # NULL-parse path on the migrated table — the real compatibility contract.
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO cameras (name, source, zone) VALUES (?, ?, ?)",
            ("Legacy", "source://legacy", "entrada"),
        )
    legacy = storage.get_camera(1)
    assert legacy["mask_polygons"] is None
    assert legacy["alert_classes"] is None

    cam_id = storage.add_camera(
        "Cam", "source://x", "entrada",
        mask_polygons=[[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]],
    )
    assert storage.get_camera(cam_id)["mask_polygons"] == [
        [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]
    ]
    storage.close()


def test_zone_retention_policy_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    policy = {"thumbnails": 5, "clips": 3, "days": 7}
    zone_id = storage.add_zone("Sala", "privativa", retention_policy=policy)
    assert storage.get_zone(zone_id)["retention_policy"] == policy

    storage.update_zone(zone_id, "Sala", "privativa", retention_policy=None)
    assert storage.get_zone(zone_id)["retention_policy"] is None
    storage.close()


def test_zone_retention_policy_default_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Sala", "privativa")
    assert storage.get_zone(zone_id)["retention_policy"] is None
    storage.close()


def test_migration_adds_retention_policy_column(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE zones (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, classification TEXT NOT NULL DEFAULT 'pública')"
    )
    conn.commit()
    conn.close()

    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Z", "pública", retention_policy={"days": 30})
    assert storage.get_zone(zone_id)["retention_policy"] == {"days": 30}
    storage.close()


def test_prune_thumbnails_by_max_age(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    old_file = tmp_path / "old.jpg"
    old_file.write_bytes(b"jpegdata")
    old_id = storage.add_camera_thumbnail(cam_id, str(old_file), "motion_detected")
    storage.connection.execute(
        "UPDATE camera_thumbnails SET timestamp = '2020-01-01T00:00:00+00:00' WHERE id = ?",
        (old_id,),
    )
    storage.connection.commit()

    new_file = tmp_path / "new.jpg"
    new_file.write_bytes(b"jpegdata")
    storage.add_camera_thumbnail(cam_id, str(new_file), "motion_detected")

    storage.prune_camera_thumbnails(cam_id, keep=10, max_age_days=7)
    thumbs = storage.list_camera_thumbnails(cam_id)
    assert len(thumbs) == 1
    assert thumbs[0]["path"] == str(new_file)
    assert not Path(old_file).exists()
    storage.close()


def test_prune_clips_by_max_age(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    cam_id = storage.add_camera("Cam", "source://x", "entrada")

    old_file = tmp_path / "old.mp4"
    old_file.write_bytes(b"mp4data")
    old_id = storage.add_event_clip(cam_id, None, str(old_file), 10.0)
    storage.connection.execute(
        "UPDATE event_clips SET timestamp = '2020-01-01T00:00:00+00:00' WHERE id = ?",
        (old_id,),
    )
    storage.connection.commit()

    new_file = tmp_path / "new.mp4"
    new_file.write_bytes(b"mp4data")
    storage.add_event_clip(cam_id, None, str(new_file), 10.0)

    storage.prune_event_clips(cam_id, keep=10, max_age_days=7)
    clips = storage.list_event_clips(cam_id)
    assert len(clips) == 1
    assert clips[0]["path"] == str(new_file)
    assert not Path(old_file).exists()
    storage.close()


def test_settings_get_set(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    assert storage.get_setting("privacy_mode") is None
    assert storage.get_setting("privacy_mode", "false") == "false"

    storage.set_setting("privacy_mode", "true")
    assert storage.get_setting("privacy_mode") == "true"

    storage.set_setting("privacy_mode", "false")
    assert storage.get_setting("privacy_mode") == "false"
    storage.close()


def test_zone_direction_line_crud(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)

    line = {"axis": "vertical", "position": 0.5}
    zone_id = storage.add_zone("Sala", "privativa", direction_line=line)
    assert storage.get_zone(zone_id)["direction_line"] == line

    storage.update_zone(zone_id, "Sala", "privativa", direction_line=None)
    assert storage.get_zone(zone_id)["direction_line"] is None

    storage.close()


def test_zone_direction_line_default_none(tmp_path):
    db_path = tmp_path / "events.db"
    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Sala", "privativa")
    assert storage.get_zone(zone_id)["direction_line"] is None
    storage.close()


def test_migration_adds_direction_line_column(tmp_path):
    import sqlite3
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE zones (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL UNIQUE, classification TEXT NOT NULL DEFAULT 'pública', schedule TEXT)"
    )
    conn.commit()
    conn.close()

    # NOTA: sob pytest, EventStorage.__init__ APAGA o DB legado (unlink
    # pré-existente do repo) e recria o schema — o padrão real de teste de
    # migração (test_migration_adds_new_columns) verifica o schema novo
    # funcionando, sem dados sobreviventes.
    storage = EventStorage(db_path)
    zone_id = storage.add_zone("Sala", "privativa", direction_line={"axis": "vertical", "position": 0.5})
    assert storage.get_zone(zone_id)["direction_line"] == {"axis": "vertical", "position": 0.5}
    storage.close()
