"""Development cards played through the dashboard actions."""

import json
import random
from unittest.mock import MagicMock

import pytest

from light_map.action_dispatcher import (
    handle_catan_build,
    handle_catan_dev_buy,
    handle_catan_dev_play,
    handle_catan_dev_skip,
    handle_catan_new_game,
    handle_catan_road,
    handle_catan_robber,
    handle_catan_roll,
)
from light_map.catan.board import COSTS, Board, edge_to_list, vertex_edges, vertex_to_list
from light_map.catan.devcards import KNIGHT, MONOPOLY, ROAD_BUILDING, VICTORY_POINT, YEAR_OF_PLENTY
from light_map.catan.manager import CatanManager
from light_map.state.world_state import WorldState


@pytest.fixture
def table():
    app = MagicMock()
    app.catan_manager = CatanManager(board=Board.random(random.Random(9)), rng=random.Random(3))
    app.catan_manager.load_for_map = lambda _path: True
    state = WorldState()
    return app, state


def send(handler, table, **data):
    app, state = table
    handler(app, {"payload": json.dumps(data)}, state)


def view(table):
    return table[1].catan.to_dict()


def board(table):
    return table[0].catan_manager.board


def notices(table):
    return [c.args[0] for c in table[0].notifications.add_notification.call_args_list]


def start_playing(table):
    send(handle_catan_new_game, table, players=3)
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
    send(handle_catan_roll, table, **{})
    # a known roll: rojo is first and the production of the setup is cleared
    if view(table)["game"]["phase"] != "main":
        b.game.phase = "main"
    b.hands.clear()
    table[0].catan_manager.publish(table[1])


def hold(table, player, card):
    board(table).dev.hand(player)[card] += 1
    table[0].catan_manager.publish(table[1])


def test_buying_through_the_dashboard_pays_and_gives_a_card(table):
    start_playing(table)
    for resource, amount in COSTS["dev"].items():
        board(table).add_cards("rojo", resource, amount)
    board(table).dev.deck = [KNIGHT]
    send(handle_catan_dev_buy, table, player="rojo")
    data = view(table)
    assert data["stats"]["rojo"]["dev_cards"] == 1
    assert data["game"]["dev"]["hand"] == {"knight": 1}
    assert data["game"]["dev"]["bought"] == ["knight"] and data["game"]["dev"]["deck_left"] == 0
    assert notices(table) == []


def test_only_the_player_in_turn_sees_their_cards_and_the_victory_points_stay_hidden(table):
    start_playing(table)
    hold(table, "rojo", VICTORY_POINT)
    hold(table, "azul", KNIGHT)
    data = view(table)
    assert data["game"]["dev"]["hand"] == {"victory_point": 1}  # rojo, the current player
    assert "azul" not in json.dumps(data["game"]["dev"])
    assert data["stats"]["azul"]["dev_cards"] == 1  # others only see how many
    assert data["stats"]["rojo"]["points"] == board(table).public_points("rojo")


def test_a_refused_purchase_is_explained_in_spanish(table):
    start_playing(table)
    send(handle_catan_dev_buy, table, player="rojo")  # no cards
    assert view(table)["notice"]["text"] == "No tienes las cartas necesarias"
    board(table).dev.deck = []
    for resource, amount in COSTS["dev"].items():
        board(table).add_cards("rojo", resource, amount)
    send(handle_catan_dev_buy, table, player="rojo")
    assert view(table)["notice"]["text"] == "Ya no quedan cartas de desarrollo"


def test_year_of_plenty_and_monopoly_through_the_actions(table):
    start_playing(table)
    hold(table, "rojo", YEAR_OF_PLENTY)
    send(
        handle_catan_dev_play, table, player="rojo", card=YEAR_OF_PLENTY, resources=["ore", "wheat"]
    )
    assert board(table).hands["rojo"]["ore"] == 1 and board(table).hands["rojo"]["wheat"] == 1
    board(table).add_cards("azul", "ore", 3)
    board(table).game.dev_played = False
    hold(table, "rojo", MONOPOLY)
    send(handle_catan_dev_play, table, player="rojo", card=MONOPOLY, resource="ore")
    assert board(table).hands["rojo"]["ore"] == 4 and board(table).hands["azul"]["ore"] == 0


def test_a_bad_play_is_refused_with_a_spanish_message_and_keeps_the_card(table):
    start_playing(table)
    hold(table, "rojo", YEAR_OF_PLENTY)
    send(handle_catan_dev_play, table, player="rojo", card=YEAR_OF_PLENTY, resources=["ore"])
    assert view(table)["notice"]["text"] == "Elige dos recursos"
    send(handle_catan_dev_play, table, player="rojo", card=KNIGHT)
    assert view(table)["notice"]["text"] == "rojo no tiene esa carta"
    send(handle_catan_dev_play, table, player="rojo", card=VICTORY_POINT)
    assert view(table)["notice"]["text"] == "Esa carta no se puede jugar"
    assert board(table).dev.hand("rojo")[YEAR_OF_PLENTY] == 1
    assert all(m.startswith("Catan: ") and m.isascii() for m in notices(table))


def test_a_knight_through_the_actions_moves_the_robber_and_counts(table):
    start_playing(table)
    hold(table, "rojo", KNIGHT)
    send(handle_catan_dev_play, table, player="rojo", card=KNIGHT)
    assert view(table)["game"]["phase"] == "robber"
    target = next(c for c in board(table).tiles if c != board(table).robber)
    send(handle_catan_robber, table, tile=list(target))
    assert view(table)["game"]["phase"] in ("steal", "main")
    assert view(table)["stats"]["rojo"]["knights"] == 1


def test_road_building_through_the_actions_and_skipping(table):
    start_playing(table)
    b = board(table)
    hold(table, "rojo", ROAD_BUILDING)
    send(handle_catan_dev_play, table, player="rojo", card=ROAD_BUILDING)
    data = view(table)["game"]
    assert data["phase"] == "road_building" and data["dev"]["free_roads"] == 2
    edge = next(e for e in b.all_edges() if e not in b.roads and b.road_error(e, "rojo") is None)
    send(handle_catan_road, table, player="rojo", edge=edge_to_list(edge))
    assert view(table)["game"]["dev"]["free_roads"] == 1
    send(handle_catan_dev_skip, table, player="rojo")
    assert view(table)["game"]["phase"] == "main"
    assert sum(b.hands.get("rojo", {}).values()) == 0


def test_the_view_describes_the_army_and_the_deck(table):
    start_playing(table)
    data = view(table)
    assert data["game"]["dev"]["deck_left"] == 25
    assert data["stats"]["rojo"]["has_largest_army"] is False
    assert data["game"]["costs"]["dev"] == COSTS["dev"]
