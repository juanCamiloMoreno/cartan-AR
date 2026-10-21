"""Catan board model: tiles, buildings, dice production and the robber.

Tiles use axial (q, r) coordinates. A vertex is identified by the frozenset of the
three tiles that meet at it (tiles may lie outside the board, e.g. on the coast).
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from enum import Enum


RESOURCES = ["wood"] * 4 + ["sheep"] * 4 + ["wheat"] * 4 + ["brick"] * 3 + ["ore"] * 3 + ["desert"]
NUMBERS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
ROW_SIZES = [3, 4, 5, 4, 3]

# Axial directions in circular order, so consecutive entries are adjacent to each other.
DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

Coord = tuple[int, int]
Vertex = frozenset


class Building(Enum):
    SETTLEMENT = 1
    CITY = 2


@dataclass(frozen=True)
class Tile:
    resource: str
    number: int | None


def axial_cells() -> list[Coord]:
    """Axial (q, r) coordinates for the 19-tile board, row by row."""
    cells = []
    for row, count in enumerate(ROW_SIZES):
        r = row - 2
        q_start = max(-2, -2 - r)
        cells.extend((q_start + i, r) for i in range(count))
    return cells


def neighbors(a: Coord, b: Coord) -> bool:
    return (a[0] - b[0], a[1] - b[1]) in DIRECTIONS


def vertices_of(cell: Coord) -> list[Vertex]:
    """The six vertices of a tile."""
    q, r = cell
    around = [(q + dq, r + dr) for dq, dr in DIRECTIONS]
    return [frozenset({cell, around[i], around[(i + 1) % 6]}) for i in range(6)]


def vertex_to_list(vertex: Vertex) -> list[list[int]]:
    """JSON-friendly, deterministic form of a vertex: its three tiles, sorted."""
    return [list(cell) for cell in sorted(vertex)]


def vertex_from_list(cells: list[list[int]]) -> Vertex:
    vertex = frozenset((int(c[0]), int(c[1])) for c in cells)
    if len(vertex) != 3:
        raise ValueError("A vertex is made of exactly three different tiles")
    return vertex


def roll_dice(rng: random.Random | None = None) -> tuple[int, int]:
    rng = rng or random
    return rng.randint(1, 6), rng.randint(1, 6)


def players_to_discard(hands: dict[str, int]) -> dict[str, int]:
    """On a 7, players holding more than 7 cards discard half (rounded down)."""
    return {name: n // 2 for name, n in hands.items() if n > 7}


class Board:
    def __init__(self, tiles: dict[Coord, Tile], robber: Coord):
        self.tiles = tiles
        self.robber = robber
        self.buildings: dict[Vertex, tuple[str, Building]] = {}

    @classmethod
    def random(cls, rng: random.Random | None = None) -> Board:
        """Random board with the standard tile mix and no adjacent 6/8 tiles."""
        rng = rng or random.Random()
        cells = axial_cells()
        while True:
            resources = RESOURCES[:]
            numbers = NUMBERS[:]
            rng.shuffle(resources)
            rng.shuffle(numbers)
            nums = iter(numbers)
            tiles = {
                c: Tile(res, None if res == "desert" else next(nums))
                for c, res in zip(cells, resources, strict=True)
            }
            hot = [c for c, t in tiles.items() if t.number in (6, 8)]
            if any(neighbors(a, b) for i, a in enumerate(hot) for b in hot[i + 1 :]):
                continue
            robber = next(c for c, t in tiles.items() if t.resource == "desert")
            return cls(tiles, robber)

    def to_dict(self) -> dict:
        return {
            "tiles": [
                {"q": q, "r": r, "resource": t.resource, "number": t.number}
                for (q, r), t in self.tiles.items()
            ],
            "robber": list(self.robber),
            "buildings": [
                {"vertex": vertex_to_list(v), "player": player, "kind": kind.name.lower()}
                for v, (player, kind) in self.buildings.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Board:
        tiles = {(t["q"], t["r"]): Tile(t["resource"], t["number"]) for t in data["tiles"]}
        board = cls(tiles, robber=tuple(data["robber"]))
        for item in data.get("buildings", []):
            board.buildings[vertex_from_list(item["vertex"])] = (
                item["player"],
                Building[item["kind"].upper()],
            )
        return board

    def build(self, vertex: Vertex, player: str, kind: Building) -> None:
        current = self.buildings.get(vertex)
        if kind is Building.SETTLEMENT:
            if current is not None:
                raise ValueError("Vertex is already occupied")
        elif current != (player, Building.SETTLEMENT):
            # A city can only replace the owner's own settlement.
            raise ValueError("A city must replace the player's own settlement")
        self.buildings[vertex] = (player, kind)

    def remove(self, vertex: Vertex) -> None:
        if vertex not in self.buildings:
            raise ValueError("There is nothing to remove at this vertex")
        del self.buildings[vertex]

    def all_vertices(self) -> set[Vertex]:
        return {v for cell in self.tiles for v in vertices_of(cell)}

    def production(self, total: int) -> dict[str, Counter]:
        """Resources each player collects for a dice total (the robber's tile pays nothing)."""
        if total == 7:
            return {}
        gains: dict[str, Counter] = {}
        for cell, tile in self.tiles.items():
            if tile.number != total or cell == self.robber:
                continue
            for vertex in vertices_of(cell):
                owner = self.buildings.get(vertex)
                if owner is None:
                    continue
                player, kind = owner
                gains.setdefault(player, Counter())[tile.resource] += kind.value
        return gains

    def move_robber(self, cell: Coord) -> None:
        if cell not in self.tiles:
            raise ValueError("Tile is not on the board")
        if cell == self.robber:
            raise ValueError("The robber must move to a different tile")
        self.robber = cell

    def stealable_players(self, cell: Coord, mover: str) -> list[str]:
        """Other players with a building on the tile, without duplicates."""
        victims: list[str] = []
        for vertex in vertices_of(cell):
            owner = self.buildings.get(vertex)
            if owner and owner[0] != mover and owner[0] not in victims:
                victims.append(owner[0])
        return victims
