import json
from collections import Counter
from unittest.mock import MagicMock

import numpy as np
import pytest

import light_map.menu.menu_config as config_vars
from light_map.action_dispatcher import (
    handle_catan_cards,
    handle_catan_players,
    handle_catan_road,
    handle_catan_stats_mode,
)
from light_map.catan.board import (
    Board,
    Building,
    Tile,
    edge_from_list,
    edge_to_list,
    edges_of,
    vertices_of,
)
from light_map.catan.layout import PANEL_H, PANEL_W, edge_endpoints, panel_at, panel_rect
from light_map.catan.manager import CatanManager
from light_map.core.app_context import AppContext
from light_map.core.common_types import Action, TimerKey
from light_map.core.scene import HandInput
from light_map.map.map_scene import ViewingScene
from light_map.rendering.layers.catan_layer import CatanLayer
from light_map.state.world_state import WorldState


EDGE = edge_to_list(edges_of((0, 0))[0])


def small_board() -> Board:
    return Board(
        {(0, 0): Tile("wood", 6), (1, 0): Tile("brick", 8), (-1, 0): Tile("desert", None)},
        robber=(-1, 0),
    )


# Model


def test_edge_round_trip_and_validation():
    edge = edges_of((0, 0))[2]
    assert edge_from_list(edge_to_list(edge)) == edge
    with pytest.raises(ValueError):
        edge_from_list([[0, 0], [2, 0]])  # not adjacent
    with pytest.raises(ValueError):
        edge_from_list([[0, 0], [0, 0]])


def test_edge_endpoints_are_two_vertices_one_hex_side_apart():
    (x1, y1), (x2, y2) = edge_endpoints(edges_of((0, 0))[0])
    assert ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 == pytest.approx(70, abs=1)


def test_toggle_road_builds_then_removes_and_blocks_other_players():
    board = small_board()
    edge = edges_of((0, 0))[0]
    board.toggle_road(edge, "rojo")
    assert board.roads[edge] == "rojo"
    with pytest.raises(ValueError):
        board.toggle_road(edge, "azul")
    board.toggle_road(edge, "rojo")
    assert edge not in board.roads


def test_road_must_be_on_the_board():
    board = small_board()
    with pytest.raises(ValueError):
        board.toggle_road(frozenset({(5, 5), (6, 5)}), "rojo")


def test_cards_never_go_below_zero_and_reject_unknown_input():
    board = small_board()
    board.add_cards("rojo", "wood", 2)
    board.add_cards("rojo", "wood", -5)
    assert board.hand("rojo")["wood"] == 0
    with pytest.raises(ValueError):
        board.add_cards("rojo", "gold", 1)
    with pytest.raises(ValueError):
        board.add_cards("verde", "wood", 1)


def test_player_stats_count_pieces_cards_and_points():
    board = small_board()
    v1, v2 = vertices_of((0, 0))[:2]
    board.build(v1, "rojo", Building.SETTLEMENT)
    board.build(v2, "rojo", Building.SETTLEMENT)
    board.build(v2, "rojo", Building.CITY)
    board.toggle_road(edges_of((0, 0))[0], "rojo")
    board.add_cards("rojo", "ore", 3)
    board.add_cards("rojo", "wood", 1)
    stats = board.player_stats("rojo")
    assert stats["settlements"] == 1
    assert stats["cities"] == 1
    assert stats["roads"] == 1
    assert stats["cards"] == 4
    assert stats["points"] == 3
    assert stats["hand"]["ore"] == 3
    assert stats["mode"] == "simple"


def test_player_count_limits_and_blocks_removing_a_player_with_pieces():
    board = small_board()
    board.set_player_count(3)
    assert board.players == ["rojo", "azul", "blanco"]
    with pytest.raises(ValueError):
        board.set_player_count(1)
    with pytest.raises(ValueError):
        board.set_player_count(5)
    board.add_cards("blanco", "wood", 1)
    with pytest.raises(ValueError):
        board.set_player_count(2)
    assert board.players == ["rojo", "azul", "blanco"]


def test_stats_mode_per_player_all_and_toggle():
    board = small_board()
    board.set_stats_mode("rojo", "resources")
    assert board.stats_mode("rojo") == "resources"
    assert board.stats_mode("azul") == "simple"
    board.set_stats_mode("rojo", "toggle")
    assert board.stats_mode("rojo") == "simple"
    board.set_stats_mode(None, "resources")
    assert all(board.stats_mode(p) == "resources" for p in board.players)
    with pytest.raises(ValueError):
        board.set_stats_mode("rojo", "fancy")


def test_everything_survives_a_json_round_trip():
    board = small_board()
    board.build(vertices_of((0, 0))[0], "azul", Building.SETTLEMENT)
    board.toggle_road(edges_of((0, 0))[1], "azul")
    board.add_cards("azul", "sheep", 2)
    board.set_player_count(3)
    board.set_stats_mode("azul", "resources")
    loaded = Board.from_dict(json.loads(json.dumps(board.to_dict())))
    assert loaded.roads == board.roads
    assert loaded.players == ["rojo", "azul", "blanco"]
    assert loaded.hands["azul"] == Counter({"sheep": 2})
    assert loaded.stats_mode("azul") == "resources"


def test_old_saved_boards_without_the_new_fields_still_load():
    data = small_board().to_dict()
    for key in ("roads", "players", "hands", "stats_modes"):
        data.pop(key)
    board = Board.from_dict(data)
    assert board.roads == {}
    assert len(board.players) == 4
    assert board.player_stats("rojo")["cards"] == 0


# Manager


def manager_with_board():
    manager = CatanManager(board=small_board())
    return manager, WorldState()


def test_a_roll_pays_the_resources_into_the_hands():
    manager, state = manager_with_board()
    manager.board.build(vertices_of((0, 0))[0], "rojo", Building.SETTLEMENT)
    manager.roll(state, (3, 3))  # the wood tile has a 6
    assert manager.board.hand("rojo")["wood"] == 1
    assert state.catan.stats["rojo"]["cards"] == 1


def test_a_seven_pays_nothing():
    manager, state = manager_with_board()
    manager.board.build(vertices_of((0, 0))[0], "rojo", Building.SETTLEMENT)
    manager.roll(state, (3, 4))
    assert manager.board.hand("rojo")["wood"] == 0


def test_publish_includes_roads_players_and_stats():
    manager, state = manager_with_board()
    manager.toggle_road(state, "rojo", EDGE)
    manager.set_player_count(state, 2)
    data = state.catan.to_dict()
    assert data["players"] == ["rojo", "azul"]
    assert data["roads"] == [{"edge": EDGE, "player": "rojo"}]
    assert data["stats"]["rojo"]["roads"] == 1
    assert len(data["board"]["edges"]) == len(manager.board.all_edges())


# Dispatcher


def make_app():
    app = MagicMock()
    app.catan_manager = CatanManager(board=small_board())
    app.catan_manager.load_for_map = lambda _path: True
    return app, WorldState()


def payload(**kwargs):
    return {"payload": json.dumps(kwargs)}


def test_dispatcher_road_cards_players_and_mode():
    app, state = make_app()
    handle_catan_road(app, payload(player="rojo", edge=EDGE), state)
    handle_catan_cards(app, payload(player="rojo", resource="ore", amount=2), state)
    handle_catan_players(app, payload(count=3), state)
    handle_catan_stats_mode(app, payload(player="all", mode="resources"), state)
    board = app.catan_manager.board
    assert board.roads[edge_from_list(EDGE)] == "rojo"
    assert board.hand("rojo")["ore"] == 2
    assert board.players == ["rojo", "azul", "blanco"]
    assert all(board.stats_mode(p) == "resources" for p in board.players)


def test_dispatcher_reports_errors_on_screen():
    app, state = make_app()
    handle_catan_cards(app, payload(player="rojo", resource="gold", amount=1), state)
    app.notifications.add_notification.assert_called_once()


# Projection


def make_layer(width=1536, height=864):
    manager, state = manager_with_board()
    map_system = MagicMock()
    map_system.world_to_screen.side_effect = lambda x, y: (int(x), int(y))
    manager.publish(state)
    return CatanLayer(state, map_system, width, height), manager, state


def panel_pixels(buffer, index, width=1536, height=864):
    x, y, w, h = panel_rect(index, width, height)
    return buffer[y : y + h, x : x + w]


def draw(layer, state):
    return layer._generate_patches(0.0)[0].data


def test_panels_are_drawn_in_each_players_corner_only():
    layer, manager, state = make_layer()
    manager.set_player_count(state, 2)
    buffer = draw(layer, state)
    assert panel_pixels(buffer, 0)[..., 3].max() > 0  # seat 0
    assert panel_pixels(buffer, 1)[..., 3].max() > 0  # seat 1
    assert panel_pixels(buffer, 2)[..., 3].max() == 0  # nobody sits here
    assert panel_pixels(buffer, 3)[..., 3].max() == 0


def test_resources_mode_draws_a_taller_panel_than_simple():
    layer, manager, state = make_layer()
    manager.set_player_count(state, 2)
    simple = int((panel_pixels(draw(layer, state), 0)[..., 3] > 0).any(axis=1).sum())
    manager.set_stats_mode(state, "rojo", "resources")
    full = int((panel_pixels(draw(layer, state), 0)[..., 3] > 0).any(axis=1).sum())
    assert full > simple


def test_roads_are_drawn():
    layer, manager, state = make_layer()
    manager.publish(state)
    before = int(np.count_nonzero(draw(layer, state)[..., 3]))
    manager.toggle_road(state, "rojo", EDGE)
    assert int(np.count_nonzero(draw(layer, state)[..., 3])) > before


# Layout


def test_panels_fit_the_screen_and_do_not_overlap():
    rects = [panel_rect(i, 1536, 864) for i in range(4)]
    for x, y, w, h in rects:
        assert x >= 0 and y >= 0 and x + w <= 1536 and y + h <= 864
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            assert (
                a[0] + a[2] <= b[0]
                or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1]
                or b[1] + b[3] <= a[1]
            )


def test_panel_at_finds_the_player_under_a_point():
    players = ["rojo", "azul", "blanco"]
    x, y, w, h = panel_rect(1, 1536, 864)
    assert panel_at((x + w / 2, y + h / 2), players, 1536, 864) == "azul"
    assert panel_at((768, 432), players, 1536, 864) is None


# Gesture


@pytest.fixture
def context():
    ctx = MagicMock(spec=AppContext)
    ctx.events = MagicMock()
    ctx.events.has_event.return_value = False
    ctx.notifications = MagicMock()
    ctx.app_config = MagicMock()
    ctx.app_config.projector_ppi = 96.0
    ctx.app_config.width = 1536
    ctx.app_config.height = 864
    ctx.show_tokens = True
    ctx.inspected_token_id = None
    ctx.map_system = MagicMock()  # pointing also runs the token inspection code
    ctx.map_system.ghost_tokens = []
    ctx.map_system.screen_to_world.return_value = (0.0, 0.0)
    ctx.map_system.is_map_loaded.return_value = False
    ctx.map_system.svg_loader.get_visibility_blockers.return_value = []
    ctx.raw_tokens = []
    ctx.visibility_engine = None
    ctx.state = WorldState()
    return ctx


def make_scene(context):
    """A viewing scene whose token/door hit-test is stubbed (pointing also runs that code)."""
    scene = ViewingScene(context)
    scene._find_target_at_point = lambda _pos: None
    return scene


def hand_at(gesture, point):
    return [HandInput(gesture, point, (0.0, 0.0), None)]


def over_panel(index):
    x, y, w, h = panel_rect(index, 1536, 864)
    return (x + w // 2, y + h // 2)


def stats_calls(context):
    return [
        c
        for c in context.events.schedule.call_args_list
        if c.kwargs.get("key") == TimerKey.CATAN_STATS_HOLD
    ]


def test_stats_gesture_does_not_clash_with_the_other_one_hand_gestures():
    # Pointing is shared with the zoom gesture, but zoom needs both hands pointing.
    assert config_vars.CATAN_STATS_GESTURE not in {
        config_vars.CATAN_ROLL_GESTURE,
        config_vars.SUMMON_STEP_1_GESTURE,
        config_vars.SUMMON_STEP_2_GESTURE,
        config_vars.SELECT_GESTURE,
        config_vars.PAN_GESTURE,
    }


def test_holding_the_gesture_over_a_panel_schedules_the_toggle(context):
    manager = CatanManager(board=small_board())
    manager.publish(context.state)
    scene = make_scene(context)
    scene.update(hand_at(config_vars.CATAN_STATS_GESTURE, over_panel(1)), [], 0.0)
    calls = stats_calls(context)
    assert len(calls) == 1
    delay, callback = calls[0].args
    assert delay == config_vars.CATAN_STATS_HOLD_TIME
    assert callback() == Action.CATAN_STATS_REQUEST


def test_the_toggle_request_targets_the_panel_that_was_held(context):
    manager = CatanManager(board=small_board())
    manager.publish(context.state)
    scene = make_scene(context)
    scene.update(hand_at(config_vars.CATAN_STATS_GESTURE, over_panel(1)), [], 0.0)
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    (queued,) = context.state.pending_actions
    assert queued["action"] == "CATAN_STATS_MODE"
    assert json.loads(queued["payload"]) == {"player": "azul", "mode": "toggle"}


def test_other_gestures_or_places_do_not_schedule_a_toggle(context):
    manager = CatanManager(board=small_board())
    manager.publish(context.state)
    scene = make_scene(context)
    scene.update(hand_at(config_vars.CATAN_STATS_GESTURE, (768, 432)), [], 0.0)
    scene.update(hand_at(config_vars.CATAN_ROLL_GESTURE, over_panel(1)), [], 0.0)
    assert stats_calls(context) == []


def test_no_toggle_without_a_catan_game(context):
    scene = make_scene(context)
    scene.update(hand_at(config_vars.CATAN_STATS_GESTURE, over_panel(0)), [], 0.0)
    assert stats_calls(context) == []


def test_moving_to_another_panel_restarts_the_hold(context):
    manager = CatanManager(board=small_board())
    manager.publish(context.state)
    scene = make_scene(context)
    scene.update(hand_at(config_vars.CATAN_STATS_GESTURE, over_panel(0)), [], 0.0)
    context.events.has_event.side_effect = lambda key: key == TimerKey.CATAN_STATS_HOLD
    scene.update(hand_at(config_vars.CATAN_STATS_GESTURE, over_panel(1)), [], 0.1)
    context.events.cancel.assert_any_call(TimerKey.CATAN_STATS_HOLD)


def test_panel_constants_are_consistent():
    assert PANEL_W > 0 and PANEL_H > 0


def test_fit_board_view_centers_the_board_between_the_panels():
    from light_map.catan.layout import BOARD_HEIGHT, BOARD_WIDTH, PANEL_W, fit_board_view

    for width, height in ((1920, 1080), (1371, 771)):
        x, y, zoom = fit_board_view(width, height)
        assert zoom > 0
        # centered
        assert x == pytest.approx(width - x - zoom * BOARD_WIDTH)
        assert y == pytest.approx(height - y - zoom * BOARD_HEIGHT)
        # inside the screen and clear of the side panels
        assert x >= PANEL_W and x + zoom * BOARD_WIDTH <= width - PANEL_W
        assert y >= 0 and y + zoom * BOARD_HEIGHT <= height
