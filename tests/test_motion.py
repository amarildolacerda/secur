import numpy as np
import cv2
from secur.motion import MotionDetector


def test_motion_detector_no_motion():
    detector = MotionDetector(min_area=100)
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    assert detector.detect(frame) is False


def test_motion_detector_with_motion():
    detector = MotionDetector(min_area=100)
    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    frame2 = frame1.copy()
    cv2.rectangle(frame2, (50, 50), (150, 150), (255, 255, 255), -1)

    detector.detect(frame1)
    assert detector.detect(frame2) is True


def test_motion_detector_exclusion_zone():
    detector = MotionDetector(min_area=100)
    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    frame2 = frame1.copy()
    cv2.rectangle(frame2, (50, 50), (150, 150), (255, 255, 255), -1)

    detector.detect(frame1)
    # Exclui a região inteira onde está o movimento (centroide ~100,100)
    exclusion = [[{"x": 0, "y": 0}, {"x": 200, "y": 0}, {"x": 200, "y": 200}, {"x": 0, "y": 200}]]
    assert detector.detect(frame2, exclusion_polygons=exclusion) is False


def test_motion_detector_exclusion_zone_other_region():
    detector = MotionDetector(min_area=100)
    frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
    frame2 = frame1.copy()
    cv2.rectangle(frame2, (50, 50), (150, 150), (255, 255, 255), -1)

    detector.detect(frame1)
    # Exclui apenas o canto superior esquerdo; movimento no centro permanece
    exclusion = [[{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 50}, {"x": 0, "y": 50}]]
    assert detector.detect(frame2, exclusion_polygons=exclusion) is True
