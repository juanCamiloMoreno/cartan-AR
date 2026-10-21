import random
from collections import Counter

import pytest

from light_map.catan.board import (
    Board,
    Building,
    Tile,
    axial_cells,
    neighbors,
    roll_dice,
    vertices_of,
)


def make_board() -> Board:
    """Small deterministic board: wood 6 at (0,0), brick 8 at (1,0), desert at (-1,0)."""
    tiles = {
        (0, 0): Tile("wood", 6),
        (1, 0): Tile("brick", 8),
        (-1, 0): Tile("desert", None),
    }
    return Board(tiles, robber=(-1, 0))


def test_standard_board_has_19_tiles_and_correct_resources():
    board = Board.random(random.Random(1))
    assert len(board.tiles) == 19
    counts = Counter(t.resource for t in board.tiles.values())
    assert counts == {"wood": 4, "sheep": 4, "wheat": 4, "brick": 3, "ore": 3, "desert": 1}
    numbers = sorted(t.number for t in board.tiles.values() if t.number)
    assert numbers == [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]


def test_robber_starts_on_desert():
    board = Board.random(random.Random(2))
    assert board.tiles[board.robber].resource == "desert"


def test_no_adjacent_red_numbers():
    for seed in range(20):
        board = Board.random(random.Random(seed))
        hot = [c for c, t in board.tiles.items() if t.number in (6, 8)]
        assert not any(neighbors(a, b) for i, a in enumerate(hot) for b in hot[i + 1 :])


def test_axial_cells_count():
    assert len(axial_cells()) == 19


def test_tile_has_six_distinct_vertices_each_shared_with_neighbors():
    verts = vertices_of((0, 0))
    assert len(set(verts)) == 6
    # Every vertex touches 3 tiles, including this one.
    assert all((0, 0) in v and len(v) == 3 for v in verts)
    # Adjacent tiles share exactly 2 vertices.
    assert len(set(verts) & set(vertices_of((1, 0)))) == 2


def test_roll_dice_range_and_determinism():
    rolls = [roll_dice(random.Random(5)) for _ in range(3)]
    assert len(set(rolls)) == 1
    d1, d2 = rolls[0]
    assert 1 <= d1 <= 6 and 1 <= d2 <= 6


def test_settlement_produces_one_city_produces_two():
    board = make_board()
    shared = set(vertices_of((0, 0)))
    v_settle, v_city = sorted(shared, key=sorted)[:2]
    board.build(v_settle, "ana", Building.SETTLEMENT)
    board.build(v_city, "beto", Building.SETTLEMENT)
    board.build(v_city, "beto", Building.CITY)
    out = board.production(6)
    assert out == {"ana": Counter(wood=1), "beto": Counter(wood=2)}


def test_building_on_two_matching_tiles_pays_both():
    board = Board(
        {(0, 0): Tile("wood", 6), (1, 0): Tile("brick", 6), (0, 1): Tile("ore", 6)},
        robber=(5, 5),
    )
    vertex = frozenset({(0, 0), (1, 0), (0, 1)})
    board.build(vertex, "ana", Building.SETTLEMENT)
    assert board.production(6) == {"ana": Counter(wood=1, brick=1, ore=1)}


def test_wrong_number_produces_nothing():
    board = make_board()
    board.build(vertices_of((0, 0))[0], "ana", Building.SETTLEMENT)
    assert board.production(5) == {}


def test_robber_blocks_production_of_its_tile():
    board = make_board()
    board.build(vertices_of((0, 0))[0], "ana", Building.SETTLEMENT)
    board.move_robber((0, 0))
    assert board.production(6) == {}
    board.move_robber((1, 0))
    assert board.production(6) == {"ana": Counter(wood=1)}


def test_seven_produces_nothing():
    board = make_board()
    board.build(vertices_of((0, 0))[0], "ana", Building.SETTLEMENT)
    assert board.production(7) == {}


def test_move_robber_must_change_tile_and_stay_on_board():
    board = make_board()
    with pytest.raises(ValueError):
        board.move_robber((-1, 0))  # already there
    with pytest.raises(ValueError):
        board.move_robber((9, 9))  # not on board


def test_stealable_players_exclude_mover_and_duplicates():
    board = make_board()
    vs = sorted(vertices_of((0, 0)), key=sorted)
    board.build(vs[0], "ana", Building.SETTLEMENT)
    board.build(vs[1], "ana", Building.SETTLEMENT)
    board.build(vs[1], "ana", Building.CITY)
    board.build(vs[2], "beto", Building.SETTLEMENT)
    assert board.stealable_players((0, 0), mover="ana") == ["beto"]
    assert sorted(board.stealable_players((0, 0), mover="carla")) == ["ana", "beto"]


def test_build_rejects_occupied_vertex_and_bad_upgrade():
    board = make_board()
    v = vertices_of((0, 0))[0]
    board.build(v, "ana", Building.SETTLEMENT)
    with pytest.raises(ValueError):
        board.build(v, "beto", Building.SETTLEMENT)
    with pytest.raises(ValueError):
        board.build(v, "beto", Building.CITY)  # only the owner can upgrade
    board.build(v, "ana", Building.CITY)
    assert board.buildings[v] == ("ana", Building.CITY)
    with pytest.raises(ValueError):
        board.build(v, "ana", Building.CITY)  # already a city
    with pytest.raises(ValueError):
        board.build(vertices_of((1, 0))[0], "ana", Building.CITY)  # no settlement yet


def test_discard_required_for_hands_over_seven():
    from light_map.catan.board import players_to_discard

    hands = {"ana": 8, "beto": 7, "carla": 10}
    assert players_to_discard(hands) == {"ana": 4, "carla": 5}
