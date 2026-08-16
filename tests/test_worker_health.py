"""Contrato de saúde do worker: status() deve expor `healthy` derivado de
last_frame_time — uma câmera com fonte morta (RTSP inacessível) não pode
permanecer saudável só porque a thread segue viva (running=True).

RED->GREEN: cobre o helper `_worker_healthy` e o uso em `status()`.
"""

import time

from src.config import WORKER_HEALTHY_TIMEOUT_SECONDS
from src.main import CameraWorker, _worker_healthy


def _make_worker():
    # Thread nunca é iniciada (status() usa only self.camera/last_frame_time).
    return CameraWorker(
        {"id": "cam1", "name": "Cam", "zone": "entrada", "source": "rtsp://dead"},
        storage=None,
        alerts=None,
        object_detector=None,
    )


def test_worker_healthy_contract_status_has_healthy():
    worker = _make_worker()
    status = worker.status()
    assert "healthy" in status
    assert "running" in status  # compatibilidade mantida


def test_worker_healthy_false_when_no_frame_ever():
    # last_frame_time nunca atualizado (fonte nunca entregou frame)
    worker = _make_worker()
    worker.last_frame_time = None
    assert worker.status()["healthy"] is False


def test_worker_healthy_true_when_recent_frame():
    worker = _make_worker()
    worker.last_frame_time = time.time()
    assert worker.status()["healthy"] is True


def test_worker_healthy_false_when_stale_frame():
    worker = _make_worker()
    worker.last_frame_time = time.time() - WORKER_HEALTHY_TIMEOUT_SECONDS - 1
    assert worker.status()["healthy"] is False


def test_worker_healthy_helper_boundary():
    now = 1000.0
    assert _worker_healthy(now, now, 15.0) is True
    assert _worker_healthy(now - 15.0, now, 15.0) is True  # exatamente no limite
    assert _worker_healthy(now - 15.001, now, 15.0) is False
    assert _worker_healthy(None, now, 15.0) is False
