import cv2
import numpy as np
from src.camera import CameraStream


def write_test_video(path):
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (100, 100))
    assert writer.isOpened(), "Failed to open VideoWriter"
    for i in range(5):
        frame = np.full((100, 100, 3), i * 40, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_camera_validate_local_video(tmp_path):
    video_path = tmp_path / "test_video.avi"
    write_test_video(video_path)

    assert CameraStream.validate_source(str(video_path)) is True

    stream = CameraStream(str(video_path))
    frame = stream.read()
    assert frame is not None
    stream.release()


def test_camera_validate_invalid_source():
    assert CameraStream.validate_source("invalid://source") is False
