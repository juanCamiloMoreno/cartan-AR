import numpy as np

from light_map.core.common_types import ImagePatch, LayerMode
from light_map.rendering import composition_utils
from light_map.rendering.composition_utils import composite_patch


def blend(patch_data, sparse_fraction):
    rng = np.random.default_rng(1)
    buffer = rng.integers(0, 256, (120, 160, 4), dtype=np.uint8)
    original = composition_utils.SPARSE_FRACTION
    composition_utils.SPARSE_FRACTION = sparse_fraction
    try:
        composite_patch(buffer, ImagePatch(0, 0, 160, 120, patch_data), LayerMode.NORMAL, 160, 120)
    finally:
        composition_utils.SPARSE_FRACTION = original
    return buffer


def test_the_sparse_blend_gives_the_same_pixels_as_the_full_blend():
    rng = np.random.default_rng(2)
    patch = np.zeros((120, 160, 4), np.uint8)
    patch[10:50, 20:90] = rng.integers(0, 256, (40, 70, 4), dtype=np.uint8)
    patch[60:70, 100:150, 3] = 0
    patch[80:100, 5:60] = (30, 60, 200, 128)
    full = blend(patch, 0.0)  # never sparse
    sparse = blend(patch, 1.1)  # always sparse
    assert np.abs(full.astype(int) - sparse.astype(int)).max() <= 1
