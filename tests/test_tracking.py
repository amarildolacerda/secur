from src.tracking import bbox_iou, bbox_centroid, IoUTracker


def test_bbox_iou_identical():
    bbox = {"x": 10, "y": 10, "w": 50, "h": 50}
    assert bbox_iou(bbox, dict(bbox)) == 1.0


def test_bbox_iou_disjoint():
    a = {"x": 0, "y": 0, "w": 10, "h": 10}
    b = {"x": 100, "y": 100, "w": 10, "h": 10}
    assert bbox_iou(a, b) == 0.0


def test_bbox_iou_partial_overlap():
    a = {"x": 0, "y": 0, "w": 10, "h": 10}
    b = {"x": 5, "y": 0, "w": 10, "h": 10}
    expected = 5 * 10 / (10 * 10 + 10 * 10 - 5 * 10)
    assert abs(bbox_iou(a, b) - expected) < 1e-9


def test_bbox_centroid():
    assert bbox_centroid({"x": 10, "y": 20, "w": 30, "h": 40}) == (25.0, 40.0)


def test_tracker_associates_bbox_across_frames():
    tracker = IoUTracker(iou_threshold=0.3)
    d1 = [{"label": "person", "bbox": {"x": 10, "y": 10, "w": 50, "h": 100}}]
    tracks1 = tracker.update(d1, now=1.0)
    assert len(tracks1) == 1
    track_id = tracks1[0]["id"]
    assert tracks1[0]["first_seen"] == 1.0

    d2 = [{"label": "person", "bbox": {"x": 15, "y": 12, "w": 50, "h": 100}}]
    tracks2 = tracker.update(d2, now=2.0)
    assert len(tracks2) == 1
    assert tracks2[0]["id"] == track_id
    assert tracks2[0]["prev_centroid"] == (35.0, 60.0)
    assert tracks2[0]["centroid"] == (40.0, 62.0)
    assert tracks2[0]["first_seen"] == 1.0


def test_tracker_creates_new_track_when_no_match():
    tracker = IoUTracker(iou_threshold=0.3)
    tracker.update([{"label": "person", "bbox": {"x": 0, "y": 0, "w": 50, "h": 100}}], now=1.0)
    tracks = tracker.update(
        [{"label": "car", "bbox": {"x": 300, "y": 0, "w": 50, "h": 100}}], now=2.0
    )
    assert len(tracks) == 2
    assert {t["label"] for t in tracks} == {"person", "car"}


def test_tracker_expires_stale_tracks():
    tracker = IoUTracker(iou_threshold=0.3, max_age_seconds=2.0)
    tracker.update([{"label": "person", "bbox": {"x": 0, "y": 0, "w": 50, "h": 100}}], now=1.0)
    tracks = tracker.update([], now=10.0)
    assert tracks == []
