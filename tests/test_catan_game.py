import json
import random

import pytest

from light_map.catan import game as g
from light_map.catan.board import (
    COSTS,
    Board,
    Building,
    edge_vertices,
    vertex_edges,
    vertex_neighbors,
)
from light_map.catan.game import Game, GameState


# Helpers


@pytest.fixture
def game():
    board = Board.random(random.Random(11))
    return Game(board, rng=random.Random(5))


def land_vertices(board):
    return sorted(
        (v for v in board.all_vertices() if all(c in board.tiles for c in v)),
        key=lambda v: sorted(v),
    )


def free_settlement(board, player):
    return next(
        v for v in land_vertices(board) if board.settlement_error(v, player, setup=True) is None
    )


def some_edge_at(board, vertex):
    return next(e for e in vertex_edges(vertex) if e in board.all_edges() and e not in board.roads)


def play_setup(game):
    """Plays every setup turn with the first legal move."""
    board = game.board
    while game.state.phase == g.SETUP:
        player = game.current_player
        vertex = free_settlement(board, player)
        game.build(player, vertex)
        game.build_road(player, some_edge_at(board, vertex))


def give(board, player, **cards):
    for resource, amount in cards.items():
        board.add_cards(player, resource, amount)


@pytest.fixture
def started(game):
    game.new_game(3)
    play_setup(game)
    return game


# Starting


def test_boards_start_in_free_mode():
    assert Board.random().game.phase == g.FREE


def test_new_game_resets_the_board_and_starts_setup(game):
    board = game.board
    board.build(land_vertices(board)[0], "rojo", Building.SETTLEMENT)
    give(board, "rojo", wood=3)
    game.new_game(3)
    assert game.state.phase == g.SETUP
    assert board.players == ["rojo", "azul", "blanco"]
    assert not board.buildings and not board.roads and not any(board.hands.values())
    assert board.tiles[board.robber].resource == "desert"
    assert game.current_player == "rojo"


def test_setup_order_goes_forward_then_backward(game):
    game.new_game(3)
    order = []
    while game.state.phase == g.SETUP:
        player = game.current_player
        order.append(player)
        vertex = free_settlement(game.board, player)
        game.build(player, vertex)
        game.build_road(player, some_edge_at(game.board, vertex))
    assert order == ["rojo", "azul", "blanco", "blanco", "azul", "rojo"]


def test_setup_rejects_the_wrong_player_and_the_wrong_step(game):
    game.new_game(2)
    vertex = free_settlement(game.board, "azul")
    with pytest.raises(ValueError, match="rojo's turn"):
        game.build("azul", vertex)
    with pytest.raises(ValueError, match="settlement first"):
        game.build_road("rojo", some_edge_at(game.board, vertex))
    game.build("rojo", vertex)
    with pytest.raises(ValueError, match="road next"):
        game.build("rojo", free_settlement(game.board, "rojo"))


def test_setup_road_must_start_at_the_settlement_just_placed(game):
    game.new_game(2)
    board = game.board
    vertex = free_settlement(board, "rojo")
    game.build("rojo", vertex)
    far = next(e for e in board.all_edges() if vertex not in edge_vertices(e))
    with pytest.raises(ValueError, match="just placed"):
        game.build_road("rojo", far)
    assert game.state.setup_step == "road"


def test_setup_respects_the_distance_rule(game):
    game.new_game(2)
    board = game.board
    vertex = free_settlement(board, "rojo")
    game.build("rojo", vertex)
    game.build_road("rojo", some_edge_at(board, vertex))
    with pytest.raises(ValueError, match="distance"):
        game.build("azul", vertex_neighbors(vertex)[0])


def test_second_round_settlement_pays_the_adjacent_tiles_and_first_does_not(game):
    game.new_game(2)
    board = game.board
    first = free_settlement(board, "rojo")
    game.build("rojo", first)
    assert sum(board.hands["rojo"].values()) == 0 if "rojo" in board.hands else True
    game.build_road("rojo", some_edge_at(board, first))
    for _ in range(2):  # azul's first turn and then azul's second turn comes before rojo's
        player = game.current_player
        vertex = free_settlement(board, player)
        game.build(player, vertex)
        expected = board.tile_resources_at(vertex)
        game.build_road(player, some_edge_at(board, vertex))
    assert board.hands["azul"] == expected


def test_setup_ends_in_the_roll_phase_for_the_first_player(started):
    assert started.state.phase == g.ROLL
    assert started.current_player == "rojo"
    assert started.state.turn == 1
    assert all(started.board.piece_count(p, "settlement") == 2 for p in started.state.order)
    assert all(started.board.piece_count(p, "road") == 2 for p in started.state.order)


# Rolling


def test_only_the_roll_phase_allows_rolling(started):
    started.roll((2, 2))
    with pytest.raises(ValueError, match="Not allowed"):
        started.roll((2, 2))


def test_a_roll_moves_to_the_main_phase(started):
    assert started.roll((3, 3)) == 6
    assert started.state.phase == g.MAIN


def test_roll_pays_the_owner_of_a_building_on_that_number(started):
    board = started.board
    for cell, tile in board.tiles.items():
        if tile.number and cell != board.robber:
            vertex = next(
                (v for v in land_vertices(board) if cell in v and v not in board.buildings), None
            )
            if vertex and all(n not in board.buildings for n in vertex_neighbors(vertex)):
                board.build(vertex, "rojo", Building.SETTLEMENT)
                board.hands.clear()
                total = tile.number
                dice = (total // 2, total - total // 2)
                started.roll(dice)
                assert board.hands["rojo"][tile.resource] >= 1
                return
    pytest.fail("no usable tile")


def test_seven_without_big_hands_goes_straight_to_the_robber(started):
    started.board.hands.clear()
    started.roll((3, 4))
    assert started.state.phase == g.ROBBER


def test_seven_makes_players_with_more_than_seven_cards_discard_half(started):
    board = started.board
    board.hands.clear()
    give(board, "azul", wood=5, brick=4)  # 9 cards -> discard 4
    give(board, "blanco", ore=7)  # exactly 7 -> keeps everything
    started.roll((3, 4))
    assert started.state.phase == g.DISCARD
    assert started.state.discards == {"azul": 4}

    with pytest.raises(ValueError, match="exactly 4"):
        started.discard("azul", {"wood": 2})
    with pytest.raises(ValueError, match="does not have to"):
        started.discard("blanco", {"ore": 1})
    with pytest.raises(ValueError, match="Not enough"):
        started.discard("azul", {"wheat": 4})
    started.discard("azul", {"wood": 3, "brick": 1})
    assert sum(board.hands["azul"].values()) == 5
    assert started.state.phase == g.ROBBER


# Robber


def prepare_robber(game, victim_cards=True):
    board = game.board
    board.hands.clear()
    target = next(c for c in board.tiles if c != board.robber)
    vertex = next(v for v in land_vertices(board) if target in v)
    for v in list(board.buildings):
        if target in v:
            del board.buildings[v]
    board.buildings[vertex] = ("azul", Building.SETTLEMENT)
    if victim_cards:
        give(board, "azul", wood=2, ore=1)
    game.roll((3, 4))
    assert game.state.phase == g.ROBBER
    return target


def test_robber_must_move_to_a_different_tile_and_only_in_its_phase(started):
    with pytest.raises(ValueError, match="Not allowed"):
        started.move_robber((0, 0))
    prepare_robber(started)
    with pytest.raises(ValueError, match="different tile"):
        started.move_robber(started.board.robber)
    assert started.state.phase == g.ROBBER


def test_robber_with_a_victim_that_has_cards_goes_to_the_steal_phase(started):
    target = prepare_robber(started)
    started.move_robber(target)
    assert started.board.robber == target
    assert started.state.phase == g.STEAL
    assert started.state.victims == ["azul"]


def test_robber_where_nobody_can_be_robbed_goes_straight_to_main(started):
    target = prepare_robber(started, victim_cards=False)
    started.move_robber(target)
    assert started.state.phase == g.MAIN


def test_steal_moves_one_random_card_to_the_current_player(started):
    target = prepare_robber(started)
    started.move_robber(target)
    with pytest.raises(ValueError, match="cannot be robbed"):
        started.steal("blanco")
    resource = started.steal("azul")
    board = started.board
    assert sum(board.hands["azul"].values()) == 2
    assert board.hands["rojo"][resource] == 1
    assert started.state.phase == g.MAIN


# Main phase


def test_building_needs_the_cards_and_the_turn(started):
    started.roll((2, 2))
    board = started.board
    board.hands.clear()
    spot = free_settlement(board, "rojo")  # far from every settlement
    board.toggle_road(some_edge_at(board, spot), "rojo")  # a road of rojo reaching it
    with pytest.raises(ValueError, match="Not enough cards"):
        started.build("rojo", spot)
    give(board, "rojo", **COSTS["settlement"])
    with pytest.raises(ValueError, match="rojo's turn"):
        started.build("azul", spot)
    started.build("rojo", spot)
    assert board.buildings[spot] == ("rojo", Building.SETTLEMENT)
    assert sum(board.hands["rojo"].values()) == 0


def test_city_upgrade_costs_and_scores(started):
    started.roll((2, 2))
    board = started.board
    board.hands.clear()
    vertex = next(v for v, (p, _) in board.buildings.items() if p == "rojo")
    with pytest.raises(ValueError, match="Not enough"):
        started.build("rojo", vertex)
    give(board, "rojo", **COSTS["city"])
    started.build("rojo", vertex)
    assert board.buildings[vertex] == ("rojo", Building.CITY)
    assert board.victory_points("rojo") == 3


def test_road_costs_cards_and_must_connect(started):
    started.roll((2, 2))
    board = started.board
    board.hands.clear()
    edge = next(
        e for e in board.all_edges() if e not in board.roads and board.road_error(e, "rojo") is None
    )
    with pytest.raises(ValueError, match="Not enough"):
        started.build_road("rojo", edge)
    give(board, "rojo", **COSTS["road"])
    started.build_road("rojo", edge)
    assert board.roads[edge] == "rojo"
    far = next(e for e in board.all_edges() if e not in board.roads and board.road_error(e, "rojo"))
    give(board, "rojo", **COSTS["road"])
    with pytest.raises(ValueError, match="connect"):
        started.build_road("rojo", far)


def test_reaching_ten_points_ends_the_game(started):
    started.roll((2, 2))
    board = started.board
    board.hands.clear()
    spare = [v for v in land_vertices(board) if v not in board.buildings]
    for vertex in spare[:3]:
        board.buildings[vertex] = ("rojo", Building.CITY)  # 6 points
    for vertex in spare[3:5]:
        board.buildings[vertex] = ("rojo", Building.SETTLEMENT)  # 2 more, 4 settlements in all
    assert board.victory_points("rojo") == 10 - 0
    vertex = next(
        v for v, (p, k) in board.buildings.items() if p == "rojo" and k is Building.SETTLEMENT
    )
    give(board, "rojo", **COSTS["city"])
    started.build("rojo", vertex)
    assert board.victory_points("rojo") >= 10
    assert started.state.phase == g.FINISHED
    assert started.state.winner == "rojo"
    assert started.current_player is None
    with pytest.raises(ValueError, match="Not allowed"):
        started.end_turn()


def test_bank_trade_four_for_one(started):
    started.roll((2, 2))
    board = started.board
    board.hands.clear()
    give(board, "rojo", wood=5)
    started.bank_trade("rojo", "wood", "ore")
    assert board.hands["rojo"]["wood"] == 1 and board.hands["rojo"]["ore"] == 1
    with pytest.raises(ValueError, match="Not enough"):
        started.bank_trade("rojo", "wood", "ore")
    with pytest.raises(ValueError, match="different"):
        started.bank_trade("rojo", "wood", "wood")
    with pytest.raises(ValueError, match="rojo's turn"):
        started.bank_trade("azul", "wood", "ore")


def test_end_turn_passes_to_the_next_player_who_must_roll(started):
    started.roll((2, 2))
    started.end_turn()
    assert started.current_player == "azul"
    assert started.state.phase == g.ROLL
    assert started.state.turn == 2
    started.roll((2, 2))
    started.end_turn()
    started.roll((2, 2))
    started.end_turn()
    assert started.current_player == "rojo"


def test_cannot_end_the_turn_before_rolling(started):
    with pytest.raises(ValueError, match="Not allowed"):
        started.end_turn()


def test_free_play_leaves_the_game(started):
    started.free_play()
    assert not started.active
    assert started.current_player is None


# Persistence and hints


def test_game_state_survives_a_json_round_trip(started):
    started.roll((3, 4))
    data = json.loads(json.dumps(started.board.to_dict()))
    loaded = Board.from_dict(data)
    assert loaded.game.phase == started.state.phase
    assert loaded.game.order == started.state.order
    assert loaded.game.last_dice == (3, 4)
    assert loaded.game.turn == started.state.turn


def test_old_boards_without_game_data_are_in_free_mode():
    data = Board.random(random.Random(1)).to_dict()
    data.pop("game")
    assert Board.from_dict(data).game.phase == g.FREE


def test_unknown_phase_in_a_file_falls_back_to_free():
    assert GameState.from_dict({"phase": "weird"}).phase == g.FREE


def test_there_is_a_hint_for_every_phase(started):
    seen = set()
    for phase in g.PHASES:
        started.state.phase = phase
        started.state.winner = "rojo"
        started.state.discards = {"azul": 2}
        started.state.victims = ["azul"]
        hint = started.hint()
        assert hint
        seen.add(hint)
    assert len(seen) == len(g.PHASES)
