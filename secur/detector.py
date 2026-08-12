import logging
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


class ObjectDetector:
    def __init__(
        self,
        model_path: str = None,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        classes: List[str] = None,
    ):
        self.model = None
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.classes = classes or []

        if model_path:
            model_file = Path(model_path)
            if model_file.exists():
                try:
                    self.model = cv2.dnn.readNetFromONNX(str(model_file))
                    logger.info("Loaded object detection model from %s", model_path)
                except Exception:
                    logger.exception("Failed to load object detection model from %s", model_path)
                    self.model = None
            else:
                logger.warning("Modelo de detecção não encontrado: %s", model_path)

        if self.model is None:
            logger.info("Nenhum modelo de detecção configurado; operação de movimento será usada sem classificação de objetos")

    def detect(self, frame) -> List[Dict]:
        if self.model is None:
            logger.debug("Skipping object detection because model is not loaded")
            return []

        height, width = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (640, 640), swapRB=True, crop=False)
        self.model.setInput(blob)
        outputs = self.model.forward()

        if isinstance(outputs, tuple):
            outputs = outputs[0]

        detections = []
        boxes = []
        confidences = []
        class_ids = []

        for detection in outputs[0]:
            scores = detection[5:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id] * detection[4])
            if confidence < self.confidence_threshold:
                continue

            cx, cy, w, h = detection[:4]
            x = int((cx - w / 2) * width)
            y = int((cy - h / 2) * height)
            w = int(w * width)
            h = int(h * height)

            boxes.append([x, y, w, h])
            confidences.append(confidence)
            class_ids.append(class_id)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.confidence_threshold, self.iou_threshold)

        if len(indices) > 0:
            for i in indices.flatten():
                class_id = class_ids[i]
                label = self.classes[class_id] if class_id < len(self.classes) else str(class_id)
                x, y, w, h = boxes[i]
                detections.append(
                    {
                        "class_id": class_id,
                        "label": label,
                        "confidence": float(confidences[i]),
                        "bbox": {"x": x, "y": y, "w": w, "h": h},
                    }
                )

        logger.debug("Detected %d objects", len(detections))
        return detections
