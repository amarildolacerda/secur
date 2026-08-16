import numpy as np
from src.masking import apply_mask_blur, frame_for_storage

POLYGONS = [[{"x": 40, "y": 40}, {"x": 60, "y": 40}, {"x": 60, "y": 60}, {"x": 40, "y": 60}]]


def _frame_with_white_square():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[45:55, 45:55] = 255  # quadrado branco 10x10 no centro
    return frame


def test_apply_mask_blur_masks_polygon_region():
    frame = _frame_with_white_square()
    out = apply_mask_blur(frame, POLYGONS)
    # dentro do polígono o blur espalha o branco com o fundo preto
    assert int(out[50, 50, 0]) < 200
    # fora do polígono permanece intacto
    assert int(out[10, 10, 0]) == 0


def test_apply_mask_blur_keeps_original_intact():
    frame = _frame_with_white_square()
    original = frame.copy()
    apply_mask_blur(frame, POLYGONS)
    assert np.array_equal(frame, original)


def test_apply_mask_blur_no_polygons_returns_copy():
    frame = _frame_with_white_square()
    out = apply_mask_blur(frame, None)
    assert np.array_equal(out, frame)
    assert out is not frame


def test_frame_for_storage_no_polygons_returns_same_frame():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    assert frame_for_storage(frame, None) is frame
    assert frame_for_storage(frame, []) is frame


def test_frame_for_storage_with_polygons_returns_masked():
    frame = _frame_with_white_square()
    out = frame_for_storage(frame, POLYGONS)
    assert not np.array_equal(out, frame)
    assert int(out[50, 50, 0]) < 200
