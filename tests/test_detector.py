import numpy as np
import pytest
from src.detector import ObjectDetector

CLASSES = [f"c{i}" for i in range(80)]


def _detector():
    return ObjectDetector(classes=CLASSES)


def test_parse_yolov8_scales_from_input_space():
    det = _detector()
    arr = np.zeros((2, 84), dtype=np.float32)
    arr[0, 0:4] = [218.9, 233.1, 59.6, 159.1]  # coords in 640-space
    arr[0, 4 + 0] = 0.9  # person
    arr[1, 0:4] = [10, 10, 5, 5]
    arr[1, 4 + 2] = 0.1  # low confidence -> filtered
    out = det._parse_output(arr, 960, 540)
    assert len(out) == 1
    assert out[0]["label"] == "c0"
    assert 0 < out[0]["bbox"]["x"] < 960
    assert 0 < out[0]["bbox"]["y"] < 540


def test_parse_yolov5_normalized_with_objectness():
    det = _detector()
    arr = np.zeros((1, 85), dtype=np.float32)
    arr[0, 0:4] = [0.3, 0.4, 0.1, 0.2]  # normalized
    arr[0, 4] = 0.9  # objectness
    arr[0, 5 + 0] = 0.8  # person score
    out = det._parse_output(arr, 960, 540)
    assert len(out) == 1
    assert out[0]["label"] == "c0"
    assert out[0]["bbox"]["x"] == int((0.3 - 0.05) * 960)
    assert out[0]["confidence"] == pytest.approx(0.72)


def test_parse_filters_low_confidence():
    det = _detector()
    arr = np.zeros((1, 84), dtype=np.float32)
    arr[0, 4 + 1] = 0.1  # below default 0.25 threshold
    assert det._parse_output(arr, 640, 480) == []
