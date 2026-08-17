"""Focused tests for the worker's latest-frame accessors and the
Telegram thumbnail fallback path (_latest_thumbnail_path)."""

import importlib

import numpy as np

main_mod = importlib.import_module("src.main")
from src.main import CameraWorker, CameraManager


def _frame(fill=100):
    return np.full((480, 640, 3), fill, np.uint8)


def _make_worker(storage=None):
    return CameraWorker(
        {"id": "cam1", "name": "Cam", "zone": "entrada", "source": "rtsp://x"},
        storage=storage,
        alerts=None,
        object_detector=None,
    )


class _FakeStorage:
    def __init__(self):
        self.added = []

    def add_camera_thumbnail(self, camera_id, path, event_type, event_id=None):
        self.added.append((camera_id, path, event_type))

    def prune_camera_thumbnails(self, camera_id, keep=None, max_age_days=None):
        pass


# ---------- CameraWorker.get_latest_frame ----------

def test_worker_get_latest_frame_initial_none():
    worker = _make_worker()
    assert worker.get_latest_frame() == (None, None)


def test_worker_get_latest_frame_returns_stored_frame():
    worker = _make_worker()
    worker._latest_frame = _frame()
    worker._latest_frame_time = 1234.5
    frame, ts = worker.get_latest_frame()
    assert frame is not None and ts == 1234.5


# ---------- CameraManager.get_latest_frame ----------

def test_manager_get_latest_frame_unknown_camera_returns_none():
    manager = CameraManager(storage=None, alerts=None, object_detector=None)
    assert manager.get_latest_frame("missing") == (None, None)


def test_manager_get_latest_frame_delegates_to_worker():
    manager = CameraManager(storage=None, alerts=None, object_detector=None)
    worker = _make_worker()
    worker._latest_frame = _frame()
    worker._latest_frame_time = 99.0
    manager.workers["cam1"] = worker
    frame, ts = manager.get_latest_frame("cam1")
    assert frame is not None and ts == 99.0


# ---------- _latest_thumbnail_path (Telegram fallback) ----------

def test_latest_thumbnail_path_initial_none():
    worker = _make_worker()
    assert worker._latest_thumbnail_path() is None


def test_latest_thumbnail_path_tracks_last_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "THUMBNAILS_DIR", tmp_path)
    worker = _make_worker(storage=_FakeStorage())
    path = worker._capture_thumbnail(_frame(), "motion_detected", 1000.0)
    assert path is not None
    assert worker._latest_thumbnail_path() == path