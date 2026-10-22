import json
import random
from unittest.mock import MagicMock

import pytest

import light_map.menu.menu_config as config_vars
from light_map.action_dispatcher import (
    handle_catan_build,
    handle_catan_new_game,
    handle_catan_road,
    handle_catan_roll,
    handle_catan_trade_accept,
    handle_catan_trade_cancel,
    handle_catan_trade_decline,
    handle_catan_trade_offer,
)
from light_map.catan import game as g
from light_map.catan.board import Board, edge_to_list, vertex_edges, vertex_to_list
from light_map.catan.game import Game
from light_map.catan.layout import panel_rect
from light_map.catan.manager import CatanManager
from light_map.core.app_context import AppContext
from light_map.core.common_types import Action, TimerKey
from light_map.core.scene import HandInput
from light_map.input.gestures import GestureType
from light_map.map.map_scene import ViewingScene
from light_map.rendering.layers.catan_layer import game_banner
from light_map.rendering.layers.hand_feedback_layer import (
    PATCH_H,
    PATCH_W,
    HandFeedbackLayer,
)
from light_map.state.world_state import WorldState


W, H = 1920, 1080


@pytest.fixture
def started():
    game = Game(Board.random(random.Random(6)), rng=random.Random(2))
    game.new_game(3)
    board = game.board
    while game.state.phase == g.SETUP:
        player = game.current_player
        vertex = next(
            v
            for v in sorted(board.all_vertices(), key=sorted)
            if all(c in board.tiles for c in v)
            and board.settlement_error(v, player, setup=True) is None
        )
        game.build(player, vertex)
        game.build_road(
            player,
            next(
                e for e in vertex_edges(vertex) if e in board.all_edges() and e not in board.roads
            ),
        )
    game.roll((2, 2))
    board.hands.clear()
    return game


def give(game, player, **cards):
    for resource, amount in cards.items():
        game.board.add_cards(player, resource, amount)


def hand(game, player):
    return {r: n for r, n in game.board.hands.get(player, {}).items() if n}


# The rules


def test_the_player_in_turn_offers_and_another_one_accepts(started):
    give(started, "rojo", wood=2)
    give(started, "azul", ore=1)
    started.propose_trade("rojo", {"wood": 2}, {"ore": 1})
    assert started.state.trade == {
        "from": "rojo",
        "give": {"wood": 2},
        "get": {"ore": 1},
        "to": None,
        "declined": [],
    }
    started.accept_trade("azul")
    assert hand(started, "rojo") == {"ore": 1} and hand(started, "azul") == {"wood": 2}
    assert started.state.trade is None
    assert started.state.last_trade == {
        "from": "rojo",
        "to": "azul",
        "give": {"wood": 2},
        "get": {"ore": 1},
    }


def test_an_offer_can_be_for_one_player_only(started):
    give(started, "rojo", wood=1)
    give(started, "blanco", ore=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1}, to="azul")
    with pytest.raises(ValueError, match="for azul"):
        started.accept_trade("blanco")
    give(started, "azul", ore=1)
    started.accept_trade("azul")
    assert hand(started, "rojo") == {"ore": 1}


def test_only_the_player_in_turn_can_offer_and_only_in_the_main_phase(started):
    give(started, "azul", wood=1)
    with pytest.raises(ValueError, match="rojo's turn"):
        started.propose_trade("azul", {"wood": 1}, {"ore": 1})
    give(started, "rojo", wood=1)
    started.state.phase = g.ROLL
    with pytest.raises(ValueError, match="Not allowed"):
        started.propose_trade("rojo", {"wood": 1}, {"ore": 1})


@pytest.mark.parametrize(
    ("give_cards", "get_cards", "message"),
    [
        ({}, {"ore": 1}, "at least one"),
        ({"wood": 1}, {}, "at least one"),
        ({"wood": 0}, {"ore": 1}, "at least one"),
        ({"wood": 1}, {"wood": 2}, "same resource"),
        ({"wood": 9}, {"ore": 1}, "does not have those cards"),
        ({"gold": 1}, {"ore": 1}, "Unknown resource"),
    ],
)
def test_bad_offers_are_refused(started, give_cards, get_cards, message):
    give(started, "rojo", wood=3)
    with pytest.raises(ValueError, match=message):
        started.propose_trade("rojo", give_cards, get_cards)
    assert started.state.trade is None


def test_offers_to_yourself_or_to_nobody_are_refused(started):
    give(started, "rojo", wood=1)
    with pytest.raises(ValueError, match="yourself"):
        started.propose_trade("rojo", {"wood": 1}, {"ore": 1}, to="rojo")
    with pytest.raises(ValueError, match="Unknown player"):
        started.propose_trade("rojo", {"wood": 1}, {"ore": 1}, to="verde")


def test_only_one_offer_is_open_at_a_time(started):
    give(started, "rojo", wood=2)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1})
    with pytest.raises(ValueError, match="already open"):
        started.propose_trade("rojo", {"wood": 2}, {"ore": 1})


def test_accepting_needs_the_cards_and_never_your_own_offer(started):
    give(started, "rojo", wood=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 2})
    with pytest.raises(ValueError, match="azul does not have"):
        started.accept_trade("azul")
    with pytest.raises(ValueError, match="your own offer"):
        started.accept_trade("rojo")
    assert started.state.trade is not None  # still open
    assert hand(started, "rojo") == {"wood": 1}


def test_an_offer_that_the_proposer_can_no_longer_pay_is_closed(started):
    give(started, "rojo", wood=1)
    give(started, "azul", ore=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1})
    started.board.add_cards("rojo", "wood", -1)  # the cards were spent meanwhile
    with pytest.raises(ValueError, match="rojo does not have"):
        started.accept_trade("azul")
    assert started.state.trade is None
    assert hand(started, "azul") == {"ore": 1}


def test_accepting_without_an_offer_fails(started):
    with pytest.raises(ValueError, match="no open trade offer"):
        started.accept_trade("azul")
    with pytest.raises(ValueError, match="no open trade offer"):
        started.decline_trade("azul")
    with pytest.raises(ValueError, match="no open trade offer"):
        started.cancel_trade("rojo")


def test_everybody_declining_closes_the_offer(started):
    give(started, "rojo", wood=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1})
    started.decline_trade("azul")
    assert started.state.trade["declined"] == ["azul"]
    started.decline_trade("azul")  # saying no twice changes nothing
    assert started.state.trade["declined"] == ["azul"]
    started.decline_trade("blanco")
    assert started.state.trade is None


def test_an_offer_for_one_player_closes_when_that_player_declines(started):
    give(started, "rojo", wood=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1}, to="azul")
    started.decline_trade("blanco")  # not the one it was meant for: it stays open
    assert started.state.trade is not None
    started.decline_trade("azul")
    assert started.state.trade is None


def test_only_the_proposer_can_cancel(started):
    give(started, "rojo", wood=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1})
    with pytest.raises(ValueError, match="rojo's offer"):
        started.cancel_trade("azul")
    started.cancel_trade("rojo")
    assert started.state.trade is None
    assert hand(started, "rojo") == {"wood": 1}


def test_the_offer_disappears_when_the_turn_ends_and_the_decliner_cannot_be_the_proposer(started):
    give(started, "rojo", wood=1)
    started.propose_trade("rojo", {"wood": 1}, {"ore": 1})
    with pytest.raises(ValueError, match="your own offer"):
        started.decline_trade("rojo")
    started.end_turn()
    assert started.state.trade is None and started.state.last_trade is None


def test_trades_with_several_kinds_of_cards(started):
    give(started, "rojo", wood=2, brick=1)
    give(started, "azul", ore=1, sheep=2)
    started.propose_trade("rojo", {"wood": 2, "brick": 1}, {"ore": 1, "sheep": 2})
    started.accept_trade("azul")
    assert hand(started, "rojo") == {"ore": 1, "sheep": 2}
    assert hand(started, "azul") == {"wood": 2, "brick": 1}


def test_the_offer_survives_a_json_round_trip_and_the_hint_describes_it(started):
    give(started, "rojo", wood=2)
    started.propose_trade("rojo", {"wood": 2}, {"ore": 1}, to="azul")
    loaded = Board.from_dict(json.loads(json.dumps(started.board.to_dict())))
    assert loaded.game.trade["give"] == {"wood": 2} and loaded.game.trade["to"] == "azul"
    hint = started.hint()
    assert "Oferta de rojo para azul" in hint and "2 madera" in hint and "1 mineral" in hint


# Through the dashboard actions


@pytest.fixture
def table():
    app = MagicMock()
    app.catan_manager = CatanManager(board=Board.random(random.Random(9)), rng=random.Random(3))
    app.catan_manager.load_for_map = lambda _path: True
    return app, WorldState()


def send(handler, table, **data):
    app, state = table
    handler(app, {"payload": json.dumps(data)}, state)


def view(table):
    return table[1].catan.to_dict()


def main_phase(table):
    send(handle_catan_new_game, table, players=3)
    board = table[0].catan_manager.board
    while view(table)["game"]["phase"] == "setup":
        player = view(table)["game"]["current_player"]
        vertex = next(
            v
            for v in sorted(board.all_vertices(), key=sorted)
            if all(c in board.tiles for c in v)
            and board.settlement_error(v, player, setup=True) is None
        )
        send(handle_catan_build, table, player=player, vertex=vertex_to_list(vertex))
        edge = next(
            e for e in vertex_edges(vertex) if e in board.all_edges() and e not in board.roads
        )
        send(handle_catan_road, table, player=player, edge=edge_to_list(edge))
    board.game.phase = g.MAIN
    board.hands.clear()
    table[0].catan_manager.publish(table[1])
    return board


def test_a_whole_trade_through_the_actions(table):
    board = main_phase(table)
    board.add_cards("rojo", "wood", 2)
    board.add_cards("azul", "ore", 1)
    send(handle_catan_trade_offer, table, player="rojo", give={"wood": 2}, get={"ore": 1})
    offer = view(table)["game"]["trade"]
    assert offer["from"] == "rojo" and offer["give"] == {"wood": 2}
    send(handle_catan_trade_accept, table, player="azul")
    data = view(table)
    assert data["game"]["trade"] is None
    assert data["game"]["last_trade"]["to"] == "azul"
    assert data["stats"]["rojo"]["hand"]["ore"] == 1 and data["stats"]["azul"]["hand"]["wood"] == 2


def test_declining_and_cancelling_through_the_actions(table):
    board = main_phase(table)
    board.add_cards("rojo", "wood", 1)
    send(
        handle_catan_trade_offer, table, player="rojo", give={"wood": 1}, get={"ore": 1}, to="azul"
    )
    send(handle_catan_trade_decline, table, player="azul")
    assert view(table)["game"]["trade"] is None
    send(handle_catan_trade_offer, table, player="rojo", give={"wood": 1}, get={"ore": 1})
    send(handle_catan_trade_cancel, table, player="rojo")
    assert view(table)["game"]["trade"] is None


def test_refusals_are_explained_in_spanish(table):
    board = main_phase(table)
    send(handle_catan_trade_offer, table, player="rojo", give={"wood": 1}, get={"ore": 1})
    assert view(table)["notice"]["text"] == "rojo no tiene esas cartas"
    send(handle_catan_trade_accept, table, player="azul")
    assert view(table)["notice"]["text"] == "No hay una oferta de comercio abierta"
    board.add_cards("rojo", "wood", 1)
    send(handle_catan_trade_offer, table, player="rojo", give={"wood": 1}, get={"wood": 1})
    assert view(table)["notice"]["text"] == "No se puede cambiar un recurso por el mismo recurso"
    send(handle_catan_trade_offer, table, player="rojo", give="wood", get={"ore": 1})
    assert view(table)["notice"]["text"] == "La oferta no es válida"  # malformed: refused, no crash
    send(handle_catan_trade_offer, table, player="rojo", give={"wood": "mucho"}, get={"ore": 1})
    assert view(table)["notice"]["text"] == "La oferta no es válida"
    send(handle_catan_trade_offer, table, player="azul", give={"wood": 1}, get={"ore": 1})
    assert view(table)["notice"]["text"] == "Es el turno de rojo"


def test_the_roll_action_is_ignored_while_an_offer_is_open_without_errors(table):
    main_phase(table)
    send(handle_catan_roll, table)
    assert view(table)["game"]["phase"] == "main"


# The table: banner, pointing at your panel to accept, highlight


def test_the_banner_shows_the_open_offer_without_accents():
    trade = {
        "from": "rojo",
        "give": {"wood": 2, "brick": 1},
        "get": {"ore": 1},
        "to": None,
        "declined": [],
    }
    text = game_banner({"phase": "main", "current_player": "rojo", "trade": trade})
    assert text == "ROJO OFRECE 2 MAD + 1 LAD POR 1 MIN"
    text = game_banner(
        {"phase": "main", "current_player": "rojo", "trade": {**trade, "to": "azul"}}
    )
    assert text.endswith("(A AZUL)") and text.isascii()
    assert (
        game_banner({"phase": "main", "current_player": "rojo", "trade": None}) == "TURNO DE ROJO"
    )


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
    ctx.map_system.screen_to_world.side_effect = lambda sx, sy: (sx, sy)
    return ctx


def panel_center(board, player):
    x, y, w, h = panel_rect(list(board.players).index(player), W, H)
    return x + w // 2, y + h // 2


def open_offer(table, to=None):
    board = main_phase(table)
    board.add_cards("rojo", "wood", 1)
    send(handle_catan_trade_offer, table, player="rojo", give={"wood": 1}, get={"ore": 1}, to=to)
    return board


def scene_for(context, state):
    context.state = state
    scene = ViewingScene(context)
    scene._find_target_at_point = lambda _pos: None
    return scene


def point(position):
    return [HandInput(GestureType.POINTING, (int(position[0]), int(position[1])), (0.0, 0.0), None)]


def holds(context):
    return [
        c
        for c in context.events.schedule.call_args_list
        if c.kwargs.get("key") == TimerKey.CATAN_STATS_HOLD
    ]


def test_pointing_at_your_own_panel_while_an_offer_is_open_accepts_it(table, context):
    board = open_offer(table)
    board.add_cards("azul", "ore", 1)
    scene = scene_for(context, table[1])
    scene.update(point(panel_center(board, "azul")), [], 0.0)
    assert len(holds(context)) == 1
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    (queued,) = table[1].pending_actions
    assert queued["action"] == "CATAN_TRADE_ACCEPT"
    assert json.loads(queued["payload"]) == {"player": "azul"}
    # and the action really makes the exchange
    handle_catan_trade_accept(table[0], queued, table[1])
    assert view(table)["stats"]["rojo"]["hand"]["ore"] == 1


def test_the_proposer_and_players_not_meant_for_cannot_accept_by_pointing(table, context):
    board = open_offer(table, to="azul")
    scene = scene_for(context, table[1])
    scene.update(point(panel_center(board, "rojo")), [], 0.0)  # the proposer
    scene.update(point(panel_center(board, "blanco")), [], 0.0)  # the offer is for azul
    assert holds(context) == []
    scene.update(point(panel_center(board, "azul")), [], 0.0)
    assert len(holds(context)) == 1


def test_with_no_offer_pointing_at_a_panel_still_toggles_its_mode(table, context):
    board = main_phase(table)
    scene = scene_for(context, table[1])
    scene.update(point(panel_center(board, "azul")), [], 0.0)
    scene.update([], [Action.CATAN_STATS_REQUEST], 1.0)
    (queued,) = table[1].pending_actions
    assert queued["action"] == "CATAN_STATS_MODE"


def feedback(table):
    map_system = MagicMock()
    map_system.screen_to_world.side_effect = lambda sx, sy: (sx, sy)
    map_system.world_to_screen.side_effect = lambda x, y: (int(x), int(y))
    return HandFeedbackLayer(table[1], W, H, map_system)


def test_the_panel_that_can_accept_is_outlined_and_the_ring_says_accept(table):
    board = open_offer(table)
    layer = feedback(table)
    x, y, w, h = panel_rect(list(board.players).index("azul"), W, H)
    table[1].inputs = [HandInput(GestureType.POINTING, panel_center(board, "azul"), (0, 0), None)]
    patches = layer._generate_patches(0.0)
    lights = [p for p in patches if (p.width, p.height) != (PATCH_W, PATCH_H)]
    assert [(p.x, p.y, p.width, p.height) for p in lights] == [(x, y, w, h)]
    table[1].inputs = [HandInput(GestureType.POINTING, panel_center(board, "rojo"), (0, 0), None)]
    assert [
        p for p in layer._generate_patches(0.0) if (p.width, p.height) != (PATCH_W, PATCH_H)
    ] == []


def test_hold_time_is_the_same_as_for_the_other_pointing_actions():
    assert config_vars.CATAN_STATS_HOLD_TIME == 1.0
