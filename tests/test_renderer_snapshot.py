from types import SimpleNamespace

import numpy as np

from light_map.core.common_types import ImagePatch, Layer, LayerMode
from light_map.rendering.composition_utils import composite_patch
from light_map.rendering.renderer import Renderer


W, H = 64, 48


class Scripted(Layer):
    """A layer whose picture (a rectangle of one color) and version the test controls."""

    def __init__(self, rect, color, alpha=255, mode=LayerMode.NORMAL):
        super().__init__(state=None, is_static=False, layer_mode=mode)
        self.rect, self.color, self.alpha, self.version = rect, color, alpha, 1

    def set(self, color=None, alpha=None, rect=None):
        self.color = color or self.color
        self.alpha = self.alpha if alpha is None else alpha
        self.rect = rect or self.rect
        self.version += 1

    def get_current_version(self) -> int:
        return self.version

    def _generate_patches(self, current_time):
        x, y, w, h = self.rect
        data = np.zeros((h, w, 4), np.uint8)
        data[..., :3] = self.color
        data[..., 3] = self.alpha
        return [ImagePatch(x, y, w, h, data)]


def naive(layers):
    buffer = np.zeros((H, W, 3), np.uint8)
    for layer in layers:
        patches, _ = layer.render(0.0)
        for patch in patches:
            composite_patch(buffer, patch, layer.layer_mode, W, H)
    return buffer


def test_the_remembered_picture_gives_the_same_frames_as_blending_everything():
    renderer = Renderer(SimpleNamespace(width=W, height=H))
    bottom = Scripted((0, 0, W, H), (30, 60, 90))
    middle = Scripted((5, 5, 40, 30), (200, 20, 20), alpha=140)
    busy = Scripted((10, 10, 8, 8), (0, 255, 0))
    top = Scripted((0, 40, 64, 8), (255, 255, 255), alpha=90)
    layers = [bottom, middle, busy, top]
    for frame in range(40):
        busy.set(rect=(10 + frame, 10, 8, 8))  # moves every frame: it becomes a busy layer
        if frame == 20:
            middle.set(color=(20, 20, 200))  # a quiet layer below the busy one changes
        if frame == 30:
            top.set(alpha=200)
        got = renderer.render(None, layers, 0.0)
        assert got is not None
        expected = naive(layers)
        assert np.abs(got.astype(int) - expected.astype(int)).max() <= 2, frame
    assert renderer._snapshot is not None  # the quiet bottom layers were remembered


def test_nothing_is_blended_again_when_no_layer_changed():
    renderer = Renderer(SimpleNamespace(width=W, height=H))
    layers = [Scripted((0, 0, W, H), (1, 2, 3))]
    assert renderer.render(None, layers, 0.0) is not None
    assert renderer.render(None, layers, 0.0) is None
