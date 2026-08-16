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


def check_direction_crossing(prev_centroid, curr_centroid, line):
    """Direção do cruzamento da linha entre dois frames (None se não cruzou).

    `line`: {"axis": "vertical", "x": px} ou {"axis": "horizontal", "y": px}.
    Convenção: vertical — esquerda→direita = "entrando", direita→esquerda =
    "saindo"; horizontal — cima→baixo = "entrando", baixo→cima = "saindo".
    """
    if prev_centroid is None or curr_centroid is None:
        return None
    if line["axis"] == "vertical":
        x = line["x"]
        if prev_centroid[0] < x <= curr_centroid[0]:
            return "entrando"
        if prev_centroid[0] > x >= curr_centroid[0]:
            return "saindo"
    else:
        y = line["y"]
        if prev_centroid[1] < y <= curr_centroid[1]:
            return "entrando"
        if prev_centroid[1] > y >= curr_centroid[1]:
            return "saindo"
    return None


def check_fall(detection, aspect_ratio):
    """Heurística de queda: pessoa com bbox deitada (w/h >= aspect_ratio).

    Subset viável do spec 3.4: ângulo do torso exigiria modelo de pose
    local (YOLO-pose) com custo de inferência proibitivo no hardware alvo
    — mantido como backlog (ver README).
    """
    if detection.get("label") != "person":
        return False
    bbox = detection.get("bbox") or {}
    h = bbox.get("h", 0)
    w = bbox.get("w", 0)
    if h <= 0:
        return False
    return (w / h) >= aspect_ratio
