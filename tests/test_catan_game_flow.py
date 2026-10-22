"""A whole game played through the same actions the dashboard sends."""

import json
import random
from unittest.mock import MagicMock

import pytest

from light_map.action_dispatcher import (
    handle_catan_bank,
    handle_catan_build,
    handle_catan_discard,
    handle_catan_end_turn,
    handle_catan_free_play,
    handle_catan_new_game,
    handle_catan_order_roll,
    handle_catan_road,
    handle_catan_robber,
    handle_catan_roll,
    handle_catan_steal,
)
from light_map.catan.board import (
    COSTS,
    Board,
    edge_to_list,
    edge_vertices,
    vertex_edges,
    vertex_to_list,
)
from light_map.catan.manager import CatanManager
from light_map.state.world_state import WorldState


@pytest.fixture
def table():
    app = MagicMock()
    app.catan_manager = CatanManager(board=Board.random(random.Random(21)), rng=random.Random(2))
    app.catan_manager.load_for_map = lambda _path: True
    return app, WorldState()


def send(handler, table, **data):
    app, state = table
    handler(app, {"payload": json.dumps(data)}, state)


def view(table):
    return table[1].catan.to_dict()


def errors(table):
    return [c.args[0] for c in table[0].notifications.add_notification.call_args_list]


def board(table):
    return table[0].catan_manager.board


def vertex_for(table, player):
    b = board(table)
    return next(
        v
        for v in sorted(b.all_vertices(), key=sorted)
        if all(c in b.tiles for c in v) and b.settlement_error(v, player, setup=True) is None
    )


def play_setup(table):
    b = board(table)
    while view(table)["game"]["phase"] == "setup":
        player = view(table)["game"]["current_player"]
        vertex = vertex_for(table, player)
        send(handle_catan_build, table, player=player, vertex=vertex_to_list(vertex))
        edge = next(e for e in vertex_edges(vertex) if e in b.all_edges() and e not in b.roads)
        send(handle_catan_road, table, player=player, edge=edge_to_list(edge))
    assert not errors(table)


def test_a_full_game_flow_through_the_dashboard_actions(table):
    send(handle_catan_new_game, table, players=3)
    game = view(table)["game"]
    assert game["phase"] == "setup" and game["current_player"] == "rojo"
    assert "Preparación" in game["hint"]

    play_setup(table)
    game = view(table)["game"]
    assert game["phase"] == "roll" and game["current_player"] == "rojo" and game["turn"] == 1

    # A 7 with a rich player: discard, move the robber, steal.
    b = board(table)
    b.hands.clear()
    b.add_cards("azul", "wood", 5)
    b.add_cards("azul", "ore", 4)
    app, state = table
    app.catan_manager.roll(state, (3, 4))
    game = view(table)["game"]
    assert game["phase"] == "discard" and game["discards"] == {"azul": 4}
    send(handle_catan_discard, table, player="azul", cards={"wood": 3, "ore": 1})
    assert view(table)["game"]["phase"] == "robber"

    target = next(
        c
        for c in b.tiles
        if c != b.robber and any(c in v and p == "azul" for v, (p, _) in b.buildings.items())
    )
    send(handle_catan_robber, table, tile=list(target))
    game = view(table)["game"]
    if game["phase"] == "steal":
        send(handle_catan_steal, table, victim="azul")
    assert view(table)["game"]["phase"] == "main"

    # Bank trade then end the turn.
    b.hands.clear()
    b.add_cards("rojo", "wood", 4)
    send(handle_catan_bank, table, player="rojo", give="wood", get="ore")
    assert view(table)["stats"]["rojo"]["hand"]["ore"] == 1
    send(handle_catan_end_turn, table)
    game = view(table)["game"]
    assert game["phase"] == "roll" and game["current_player"] == "azul" and game["turn"] == 2


def test_illegal_moves_are_reported_on_screen_and_change_nothing(table):
    send(handle_catan_new_game, table, players=2)
    before = view(table)
    far_vertex = vertex_for(table, "azul")
    send(
        handle_catan_build, table, player="azul", vertex=vertex_to_list(far_vertex)
    )  # not azul's turn
    send(handle_catan_end_turn, table)  # not in main phase
    send(handle_catan_roll, table)  # setup phase: silently ignored
    assert any("Es el turno de rojo" in e for e in errors(table))
    assert any("No se puede hacer eso ahora" in e for e in errors(table))
    assert view(table)["buildings"] == before["buildings"]
    assert view(table)["game"]["phase"] == "setup"


def test_the_roll_gesture_is_silent_when_it_is_not_the_roll_phase(table):
    send(handle_catan_new_game, table, players=2)
    send(handle_catan_roll, table)
    assert errors(table) == []


def test_free_mode_is_untouched_until_a_game_starts(table):
    b = board(table)
    vertex = next(iter(b.all_vertices()))
    send(handle_catan_build, table, player="rojo", vertex=vertex_to_list(vertex))
    assert view(table)["game"]["phase"] == "free"
    assert not errors(table)
    send(handle_catan_new_game, table, players=2)
    assert not view(table)["buildings"]
    send(handle_catan_free_play, table)
    assert view(table)["game"]["phase"] == "free"


def test_pieces_cannot_be_removed_during_a_game(table):
    from light_map.action_dispatcher import handle_catan_remove

    send(handle_catan_new_game, table, players=2)
    play_vertex = vertex_for(table, "rojo")
    send(handle_catan_build, table, player="rojo", vertex=vertex_to_list(play_vertex))
    send(handle_catan_remove, table, vertex=vertex_to_list(play_vertex))
    assert any("No se pueden quitar piezas" in e for e in errors(table))
    assert view(table)["buildings"]


def test_game_view_exposes_what_the_dashboard_needs(table):
    send(handle_catan_new_game, table, players=4)
    game = view(table)["game"]
    assert set(game) >= {
        "phase",
        "current_player",
        "turn",
        "setup_step",
        "discards",
        "victims",
        "winner",
        "hint",
        "costs",
    }
    assert game["costs"]["city"] == COSTS["city"]
    assert view(table)["players"] == ["rojo", "azul", "blanco", "naranja"]


def test_the_game_is_saved_with_the_board_and_comes_back(table, tmp_path):
    manager = table[0].catan_manager
    manager._sidecar = str(tmp_path / "catan.board.json")
    send(handle_catan_new_game, table, players=3)
    play_setup(table)
    saved = json.loads((tmp_path / "catan.board.json").read_text(encoding="utf-8"))
    loaded = Board.from_dict(saved)
    assert loaded.game.phase == "roll"
    assert loaded.game.order == ["rojo", "azul", "blanco"]
    assert len(loaded.buildings) == 6 and len(loaded.roads) == 6


def test_a_road_edge_helper_matches_the_geometry(table):
    b = board(table)
    edge = next(iter(b.all_edges()))
    assert len(edge_vertices(edge)) == 2


def test_a_refused_move_is_also_published_for_the_dashboard(table):
    send(handle_catan_new_game, table, players=2)
    assert view(table)["notice"] is None
    far_vertex = vertex_for(table, "azul")
    send(handle_catan_build, table, player="azul", vertex=vertex_to_list(far_vertex))
    first = view(table)["notice"]
    assert "Es el turno de rojo" in first["text"]
    send(handle_catan_end_turn, table)
    second = view(table)["notice"]
    assert "No se puede hacer eso ahora" in second["text"]
    assert second["id"] != first["id"]  # the dashboard can tell it is a new message


def test_the_notice_covers_every_kind_of_refusal(table):
    send(handle_catan_new_game, table, players=2, phased=True)
    send(handle_catan_order_roll, table, player="naranja", value=3)
    assert "no tiene que tirar el dado" in view(table)["notice"]["text"]
    send(handle_catan_roll, table)
    assert view(table)["notice"]["text"]  # the roll gesture stays silent, so the last one remains
