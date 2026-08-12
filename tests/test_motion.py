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
