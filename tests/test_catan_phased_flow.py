"""A phased game (board hidden until the reveal) played through the dashboard actions."""

import json
import random
from unittest.mock import MagicMock

import numpy as np
import pytest

from light_map.action_dispatcher import (
    handle_catan_build,
    handle_catan_free_play,
    handle_catan_new_game,
    handle_catan_order_roll,
    handle_catan_reveal_all,
    handle_catan_reveal_next,
    handle_catan_road,
    handle_catan_roll,
)
from light_map.catan.board import Board, edge_to_list, vertex_edges, vertex_to_list
from light_map.catan.manager import CatanManager
from light_map.catan.svg import BLANK_TILE, build_blank_svg, build_svg
from light_map.rendering.layers.catan_layer import CatanLayer, game_banner
from light_map.state.world_state import WorldState


@pytest.fixture
def table(tmp_path):
    svg = tmp_path / "catan.svg"
    board = Board.random(random.Random(3))
    svg.write_text(build_svg(board.tiles), encoding="utf-8")
    manager = CatanManager(board=board, rng=random.Random(4))
    manager._loaded_from = str(svg)
    manager._sidecar = str(tmp_path / "catan.board.json")
    manager.load_for_map = lambda _path: True
    app = MagicMock()
    app.catan_manager = manager
    app.current_map_path = str(svg)
    return app, WorldState(), svg


def send(handler, table, **data):
    app, state, _ = table
    handler(app, {"payload": json.dumps(data)}, state)


def view(table):
    return table[1].catan.to_dict()


def errors(table):
    return [c.args[0] for c in table[0].notifications.add_notification.call_args_list]


def board(table):
    return table[0].catan_manager.board


def finish_order(table, players):
    rank = {"rojo": 6, "azul": 5, "blanco": 4, "naranja": 3}
    for player in players:
        send(handle_catan_order_roll, table, player=player, value=rank[player])


def play_setup(table):
    b = board(table)
    while view(table)["game"]["phase"] == "setup":
        player = view(table)["game"]["current_player"]
        vertex = next(
            v
            for v in sorted(b.all_vertices(), key=sorted)
            if all(c in b.tiles for c in v) and b.settlement_error(v, player, setup=True) is None
        )
        send(handle_catan_build, table, player=player, vertex=vertex_to_list(vertex))
        edge = next(e for e in vertex_edges(vertex) if e in b.all_edges() and e not in b.roads)
        send(handle_catan_road, table, player=player, edge=edge_to_list(edge))


def start(table, players=3):
    send(handle_catan_new_game, table, players=players, phased=True)


# Starting a phased game


def test_a_phased_game_blanks_the_map_and_reloads_it_once(table):
    app, _, svg = table
    start(table)
    text = svg.read_text(encoding="utf-8")
    assert text == build_blank_svg(board(table).tiles)
    assert BLANK_TILE in text and "<text" not in text
    app.load_map.assert_called_once_with(app.current_map_path)
    assert errors(table) == []


def test_the_view_hides_the_tiles_the_robber_and_the_report(table):
    start(table)
    data = view(table)
    assert {t["resource"] for t in data["board"]["tiles"]} == {"hidden"}
    assert all(t["number"] is None for t in data["board"]["tiles"])
    assert data["robber"] is None
    assert data["generator"] is None
    game = data["game"]
    assert game["phase"] == "order" and game["hidden"] and game["phased"]
    assert game["order_pending"] == ["rojo", "azul", "blanco"]


def test_a_normal_game_does_not_touch_the_map(table):
    app, _, svg = table
    before = svg.read_text(encoding="utf-8")
    send(handle_catan_new_game, table, players=3)
    assert svg.read_text(encoding="utf-8") == before
    app.load_map.assert_not_called()
    assert {t["resource"] for t in view(table)["board"]["tiles"]} != {"hidden"}


# Flow


def test_the_whole_phased_flow(table):
    app, state, svg = table
    start(table, 3)

    # 1. who starts: a tie between rojo and azul is decided in a second round
    send(handle_catan_order_roll, table, player="rojo", value=5)
    send(handle_catan_order_roll, table, player="azul", value=5)
    send(handle_catan_order_roll, table, player="blanco", value=2)
    game = view(table)["game"]
    assert game["phase"] == "order" and game["order_pending"] == ["rojo", "azul"]
    send(handle_catan_order_roll, table, player="rojo", value=1)
    send(handle_catan_order_roll, table, player="azul", value=4)
    game = view(table)["game"]
    assert game["phase"] == "setup" and game["order"] == ["azul", "rojo", "blanco"]
    assert game["current_player"] == "azul"

    # 2. setup on the empty board: still hidden and nothing is paid
    play_setup(table)
    game = view(table)["game"]
    assert game["phase"] == "reveal" and game["hidden"]
    assert not any(board(table).hands.values())
    assert errors(table) == []

    # 3. reveal one by one
    send(handle_catan_reveal_next, table)
    shown = [t for t in view(table)["board"]["tiles"] if t["resource"] != "hidden"]
    assert len(shown) == 1 and shown[0]["number"] is None
    assert view(table)["game"]["reveal_done"] == 1
    for _ in range(18):
        send(handle_catan_reveal_next, table)
    assert all(t["resource"] != "hidden" for t in view(table)["board"]["tiles"])
    assert view(table)["game"]["phase"] == "reveal"
    app.load_map.assert_called_once()  # the map is only reloaded at the start and the end

    for _ in range(18):
        send(handle_catan_reveal_next, table)

    # 4. everything is out: the full map is back, the second settlements are paid, play starts
    game = view(table)["game"]
    assert game["phase"] == "roll" and not game["hidden"] and game["current_player"] == "azul"
    assert svg.read_text(encoding="utf-8") == build_svg(board(table).tiles)
    assert app.load_map.call_count == 2
    assert view(table)["robber"] is not None
    assert view(table)["generator"] is None or view(table)["generator"]["satisfied"]
    assert sum(sum(h.values()) for h in board(table).hands.values()) > 0
    send(handle_catan_roll, table)
    assert errors(table) == []


def test_reveal_all_finishes_at_once(table):
    app, _, svg = table
    start(table, 2)
    finish_order(table, ["rojo", "azul"])
    play_setup(table)
    send(handle_catan_reveal_all, table)
    assert view(table)["game"]["phase"] == "roll"
    assert svg.read_text(encoding="utf-8") == build_svg(board(table).tiles)
    assert app.load_map.call_count == 2


def test_leaving_a_phased_game_restores_the_map(table):
    app, _, svg = table
    start(table, 2)
    send(handle_catan_free_play, table)
    assert view(table)["game"]["phase"] == "free"
    assert svg.read_text(encoding="utf-8") == build_svg(board(table).tiles)
    assert app.load_map.call_count == 2
    assert {t["resource"] for t in view(table)["board"]["tiles"]} != {"hidden"}


def test_wrong_moves_in_the_new_phases_are_reported(table):
    start(table, 2)
    send(handle_catan_order_roll, table, player="naranja", value=3)
    send(handle_catan_order_roll, table, player="rojo", value=9)
    send(handle_catan_reveal_next, table)  # not in the reveal phase
    assert len(errors(table)) == 3
    assert view(table)["game"]["phase"] == "order"


def test_the_order_die_can_be_rolled_by_the_app(table):
    start(table, 2)
    send(handle_catan_order_roll, table, player="rojo")
    assert board(table).game.order_rolls["rojo"] in range(1, 7)


# Projection


def make_layer(table):
    app, state, _ = table
    map_system = MagicMock()
    map_system.world_to_screen.side_effect = lambda x, y: (int(x), int(y))
    return CatanLayer(state, map_system, 1920, 1080), state


def painted(layer, x, y, radius=6):
    data = layer._generate_patches(0.0)[0].data[..., 3]
    return int(
        (data[int(y) - radius : int(y) + radius, int(x) - radius : int(x) + radius] > 0).sum()
    )


def test_the_layer_paints_a_tile_only_once_it_is_revealed(table):
    layer, _ = make_layer(table)
    start(table, 2)
    finish_order(table, ["rojo", "azul"])
    play_setup(table)
    first = view(table)["game"]  # reveal phase
    assert first["phase"] == "reveal"
    tiles = view(table)["board"]["tiles"]
    target_cell = board(table).game.tile_order[0]
    target = next(t for t in tiles if (t["q"], t["r"]) == target_cell)
    # a spot on the hexagon away from the center, the buildings and the harbors
    probe = (target["x"] + 40, target["y"] - 10)
    assert painted(layer, *probe) == 0
    send(handle_catan_reveal_next, table)
    assert painted(layer, *probe) > 0


def test_the_layer_draws_the_number_token_after_the_tiles(table):
    layer, _ = make_layer(table)
    start(table, 2)
    finish_order(table, ["rojo", "azul"])
    play_setup(table)
    for _ in range(19):
        send(handle_catan_reveal_next, table)
    cell = board(table).game.number_order[0]
    tile = next(t for t in view(table)["board"]["tiles"] if (t["q"], t["r"]) == cell)
    cx, cy = int(tile["x"]), int(tile["y"])
    window = (slice(cy - 25, cy + 25), slice(cx - 25, cx + 25))
    before = layer._generate_patches(0.0)[0].data[window].copy()
    send(handle_catan_reveal_next, table)
    after = layer._generate_patches(0.0)[0].data[window]
    assert not np.array_equal(before, after)  # the token (a light disc with the number) appeared


def test_the_hidden_robber_is_not_drawn(table):
    layer, state = make_layer(table)
    start(table, 2)
    rx, ry = None, None
    desert = next(c for c, t in board(table).tiles.items() if t.resource == "desert")
    tile = next(t for t in view(table)["board"]["tiles"] if (t["q"], t["r"]) == desert)
    assert painted(layer, tile["x"], tile["y"], radius=18) == 0
    assert rx is None and ry is None


def test_banner_texts_for_the_new_phases():
    assert (
        game_banner({"phase": "order", "current_player": "azul"})
        == "QUIEN EMPIEZA: AZUL TIRA EL DADO"
    )
    text = game_banner({"phase": "reveal", "reveal_done": 5, "reveal_total": 37})
    assert text == "REVELANDO EL TABLERO 5/37"
    assert text.isascii()


def test_the_projection_is_a_transparent_overlay_even_when_hidden(table):
    layer, _ = make_layer(table)
    start(table, 2)
    patch = layer._generate_patches(0.0)[0]
    assert patch.data.dtype == np.uint8 and patch.data.shape == (1080, 1920, 4)
