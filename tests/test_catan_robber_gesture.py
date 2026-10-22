import json
import math
import random
from unittest.mock import MagicMock

import pytest

import light_map.menu.menu_config as config_vars
from light_map.action_dispatcher import handle_catan_robber, handle_catan_steal
from light_map.catan import game as g
from light_map.catan.board import Board, Building, vertices_of
from light_map.catan.layout import SIZE, cell_at_world, panel_rect, tile_center
from light_map.catan.manager import CatanManager
from light_map.core.app_context import AppContext
from light_map.core.common_types import Action, TimerKey
from light_map.core.scene import HandInput
from light_map.input.gestures import GestureType
from light_map.map.map_scene import ViewingScene
from light_map.rendering.layers.hand_feedback_layer import (
    PATCH_H,
    PATCH_W,
    HandFeedbackLayer,
)
from light_map.state.world_state import WorldState


W, H = 1920, 1080


# Which hexagon is under a point of the board


def test_the_center_of_every_tile_maps_back_to_that_tile():
    for cell in Board.random(random.Random(1)).tiles:
        assert cell_at_world(*tile_center(*cell)) == cell


def test_points_inside_a_tile_map_to_it_and_points_across_the_edge_to_the_neighbor():
    for cell in ((0, 0), (1, -1), (-2, 1)):
        cx, cy = tile_center(*cell)
        for angle in range(0, 360, 30):
            near = (
                cx + 0.7 * SIZE * math.cos(math.radians(angle)),
                cy + 0.7 * SIZE * math.sin(math.radians(angle)),
            )
            assert cell_at_world(*near) == cell, (cell, angle)
    x, y = tile_center(0, 0)
    east = (x + 1.2 * SIZE * math.sqrt(3) / 2 * 2 - 5, y)  # past the shared edge with (1, 0)
    assert cell_at_world(*east) == (1, 0)


def test_a_point_in_the_sea_is_not_on_any_tile():
    tiles = Board.random(random.Random(1)).tiles
    assert cell_at_world(-500, -500) not in tiles
    assert cell_at_world(5000, 400) not in tiles


# Scene


def board_in_phase(phase, victims=()):
    board = Board.random(random.Random(8))
    manager = CatanManager(board=board, rng=random.Random(1))
    state = WorldState()
    manager.new_game(state, 3)
    board.game.phase = phase
    board.game.order = ["rojo", "azul", "blanco"]
    board.game.current = 0
    board.game.victims = list(victims)
    manager.publish(state)
    return manager, state


@pytest.fixture
def context():
    ctx = MagicMock(spec=AppContext)
    ctx.events = MagicMock()
    ctx.events.has_event.return_value = False
    ctx.notifications = MagicMock()
    ctx.app_config = MagicMock()
    ctx.app_config.projector_ppi = 96.0
    ctx.app_config.width = W
    ctx.app_config.height = H
    ctx.show_tokens = True
    ctx.inspected_token_id = None
    ctx.raw_tokens = []
    ctx.visibility_engine = None
    ctx.map_system = MagicMock()
    ctx.map_system.screen_to_world.side_effect = lambda sx, sy: (sx, sy)  # screen = world
    return ctx


def scene_for(context, state):
    context.state = state
    scene = ViewingScene(context)
    scene._find_target_at_point = lambda _pos: None
    return scene


def point(gesture, position):
    return [HandInput(gesture, (int(position[0]), int(position[1])), (0.0, 0.0), None)]


def hold_calls(context):
    return [
        c
        for c in context.events.schedule.call_args_list
        if c.kwargs.get("key") == TimerKey.CATAN_STATS_HOLD
    ]


def other_tile(manager):
    """A tile without the robber, as central as possible (away from the corner panels)."""
    board = manager.board
    cx, cy = tile_center(0, 0)
    free = [c for c in board.tiles if c != board.robber]
    return min(free, key=lambda c: math.dist(tile_center(*c), (cx, cy)))


def test_pointing_at_a_hexagon_while_the_robber_moves_schedules_the_move(context):
    manager, state = board_in_phase(g.ROBBER)
    scene = scene_for(context, state)
    target = other_tile(manager)
    scene.update(point(GestureType.POINTING, tile_center(*target)), [], 0.0)
    (call,) = hold_calls(context)
    delay, callback = call.args
    assert delay == config_vars.CATAN_STATS_HOLD_TIME
    assert callback() == Action.CATAN_STATS_REQUEST

    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    (queued,) = state.pending_actions
    assert queued["action"] == "CATAN_ROBBER"
    assert json.loads(queued["payload"]) == {"tile": list(target)}


def test_the_queued_action_really_moves_the_robber(context):
    manager, state = board_in_phase(g.ROBBER)
    scene = scene_for(context, state)
    target = other_tile(manager)
    scene.update(point(GestureType.POINTING, tile_center(*target)), [], 0.0)
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    app = MagicMock()
    app.catan_manager = manager
    manager.load_for_map = lambda _path: True
    handle_catan_robber(app, state.pending_actions[0], state)
    assert manager.board.robber == target
    assert manager.board.game.phase in (g.STEAL, g.MAIN)


def test_the_tile_that_already_has_the_robber_cannot_be_chosen(context):
    manager, state = board_in_phase(g.ROBBER)
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, tile_center(*manager.board.robber)), [], 0.0)
    assert hold_calls(context) == []


def test_pointing_at_the_sea_or_with_another_gesture_does_nothing(context):
    manager, state = board_in_phase(g.ROBBER)
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, (-400, -400)), [], 0.0)
    scene.update(point(GestureType.OPEN_PALM, tile_center(*other_tile(manager))), [], 0.0)
    scene.update(point(GestureType.CLOSED_FIST, tile_center(*other_tile(manager))), [], 0.0)
    assert hold_calls(context) == []


def test_moving_to_another_hexagon_restarts_the_hold(context):
    manager, state = board_in_phase(g.ROBBER)
    scene = scene_for(context, state)
    tiles = [c for c in manager.board.tiles if c != manager.board.robber]
    scene.update(point(GestureType.POINTING, tile_center(*tiles[0])), [], 0.0)
    context.events.has_event.side_effect = lambda key: key == TimerKey.CATAN_STATS_HOLD
    scene.update(point(GestureType.POINTING, tile_center(*tiles[1])), [], 0.1)
    context.events.cancel.assert_any_call(TimerKey.CATAN_STATS_HOLD)


def test_outside_the_robber_phase_hexagons_are_ignored(context):
    manager, state = board_in_phase(g.MAIN)
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, tile_center(*other_tile(manager))), [], 0.0)
    assert hold_calls(context) == []


def victim_panel_center(manager, player):
    index = list(manager.board.players).index(player)
    x, y, w, h = panel_rect(index, W, H)
    return x + w // 2, y + h // 2


def test_pointing_at_a_victims_panel_steals_from_them(context):
    manager, state = board_in_phase(g.STEAL, victims=["azul"])
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, victim_panel_center(manager, "azul")), [], 0.0)
    assert len(hold_calls(context)) == 1
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    (queued,) = state.pending_actions
    assert queued["action"] == "CATAN_STEAL"
    assert json.loads(queued["payload"]) == {"victim": "azul"}


def test_in_the_steal_phase_only_victims_count_and_panels_do_not_toggle(context):
    manager, state = board_in_phase(g.STEAL, victims=["azul"])
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, victim_panel_center(manager, "blanco")), [], 0.0)
    scene.update(point(GestureType.POINTING, tile_center(*other_tile(manager))), [], 0.0)
    assert hold_calls(context) == []


def test_the_steal_action_takes_a_card(context):
    manager, state = board_in_phase(g.STEAL, victims=["azul"])
    manager.board.add_cards("azul", "wood", 2)
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, victim_panel_center(manager, "azul")), [], 0.0)
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    app = MagicMock()
    app.catan_manager = manager
    manager.load_for_map = lambda _path: True
    handle_catan_steal(app, state.pending_actions[0], state)
    assert manager.board.hands["azul"]["wood"] == 1
    assert manager.board.hands["rojo"]["wood"] == 1


def test_a_panel_still_toggles_its_mode_in_the_other_phases(context):
    manager, state = board_in_phase(g.MAIN)
    scene = scene_for(context, state)
    scene.update(point(GestureType.POINTING, victim_panel_center(manager, "azul")), [], 0.0)
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    (queued,) = state.pending_actions
    assert queued["action"] == "CATAN_STATS_MODE"
    assert json.loads(queued["payload"]) == {"player": "azul", "mode": "toggle"}


# Feedback on the table


def feedback_layer(state):
    map_system = MagicMock()
    map_system.screen_to_world.side_effect = lambda sx, sy: (sx, sy)
    map_system.world_to_screen.side_effect = lambda x, y: (int(x), int(y))
    return HandFeedbackLayer(state, W, H, map_system)


def pointing(state, position):
    state.inputs = [
        HandInput(GestureType.POINTING, (int(position[0]), int(position[1])), (0, 0), None)
    ]


def rings(patches):
    return [p for p in patches if (p.width, p.height) == (PATCH_W, PATCH_H)]


def highlights(patches):
    return [p for p in patches if (p.width, p.height) != (PATCH_W, PATCH_H)]


def test_the_aimed_hexagon_is_lit_up_and_the_ring_fills_while_holding(context):
    manager, state = board_in_phase(g.ROBBER)
    layer = feedback_layer(state)
    target = other_tile(manager)
    center = tile_center(*target)
    pointing(state, center)
    first = layer._generate_patches(10.0)
    (light,) = highlights(first)
    assert light.x <= center[0] <= light.x + light.width
    assert light.y <= center[1] <= light.y + light.height
    assert (light.data[..., 3] > 0).any()
    start = int((rings(first)[0].data[..., 3] > 0).sum())
    full = int(
        (
            rings(layer._generate_patches(10.0 + config_vars.CATAN_STATS_HOLD_TIME))[0].data[..., 3]
            > 0
        ).sum()
    )
    assert full > start


def test_nothing_is_lit_when_the_hand_aims_at_the_sea_or_the_robbers_own_tile(context):
    manager, state = board_in_phase(g.ROBBER)
    layer = feedback_layer(state)
    pointing(state, (-300, -300))
    assert highlights(layer._generate_patches(0.0)) == []
    pointing(state, tile_center(*manager.board.robber))
    assert highlights(layer._generate_patches(0.0)) == []


def test_the_victims_panel_is_outlined_in_the_steal_phase(context):
    manager, state = board_in_phase(g.STEAL, victims=["azul"])
    layer = feedback_layer(state)
    pointing(state, victim_panel_center(manager, "azul"))
    (light,) = highlights(layer._generate_patches(0.0))
    index = list(manager.board.players).index("azul")
    x, y, w, h = panel_rect(index, W, H)
    assert (light.x, light.y, light.width, light.height) == (x, y, w, h)
    pointing(state, victim_panel_center(manager, "blanco"))  # not a victim
    assert highlights(layer._generate_patches(0.0)) == []


def test_without_a_map_the_layer_still_works_outside_the_robber_phase(context):
    manager, state = board_in_phase(g.MAIN)
    layer = HandFeedbackLayer(state, W, H)  # no map system
    pointing(state, tile_center(*other_tile(manager)))
    assert len(layer._generate_patches(0.0)) == 1  # just the ring


def test_building_something_does_not_change_the_aiming(context):
    manager, state = board_in_phase(g.ROBBER)
    manager.board.buildings[vertices_of((0, 0))[0]] = ("rojo", Building.SETTLEMENT)
    manager.publish(state)
    layer = feedback_layer(state)
    pointing(state, tile_center(*other_tile(manager)))
    assert len(highlights(layer._generate_patches(0.0))) == 1
