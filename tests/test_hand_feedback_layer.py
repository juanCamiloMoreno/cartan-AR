import numpy as np
import pytest

import light_map.menu.menu_config as config_vars
from light_map.catan.board import Board, Tile
from light_map.catan.layout import panel_rect
from light_map.catan.manager import CatanManager
from light_map.core.scene import HandInput
from light_map.input.gestures import GestureType
from light_map.rendering.layers.hand_feedback_layer import PATCH_H, PATCH_W, HandFeedbackLayer
from light_map.state.world_state import WorldState


W, H = 1920, 1080


def hand(gesture, pos):
    return HandInput(gesture, pos, (0.0, 0.0), None)


@pytest.fixture
def state():
    return WorldState()


@pytest.fixture
def layer(state):
    return HandFeedbackLayer(state, W, H)


def with_catan(state):
    board = Board({(0, 0): Tile("wood", 6)}, robber=(0, 0))
    CatanManager(board=board).publish(state)


def drawn_pixels(patch):
    return int(np.count_nonzero(patch.data[..., 3]))


def test_nothing_is_drawn_without_hands(layer):
    assert layer._generate_patches(0.0) == []


def test_one_patch_per_hand_centered_on_the_hand(layer, state):
    state.inputs = [
        hand(GestureType.OPEN_PALM, (900, 500)),
        hand(GestureType.CLOSED_FIST, (300, 700)),
    ]
    patches = layer._generate_patches(0.0)
    assert len(patches) == 2
    for patch, (px, py) in zip(patches, [(900, 500), (300, 700)], strict=True):
        assert (patch.width, patch.height) == (PATCH_W, PATCH_H)
        assert patch.x < px < patch.x + PATCH_W
        assert patch.y < py < patch.y + PATCH_H
        assert drawn_pixels(patch) > 0


def test_patches_stay_inside_the_screen_at_the_edges(layer, state):
    state.inputs = [hand(GestureType.POINTING, (5, 5)), hand(GestureType.POINTING, (W - 2, H - 2))]
    for patch in layer._generate_patches(0.0):
        assert patch.x >= 0 and patch.y >= 0
        assert patch.x + patch.width <= W and patch.y + patch.height <= H


def test_every_gesture_has_a_distinct_label_drawing(layer, state):
    seen = set()
    for gesture in GestureType:
        if gesture in (GestureType.NONE,):
            continue
        state.inputs = [hand(gesture, (900, 500))]
        (patch,) = layer._generate_patches(0.0)
        seen.add(patch.data.tobytes())
    assert len(seen) >= 8  # palma, puno, pistola, senalar, paz, rock, shaka and the unknown one


def test_roll_gesture_progress_grows_while_held_and_resets_when_released(layer, state):
    state.inputs = [hand(config_vars.CATAN_ROLL_GESTURE, (900, 500))]
    start = drawn_pixels(layer._generate_patches(10.0)[0])
    half = drawn_pixels(layer._generate_patches(10.0 + config_vars.CATAN_ROLL_HOLD_TIME / 2)[0])
    full = drawn_pixels(layer._generate_patches(10.0 + config_vars.CATAN_ROLL_HOLD_TIME)[0])
    assert start < half < full

    state.inputs = [hand(GestureType.OPEN_PALM, (900, 500))]
    layer._generate_patches(20.0)
    state.inputs = [hand(config_vars.CATAN_ROLL_GESTURE, (900, 500))]
    again = drawn_pixels(layer._generate_patches(20.5)[0])
    assert again == start  # the hold started over


def test_stats_gesture_only_shows_progress_over_a_panel(layer, state):
    with_catan(state)
    x, y, w, h = panel_rect(0, W, H)
    over = (x + w // 2, y + h // 2)

    state.inputs = [hand(config_vars.CATAN_STATS_GESTURE, (900, 500))]  # middle of the table
    away = drawn_pixels(layer._generate_patches(0.0)[0])
    layer._generate_patches(1.0)
    away_later = drawn_pixels(layer._generate_patches(1.0)[0])
    assert away == away_later  # no ring growing

    state.inputs = [hand(config_vars.CATAN_STATS_GESTURE, over)]
    start = drawn_pixels(layer._generate_patches(5.0)[0])
    full = drawn_pixels(layer._generate_patches(5.0 + config_vars.CATAN_STATS_HOLD_TIME)[0])
    assert full > start


def test_version_follows_hands_and_the_game(layer, state):
    state.inputs = [hand(GestureType.OPEN_PALM, (1, 1))]
    assert layer.get_current_version() == max(state.hands_version, state.catan_version)
