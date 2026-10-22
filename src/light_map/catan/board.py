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

PLAYER_NAMES = ("rojo", "azul", "blanco", "naranja")
RESOURCE_NAMES = ("wood", "brick", "sheep", "wheat", "ore")
STATS_MODES = ("simple", "resources")
MIN_PLAYERS = 2
MAX_PLAYERS = 4

Coord = tuple[int, int]
Vertex = frozenset
Edge = frozenset  # the two adjacent tiles that share the edge

COSTS: dict[str, dict[str, int]] = {
    "road": {"wood": 1, "brick": 1},
    "settlement": {"wood": 1, "brick": 1, "sheep": 1, "wheat": 1},
    "city": {"wheat": 2, "ore": 3},
}
PIECE_LIMITS = {"road": 15, "settlement": 5, "city": 4}
WIN_POINTS = 10
BANK_RATE = 4  # cards of one kind for one of another


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


def edges_of(cell: Coord) -> list[Edge]:
    """The six edges of a tile (each one is shared with a neighbouring tile)."""
    return [frozenset({cell, (cell[0] + dq, cell[1] + dr)}) for dq, dr in DIRECTIONS]


def edge_to_list(edge: Edge) -> list[list[int]]:
    return [list(cell) for cell in sorted(edge)]


def edge_from_list(cells: list[list[int]]) -> Edge:
    edge = frozenset((int(c[0]), int(c[1])) for c in cells)
    if len(edge) != 2:
        raise ValueError("An edge is made of exactly two different tiles")
    a, b = edge
    if not neighbors(a, b):
        raise ValueError("The two tiles of an edge must be adjacent")
    return edge


def edge_vertices(edge: Edge) -> tuple[Vertex, Vertex]:
    """The two vertices at the ends of an edge."""
    a, b = sorted(edge)
    ends = [
        frozenset({a, b, (a[0] + dq, a[1] + dr)})
        for dq, dr in DIRECTIONS
        if neighbors((a[0] + dq, a[1] + dr), b)
    ]
    return ends[0], ends[1]


def vertex_edges(vertex: Vertex) -> list[Edge]:
    """The three edges that meet at a vertex."""
    a, b, c = sorted(vertex)
    return [frozenset({a, b}), frozenset({a, c}), frozenset({b, c})]


def vertex_neighbors(vertex: Vertex) -> list[Vertex]:
    """The three vertices one edge away."""
    result = []
    for edge in vertex_edges(vertex):
        first, second = edge_vertices(edge)
        result.append(second if first == vertex else first)
    return result


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
        self.roads: dict[Edge, str] = {}
        self.players: list[str] = list(PLAYER_NAMES)
        self.hands: dict[str, Counter] = {}
        self.stats_modes: dict[str, str] = {}
        from light_map.catan.game import GameState  # game.py imports this module

        self.game = GameState()

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
            "roads": [
                {"edge": edge_to_list(e), "player": player} for e, player in self.roads.items()
            ],
            "players": list(self.players),
            "hands": {p: {r: n for r, n in h.items() if n} for p, h in self.hands.items()},
            "stats_modes": dict(self.stats_modes),
            "game": self.game.to_dict(),
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
        for item in data.get("roads", []):
            board.roads[edge_from_list(item["edge"])] = item["player"]
        board.players = list(data.get("players", PLAYER_NAMES))
        for player, hand in data.get("hands", {}).items():
            board.hands[player] = Counter({r: int(n) for r, n in hand.items() if int(n) > 0})
        board.stats_modes = {
            p: m for p, m in data.get("stats_modes", {}).items() if m in STATS_MODES
        }
        if "game" in data:
            from light_map.catan.game import GameState

            board.game = GameState.from_dict(data["game"])
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

    # Roads, hands and per-player statistics

    def all_edges(self) -> set[Edge]:
        return {e for cell in self.tiles for e in edges_of(cell)}

    def _check_player(self, player: str) -> None:
        if player not in self.players:
            raise ValueError(f"Unknown player: {player}")

    def toggle_road(self, edge: Edge, player: str) -> None:
        """Builds a road, or removes the player's own road if there already is one."""
        self._check_player(player)
        if edge not in self.all_edges():
            raise ValueError("That edge is not on the board")
        owner = self.roads.get(edge)
        if owner is None:
            self.roads[edge] = player
        elif owner == player:
            del self.roads[edge]
        else:
            raise ValueError("Edge is already occupied by another player")

    def hand(self, player: str) -> Counter:
        return self.hands.setdefault(player, Counter())

    def add_cards(self, player: str, resource: str, amount: int) -> None:
        """Adds (or, with a negative amount, removes) cards. The hand never goes below zero."""
        self._check_player(player)
        if resource not in RESOURCE_NAMES:
            raise ValueError(f"Unknown resource: {resource}")
        hand = self.hand(player)
        hand[resource] = max(0, hand[resource] + int(amount))

    def collect(self, gains: dict[str, Counter]) -> None:
        """Adds a roll's production to the players' hands."""
        for player, counter in gains.items():
            if player in self.players:
                for resource, amount in counter.items():
                    self.add_cards(player, resource, amount)

    def set_player_count(self, count: int) -> None:
        if not MIN_PLAYERS <= count <= MAX_PLAYERS:
            raise ValueError(f"Between {MIN_PLAYERS} and {MAX_PLAYERS} players are supported")
        keep = list(PLAYER_NAMES[:count])
        for player in self.players:
            if player not in keep and self.has_pieces(player):
                raise ValueError(f"{player} still has pieces on the board or cards in hand")
        self.players = keep

    def has_pieces(self, player: str) -> bool:
        return (
            any(owner == player for owner, _ in self.buildings.values())
            or any(owner == player for owner in self.roads.values())
            or sum(self.hands.get(player, Counter()).values()) > 0
        )

    def set_stats_mode(self, player: str | None, mode: str) -> None:
        """Sets the statistics mode of one player, or of everybody when player is None.

        Mode "toggle" flips a single player between "simple" and "resources".
        """
        targets = self.players if player is None else [player]
        for name in targets:
            self._check_player(name)
            new = mode
            if mode == "toggle":
                new = "simple" if self.stats_mode(name) == "resources" else "resources"
            if new not in STATS_MODES:
                raise ValueError(f"Unknown statistics mode: {mode}")
            self.stats_modes[name] = new

    def stats_mode(self, player: str) -> str:
        return self.stats_modes.get(player, "simple")

    def player_stats(self, player: str) -> dict:
        settlements = sum(
            1 for p, k in self.buildings.values() if p == player and k is Building.SETTLEMENT
        )
        cities = sum(1 for p, k in self.buildings.values() if p == player and k is Building.CITY)
        hand = self.hands.get(player, Counter())
        return {
            "settlements": settlements,
            "cities": cities,
            "roads": sum(1 for owner in self.roads.values() if owner == player),
            "cards": sum(hand.values()),
            "points": settlements + 2 * cities,
            "hand": {r: hand.get(r, 0) for r in RESOURCE_NAMES},
            "mode": self.stats_mode(player),
        }

    # Rules: costs, placement and scoring

    def piece_count(self, player: str, kind: str) -> int:
        if kind == "road":
            return sum(1 for owner in self.roads.values() if owner == player)
        wanted = Building.SETTLEMENT if kind == "settlement" else Building.CITY
        return sum(1 for owner, k in self.buildings.values() if owner == player and k is wanted)

    def check_piece_available(self, player: str, kind: str) -> str | None:
        if self.piece_count(player, kind) >= PIECE_LIMITS[kind]:
            return f"No {kind}s left to place"
        return None

    def settlement_error(self, vertex: Vertex, player: str, setup: bool = False) -> str | None:
        """Why the player cannot place a settlement here, or None if they can."""
        if vertex not in self.all_vertices():
            return "That vertex is not on the board"
        if vertex in self.buildings:
            return "Vertex is already occupied"
        if any(n in self.buildings for n in vertex_neighbors(vertex)):
            return "Too close to another settlement (the distance rule)"
        if not setup and not any(self.roads.get(e) == player for e in vertex_edges(vertex)):
            return "A settlement must be connected to one of your roads"
        return self.check_piece_available(player, "settlement")

    def city_error(self, vertex: Vertex, player: str) -> str | None:
        if self.buildings.get(vertex) != (player, Building.SETTLEMENT):
            return "A city must replace your own settlement"
        return self.check_piece_available(player, "city")

    def road_error(self, edge: Edge, player: str, must_touch: Vertex | None = None) -> str | None:
        """Why the player cannot place a road here, or None.

        must_touch is used in the setup phase, where the road has to start at the settlement
        that was just placed.
        """
        if edge not in self.all_edges():
            return "That edge is not on the board"
        if edge in self.roads:
            return "Edge is already occupied"
        ends = edge_vertices(edge)
        if must_touch is not None:
            if must_touch not in ends:
                return "The road must start at the settlement you just placed"
        elif not any(self._connects(v, edge, player) for v in ends):
            return "A road must connect to your roads or buildings"
        return self.check_piece_available(player, "road")

    def _connects(self, vertex: Vertex, edge: Edge, player: str) -> bool:
        owner = self.buildings.get(vertex)
        if owner is not None:
            return owner[0] == player
        return any(self.roads.get(e) == player for e in vertex_edges(vertex) if e != edge)

    def victory_points(self, player: str) -> int:
        return self.piece_count(player, "settlement") + 2 * self.piece_count(player, "city")

    def can_afford(self, player: str, cost: dict[str, int]) -> bool:
        hand = self.hands.get(player, Counter())
        return all(hand.get(r, 0) >= n for r, n in cost.items())

    def pay(self, player: str, cost: dict[str, int]) -> None:
        if not self.can_afford(player, cost):
            raise ValueError("Not enough cards")
        for resource, amount in cost.items():
            self.add_cards(player, resource, -amount)

    def tile_resources_at(self, vertex: Vertex) -> Counter:
        """One card per land tile around a vertex (what a second setup settlement pays)."""
        gains: Counter = Counter()
        for cell in vertex:
            tile = self.tiles.get(cell)
            if tile is not None and tile.resource != "desert":
                gains[tile.resource] += 1
        return gains
