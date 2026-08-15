from secur.behavior import check_loitering


def _track(first_seen, label="person", centroid=(10.0, 10.0), first_centroid=(10.0, 10.0)):
    return {
        "id": 1,
        "label": label,
        "centroid": centroid,
        "first_centroid": first_centroid,
        "first_seen": first_seen,
        "last_seen": first_seen + 1,
    }


def test_check_loitering_no_tracks():
    assert check_loitering([], 100.0, 30, 80) is None


def test_check_loitering_not_enough_time():
    tracks = [_track(first_seen=100.0)]
    assert check_loitering(tracks, 120.0, 30, 80) is None


def test_check_loitering_triggers_after_threshold():
    tracks = [_track(first_seen=100.0)]
    track = check_loitering(tracks, 130.0, 30, 80)
    assert track is tracks[0]


def test_check_loitering_ignores_continuous_movement():
    tracks = [_track(first_seen=100.0, centroid=(400.0, 400.0))]
    assert check_loitering(tracks, 130.0, 30, 80) is None


def test_check_loitering_filters_labels():
    tracks = [_track(first_seen=100.0, label="bird")]
    assert check_loitering(tracks, 130.0, 30, 80, labels={"person", "car"}) is None

    tracks = [_track(first_seen=100.0, label="person")]
    assert check_loitering(tracks, 130.0, 30, 80, labels={"person", "car"}) is tracks[0]

from secur.behavior import check_direction_crossing


def test_direction_crossing_vertical_entering():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing((50.0, 60.0), (150.0, 60.0), line) == "entrando"


def test_direction_crossing_vertical_leaving():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing((150.0, 60.0), (50.0, 60.0), line) == "saindo"


def test_direction_crossing_horizontal_entering():
    line = {"axis": "horizontal", "y": 100.0}
    assert check_direction_crossing((50.0, 60.0), (50.0, 150.0), line) == "entrando"


def test_direction_crossing_horizontal_leaving():
    line = {"axis": "horizontal", "y": 100.0}
    assert check_direction_crossing((50.0, 150.0), (50.0, 60.0), line) == "saindo"


def test_direction_crossing_no_cross():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing((50.0, 60.0), (60.0, 60.0), line) is None


def test_direction_crossing_no_prev_centroid():
    line = {"axis": "vertical", "x": 100.0}
    assert check_direction_crossing(None, (150.0, 60.0), line) is None
