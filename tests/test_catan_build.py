import json
import random
from unittest.mock import MagicMock

import pytest

from light_map.action_dispatcher import (
    handle_catan_build,
    handle_catan_remove,
    handle_catan_robber,
)
from light_map.catan.board import (
    Board,
    Building,
    Tile,
    vertex_from_list,
    vertex_to_list,
    vertices_of,
)
from light_map.catan.layout import tile_center, vertex_position
from light_map.catan.manager import CatanManager
from light_map.rendering.layers.catan_layer import CatanLayer
from light_map.state.world_state import WorldState


VERTEX = vertex_to_list(vertices_of((0, 0))[0])


def small_board() -> Board:
    return Board(
        {(0, 0): Tile("wood", 6), (1, 0): Tile("brick", 8), (-1, 0): Tile("desert", None)},
        robber=(-1, 0),
    )


def test_vertex_list_round_trip():
    vertex = vertices_of((0, 0))[2]
    assert vertex_from_list(vertex_to_list(vertex)) == vertex
    assert len(vertex_to_list(vertex)) == 3


def test_vertex_position_is_the_mean_of_its_three_tiles():
    vertex = vertices_of((0, 0))[0]
    xs, ys = zip(*(tile_center(*c) for c in vertex), strict=True)
    assert vertex_position(vertex) == (sum(xs) / 3, sum(ys) / 3)


def test_board_remove_building():
    board = small_board()
    vertex = vertices_of((0, 0))[0]
    board.build(vertex, "rojo", Building.SETTLEMENT)
    board.remove(vertex)
    assert vertex not in board.buildings
    with pytest.raises(ValueError):
        board.remove(vertex)


def test_board_with_buildings_round_trips_through_json():
    board = small_board()
    vertex = vertices_of((0, 0))[0]
    board.build(vertex, "rojo", Building.SETTLEMENT)
    board.build(vertex, "rojo", Building.CITY)
    restored = Board.from_dict(json.loads(json.dumps(board.to_dict())))
    assert restored.buildings == board.buildings


def test_manager_publishes_board_and_buildings_before_any_roll():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.publish(state)
    view = state.catan
    assert view.total is None and view.dice is None
    assert len(view.board["tiles"]) == 3
    assert len(view.board["vertices"]) == len(
        {v for c in small_board().tiles for v in vertices_of(c)}
    )
    assert state.to_dict()["catan"]["total"] is None


def test_build_places_a_settlement_then_upgrades_to_a_city():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.build(state, "rojo", VERTEX)
    assert state.catan.to_dict()["buildings"][0]["kind"] == "settlement"
    manager.build(state, "rojo", VERTEX)
    assert state.catan.to_dict()["buildings"][0]["kind"] == "city"
    with pytest.raises(ValueError):
        manager.build(state, "rojo", VERTEX)  # a city cannot be upgraded further


def test_build_on_a_vertex_owned_by_someone_else_fails():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.build(state, "rojo", VERTEX)
    with pytest.raises(ValueError):
        manager.build(state, "azul", VERTEX)


def test_roll_after_building_pays_the_owner():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.build(state, "rojo", VERTEX)
    manager.roll(state, dice=(3, 3))
    assert state.catan.payouts == {"rojo": {"wood": 1}}
    manager.build(state, "rojo", VERTEX)  # city keeps the last roll and pays double
    assert state.catan.total == 6
    assert state.catan.payouts == {"rojo": {"wood": 2}}


def test_remove_and_move_robber_publish_changes():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.build(state, "rojo", VERTEX)
    manager.remove(state, VERTEX)
    assert state.catan.to_dict()["buildings"] == []
    manager.move_robber(state, (1, 0))
    assert state.catan.robber == (1, 0)


def test_changes_are_saved_next_to_the_svg(tmp_path):
    svg = tmp_path / "catan.svg"
    svg.write_text("<svg/>")
    (tmp_path / "catan.board.json").write_text(json.dumps(Board.random(random.Random(2)).to_dict()))
    state = WorldState()
    manager = CatanManager()
    assert manager.sync(state, str(svg)) is True
    vertex = vertex_to_list(vertices_of((0, 0))[0])
    manager.build(state, "azul", vertex)

    reloaded = CatanManager()
    reloaded.sync(WorldState(), str(svg))
    assert list(reloaded.board.buildings.values()) == [("azul", Building.SETTLEMENT)]


def test_sync_without_board_clears_the_view(tmp_path):
    state = WorldState()
    state.catan = object()
    assert CatanManager().sync(state, str(tmp_path / "none.svg")) is False
    assert state.catan is None


def make_app(tmp_path):
    svg = tmp_path / "catan.svg"
    svg.write_text("<svg/>")
    (tmp_path / "catan.board.json").write_text(json.dumps(small_board().to_dict()))
    app = MagicMock()
    app.current_map_path = str(svg)
    app.catan_manager = CatanManager()
    return app


def test_dispatcher_build_remove_and_robber(tmp_path):
    state = WorldState()
    app = make_app(tmp_path)
    payload = json.dumps({"player": "rojo", "vertex": VERTEX})

    handle_catan_build(app, {"payload": payload}, state)
    assert len(state.catan.to_dict()["buildings"]) == 1

    handle_catan_robber(app, {"payload": json.dumps({"tile": [1, 0]})}, state)
    assert state.catan.robber == (1, 0)

    handle_catan_remove(app, {"payload": json.dumps({"vertex": VERTEX})}, state)
    assert state.catan.to_dict()["buildings"] == []


def test_dispatcher_reports_invalid_moves_as_notifications(tmp_path):
    state = WorldState()
    app = make_app(tmp_path)
    handle_catan_build(app, {"payload": json.dumps({"player": "rojo", "vertex": VERTEX})}, state)
    handle_catan_build(app, {"payload": json.dumps({"player": "azul", "vertex": VERTEX})}, state)
    app.notifications.add_notification.assert_called_once()
    handle_catan_build(app, {"payload": "not json"}, state)
    assert app.notifications.add_notification.call_count == 2


def dice_corner(patch):
    """Top-right area of an 800x800 layer where the dice are drawn."""
    return patch.data[10:130, 540:790, 3]


def test_layer_shows_the_dice_after_a_roll():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.build(state, "rojo", VERTEX)
    (before,), _ = make_layer(state).render()
    assert dice_corner(before).max() == 0

    manager.roll(state, dice=(3, 4))
    (after,), _ = make_layer(state).render()
    assert dice_corner(after).max() > 0


def test_dice_pips_match_the_values_rolled():
    def painted(dice):
        state = WorldState()
        CatanManager(board=small_board()).roll(state, dice=dice)
        (patch,), _ = make_layer(state).render()
        area = patch.data[10:130, 540:790]
        dark = (area[:, :, :3].max(axis=2) < 100) & (area[:, :, 3] > 0)
        return int(dark.sum())

    # Pips are dark dots on a white face: more pips -> more dark pixels.
    # The same dice in another order paint the same area.
    assert painted((6, 6)) > painted((1, 1))
    assert painted((2, 5)) == painted((5, 2))


def make_layer(state: WorldState) -> CatanLayer:
    map_system = MagicMock()
    map_system.world_to_screen.side_effect = lambda x, y: (x, y)
    return CatanLayer(state, map_system, 800, 800)


def test_layer_draws_buildings_without_any_roll():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.build(state, "rojo", VERTEX)
    (patch,), _ = make_layer(state).render()
    x, y = (int(v) for v in vertex_position(vertices_of((0, 0))[0]))
    assert patch.data[y, x, 3] > 0
    # No tile is highlighted before a roll: a point inside tile (1, 0) stays transparent.
    tx, ty = (int(v) for v in tile_center(1, 0))
    assert patch.data[ty + 25, tx, 3] == 0
