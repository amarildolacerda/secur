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