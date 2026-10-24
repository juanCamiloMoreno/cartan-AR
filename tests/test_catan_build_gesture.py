import json
import math
import random
from unittest.mock import MagicMock

import pytest

import light_map.menu.menu_config as config_vars
from light_map.action_dispatcher import handle_catan_build, handle_catan_road
from light_map.catan import aim as aim_module
from light_map.catan.aim import (
    BuildAim,
    allowed_kinds,
    nearest_spot,
    spot_position,
    what_it_builds,
)
from light_map.catan.board import Board, Building, edge_vertices, edges_of
from light_map.catan.layout import SIZE, panel_rect, tile_center
from light_map.catan.manager import CatanManager
from light_map.core.app_context import AppContext
from light_map.core.common_types import Action, TimerKey
from light_map.core.scene import HandInput
from light_map.input.gestures import GestureType
from light_map.map.map_scene import ViewingScene
from light_map.state.world_state import WorldState


W, H = 1920, 1080


def started(phase="setup"):
    board = Board.random(random.Random(8))
    manager = CatanManager(board=board, rng=random.Random(1))
    state = WorldState()
    manager.new_game(state, 3)
    board.game.phase = phase
    board.game.order = ["rojo", "azul", "blanco"]
    board.game.current = 0
    manager.publish(state)
    return manager, state


def hand(gesture, position):
    return [HandInput(gesture, (int(position[0]), int(position[1])), (0.0, 0.0), None)]


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


def a_vertex(board):
    inner = [v for v in board.all_vertices() if all(c in board.tiles for c in v)]
    center = tile_center(0, 0)  # away from the corner panels, as the screen equals the world here
    return min(inner, key=lambda v: (math.dist(spot_position(("vertex", v)), center), sorted(v)))


def app_for(manager):
    app = MagicMock()
    app.catan_manager = manager
    manager.load_for_map = lambda _path: True
    return app


# What can be aimed at


def test_the_game_phase_decides_what_can_be_aimed():
    assert allowed_kinds({"phase": "setup", "setup_step": "settlement"}) == ("vertex",)
    assert allowed_kinds({"phase": "setup", "setup_step": "road"}) == ("edge",)
    assert allowed_kinds({"phase": "main"}) == ("vertex", "edge")
    assert allowed_kinds({"phase": "road_building"}) == ("edge",)
    for phase in ("roll", "robber", "discard", "steal", "finished", "order", None):
        assert allowed_kinds({"phase": phase}) == ()
    assert allowed_kinds(None) == ()


def test_the_nearest_corner_or_side_to_the_finger_is_chosen():
    board = Board.random(random.Random(8))
    vertex = a_vertex(board)
    x, y = spot_position(("vertex", vertex))
    assert nearest_spot((x + 5, y - 4), board.tiles, ("vertex", "edge")) == ("vertex", vertex)
    edge = next(e for cell in board.tiles for e in edges_of(cell))
    ex, ey = spot_position(("edge", edge))
    assert nearest_spot((ex, ey), board.tiles, ("vertex", "edge")) == ("edge", edge)
    assert nearest_spot((ex, ey), board.tiles, ("vertex",))[0] == "vertex"


def test_a_finger_far_from_everything_aims_at_nothing():
    board = Board.random(random.Random(8))
    assert nearest_spot((-900, -900), board.tiles, ("vertex", "edge")) is None
    x, y = spot_position(("vertex", a_vertex(board)))
    assert nearest_spot((x + SIZE * 30, y), board.tiles, ("vertex",)) is None


def test_what_peace_would_build_depends_on_the_spot():
    manager, state = started("main")
    vertex = a_vertex(manager.board)
    assert what_it_builds(("vertex", vertex), state.catan) == "casa"
    assert what_it_builds(("edge", next(iter(edges_of((0, 0))))), state.catan) == "camino"
    manager.board.buildings[vertex] = ("rojo", Building.SETTLEMENT)
    manager.publish(state)
    assert what_it_builds(("vertex", vertex), state.catan) == "ciudad"
    manager.board.buildings[vertex] = ("azul", Building.SETTLEMENT)
    manager.publish(state)
    assert what_it_builds(("vertex", vertex), state.catan) == "casa"


# The aim itself


def aim_update(aim, hands, state, now):
    return aim.update(hands, state.catan, lambda x, y: (x, y), (W, H), now)


def test_only_a_pointing_finger_aims_and_the_aim_fades():
    manager, state = started()
    aim = BuildAim()
    vertex = a_vertex(manager.board)
    pos = spot_position(("vertex", vertex))
    assert aim_update(aim, hand(GestureType.OPEN_PALM, pos), state, 0.0) is None
    assert aim_update(aim, hand(GestureType.POINTING, pos), state, 1.0) == ("vertex", vertex)
    assert aim_update(aim, [], state, 3.0) == ("vertex", vertex)  # still there while showing peace
    assert aim_update(aim, [], state, 1.0 + aim_module.AIM_MEMORY + 0.1) is None


def test_pointing_at_a_player_panel_does_not_aim():
    manager, state = started()
    aim = BuildAim()
    x, y, w, h = panel_rect(0, W, H)
    assert aim_update(aim, hand(GestureType.POINTING, (x + w // 2, y + h // 2)), state, 0.0) is None


def test_nothing_is_aimed_outside_the_building_phases():
    manager, state = started("main")
    manager.board.game.phase = "roll"
    manager.publish(state)
    aim = BuildAim()
    pos = spot_position(("vertex", a_vertex(manager.board)))
    assert aim_update(aim, hand(GestureType.POINTING, pos), state, 0.0) is None


# Scene


def build_hold_calls(context):
    return [
        c
        for c in context.events.schedule.call_args_list
        if c.kwargs.get("key") == TimerKey.CATAN_BUILD_HOLD
    ]


def test_peace_over_an_aimed_corner_schedules_a_build_and_queues_it(context):
    manager, state = started()
    scene = scene_for(context, state)
    pos = spot_position(("vertex", a_vertex(manager.board)))
    scene.update(hand(GestureType.POINTING, pos), [], 0.0)
    assert build_hold_calls(context) == []
    scene.update(hand(GestureType.VICTORY, pos), [], 0.5)
    (call,) = build_hold_calls(context)
    delay, callback = call.args
    assert delay == config_vars.CATAN_BUILD_HOLD_TIME
    assert callback() == Action.CATAN_BUILD_REQUEST

    scene.update([], [Action.CATAN_BUILD_REQUEST], 1.5)
    (queued,) = state.pending_actions
    assert queued["action"] == "CATAN_BUILD"
    assert json.loads(queued["payload"])["player"] == state.catan.game["current_player"]


def test_peace_without_an_aim_does_nothing(context):
    manager, state = started()
    scene = scene_for(context, state)
    pos = spot_position(("vertex", a_vertex(manager.board)))
    scene.update(hand(GestureType.VICTORY, pos), [], 0.0)
    assert build_hold_calls(context) == []


def test_the_queued_actions_really_build_in_the_setup(context):
    manager, state = started()
    app = app_for(manager)
    scene = scene_for(context, state)
    vertex = a_vertex(manager.board)
    scene.update(hand(GestureType.POINTING, spot_position(("vertex", vertex))), [], 0.0)
    scene.update([], [Action.CATAN_BUILD_REQUEST], 0.5)
    handle_catan_build(app, state.pending_actions.pop(), state)
    assert manager.board.buildings[vertex][0] == state.catan.game["current_player"]
    assert state.catan.game["setup_step"] == "road"

    edge = next(e for e in manager.board.all_edges() if vertex in edge_vertices(e))
    scene.update(hand(GestureType.POINTING, spot_position(("edge", edge))), [], 5.0)
    scene.update([], [Action.CATAN_BUILD_REQUEST], 5.5)
    handle_catan_road(app, state.pending_actions.pop(), state)
    assert edge in manager.board.roads


def test_a_refused_build_changes_nothing(context):
    manager, state = started("main")
    scene = scene_for(context, state)
    vertex = a_vertex(manager.board)
    scene.update(hand(GestureType.POINTING, spot_position(("vertex", vertex))), [], 0.0)
    scene.update([], [Action.CATAN_BUILD_REQUEST], 0.5)
    handle_catan_build(app_for(manager), state.pending_actions.pop(), state)  # no cards
    assert vertex not in manager.board.buildings


# Feedback layer


def test_the_layer_marks_the_aim_and_shows_the_build_progress():
    from unittest.mock import MagicMock as Mock

    from light_map.rendering.layers.hand_feedback_layer import PATCH_H, PATCH_W, HandFeedbackLayer

    manager, state = started()
    map_system = Mock()
    map_system.screen_to_world.side_effect = lambda x, y: (x, y)
    map_system.world_to_screen.side_effect = lambda x, y: (x, y)
    layer = HandFeedbackLayer(state, W, H, map_system)
    pos = spot_position(("vertex", a_vertex(manager.board)))

    state.inputs = hand(GestureType.POINTING, pos)
    patches = layer._generate_patches(0.0)
    assert len(patches) == 2  # the marker on the corner plus the ring on the hand
    assert any((p.width, p.height) != (PATCH_W, PATCH_H) for p in patches)

    state.inputs = hand(GestureType.VICTORY, pos)
    layer._generate_patches(0.5)
    hold = layer._hold_for(0, state.inputs[0], 0.9)
    assert hold[0] == "construir"
    assert hold[1] == config_vars.CATAN_BUILD_HOLD_TIME


def test_a_still_hand_keeps_asking_for_redraws_so_the_ring_keeps_filling():
    import time

    from light_map.rendering.layers.hand_feedback_layer import HandFeedbackLayer

    manager, state = started()
    layer = HandFeedbackLayer(state, W, H, MagicMock())
    state.inputs = hand(GestureType.OPEN_PALM, (900, 500))
    first = layer.get_current_version()
    time.sleep(0.08)
    assert layer.get_current_version() > first  # same hand, same place: still a new frame
    state.inputs = []
    quiet = layer.get_current_version()
    time.sleep(0.08)
    assert layer.get_current_version() == quiet  # no hand: nothing to redraw
