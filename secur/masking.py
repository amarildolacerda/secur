"""Mascaramento de regiões para privacidade (Fase 4.1).

A máscara é aplicada APENAS nos frames que serão persistidos ou exibidos
(thumbnail, clipe, snapshot). O frame de detecção SEMPRE usa o original.
"""

import cv2
import numpy as np


def apply_mask_blur(frame, polygons):
    """Retorna cópia do frame com blur gaussiano nas regiões dos polígonos.

    polygons é uma lista de polígonos; cada polígono é uma lista de
    {"x": int, "y": int} (mesmo formato de exclusion_zones/mask_polygons).
    O frame original nunca é modificado.
    """
    if not polygons:
        return frame.copy()
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for poly in polygons:
        pts = np.array([[p["x"], p["y"]] for p in poly], dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    blurred = cv2.GaussianBlur(frame, (0, 0), 15)
    out = frame.copy()
    out[mask > 0] = blurred[mask > 0]
    return out


def frame_for_storage(frame, mask_polygons):
    """Frame pronto para persistência/exibição: mascarado se configurado.

    Sem polígonos retorna o MESMO frame (sem cópia) para não alocar memória
    no hot path do worker.
    """
    if mask_polygons:
        return apply_mask_blur(frame, mask_polygons)
    return frame
