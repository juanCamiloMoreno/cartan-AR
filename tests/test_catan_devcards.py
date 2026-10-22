import json
import random
from collections import Counter

import pytest

from light_map.catan import game as g
from light_map.catan.board import COSTS, Board, Building, vertex_edges
from light_map.catan.devcards import (
    ARMY_MIN,
    ARMY_POINTS,
    DECK,
    KNIGHT,
    MONOPOLY,
    ROAD_BUILDING,
    VICTORY_POINT,
    YEAR_OF_PLENTY,
    DevCards,
)
from light_map.catan.game import Game


# The deck and the hands


def test_the_deck_has_the_25_official_cards_shuffled():
    deck = DevCards.new(random.Random(1)).deck
    assert len(deck) == 25 == sum(DECK.values())
    assert Counter(deck) == Counter(DECK)
    assert deck != DevCards.new(random.Random(2)).deck


def test_drawing_takes_the_top_card_into_the_hand_and_an_empty_deck_refuses():
    dev = DevCards(deck=[KNIGHT, MONOPOLY])
    assert dev.draw("rojo") == MONOPOLY
    assert dev.hand("rojo") == Counter({MONOPOLY: 1})
    assert dev.count("rojo") == 1 and dev.deck == [KNIGHT]
    dev.draw("azul")
    with pytest.raises(ValueError, match="empty"):
        dev.draw("rojo")


def test_removing_a_card_you_do_not_have_fails():
    dev = DevCards()
    with pytest.raises(ValueError, match="does not have"):
        dev.remove("rojo", KNIGHT)


def test_the_hidden_victory_points_are_counted_apart():
    dev = DevCards(hands={"rojo": Counter({VICTORY_POINT: 2, KNIGHT: 1})})
    assert dev.victory_points("rojo") == 2 and dev.victory_points("azul") == 0
    assert dev.count("rojo") == 3


def test_the_deck_and_hands_survive_a_round_trip_and_unknown_cards_are_dropped():
    dev = DevCards.new(random.Random(3))
    dev.draw("rojo")
    dev.play_knight("rojo")
    loaded = DevCards.from_dict(json.loads(json.dumps(dev.to_dict())))
    assert loaded.deck == dev.deck and loaded.hands == dev.hands
    assert loaded.knights == {"rojo": 1}
    cleaned = DevCards.from_dict({"deck": ["knight", "dragon"], "hands": {"rojo": {"dragon": 3}}})
    assert cleaned.deck == ["knight"] and cleaned.count("rojo") == 0
    assert DevCards.from_dict(None).deck == []


# Largest army


def test_the_army_needs_three_knights_and_only_a_strictly_bigger_one_takes_it():
    dev = DevCards()
    for _ in range(ARMY_MIN - 1):
        dev.play_knight("rojo")
    assert dev.army_owner is None
    dev.play_knight("rojo")
    assert dev.army_owner == "rojo"
    for _ in range(ARMY_MIN):
        dev.play_knight("azul")
    assert dev.army_owner == "rojo"  # a tie keeps the card where it was
    dev.play_knight("azul")
    assert dev.army_owner == "azul"


# Points


def test_the_army_is_worth_two_points_and_hidden_victory_points_stay_hidden():
    board = Board.random(random.Random(1))
    board.dev.knights["rojo"] = 3
    board.dev.refresh_army()
    board.dev.hands["rojo"] = Counter({VICTORY_POINT: 2})
    assert board.public_points("rojo") == ARMY_POINTS
    assert board.victory_points("rojo") == ARMY_POINTS + 2
    stats = board.player_stats("rojo")
    assert stats["points"] == ARMY_POINTS  # what everybody sees
    assert stats["dev_cards"] == 2 and stats["knights"] == 3 and stats["has_largest_army"]
    assert not board.player_stats("azul")["has_largest_army"]


def test_the_dev_state_is_saved_with_the_board_and_old_boards_have_none():
    board = Board.random(random.Random(1))
    board.dev = DevCards.new(random.Random(2))
    board.dev.draw("rojo")
    loaded = Board.from_dict(json.loads(json.dumps(board.to_dict())))
    assert loaded.dev.deck == board.dev.deck and loaded.dev.hands == board.dev.hands
    data = board.to_dict()
    data.pop("dev")
    assert Board.from_dict(data).dev.deck == []


# In a game


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
        edge = next(
            e for e in vertex_edges(vertex) if e in board.all_edges() and e not in board.roads
        )
        game.build_road(player, edge)
    game.roll((2, 2))
    board.hands.clear()  # the roll may have paid something: start every test with empty hands
    assert game.state.phase == g.MAIN
    return game


def give_card(game, player, card, bought_now=False):
    game.board.dev.hand(player)[card] += 1
    if bought_now:
        game.state.bought.append(card)


def give_cards(game, player, **cards):
    for resource, amount in cards.items():
        game.board.add_cards(player, resource, amount)


def test_a_new_game_starts_with_a_full_shuffled_deck():
    game = Game(Board.random(random.Random(6)), rng=random.Random(2))
    game.board.dev.knights["rojo"] = 5
    game.new_game(2)
    assert len(game.board.dev.deck) == 25 and not game.board.dev.knights
    assert game.board.dev.army_owner is None


# Buying


def test_buying_costs_sheep_wheat_and_ore_and_draws_a_card(started):
    give_cards(started, "rojo", **COSTS["dev"])
    started.board.dev.deck = [MONOPOLY, KNIGHT]
    assert started.buy_dev_card("rojo") == KNIGHT
    assert sum(started.board.hands["rojo"].values()) == 0
    assert started.board.dev.count("rojo") == 1 and len(started.board.dev.deck) == 1
    assert started.state.bought == [KNIGHT]


def test_buying_needs_the_cards_your_turn_the_main_phase_and_a_card_in_the_deck(started):
    with pytest.raises(ValueError, match="Not enough"):
        started.buy_dev_card("rojo")
    give_cards(started, "azul", **COSTS["dev"])
    with pytest.raises(ValueError, match="rojo's turn"):
        started.buy_dev_card("azul")
    give_cards(started, "rojo", **COSTS["dev"])
    started.board.dev.deck = []
    with pytest.raises(ValueError, match="empty"):
        started.buy_dev_card("rojo")
    assert sum(started.board.hands["rojo"].values()) == 3  # nothing was charged
    started.state.phase = g.ROLL
    with pytest.raises(ValueError, match="Not allowed"):
        started.buy_dev_card("rojo")


# Playing rules


def test_a_card_bought_this_turn_cannot_be_played_but_one_from_before_can(started):
    give_card(started, "rojo", KNIGHT, bought_now=True)
    with pytest.raises(ValueError, match="bought this turn"):
        started.play_dev_card("rojo", KNIGHT)
    give_card(started, "rojo", KNIGHT)  # a second knight, held since an earlier turn
    started.play_dev_card("rojo", KNIGHT)
    assert started.state.phase == g.ROBBER


def test_only_one_card_per_turn(started):
    give_card(started, "rojo", YEAR_OF_PLENTY)
    give_card(started, "rojo", MONOPOLY)
    started.play_dev_card("rojo", YEAR_OF_PLENTY, resources=["wood", "ore"])
    with pytest.raises(ValueError, match="Only one"):
        started.play_dev_card("rojo", MONOPOLY, resource="wood")


def test_you_cannot_play_a_card_you_do_not_have_or_a_victory_point_or_on_another_turn(started):
    with pytest.raises(ValueError, match="does not have"):
        started.play_dev_card("rojo", KNIGHT)
    give_card(started, "rojo", VICTORY_POINT)
    with pytest.raises(ValueError, match="cannot be played"):
        started.play_dev_card("rojo", VICTORY_POINT)
    give_card(started, "azul", KNIGHT)
    with pytest.raises(ValueError, match="rojo's turn"):
        started.play_dev_card("azul", KNIGHT)
    started.state.phase = g.DISCARD
    give_card(started, "rojo", KNIGHT)
    with pytest.raises(ValueError, match="Not allowed"):
        started.play_dev_card("rojo", KNIGHT)


def test_the_per_turn_flags_reset_when_the_turn_ends(started):
    give_card(started, "rojo", YEAR_OF_PLENTY, bought_now=True)
    give_card(started, "rojo", YEAR_OF_PLENTY)
    started.play_dev_card("rojo", YEAR_OF_PLENTY, resources=["wood", "wood"])
    started.end_turn()
    assert started.state.dev_played is False and started.state.bought == []
    for _ in range(2):
        started.roll((2, 2))
        started.end_turn()
    started.roll((2, 2))  # rojo again: the card bought two turns ago is playable now
    started.play_dev_card("rojo", YEAR_OF_PLENTY, resources=["ore", "ore"])
    assert started.board.hands["rojo"]["ore"] == 2


# Knight


def test_a_knight_moves_the_robber_and_steals_like_a_seven_without_discarding(started):
    board = started.board
    give_card(started, "rojo", KNIGHT)
    give_cards(started, "azul", wood=9)  # a seven would make azul discard; a knight does not
    target = next(c for c in board.tiles if c != board.robber)
    vertex = next(v for v in board.all_vertices() if target in v and v not in board.buildings)
    board.buildings[vertex] = ("azul", Building.SETTLEMENT)
    started.play_dev_card("rojo", KNIGHT)
    assert started.state.phase == g.ROBBER and started.state.discards == {}
    started.move_robber(target)
    assert started.state.phase == g.STEAL
    started.steal("azul")
    assert started.state.phase == g.MAIN
    assert board.dev.knights["rojo"] == 1


def test_a_knight_played_before_rolling_returns_to_the_roll_phase(started):
    started.end_turn()
    assert started.state.phase == g.ROLL
    give_card(started, "azul", KNIGHT)
    started.play_dev_card("azul", KNIGHT)
    assert started.state.phase == g.ROBBER
    started.move_robber(next(c for c in started.board.tiles if c != started.board.robber))
    assert started.state.phase in (g.STEAL, g.ROLL)
    if started.state.phase == g.STEAL:
        started.steal(started.state.victims[0])
    assert started.state.phase == g.ROLL  # the dice still have to be rolled
    started.roll((2, 2))
    assert started.state.phase == g.MAIN


def test_a_seven_still_goes_back_to_the_main_phase_after_a_knight_was_played_before(started):
    give_card(started, "rojo", KNIGHT)
    started.state.phase = g.ROLL
    started.play_dev_card("rojo", KNIGHT)
    started.move_robber(next(c for c in started.board.tiles if c != started.board.robber))
    if started.state.phase == g.STEAL:
        started.steal(started.state.victims[0])
    started.roll((3, 4))
    started.move_robber(next(c for c in started.board.tiles if c != started.board.robber))
    if started.state.phase == g.STEAL:
        started.steal(started.state.victims[0])
    assert started.state.phase == g.MAIN


def test_the_third_knight_gives_the_largest_army_and_the_points(started):
    board = started.board
    for turn in range(ARMY_MIN):
        give_card(started, "rojo", KNIGHT)
        started.state.dev_played = False
        started.play_dev_card("rojo", KNIGHT)
        started.move_robber(next(c for c in board.tiles if c != board.robber))
        if started.state.phase == g.STEAL:
            started.steal(started.state.victims[0])
        assert (board.dev.army_owner == "rojo") == (turn == ARMY_MIN - 1)
    assert board.public_points("rojo") == board.piece_count("rojo", "settlement") + ARMY_POINTS


# Road building


def test_road_building_places_two_free_roads_and_returns_to_the_turn(started):
    board = started.board
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    assert started.state.phase == g.ROAD_BUILDING_PHASE and started.state.free_roads == 2
    roads_before = board.piece_count("rojo", "road")
    for _ in range(2):
        edge = next(
            e
            for e in board.all_edges()
            if e not in board.roads and board.road_error(e, "rojo") is None
        )
        started.build_road("rojo", edge)
    assert board.piece_count("rojo", "road") == roads_before + 2
    assert sum(board.hands.get("rojo", Counter()).values()) == 0  # nothing paid
    assert started.state.phase == g.MAIN and started.state.free_roads == 0


def test_road_building_rejects_illegal_roads_and_can_be_cut_short(started):
    board = started.board
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    far = next(e for e in board.all_edges() if board.road_error(e, "rojo") and e not in board.roads)
    with pytest.raises(ValueError, match="connect"):
        started.build_road("rojo", far)
    assert started.state.free_roads == 2
    edge = next(
        e for e in board.all_edges() if e not in board.roads and board.road_error(e, "rojo") is None
    )
    started.build_road("rojo", edge)
    started.skip_road_building("rojo")
    assert started.state.phase == g.MAIN and started.state.free_roads == 0
    with pytest.raises(ValueError, match="Not allowed"):
        started.skip_road_building("rojo")


def test_road_building_gives_only_as_many_roads_as_you_have_left(started):
    board = started.board
    spare = [e for e in sorted(board.all_edges(), key=sorted) if e not in board.roads]
    for edge in spare[: 14 - board.piece_count("rojo", "road")]:
        board.roads[edge] = "rojo"  # 14 of the 15 roads are already out
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    if started.state.phase == g.ROAD_BUILDING_PHASE:
        assert started.state.free_roads == 1


def test_road_building_with_no_legal_road_is_spent_without_changing_the_phase(started):
    board = started.board
    for edge in board.all_edges():
        board.roads.setdefault(edge, "azul")  # nowhere left to build
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    assert started.state.phase == g.MAIN and started.state.dev_played
    assert board.dev.count("rojo") == 0


def test_road_building_counts_toward_the_longest_road(started):
    board = started.board
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    for _ in range(2):
        edge = next(
            e
            for e in board.all_edges()
            if e not in board.roads and board.road_error(e, "rojo") is None
        )
        started.build_road("rojo", edge)
    assert board.longest_road_length("rojo") >= 2


# Year of plenty and monopoly


def test_year_of_plenty_gives_two_resources_of_your_choice(started):
    give_card(started, "rojo", YEAR_OF_PLENTY)
    started.play_dev_card("rojo", YEAR_OF_PLENTY, resources=["ore", "ore"])
    assert started.board.hands["rojo"]["ore"] == 2
    assert started.board.dev.count("rojo") == 0


def test_year_of_plenty_needs_exactly_two_known_resources_and_keeps_the_card_otherwise(started):
    give_card(started, "rojo", YEAR_OF_PLENTY)
    for bad in (None, ["wood"], ["wood", "gold"], ["wood", "ore", "ore"]):
        with pytest.raises(ValueError, match="two resources"):
            started.play_dev_card("rojo", YEAR_OF_PLENTY, resources=bad)
    assert started.board.dev.hand("rojo")[YEAR_OF_PLENTY] == 1 and not started.state.dev_played


def test_monopoly_takes_every_card_of_a_resource_from_the_others(started):
    give_card(started, "rojo", MONOPOLY)
    give_cards(started, "rojo", wheat=1)
    give_cards(started, "azul", wheat=3, ore=2)
    give_cards(started, "blanco", wheat=2)
    started.play_dev_card("rojo", MONOPOLY, resource="wheat")
    hands = started.board.hands
    assert hands["rojo"]["wheat"] == 6
    assert hands["azul"]["wheat"] == 0 and hands["blanco"]["wheat"] == 0
    assert hands["azul"]["ore"] == 2  # only the named resource moves


def test_monopoly_needs_a_known_resource(started):
    give_card(started, "rojo", MONOPOLY)
    with pytest.raises(ValueError, match="Choose a resource"):
        started.play_dev_card("rojo", MONOPOLY, resource="gold")
    assert started.board.dev.hand("rojo")[MONOPOLY] == 1


# Victory points


def test_a_victory_point_card_can_win_the_game_when_it_is_bought(started):
    board = started.board
    spare = [
        v
        for v in sorted(board.all_vertices(), key=sorted)
        if all(c in board.tiles for c in v) and v not in board.buildings
    ]
    for vertex in spare[:4]:
        board.buildings[vertex] = ("rojo", Building.CITY)  # 8 points
    for vertex in spare[10:11]:
        board.buildings[vertex] = ("rojo", Building.SETTLEMENT)  # 9 in all with the setup ones
    assert board.victory_points("rojo") >= 9
    board.dev.deck = [VICTORY_POINT]
    give_cards(started, "rojo", **COSTS["dev"])
    started.buy_dev_card("rojo")
    assert started.state.phase == g.FINISHED and started.state.winner == "rojo"


def test_hidden_victory_points_do_not_show_in_the_public_points(started):
    give_card(started, "rojo", VICTORY_POINT)
    assert started.board.victory_points("rojo") == started.board.public_points("rojo") + 1
    assert started.board.player_stats("rojo")["points"] == started.board.public_points("rojo")


def test_the_largest_army_can_win_the_game(started):
    board = started.board
    spare = [
        v
        for v in sorted(board.all_vertices(), key=sorted)
        if all(c in board.tiles for c in v) and v not in board.buildings
    ]
    for vertex in spare[:4]:
        board.buildings[vertex] = ("rojo", Building.CITY)
    board.dev.knights["rojo"] = ARMY_MIN - 1
    give_card(started, "rojo", KNIGHT)
    started.play_dev_card("rojo", KNIGHT)
    assert board.dev.army_owner == "rojo"
    assert started.state.phase == g.FINISHED and started.state.winner == "rojo"


# State and hints


def test_the_card_state_survives_a_json_round_trip(started):
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    loaded = Board.from_dict(json.loads(json.dumps(started.board.to_dict())))
    assert loaded.game.phase == g.ROAD_BUILDING_PHASE
    assert loaded.game.free_roads == 2 and loaded.game.dev_played
    assert loaded.game.resume_phase == g.MAIN


def test_the_hint_for_the_road_building_phase_says_how_many_roads_are_left(started):
    give_card(started, "rojo", ROAD_BUILDING)
    started.play_dev_card("rojo", ROAD_BUILDING)
    assert "2 camino" in started.hint()
