import logging
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

# Tamanho de entrada usado pelo blob e pela escala das bounding boxes.
INPUT_SIZE = 640


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
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (INPUT_SIZE, INPUT_SIZE), swapRB=True, crop=False)
        self.model.setInput(blob)
        outputs = self.model.forward()

        if isinstance(outputs, tuple):
            outputs = outputs[0]

        arr = np.squeeze(outputs)
        # YOLOv8 exporta (84, 8400): features na primeira dimensão -> transpõe para (N, feat).
        # YOLOv5 exporta (N, 85): features na última dimensão -> mantém.
        if arr.ndim == 2 and arr.shape[1] > arr.shape[0]:
            arr = arr.T
        if arr.ndim != 2:
            return []

        return self._parse_output(arr, width, height)

    def _parse_output(self, arr, width, height):
        detections = []
        boxes = []
        confidences = []
        class_ids = []

        feat = arr.shape[1]
        scale_x = width / INPUT_SIZE
        scale_y = height / INPUT_SIZE

        for d in arr:
            if feat == 84:
                # YOLOv8: [cx, cy, w, h, score_0..score_79] (sem objectness; coords em pixels do input)
                scores = d[4:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])
                if confidence < self.confidence_threshold:
                    continue
                cx, cy, w, h = d[0], d[1], d[2], d[3]
                x = int((cx - w / 2) * scale_x)
                y = int((cy - h / 2) * scale_y)
                w = int(w * scale_x)
                h = int(h * scale_y)
            else:
                # YOLOv5: [cx, cy, w, h, objectness, score_0..score_79] (coords normalizadas)
                scores = d[5:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id] * d[4])
                if confidence < self.confidence_threshold:
                    continue
                cx, cy, w, h = d[0], d[1], d[2], d[3]
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
