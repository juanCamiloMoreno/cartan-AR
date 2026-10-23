import json
import random
from unittest.mock import MagicMock

import numpy as np

from light_map.action_dispatcher import handle_catan_roll
from light_map.catan.board import Board, Building, Tile, vertices_of
from light_map.catan.layout import hex_corners, sidecar_path, tile_center
from light_map.catan.manager import CatanManager
from light_map.catan.view import CatanView
from light_map.rendering.layers.catan_layer import CatanLayer
from light_map.state.world_state import WorldState


def small_board() -> Board:
    return Board(
        {(0, 0): Tile("wood", 6), (1, 0): Tile("brick", 8), (-1, 0): Tile("desert", None)},
        robber=(-1, 0),
    )


def test_board_round_trips_through_json(tmp_path):
    board = Board.random(random.Random(3))
    restored = Board.from_dict(json.loads(json.dumps(board.to_dict())))
    assert restored.tiles == board.tiles
    assert restored.robber == board.robber


def test_sidecar_path_sits_next_to_the_svg():
    assert sidecar_path("maps/catan.svg").endswith("catan.board.json")


def test_tile_geometry_is_a_regular_hexagon_around_its_center():
    cx, cy = tile_center(0, 0)
    corners = hex_corners(0, 0)
    assert len(corners) == 6
    dists = [((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in corners]
    assert max(dists) - min(dists) < 1e-6
    # Neighbouring tiles are further apart than a corner radius.
    nx, ny = tile_center(1, 0)
    assert ((nx - cx) ** 2 + (ny - cy) ** 2) ** 0.5 > dists[0]


def test_world_state_catan_defaults_and_versioning():
    state = WorldState()
    assert state.catan is None
    before = state.catan_version
    state.catan = CatanView(dice=(3, 4), total=7, producing=(), robber=(0, 0))
    assert state.catan_version > before
    assert state.to_dict()["catan"]["total"] == 7


def test_manager_roll_publishes_producing_tiles_and_payouts():
    state = WorldState()
    board = small_board()
    board.build(vertices_of((0, 0))[0], "ana", Building.SETTLEMENT)
    manager = CatanManager(board=board)

    manager.roll(state, dice=(3, 3))

    view = state.catan
    assert view.dice == (3, 3) and view.total == 6
    assert [(t.q, t.r, t.resource) for t in view.producing] == [(0, 0, "wood")]
    assert view.payouts == {"ana": {"wood": 1}}
    assert view.robber == (-1, 0)


def test_manager_roll_seven_has_no_producing_tiles():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.roll(state, dice=(3, 4))
    assert state.catan.total == 7
    assert state.catan.producing == ()


def test_manager_roll_is_random_when_no_dice_given():
    state = WorldState()
    manager = CatanManager(board=small_board(), rng=random.Random(1))
    manager.roll(state)
    d1, d2 = state.catan.dice
    assert state.catan.total == d1 + d2


def test_manager_loads_board_from_sidecar(tmp_path):
    svg = tmp_path / "catan.svg"
    svg.write_text("<svg/>")
    board = Board.random(random.Random(4))
    (tmp_path / "catan.board.json").write_text(json.dumps(board.to_dict()))

    manager = CatanManager()
    assert manager.load_for_map(str(svg)) is True
    assert manager.board.tiles == board.tiles
    assert CatanManager().load_for_map(str(tmp_path / "other.svg")) is False


def test_roll_without_board_does_nothing():
    state = WorldState()
    assert CatanManager().roll(state) is None
    assert state.catan is None


def test_dispatcher_roll_uses_payload_dice_and_current_map(tmp_path):
    svg = tmp_path / "catan.svg"
    svg.write_text("<svg/>")
    board = Board.random(random.Random(5))
    (tmp_path / "catan.board.json").write_text(json.dumps(board.to_dict()))

    state = WorldState()
    app = MagicMock()
    app.current_map_path = str(svg)
    app.catan_manager = CatanManager()

    handle_catan_roll(app, {"action": "CATAN_ROLL", "payload": "2,3"}, state)
    assert state.catan.dice == (2, 3)

    handle_catan_roll(app, {"action": "CATAN_ROLL"}, state)
    assert 2 <= state.catan.total <= 12


def make_layer(state: WorldState) -> CatanLayer:
    map_system = MagicMock()
    # Identity mapping: SVG coordinates are screen coordinates.
    map_system.world_to_screen.side_effect = lambda x, y: (x, y)
    return CatanLayer(state, map_system, 800, 800)


def test_layer_draws_nothing_without_a_roll():
    state = WorldState()
    layer = make_layer(state)
    patches, _ = layer.render()
    assert patches == []


def test_layer_highlights_only_producing_tiles():
    state = WorldState()
    manager = CatanManager(board=small_board())
    manager.roll(state, dice=(4, 4))  # total 8 -> brick at (1, 0)
    layer = make_layer(state)
    layer.width, layer.height = 1920, 1080  # room for the panels away from the tiles

    (patch,), _ = layer.render()
    assert patch.data.shape == (1080, 1920, 4)

    hit_x, hit_y = (int(v) for v in tile_center(1, 0))
    miss_x, miss_y = (int(v) for v in tile_center(0, 0))
    alpha = patch.data[..., 3]
    hit_area = alpha[hit_y - 25 : hit_y + 25, hit_x - 25 : hit_x + 25]
    miss_area = alpha[miss_y - 25 : miss_y + 25, miss_x - 25 : miss_x + 25]
    assert (hit_area == 0).any()  # the paying tile keeps its full colors
    assert (miss_area > 0).all()  # the others are darkened
    assert patch.data.dtype == np.uint8


def test_layer_redraws_when_roll_changes():
    state = WorldState()
    manager = CatanManager(board=small_board())
    layer = make_layer(state)
    manager.roll(state, dice=(4, 4))
    v1 = layer.get_current_version()
    manager.roll(state, dice=(3, 3))
    assert layer.get_current_version() > v1
