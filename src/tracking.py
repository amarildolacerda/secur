"""Tracking de objetos por IoU entre frames consecutivos (por câmera).

Módulo puro (sem cv2): mantém tracks de detecções entre frames para
alimentar as regras de comportamento (loitering, direção de movimento).
"""

from typing import Dict, List, Optional


def bbox_iou(a: Dict, b: Dict) -> float:
    """IoU entre dois bboxes {"x", "y", "w", "h"} (int ou float)."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter == 0.0:
        return 0.0

    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def bbox_centroid(bbox: Dict) -> tuple:
    """Centroide (cx, cy) do bbox {"x", "y", "w", "h"}."""
    return (bbox["x"] + bbox["w"] / 2.0, bbox["y"] + bbox["h"] / 2.0)


class IoUTracker:
    """Associa detecções entre frames por IoU, mantendo tracks por câmera.

    Track: {"id", "label", "bbox", "centroid", "prev_centroid",
            "first_centroid", "first_seen", "last_seen"}.
    Tracks não vistas por `max_age_seconds` são descartadas no próximo
    `update()`.
    """

    def __init__(self, iou_threshold: float = 0.3, max_age_seconds: float = 2.0):
        self.iou_threshold = iou_threshold
        self.max_age_seconds = max_age_seconds
        self._next_id = 0
        self.tracks: Dict[int, Dict] = {}

    def update(self, detections: List[Dict], now: float) -> List[Dict]:
        """Associa `detections` às tracks (greedy, maior IoU acima do limiar).

        Detecções sem match criam tracks novas; tracks com match atualizam
        bbox/centroid (prev_centroid guarda o valor do frame anterior).
        Retorna as tracks ativas (não expiradas).
        """
        used: set = set()
        for det in detections:
            best_id = None
            best_iou = self.iou_threshold
            for track_id, track in self.tracks.items():
                if track_id in used:
                    continue
                iou = bbox_iou(track["bbox"], det["bbox"])
                if iou > best_iou:
                    best_id, best_iou = track_id, iou
            if best_id is None:
                best_id = self._next_id
                self._next_id += 1
                centroid = bbox_centroid(det["bbox"])
                self.tracks[best_id] = {
                    "id": best_id,
                    "label": det["label"],
                    "bbox": det["bbox"],
                    "centroid": centroid,
                    "prev_centroid": None,
                    "first_centroid": centroid,
                    "first_seen": now,
                    "last_seen": now,
                }
            else:
                track = self.tracks[best_id]
                track["prev_centroid"] = track["centroid"]
                track["bbox"] = det["bbox"]
                track["centroid"] = bbox_centroid(det["bbox"])
                track["label"] = det["label"]
                track["last_seen"] = now
            used.add(best_id)

        for track_id in list(self.tracks.keys()):
            if track_id not in used and now - self.tracks[track_id]["last_seen"] > self.max_age_seconds:
                del self.tracks[track_id]

        return list(self.tracks.values())
