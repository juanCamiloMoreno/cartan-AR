from unittest.mock import MagicMock

import numpy as np

from light_map.core.common_types import MapRenderState
from light_map.rendering.layers.map_layer import MapLayer
from light_map.state.world_state import WorldState


def layer_with_loader():
    state = WorldState()
    system = MagicMock()
    system.is_map_loaded.return_value = True
    system.get_render_params.return_value = {"zoom": 1.0}
    system.svg_loader.render.side_effect = lambda *a, **k: np.zeros((8, 8, 3), np.uint8)
    return state, system, MapLayer(state, system, 8, 8)


def test_a_map_file_rewritten_under_the_same_name_is_drawn_again():
    state, system, layer = layer_with_loader()
    state.reload_map_render_state(MapRenderState(filepath="catan.svg"))
    layer._generate_patches(0.0)
    layer._generate_patches(0.1)
    assert system.svg_loader.render.call_count == 1  # nothing changed: the cache is used
    state.reload_map_render_state(MapRenderState(filepath="catan.svg"))  # same state, new file
    layer._generate_patches(0.2)
    assert system.svg_loader.render.call_count == 2
