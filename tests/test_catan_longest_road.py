import json
import random
import time

import pytest

from light_map.catan import game as g
from light_map.catan.board import (
    COSTS,
    LONGEST_ROAD_MIN,
    LONGEST_ROAD_POINTS,
    Board,
    Building,
    edge_vertices,
    edges_of,
    vertex_edges,
)
from light_map.catan.game import Game


@pytest.fixture
def board():
    return Board.random(random.Random(4))


def path_of(board, count, start=None, avoid=()):
    """`count` edges in a line (no vertex repeated), starting at `start`."""
    vertices = sorted(
        (v for v in board.all_vertices() if all(c in board.tiles for c in v)), key=sorted
    )
    for first in [start] if start else vertices:
        edges, seen, here = [], {first}, first
        while len(edges) < count:
            step = next(
                (
                    (e, other)
                    for e in vertex_edges(here)
                    if e in board.all_edges() and e not in edges and e not in avoid
                    for other in [next(v for v in edge_vertices(e) if v != here)]
                    if other not in seen
                ),
                None,
            )
            if step is None:
                break
            edges.append(step[0])
            seen.add(step[1])
            here = step[1]
        if len(edges) == count:
            return edges
    raise AssertionError("no path found")


def lay(board, player, edges):
    for edge in edges:
        board.roads[edge] = player  # no refresh: the tests call refresh themselves
    board.refresh_longest_road()


def shared_vertices(edges):
    """Vertices between consecutive edges of a line."""
    return [
        next(iter(set(edge_vertices(a)) & set(edge_vertices(b))))
        for a, b in zip(edges, edges[1:], strict=False)
    ]


# The length of a line


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8])
def test_a_straight_line_counts_its_roads(board, count):
    lay(board, "rojo", path_of(board, count))
    assert board.longest_road_length("rojo") == count


def test_no_roads_means_zero(board):
    assert board.longest_road_length("rojo") == 0


def test_a_branch_only_counts_its_longest_arm(board):
    # a vertex with arms of 3, 2 and 1 roads: the best line takes the two longest arms
    center = next(
        v for v in sorted(board.all_vertices(), key=sorted) if all(c in board.tiles for c in v)
    )
    first, second, third = vertex_edges(center)
    arm_a = [first] + path_of(
        board,
        2,
        start=next(v for v in edge_vertices(first) if v != center),
        avoid={first, second, third},
    )
    arm_b = [second] + path_of(
        board,
        1,
        start=next(v for v in edge_vertices(second) if v != center),
        avoid={first, second, third} | set(arm_a),
    )
    lay(board, "rojo", arm_a + arm_b + [third])
    assert (len(arm_a), len(arm_b)) == (3, 2)
    assert board.longest_road_length("rojo") == 5  # arms of 3 and 2; the arm of 1 is left out


def test_a_closed_loop_counts_all_its_roads(board):
    lay(board, "rojo", edges_of((0, 0)))  # the six sides of a hexagon
    assert board.longest_road_length("rojo") == 6


def test_a_loop_with_a_tail_counts_the_tail_plus_the_whole_loop(board):
    ring = edges_of((0, 0))
    ring_vertices = {v for e in ring for v in edge_vertices(e)}
    start = next(v for v in sorted(ring_vertices, key=sorted))
    tail = next(e for e in vertex_edges(start) if e in board.all_edges() and e not in ring)
    lay(board, "rojo", ring + [tail])
    assert board.longest_road_length("rojo") == 7


def test_figure_eight_of_two_loops_uses_every_road(board):
    # two hexagons sharing one side: 11 distinct roads, all reachable in a single trail
    ring_a = set(edges_of((0, 0)))
    ring_b = set(edges_of((1, 0)))
    lay(board, "rojo", sorted(ring_a | ring_b, key=sorted))
    assert len(ring_a | ring_b) == 11
    assert board.longest_road_length("rojo") >= 10


def test_other_players_roads_do_not_count(board):
    edges = path_of(board, 6)
    lay(board, "rojo", edges[:3])
    lay(board, "azul", edges[3:])
    assert board.longest_road_length("rojo") == 3
    assert board.longest_road_length("azul") == 3


# Enemy buildings cut the road


def line_with_corners(board, count=6):
    edges = path_of(board, count)
    lay(board, "rojo", edges)
    return edges, shared_vertices(edges)


def test_an_enemy_settlement_in_the_middle_cuts_the_road_in_two(board):
    edges, between = line_with_corners(board, 6)
    board.buildings[between[2]] = ("azul", Building.SETTLEMENT)  # between road 3 and 4
    assert board.longest_road_length("rojo") == 3


def test_the_road_piece_next_to_the_enemy_settlement_still_counts(board):
    edges, between = line_with_corners(board, 6)
    board.buildings[between[3]] = ("azul", Building.CITY)  # after road 4
    assert board.longest_road_length("rojo") == 4  # roads 1-4 end at the city, and 5-6 are shorter


def test_an_enemy_building_at_the_very_end_does_not_shorten_it(board):
    edges, _ = line_with_corners(board, 6)
    end = next(v for v in edge_vertices(edges[-1]) if v not in edge_vertices(edges[-2]))
    board.buildings[end] = ("azul", Building.SETTLEMENT)
    assert board.longest_road_length("rojo") == 6


def test_your_own_buildings_and_empty_vertices_do_not_cut(board):
    edges, between = line_with_corners(board, 6)
    board.buildings[between[2]] = ("rojo", Building.SETTLEMENT)
    assert board.longest_road_length("rojo") == 6


def test_an_enemy_settlement_on_a_loop_leaves_it_whole(board):
    lay(board, "rojo", edges_of((0, 0)))
    corner = next(iter(edge_vertices(edges_of((0, 0))[0])))
    board.buildings[corner] = ("azul", Building.SETTLEMENT)
    assert board.longest_road_length("rojo") == 6  # it starts and ends at the settlement


# The Longest Road card


def test_five_roads_are_needed(board):
    lay(board, "rojo", path_of(board, LONGEST_ROAD_MIN - 1))
    assert board.longest_road_owner is None
    board.roads.clear()
    lay(board, "rojo", path_of(board, LONGEST_ROAD_MIN))
    assert board.longest_road_owner == "rojo"


def test_a_tie_keeps_the_card_where_it_was(board):
    first = path_of(board, 5)
    lay(board, "rojo", first)
    second = path_of(board, 5, avoid=set(first))
    lay(board, "azul", second)
    assert board.longest_road_owner == "rojo"  # rojo had it first


def test_a_strictly_longer_road_takes_the_card(board):
    first = path_of(board, 5)
    lay(board, "rojo", first)
    longer = path_of(board, 6, avoid=set(first))
    lay(board, "azul", longer)
    assert board.longest_road_owner == "azul"


def test_cutting_the_holder_passes_the_card_to_the_only_other_leader(board):
    first = path_of(board, 6)
    lay(board, "rojo", first)
    other = path_of(board, 5, avoid=set(first))
    lay(board, "azul", other)
    assert board.longest_road_owner == "rojo"
    board.buildings[shared_vertices(first)[2]] = ("azul", Building.SETTLEMENT)
    board.refresh_longest_road()
    assert board.longest_road_owner == "azul"


def test_cutting_the_holder_with_a_tie_between_others_sets_the_card_aside(board):
    first = path_of(board, 6)
    lay(board, "rojo", first)
    second = path_of(board, 5, avoid=set(first))
    third = path_of(board, 5, avoid=set(first) | set(second))
    lay(board, "azul", second)
    lay(board, "blanco", third)
    assert board.longest_road_owner == "rojo"
    board.buildings[shared_vertices(first)[2]] = ("azul", Building.SETTLEMENT)
    board.refresh_longest_road()
    assert board.longest_road_owner is None


def test_a_cut_holder_that_still_ties_keeps_the_card(board):
    first = path_of(board, 6)
    lay(board, "rojo", first)
    second = path_of(board, 5, avoid=set(first))
    lay(board, "azul", second)
    end = next(v for v in edge_vertices(first[-1]) if v not in edge_vertices(first[-2]))
    board.build(end, "azul", Building.SETTLEMENT)  # the real method refreshes by itself
    assert board.longest_road_length("rojo") == 6
    assert board.longest_road_owner == "rojo"


def test_the_card_is_lost_when_nobody_has_five_any_more(board):
    first = path_of(board, 5)
    lay(board, "rojo", first)
    assert board.longest_road_owner == "rojo"
    board.toggle_road(first[2], "rojo")  # taking a road away (free mode)
    assert board.longest_road_owner is None


def test_building_a_road_through_the_methods_updates_the_card(board):
    edges = path_of(board, 5)
    for edge in edges:
        board.toggle_road(edge, "rojo")
    assert board.longest_road_owner == "rojo"


# Points and display


def test_the_card_is_worth_two_points(board):
    lay(board, "rojo", path_of(board, 5))
    assert board.victory_points("rojo") == LONGEST_ROAD_POINTS
    assert board.victory_points("azul") == 0
    stats = board.player_stats("rojo")
    assert stats["points"] == LONGEST_ROAD_POINTS
    assert stats["longest_road"] == 5 and stats["has_longest_road"] is True
    assert board.player_stats("azul")["has_longest_road"] is False


def test_the_holder_survives_a_json_round_trip_and_old_boards_have_none(board):
    lay(board, "rojo", path_of(board, 5))
    loaded = Board.from_dict(json.loads(json.dumps(board.to_dict())))
    assert loaded.longest_road_owner == "rojo"
    data = board.to_dict()
    data.pop("longest_road")
    assert Board.from_dict(data).longest_road_owner is None


def test_a_new_game_forgets_the_card(board):
    lay(board, "rojo", path_of(board, 5))
    game = Game(board, rng=random.Random(1))
    game.new_game(3)
    assert board.longest_road_owner is None


def test_the_longest_road_can_win_the_game(board):
    game = Game(board, rng=random.Random(1))
    game.new_game(2)
    cities = [
        v for v in sorted(board.all_vertices(), key=sorted) if all(c in board.tiles for c in v)
    ][:30:7][:4]
    for vertex in cities:
        board.buildings[vertex] = ("rojo", Building.CITY)  # 8 points
    line = path_of(board, 5)
    for edge in line[:4]:
        board.roads[edge] = "rojo"
    # the fifth road must connect: it touches the end of the four
    game.state.phase = g.MAIN
    game.state.current = 0
    game.state.order = ["rojo", "azul"]
    for resource, amount in COSTS["road"].items():
        board.add_cards("rojo", resource, amount)
    assert board.victory_points("rojo") == 8
    game.build_road("rojo", line[4])
    assert board.longest_road_owner == "rojo"
    assert board.victory_points("rojo") == 10
    assert game.state.phase == g.FINISHED and game.state.winner == "rojo"


def test_the_search_stays_fast_on_a_dense_network(board):
    # fifteen roads packed around the center: many possible lines
    dense = list(edges_of((0, 0))) + list(edges_of((1, 0))) + list(edges_of((0, 1)))
    dense = list(dict.fromkeys(dense))[:15]
    lay(board, "rojo", dense)
    started = time.perf_counter()
    length = board.longest_road_length("rojo")
    assert time.perf_counter() - started < 1.0
    assert 5 <= length <= len(dense)


# On the table and on the dashboard


def test_the_panel_of_the_holder_carries_the_tag_and_the_view_has_the_numbers(board):
    from unittest.mock import MagicMock

    import numpy as np

    from light_map.catan.layout import panel_rect
    from light_map.catan.manager import CatanManager
    from light_map.rendering.layers.catan_layer import CatanLayer
    from light_map.state.world_state import WorldState

    manager = CatanManager(board=board, rng=random.Random(1))
    state = WorldState()
    manager.publish(state)
    map_system = MagicMock()
    map_system.world_to_screen.side_effect = lambda x, y: (int(x), int(y))
    layer = CatanLayer(state, map_system, 1920, 1080)

    def panel(index):
        x, y, w, h = panel_rect(index, 1920, 1080)
        return layer._generate_patches(0.0)[0].data[y : y + h, x : x + w].copy()

    before = panel(0)
    lay(board, "rojo", path_of(board, 5))
    manager.publish(state)
    after = panel(0)
    assert not np.array_equal(before, after)  # the gold tag appeared on rojo's panel
    stats = state.catan.to_dict()["stats"]
    assert stats["rojo"]["has_longest_road"] and stats["rojo"]["longest_road"] == 5
    assert stats["rojo"]["points"] == 2
    assert not stats["azul"]["has_longest_road"]
