import json
import random
from collections import Counter

import pytest

from light_map.catan import generator as gen
from light_map.catan.board import NUMBERS, RESOURCES, Board, Building, Tile, edge_vertices
from light_map.catan.game import MAIN, Game
from light_map.catan.generator import (
    BALANCE_LIMITS,
    BoardRules,
    board_metrics,
    generate_board,
    rule_violations,
)
from light_map.catan.ports import (
    ANY,
    PORT_KINDS,
    PORT_POSITIONS,
    STANDARD_ORDER,
    coast_edges,
    outward_direction,
    place_ports,
)


STRICT = BoardRules(
    allow_adjacent_same_resource=False,
    allow_adjacent_red=False,
    allow_adjacent_low=False,
    allow_adjacent_same_number=False,
)


def make(rules=None, seed=0):
    return generate_board(rules, random.Random(seed))


# The tile mix is always the standard one


@pytest.mark.parametrize("seed", range(5))
def test_every_board_has_the_standard_tile_and_number_mix(seed):
    board, _ = make(STRICT, seed)
    assert Counter(t.resource for t in board.tiles.values()) == Counter(RESOURCES)
    assert Counter(t.number for t in board.tiles.values() if t.number) == Counter(NUMBERS)
    desert = [c for c, t in board.tiles.items() if t.resource == "desert"]
    assert len(desert) == 1 and board.tiles[desert[0]].number is None
    assert board.robber == desert[0]


def test_the_same_seed_gives_the_same_board_and_another_seed_a_different_one():
    one, _ = make(seed=3)
    again, _ = make(seed=3)
    other, _ = make(seed=4)
    assert one.to_dict() == again.to_dict()
    assert one.to_dict() != other.to_dict()


# The checklist


@pytest.mark.parametrize("seed", range(40))
def test_default_rules_never_put_6_and_8_together(seed):
    board, report = make(seed=seed)
    assert rule_violations(board.tiles, BoardRules()) == []
    assert report.satisfied


@pytest.mark.parametrize(
    ("flag", "name"),
    [
        ("allow_adjacent_same_resource", "same_resource"),
        ("allow_adjacent_red", "red"),
        ("allow_adjacent_low", "low"),
        ("allow_adjacent_same_number", "same_number"),
    ],
)
def test_each_rule_is_respected_when_off_and_can_be_broken_when_on(flag, name):
    off = BoardRules(**{flag: False})
    for seed in range(25):
        board, report = make(off, seed)
        assert name not in rule_violations(board.tiles, off), (flag, seed)
        assert report.satisfied

    on = BoardRules(**{flag: True})
    broken = [
        name in rule_violations(make(on, seed)[0].tiles, BoardRules(**{flag: False}))
        for seed in range(60)
    ]
    assert any(broken), f"{flag}=True never produced the situation"


def test_all_rules_off_at_once_is_still_feasible():
    for seed in range(5):
        board, report = make(STRICT, seed)
        assert rule_violations(board.tiles, STRICT) == []
        assert report.satisfied


def test_violations_are_found_on_a_hand_made_board():
    tiles = {
        (0, 0): Tile("wood", 6),
        (1, 0): Tile("wood", 8),  # same resource and 6-8 next to each other
        (0, 1): Tile("ore", 2),
        (1, -1): Tile("sheep", 12),  # 2 and 12 are not neighbors here
        (-1, 1): Tile("brick", 2),  # next to (0, 1)? no: (0,1)-(-1,1) are adjacent, same number
    }
    strict = rule_violations(tiles, STRICT)
    assert {"same_resource", "red", "same_number"} <= set(strict)
    assert rule_violations(tiles, BoardRules(True, True, True, True)) == []


def test_unsatisfiable_rules_return_the_best_board_and_say_so(monkeypatch):
    monkeypatch.setattr(gen, "MAX_ATTEMPTS", 2)
    board, report = generate_board(BoardRules(balance="very_fair"), random.Random(1))
    assert not report.satisfied
    assert report.attempts == 2
    assert len(board.tiles) == 19  # still a playable board


# Fairness


def test_balance_levels_meet_their_limits():
    for level in ("fair", "very_fair"):
        avg_spread, strong, total_spread = BALANCE_LIMITS[level]
        for seed in range(8):
            board, report = make(BoardRules(balance=level), seed)
            metrics = board_metrics(board.tiles)
            assert report.satisfied, (level, seed)
            assert metrics.avg_spread <= avg_spread
            assert metrics.strong_corners <= strong
            assert metrics.total_spread <= total_spread


def test_a_fairer_level_gives_fairer_boards_on_average():
    def mean_spread(level):
        values = [
            board_metrics(make(BoardRules(balance=level), seed)[0].tiles).avg_spread
            for seed in range(15)
        ]
        return sum(values) / len(values)

    assert mean_spread("very_fair") < mean_spread("fair") < mean_spread("random")


def test_metrics_of_a_known_board():
    tiles = {
        (0, 0): Tile("wood", 6),  # 5 pips
        (1, 0): Tile("wood", 12),  # 1 pip
        (0, 1): Tile("ore", 8),  # 5 pips
        (-1, 1): Tile("desert", None),
    }
    metrics = board_metrics(tiles)
    assert metrics.resource_pips == {"wood": 6, "ore": 5}
    assert metrics.resource_avg == {"wood": 3.0, "ore": 5.0}
    assert metrics.avg_spread == 2.0
    assert metrics.total_spread == 1
    assert metrics.best_corner == 11  # corner where wood-6, wood-12 and ore-8 meet
    assert metrics.strong_corners == 0


def test_report_describes_the_attempt():
    _, report = make(BoardRules(balance="fair"), 2)
    data = report.to_dict()
    assert data["satisfied"] is True and data["attempts"] >= 1
    assert data["rules"]["balance"] == "fair"
    assert set(data["metrics"]) >= {"resource_pips", "avg_spread", "strong_corners"}


# The rules object


def test_rules_round_trip_and_partial_input_uses_defaults():
    rules = BoardRules(allow_adjacent_red=True, balance="fair", shuffle_ports=False)
    assert BoardRules.from_dict(rules.to_dict()) == rules
    assert BoardRules.from_dict(None) == BoardRules()
    assert BoardRules.from_dict({"allow_adjacent_low": False}).allow_adjacent_low is False
    with pytest.raises(ValueError, match="balance"):
        BoardRules.from_dict({"balance": "perfect"})


# Ports


def sample_ports(seed=0, shuffle=True):
    board, _ = make(seed=seed)
    return board, board.ports


def test_there_are_nine_ports_four_generic_and_one_per_resource():
    _, ports = sample_ports()
    assert len(ports) == 9
    kinds = Counter(ports.values())
    assert kinds[ANY] == 4
    assert all(kinds[r] == 1 for r in PORT_KINDS if r != ANY)


def test_ports_sit_on_coast_edges_with_land_on_one_side():
    board, ports = sample_ports(5)
    ring = coast_edges(board.tiles)
    assert len(ring) == 30
    for edge in ports:
        assert edge in ring
        assert sum(1 for cell in edge if cell in board.tiles) == 1
        dq, dr = outward_direction(edge, board.tiles)
        assert (dq, dr) != (0, 0)


def test_ports_are_spread_with_gaps_of_three_and_four_edges():
    board, ports = sample_ports(7)
    ring = coast_edges(board.tiles)
    positions = sorted(ring.index(e) for e in ports)
    gaps = sorted(
        (b - a) % 30 for a, b in zip(positions, positions[1:] + [positions[0]], strict=True)
    )
    assert gaps == sorted([3, 4, 3, 3, 4, 3, 3, 4, 3])
    assert PORT_POSITIONS[0] == 0


def test_unshuffled_ports_use_the_fixed_standard_order():
    board = make(BoardRules(shuffle_ports=False), 1)[0]
    ring = coast_edges(board.tiles)
    by_position = [board.ports[ring[p]] for p in PORT_POSITIONS]
    assert by_position == list(STANDARD_ORDER)
    again = make(BoardRules(shuffle_ports=False), 99)[0]
    assert [again.ports[ring[p]] for p in PORT_POSITIONS] == list(STANDARD_ORDER)


def test_shuffled_ports_change_from_board_to_board():
    layouts = {
        tuple(sorted((tuple(sorted(e)), k) for e, k in make(seed=s)[0].ports.items()))
        for s in range(10)
    }
    assert len(layouts) > 5


def test_non_standard_islands_get_no_ports():
    tiles = {(0, 0): Tile("wood", 6), (1, 0): Tile("ore", 8)}
    assert place_ports(tiles, random.Random(1)) == {}


def test_ports_survive_a_json_round_trip_and_old_boards_have_none():
    board, _ = make(seed=2)
    loaded = Board.from_dict(json.loads(json.dumps(board.to_dict())))
    assert loaded.ports == board.ports
    data = board.to_dict()
    data.pop("ports")
    assert Board.from_dict(data).ports == {}


# Trading rates


def port_edge(board, kind):
    return next(e for e, k in board.ports.items() if k == kind)


def test_trade_rate_is_4_without_a_harbor_3_with_a_generic_one_and_2_with_the_matching_one():
    board, _ = make(seed=6)
    assert board.trade_rate("rojo", "wood") == 4

    generic = port_edge(board, ANY)
    board.buildings[edge_vertices(generic)[0]] = ("rojo", Building.SETTLEMENT)
    assert board.trade_rate("rojo", "wood") == 3
    assert board.trade_rate("azul", "wood") == 4

    wood = port_edge(board, "wood")
    board.buildings[edge_vertices(wood)[1]] = ("rojo", Building.CITY)
    assert board.trade_rate("rojo", "wood") == 2
    assert board.trade_rate("rojo", "ore") == 3  # the generic harbor still helps


def test_the_bank_trade_in_a_game_uses_the_harbor_rate():
    board, _ = make(seed=8)
    game = Game(board, rng=random.Random(1))
    game.new_game(2)
    board.buildings[edge_vertices(port_edge(board, "ore"))[0]] = ("rojo", Building.SETTLEMENT)
    game.state.phase = MAIN
    game.state.current = 0
    board.add_cards("rojo", "ore", 2)
    game.bank_trade("rojo", "ore", "wood")  # 2:1
    assert board.hands["rojo"]["ore"] == 0 and board.hands["rojo"]["wood"] == 1
    board.add_cards("rojo", "wood", 2)  # 3 wood in hand
    with pytest.raises(ValueError, match="Not enough"):
        game.bank_trade("rojo", "wood", "brick")  # no wood harbor: needs 4
