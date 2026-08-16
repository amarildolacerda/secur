import cv2

from .geometry import point_in_polygon


class MotionDetector:
    def __init__(self, min_area: int = 5000):
        self.min_area = min_area
        self.previous_frame = None

    def detect(self, frame, exclusion_polygons=None):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.previous_frame is None:
            self.previous_frame = gray
            return False

        delta = cv2.absdiff(self.previous_frame, gray)
        self.previous_frame = gray

        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            if cv2.contourArea(contour) < self.min_area:
                continue
            if exclusion_polygons:
                moments = cv2.moments(contour)
                if moments["m00"] != 0:
                    cx = moments["m10"] / moments["m00"]
                    cy = moments["m01"] / moments["m00"]
                    if any(point_in_polygon(cx, cy, poly) for poly in exclusion_polygons):
                        continue
            return True

        return False