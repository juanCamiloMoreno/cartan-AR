import random
from collections import Counter

import pytest

from light_map.catan.board import (
    COSTS,
    PIECE_LIMITS,
    Board,
    Building,
    edge_vertices,
    edges_of,
    vertex_edges,
    vertex_neighbors,
    vertices_of,
)


@pytest.fixture
def board():
    return Board.random(random.Random(7))


def interior_vertex(board):
    """A vertex whose three tiles are on the board."""
    for cell in board.tiles:
        for vertex in vertices_of(cell):
            if all(c in board.tiles for c in vertex):
                return vertex
    raise AssertionError("no interior vertex")


# Geometry


def test_every_edge_has_two_different_end_vertices_that_know_the_edge(board):
    for edge in board.all_edges():
        first, second = edge_vertices(edge)
        assert first != second
        assert edge in vertex_edges(first)
        assert edge in vertex_edges(second)


def test_vertex_neighbors_are_symmetric_and_one_edge_away(board):
    for vertex in list(board.all_vertices())[:40]:
        neighbors = vertex_neighbors(vertex)
        assert len(neighbors) == 3
        assert vertex not in neighbors
        for other in neighbors:
            assert vertex in vertex_neighbors(other)


# Settlements


def test_settlement_needs_to_be_on_the_board_and_empty(board):
    assert board.settlement_error(frozenset({(9, 9), (9, 10), (10, 9)}), "rojo", setup=True)
    vertex = interior_vertex(board)
    board.build(vertex, "rojo", Building.SETTLEMENT)
    assert "occupied" in board.settlement_error(vertex, "azul", setup=True)


def test_distance_rule_blocks_a_neighbor_vertex_but_not_two_steps_away(board):
    vertex = interior_vertex(board)
    board.build(vertex, "rojo", Building.SETTLEMENT)
    near = vertex_neighbors(vertex)[0]
    assert "distance" in board.settlement_error(near, "azul", setup=True)
    far = next(
        v for v in vertex_neighbors(near) if v != vertex and v not in vertex_neighbors(vertex)
    )
    assert board.settlement_error(far, "azul", setup=True) is None


def test_outside_setup_a_settlement_must_touch_your_own_road(board):
    vertex = interior_vertex(board)
    assert "connected" in board.settlement_error(vertex, "rojo")
    board.toggle_road(vertex_edges(vertex)[0], "rojo")
    assert board.settlement_error(vertex, "rojo") is None
    assert "connected" in board.settlement_error(vertex, "azul")


# Cities


def test_city_replaces_only_your_own_settlement(board):
    vertex = interior_vertex(board)
    assert board.city_error(vertex, "rojo")
    board.build(vertex, "rojo", Building.SETTLEMENT)
    assert board.city_error(vertex, "rojo") is None
    assert board.city_error(vertex, "azul")


# Roads


def test_road_must_connect_to_your_network(board):
    vertex = interior_vertex(board)
    own_edge, other_edge, *_ = vertex_edges(vertex)
    assert "connect" in board.road_error(own_edge, "rojo")
    board.build(vertex, "rojo", Building.SETTLEMENT)
    assert board.road_error(own_edge, "rojo") is None
    assert "connect" in board.road_error(own_edge, "azul")


def test_road_can_extend_from_your_own_road(board):
    vertex = interior_vertex(board)
    first = vertex_edges(vertex)[0]
    board.build(vertex, "rojo", Building.SETTLEMENT)
    board.toggle_road(first, "rojo")
    end = next(v for v in edge_vertices(first) if v != vertex)
    nxt = next(e for e in vertex_edges(end) if e != first and e in board.all_edges())
    assert board.road_error(nxt, "rojo") is None


def test_an_opponent_building_cuts_the_road_network(board):
    vertex = interior_vertex(board)
    first = vertex_edges(vertex)[0]
    board.build(vertex, "rojo", Building.SETTLEMENT)
    board.toggle_road(first, "rojo")
    end = next(v for v in edge_vertices(first) if v != vertex)
    nxt = next(e for e in vertex_edges(end) if e != first and e in board.all_edges())
    board.build(end, "azul", Building.SETTLEMENT)
    assert "connect" in board.road_error(nxt, "rojo")


def test_setup_road_must_start_at_the_new_settlement(board):
    vertex = interior_vertex(board)
    board.build(vertex, "rojo", Building.SETTLEMENT)
    touching = vertex_edges(vertex)[0]
    far = next(e for e in board.all_edges() if vertex not in edge_vertices(e))
    assert board.road_error(touching, "rojo", must_touch=vertex) is None
    assert "just placed" in board.road_error(far, "rojo", must_touch=vertex)


def test_occupied_or_missing_edge_is_rejected(board):
    edge = edges_of((0, 0))[0]
    board.toggle_road(edge, "rojo")
    assert "occupied" in board.road_error(edge, "azul")
    assert "not on the board" in board.road_error(frozenset({(8, 8), (9, 8)}), "rojo")


# Pieces, points and payments


def test_piece_limits_are_enforced(board):
    edges = list(board.all_edges())
    for edge in edges[: PIECE_LIMITS["road"]]:
        board.roads[edge] = "rojo"
    assert board.piece_count("rojo", "road") == PIECE_LIMITS["road"]
    assert "left" in board.check_piece_available("rojo", "road")
    assert board.check_piece_available("azul", "road") is None


def test_victory_points_count_settlements_and_cities(board):
    vertices = [v for v in board.all_vertices() if all(c in board.tiles for c in v)][:3]
    board.buildings[vertices[0]] = ("rojo", Building.SETTLEMENT)
    board.buildings[vertices[1]] = ("rojo", Building.CITY)
    board.buildings[vertices[2]] = ("azul", Building.SETTLEMENT)
    assert board.victory_points("rojo") == 3
    assert board.victory_points("azul") == 1


def test_paying_takes_the_cards_and_refuses_when_short(board):
    for resource, amount in COSTS["settlement"].items():
        board.add_cards("rojo", resource, amount)
    assert board.can_afford("rojo", COSTS["settlement"])
    board.pay("rojo", COSTS["settlement"])
    assert sum(board.hand("rojo").values()) == 0
    assert not board.can_afford("rojo", COSTS["road"])
    with pytest.raises(ValueError):
        board.pay("rojo", COSTS["road"])


def test_second_setup_settlement_pays_one_card_per_adjacent_land_tile(board):
    vertex = interior_vertex(board)
    gains = board.tile_resources_at(vertex)
    land = [c for c in vertex if board.tiles[c].resource != "desert"]
    assert sum(gains.values()) == len(land)
    assert "desert" not in gains
    assert isinstance(gains, Counter)
