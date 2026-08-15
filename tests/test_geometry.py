from secur.geometry import point_in_polygon, bbox_center_in_polygons

SQUARE = [
    {"x": 0, "y": 0},
    {"x": 100, "y": 0},
    {"x": 100, "y": 100},
    {"x": 0, "y": 100},
]


def test_point_inside():
    assert point_in_polygon(50, 50, SQUARE) is True


def test_point_outside():
    assert point_in_polygon(150, 50, SQUARE) is False


def test_point_on_edge():
    assert point_in_polygon(0, 50, SQUARE) is True


def test_point_degenerate_polygon():
    assert point_in_polygon(50, 50, [{"x": 0, "y": 0}]) is False


def test_bbox_center_inside():
    bbox = {"x": 40, "y": 40, "w": 20, "h": 20}  # centro (50, 50)
    assert bbox_center_in_polygons(bbox, [SQUARE]) is True


def test_bbox_center_outside():
    bbox = {"x": 140, "y": 40, "w": 20, "h": 20}  # centro (150, 50)
    assert bbox_center_in_polygons(bbox, [SQUARE]) is False


def test_bbox_no_polygons():
    bbox = {"x": 40, "y": 40, "w": 20, "h": 20}
    assert bbox_center_in_polygons(bbox, []) is False