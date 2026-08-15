"""Regras puras de comportamento/anomalia (Fase 3).

Recebem tracks/detections e produzem decisões — sem cv2, sem I/O,
sem acesso a config/storage (config entra como parâmetro). O
CameraWorker faz o wiring.
"""

from typing import Dict, List, Optional


def check_loitering(tracks, now, loiter_seconds, max_distance, labels=None):
    """Primeira track que permaneceu na mesma região por >= loiter_seconds.

    `max_distance`: deslocamento máximo (px) do centroide desde o primeiro
    frame para ainda ser considerada "na mesma região".
    `labels`: conjunto de labels considerados (None = todos).
    Retorna a track (dict) ou None.
    """
    if not tracks:
        return None
    for track in tracks:
        if labels is not None and track["label"] not in labels:
            continue
        age = now - track["first_seen"]
        if age < loiter_seconds:
            continue
        dx = track["centroid"][0] - track["first_centroid"][0]
        dy = track["centroid"][1] - track["first_centroid"][1]
        if (dx * dx + dy * dy) ** 0.5 <= max_distance:
            return track
    return None
