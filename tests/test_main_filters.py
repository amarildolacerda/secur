import time
from datetime import datetime

from secur.config import ALERT_COOLDOWN_SECONDS
from secur.main import filter_detections_by_classes, get_cooldown_for_event, is_within_schedule


def _epoch_at(hour, minute):
    now = datetime.now()
    return time.mktime(now.replace(hour=hour, minute=minute, second=0, microsecond=0).timetuple())


def test_filter_detections_by_classes_none_keeps_all():
    dets = [{"label": "person"}, {"label": "car"}]
    assert filter_detections_by_classes(dets, None) == dets
    assert filter_detections_by_classes(dets, []) == dets


def test_filter_detections_by_classes_filters():
    dets = [{"label": "person"}, {"label": "car"}, {"label": "bird"}]
    assert filter_detections_by_classes(dets, ["person", "car"]) == [
        {"label": "person"},
        {"label": "car"},
    ]


def test_filter_detections_by_classes_no_match():
    dets = [{"label": "bird"}]
    assert filter_detections_by_classes(dets, ["person"]) == []


def test_is_within_schedule_no_schedule():
    assert is_within_schedule(None) is True
    assert is_within_schedule({}) is True


def test_is_within_schedule_day_window():
    schedule = {"start": "08:00", "end": "18:00"}
    assert is_within_schedule(schedule, _epoch_at(10, 0)) is True
    assert is_within_schedule(schedule, _epoch_at(7, 59)) is False
    assert is_within_schedule(schedule, _epoch_at(18, 1)) is False


def test_is_within_schedule_overnight_window():
    schedule = {"start": "22:00", "end": "06:00"}
    assert is_within_schedule(schedule, _epoch_at(23, 30)) is True
    assert is_within_schedule(schedule, _epoch_at(3, 0)) is True
    assert is_within_schedule(schedule, _epoch_at(12, 0)) is False


def test_get_cooldown_for_event_fallback():
    assert get_cooldown_for_event("motion_detected") == ALERT_COOLDOWN_SECONDS


def test_get_cooldown_for_event_specific():
    from secur.config import ALERT_COOLDOWN_BY_EVENT
    assert get_cooldown_for_event("intruder_detected") == ALERT_COOLDOWN_BY_EVENT["intruder_detected"]


def test_circular_frame_buffer_keeps_newest():
    from secur.main import CircularFrameBuffer
    buf = CircularFrameBuffer(maxlen=3)
    for i in range(5):
        buf.push(i)
    assert buf.frames() == [2, 3, 4]


def test_circular_frame_buffer_empty():
    from secur.main import CircularFrameBuffer
    buf = CircularFrameBuffer(maxlen=3)
    assert buf.frames() == []

def test_resolve_retention_default_when_no_policy():
    from secur.main import resolve_retention
    assert resolve_retention(None, "thumbnails", 30) == (30, None)
    assert resolve_retention({}, "thumbnails", 30) == (30, None)


def test_resolve_retention_policy_values():
    from secur.main import resolve_retention
    policy = {"thumbnails": 5, "clips": 3, "days": 7}
    assert resolve_retention(policy, "thumbnails", 30) == (5, 7)
    assert resolve_retention(policy, "clips", 20) == (3, 7)


def test_resolve_retention_partial_policy():
    from secur.main import resolve_retention
    policy = {"days": 2}
    assert resolve_retention(policy, "thumbnails", 30) == (30, 2)


def test_resolve_retention_zero_keep_is_respected():
    from secur.main import resolve_retention
    policy = {"thumbnails": 0}
    assert resolve_retention(policy, "thumbnails", 30) == (0, None)


def test_is_privacy_mode_on():
    from secur.config import is_privacy_mode_on
    assert is_privacy_mode_on("true") is True
    assert is_privacy_mode_on("True") is True
    assert is_privacy_mode_on("false") is False
    assert is_privacy_mode_on(None) is False


def test_worker_identity_enabled_respects_privacy_mode():
    from secur.main import CameraWorker

    class FakeStorage:
        def __init__(self):
            self.value = "false"

        def get_setting(self, key, default=None):
            return self.value

    worker = CameraWorker(
        camera={"id": 1, "name": "Cam"},
        storage=FakeStorage(),
        alerts=None,
        object_detector=None,
        identity_recognizer=object(),
    )
    assert worker.identity_enabled() is True

    worker.storage.value = "true"
    worker._privacy_check_time = 0.0  # força recarga do cache
    assert worker.identity_enabled() is False


def test_worker_identity_enabled_without_recognizer():
    from secur.main import CameraWorker

    class FakeStorage:
        def get_setting(self, key, default=None):
            return "false"

    worker = CameraWorker(
        camera={"id": 1, "name": "Cam"},
        storage=FakeStorage(),
        alerts=None,
        object_detector=None,
        identity_recognizer=None,
    )
    assert worker.identity_enabled() is False

from secur.main import decide_worker_event


def test_decide_worker_event_outside_schedule_suppresses_non_identity():
    assert decide_worker_event([{"label": "person"}], None, "pública", "Cam",
                               in_schedule=False) is None


def test_decide_worker_event_unknown_in_restricted_outside_schedule():
    identity_info = {"known": False, "name": "desconhecido"}
    decision = decide_worker_event([{"label": "person"}], identity_info, "privativa", "Cam",
                                   label="person", in_schedule=False)
    assert decision[0] == "intruder_detected"


def test_decide_worker_event_known_outside_schedule():
    identity_info = {"known": True, "name": "Alice"}
    decision = decide_worker_event([{"label": "person"}], identity_info, "privativa", "Cam",
                                   label="person", in_schedule=False)
    assert decision[0] == "identity_recognized"
    assert decision[2] == "Alice"


def test_decide_worker_event_unknown_public_outside_schedule_suppressed():
    identity_info = {"known": False, "name": "desconhecido"}
    assert decide_worker_event([{"label": "person"}], identity_info, "pública", "Cam",
                               label="person", in_schedule=False) is None


def test_decide_worker_event_fall():
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True,
                                   fall=True, now=100.0)
    assert decision[0] == "fall_detected"


def test_decide_worker_event_loitering_before_direction():
    loitering = {"label": "person", "first_seen": 100.0}
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True,
                                   loitering=loitering, direction="entrando", now=130.0)
    assert decision[0] == "loitering"
    assert "30s" in decision[1]


def test_decide_worker_event_direction():
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True,
                                   direction="entrando", now=100.0)
    assert decision[0] == "direction_change"
    assert "entrando" in decision[1]


def test_decide_worker_event_identity_wins_over_fall():
    identity_info = {"known": True, "name": "Alice"}
    decision = decide_worker_event([], identity_info, "privativa", "Cam", label="person",
                                   in_schedule=True, fall=True, now=100.0)
    assert decision[0] == "identity_recognized"


def test_decide_worker_event_snapshot_and_motion_fallbacks():
    decision = decide_worker_event([{"label": "person"}], None, "pública", "Cam", in_schedule=True)
    assert decision[0] == "snapshot_info"

    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True)
    assert decision[0] == "motion_detected"


def test_get_cooldown_for_event_behavior_events():
    from secur.config import ALERT_COOLDOWN_BY_EVENT
    assert get_cooldown_for_event("loitering") == ALERT_COOLDOWN_BY_EVENT["loitering"]
    assert get_cooldown_for_event("direction_change") == ALERT_COOLDOWN_BY_EVENT["direction_change"]
    assert get_cooldown_for_event("fall_detected") == ALERT_COOLDOWN_BY_EVENT["fall_detected"]
