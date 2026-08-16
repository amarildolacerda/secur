"""Helpers de geometria para zonas de exclusão e mascaramento."""


def point_in_polygon(x, y, polygon):
    """Ray casting: True se o ponto (x, y) está dentro do polígono.

    polygon é uma lista de {"x": int, "y": int}. Pontos na borda contam como dentro.
    """
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]["x"], polygon[i]["y"]
        xj, yj = polygon[j]["x"], polygon[j]["y"]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def bbox_center_in_polygons(bbox, polygons):
    """True se o centro da bbox ({"x","y","w","h"}) está dentro de qualquer polígono."""
    cx = bbox["x"] + bbox["w"] / 2
    cy = bbox["y"] + bbox["h"] / 2
    return any(point_in_polygon(cx, cy, poly) for poly in polygons)