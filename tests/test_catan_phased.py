import json
import random
from collections import Counter

import pytest

from light_map.catan import game as g
from light_map.catan.board import Board, vertex_edges
from light_map.catan.game import Game


@pytest.fixture
def game():
    return Game(Board.random(random.Random(5)), rng=random.Random(9))


def start(game, players=3):
    game.new_game(players, phased=True)
    return game


def roll_order(game, values):
    """Everybody pending rolls the given values in order."""
    for value in values:
        player = game.order_pending()[0]
        game.order_roll(player, value)


def finish_order(game):
    """Roll so that rojo > azul > blanco (> naranja)."""
    while game.state.phase == g.ORDER:
        pending = game.order_pending()
        rank = {"rojo": 6, "azul": 5, "blanco": 4, "naranja": 3}
        for player in pending:
            game.order_roll(player, rank[player])


def free_settlement(board, player):
    return next(
        v
        for v in sorted(board.all_vertices(), key=sorted)
        if all(c in board.tiles for c in v)
        and board.settlement_error(v, player, setup=True) is None
    )


def play_setup(game):
    board = game.board
    placed = []
    while game.state.phase == g.SETUP:
        player = game.current_player
        vertex = free_settlement(board, player)
        game.build(player, vertex)
        game.build_road(
            player,
            next(
                e for e in vertex_edges(vertex) if e in board.all_edges() and e not in board.roads
            ),
        )
        placed.append((player, vertex))
    return placed


# Starting


def test_a_phased_game_starts_hidden_and_waiting_for_the_order_rolls(game):
    start(game)
    state = game.state
    assert state.phase == g.ORDER and state.phased and state.hidden
    assert state.order == [] and state.order_groups == [["rojo", "azul", "blanco"]]
    assert sorted(state.tile_order) == sorted(game.board.tiles)
    assert game.order_pending() == ["rojo", "azul", "blanco"]
    assert game.current_player == "rojo"


def test_a_normal_new_game_is_not_phased_and_shows_everything(game):
    game.new_game(3)
    assert game.state.phase == g.SETUP and not game.state.phased and not game.state.hidden
    cell = next(iter(game.board.tiles))
    assert game.visible(cell) == (game.board.tiles[cell].resource, game.board.tiles[cell].number)


def test_the_number_reveal_follows_a_spiral_from_the_outside_in(game):
    start(game)
    order = game.state.number_order
    tiles = game.board.tiles
    assert len(order) == 18 and all(tiles[c].number is not None for c in order)

    def ring(cell):
        q, r = cell
        return max(abs(q), abs(r), abs(q + r))

    rings = [ring(c) for c in order]
    assert rings == sorted(rings, reverse=True)  # outer ring first, center last


# Turn order


def test_the_highest_die_goes_first_and_the_order_is_set(game):
    start(game)
    roll_order(game, [2, 6, 4])  # rojo 2, azul 6, blanco 4
    assert game.state.phase == g.SETUP
    assert game.state.order == ["azul", "blanco", "rojo"]
    assert game.current_player == "azul"


def test_only_a_pending_player_can_roll_and_the_die_is_one_to_six(game):
    start(game)
    with pytest.raises(ValueError, match="does not have to roll"):
        game.order_roll("naranja", 3)
    with pytest.raises(ValueError, match="1 to 6"):
        game.order_roll("rojo", 7)
    game.order_roll("rojo", 3)
    with pytest.raises(ValueError, match="does not have to roll"):
        game.order_roll("rojo", 4)


def test_a_player_can_let_the_app_roll(game):
    start(game, 2)
    assert 1 <= game.order_roll("rojo") <= 6


def test_ties_roll_again_only_among_the_tied_players(game):
    start(game, 4)
    roll_order(game, [5, 5, 3, 1])  # rojo and azul tie for first
    assert game.state.phase == g.ORDER
    assert game.state.order_groups == [["rojo", "azul"], ["blanco"], ["naranja"]]
    assert game.order_pending() == ["rojo", "azul"]
    with pytest.raises(ValueError, match="does not have to roll"):
        game.order_roll("blanco", 6)
    roll_order(game, [2, 6])  # azul wins the tie
    assert game.state.order == ["azul", "rojo", "blanco", "naranja"]
    assert game.state.phase == g.SETUP


def test_everybody_tied_rolls_again_until_it_is_settled(game):
    start(game, 2)
    roll_order(game, [4, 4])
    assert game.state.order_groups == [["rojo", "azul"]]
    roll_order(game, [4, 4])
    roll_order(game, [1, 3])
    assert game.state.order == ["azul", "rojo"]


def test_order_rolls_are_only_allowed_in_the_order_phase(game):
    game.new_game(2)
    with pytest.raises(ValueError, match="Not allowed"):
        game.order_roll("rojo", 3)


# Hidden board and setup


def test_nothing_is_visible_before_the_reveal(game):
    start(game)
    assert all(game.visible(c) == (None, None) for c in game.board.tiles)


def test_setup_follows_the_rolled_order_and_pays_nothing_yet(game):
    start(game)
    roll_order(game, [2, 6, 4])
    placed = play_setup(game)
    assert [p for p, _ in placed] == ["azul", "blanco", "rojo", "rojo", "blanco", "azul"]
    assert game.state.phase == g.REVEAL
    assert not any(game.board.hands.values())
    assert len(game.state.pending_payout) == 3  # the second settlement of each player


# Reveal


def reach_reveal(game, players=3):
    start(game, players)
    finish_order(game)
    play_setup(game)
    assert game.state.phase == g.REVEAL


def test_the_reveal_shows_every_tile_then_every_number_one_by_one(game):
    reach_reveal(game)
    state = game.state
    first = state.tile_order[0]
    assert game.reveal_next() == "tile"
    assert game.visible(first)[0] == game.board.tiles[first].resource
    assert game.visible(first)[1] is None  # numbers come later
    for _ in range(18):
        assert game.reveal_next() == "tile"
    assert all(game.visible(c)[0] is not None for c in game.board.tiles)
    assert all(game.visible(c)[1] is None for c in game.board.tiles)
    number_cell = state.number_order[0]
    assert game.reveal_next() == "number"
    assert game.visible(number_cell)[1] == game.board.tiles[number_cell].number
    assert game.reveal_total() == (20, 37)


def test_revealing_the_last_number_ends_the_reveal_and_pays_the_second_settlements(game):
    reach_reveal(game)
    expected = Counter()
    payouts = {}
    for player, vertex in game.state.pending_payout:
        payouts.setdefault(player, Counter()).update(game.board.tile_resources_at(vertex))
        expected.update(game.board.tile_resources_at(vertex))
    for _ in range(37):
        assert game.state.phase == g.REVEAL
        game.reveal_next()
    assert game.state.phase == g.ROLL and not game.state.hidden
    assert game.state.turn == 1 and game.current_player == game.state.order[0]
    assert game.state.pending_payout == []
    for player, gains in payouts.items():
        assert game.board.hands[player] == gains


def test_reveal_all_skips_the_animation(game):
    reach_reveal(game)
    game.reveal_next()
    game.reveal_all()
    assert game.state.phase == g.ROLL and not game.state.hidden
    cell = next(iter(game.board.tiles))
    assert game.visible(cell) == (game.board.tiles[cell].resource, game.board.tiles[cell].number)


def test_the_reveal_only_works_in_its_phase(game):
    start(game)
    with pytest.raises(ValueError, match="Not allowed"):
        game.reveal_next()
    with pytest.raises(ValueError, match="Not allowed"):
        game.reveal_all()


def test_the_game_continues_normally_after_the_reveal(game):
    reach_reveal(game)
    game.reveal_all()
    assert game.roll((2, 2)) == 4
    assert game.state.phase == g.MAIN


# Persistence and hints


def test_the_phased_state_survives_a_json_round_trip(game):
    reach_reveal(game)
    game.reveal_next()
    data = json.loads(json.dumps(game.board.to_dict()))
    loaded = Board.from_dict(data).game
    state = game.state
    assert loaded.phase == g.REVEAL and loaded.hidden and loaded.phased
    assert loaded.tile_order == state.tile_order
    assert loaded.number_order == state.number_order
    assert loaded.tiles_shown == 1
    assert loaded.pending_payout == state.pending_payout
    assert loaded.order == state.order


def test_the_order_state_survives_a_round_trip(game):
    start(game, 3)
    game.order_roll("rojo", 4)
    loaded = Board.from_dict(json.loads(json.dumps(game.board.to_dict()))).game
    assert loaded.order_rolls == {"rojo": 4}
    assert loaded.order_groups == [["rojo", "azul", "blanco"]]


def test_hints_explain_the_new_phases(game):
    start(game, 3)
    game.order_roll("rojo", 4)
    assert "azul" in game.hint() and "rojo 4" in game.hint()
    finish_order(game)
    play_setup(game)
    game.reveal_next()
    assert "1 de 37" in game.hint()
