import time
import cv2
from typing import Optional


class CameraStream:
    def __init__(self, source: str):
        self.source = source
        self.capture = cv2.VideoCapture()
        self.failed_reads = 0
        self.connect()

    def connect(self) -> bool:
        if self.capture.isOpened():
            return True

        self.capture.open(self.source)
        return self.capture.isOpened()

    def read(self):
        if not self.capture.isOpened():
            if not self.connect():
                return None

        success, frame = self.capture.read()
        if success and frame is not None:
            self.failed_reads = 0
            return frame

        self.failed_reads += 1
        if self.failed_reads >= 5:
            self.reconnect()
        return None

    def reconnect(self):
        try:
            self.capture.release()
        except Exception:
            pass

        self.capture = cv2.VideoCapture()
        time.sleep(0.5)
        self.capture.open(self.source)
        self.failed_reads = 0

    def release(self):
        try:
            self.capture.release()
        except Exception:
            pass

    def __del__(self):
        self.release()

    @staticmethod
    def validate_source(source: str, timeout_seconds: float = 15.0) -> bool:
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            return False

        # HLS/HTTP streams need more time to buffer
        if source.startswith("http") or source.endswith(".m3u8"):
            capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)

        deadline = time.time() + timeout_seconds
        valid = False
        while time.time() < deadline:
            success, frame = capture.read()
            if success and frame is not None:
                valid = True
                break
            time.sleep(0.2)

        capture.release()
        return valid
