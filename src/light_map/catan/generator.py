"""Board generator with a checklist of rules and a fairness level.

The mandatory part is the tile mix (4 wood, 4 sheep, 4 wheat, 3 brick, 3 ore, 1 desert and the
18 number tokens). Everything else is a rule that can be switched on or off.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from itertools import combinations

from light_map.catan.board import (
    NUMBERS,
    RESOURCES,
    Board,
    Coord,
    Tile,
    axial_cells,
    neighbors,
    vertices_of,
)
from light_map.catan.ports import place_ports


PIPS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
RED_NUMBERS = (6, 8)
LOW_NUMBERS = (2, 12)
BALANCE_LEVELS = ("random", "fair", "very_fair")
MAX_ATTEMPTS = 6000

# Fairness limits per level: (largest gap between the average pips of two resources,
# most corners with 12 or more pips, largest gap between the total pips of two resources).
BALANCE_LIMITS = {
    "random": None,
    "fair": (1.5, 3, 8),
    "very_fair": (1.0, 2, 5),
}


@dataclass
class BoardRules:
    """The checklist: True means the situation is allowed."""

    allow_adjacent_same_resource: bool = True
    allow_adjacent_red: bool = False  # 6 next to 8 (the official rule forbids it)
    allow_adjacent_low: bool = True  # 2 next to 12
    allow_adjacent_same_number: bool = True
    balance: str = "random"  # "random" | "fair" | "very_fair"
    shuffle_ports: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> BoardRules:
        data = data or {}
        rules = cls()
        for name in ("allow_adjacent_same_resource", "allow_adjacent_red", "allow_adjacent_low"):
            if name in data:
                setattr(rules, name, bool(data[name]))
        for name in ("allow_adjacent_same_number", "shuffle_ports"):
            if name in data:
                setattr(rules, name, bool(data[name]))
        balance = data.get("balance", rules.balance)
        if balance not in BALANCE_LEVELS:
            raise ValueError(f"Unknown balance level: {balance}")
        rules.balance = balance
        return rules


@dataclass
class BoardMetrics:
    resource_pips: dict[str, int]  # total pips of every resource
    resource_avg: dict[str, float]  # pips per tile of every resource
    avg_spread: float  # largest gap between the averages
    total_spread: int  # largest gap between the totals
    best_corner: int  # pips of the best corner
    strong_corners: int  # corners with 12 or more pips

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GenerationReport:
    attempts: int = 0
    satisfied: bool = True  # False when the rules could not all be met (best board returned)
    metrics: BoardMetrics | None = None
    rules: BoardRules = field(default_factory=BoardRules)

    def to_dict(self) -> dict:
        return {
            "attempts": self.attempts,
            "satisfied": self.satisfied,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "rules": self.rules.to_dict(),
        }


def _adjacent_pairs(cells: list[Coord]) -> list[tuple[Coord, Coord]]:
    return [(a, b) for a, b in combinations(cells, 2) if neighbors(a, b)]


_CELLS = axial_cells()
_PAIRS = _adjacent_pairs(_CELLS)
_CORNERS = {cell: vertices_of(cell) for cell in _CELLS}
_NEIGHBORS = {c: [o for o in _CELLS if neighbors(c, o)] for c in _CELLS}


def rule_violations(tiles: dict[Coord, Tile], rules: BoardRules) -> list[str]:
    """Names of the rules this board breaks (empty when it is fine)."""
    broken: set[str] = set()
    pairs = _PAIRS if len(tiles) == len(_CELLS) else _adjacent_pairs(list(tiles))
    for a, b in pairs:
        ta, tb = tiles[a], tiles[b]
        if not rules.allow_adjacent_same_resource and ta.resource == tb.resource:
            broken.add("same_resource")
        if ta.number is None or tb.number is None:
            continue
        if not rules.allow_adjacent_red and ta.number in RED_NUMBERS and tb.number in RED_NUMBERS:
            broken.add("red")
        if not rules.allow_adjacent_low and ta.number in LOW_NUMBERS and tb.number in LOW_NUMBERS:
            broken.add("low")
        if not rules.allow_adjacent_same_number and ta.number == tb.number:
            broken.add("same_number")
    return sorted(broken)


def board_metrics(tiles: dict[Coord, Tile]) -> BoardMetrics:
    per_resource: dict[str, list[int]] = {}
    for tile in tiles.values():
        if tile.number is not None:
            per_resource.setdefault(tile.resource, []).append(PIPS[tile.number])
    totals = {r: sum(v) for r, v in per_resource.items()}
    averages = {r: sum(v) / len(v) for r, v in per_resource.items()}
    corners: dict = {}
    for cell in tiles:
        for vertex in _CORNERS.get(cell) or vertices_of(cell):
            corners[vertex] = sum(
                PIPS[tiles[c].number] for c in vertex if c in tiles and tiles[c].number is not None
            )
    values = sorted(corners.values(), reverse=True)
    return BoardMetrics(
        resource_pips=totals,
        resource_avg={r: round(a, 2) for r, a in averages.items()},
        avg_spread=round(max(averages.values()) - min(averages.values()), 2),
        total_spread=max(totals.values()) - min(totals.values()),
        best_corner=values[0],
        strong_corners=sum(1 for v in values if v >= 12),
    )


def _within_balance(metrics: BoardMetrics, level: str) -> bool:
    limits = BALANCE_LIMITS[level]
    if limits is None:
        return True
    avg_spread, strong_corners, total_spread = limits
    return (
        metrics.avg_spread <= avg_spread
        and metrics.strong_corners <= strong_corners
        and metrics.total_spread <= total_spread
    )


def _imbalance(metrics: BoardMetrics) -> float:
    """Lower is fairer; used to pick the best board when the limits cannot be met."""
    return metrics.avg_spread + 0.4 * metrics.strong_corners + 0.1 * metrics.total_spread


def _try_assign(
    cells: list[Coord],
    pool: list,
    conflict: Callable[[object, object], bool],
    rng: random.Random,
    max_nodes: int,
) -> dict[Coord, object] | None:
    """One randomized backtracking pass; None when the branch takes more than max_nodes."""
    counts = Counter(pool)
    assigned: dict[Coord, object] = {}
    nodes = 0

    def place(i: int) -> bool:
        nonlocal nodes
        if i == len(cells):
            return True
        nodes += 1
        if nodes > max_nodes:
            return False
        cell = cells[i]
        deck = [v for v, n in counts.items() for _ in range(n)]
        rng.shuffle(deck)
        for item in dict.fromkeys(deck):
            if any(conflict(item, assigned[n]) for n in _NEIGHBORS[cell] if n in assigned):
                continue
            assigned[cell] = item
            counts[item] -= 1
            if place(i + 1):
                return True
            counts[item] += 1
            del assigned[cell]
        return False

    return assigned if place(0) else None


def _assign(
    cells: list[Coord],
    pool: list,
    conflict: Callable[[object, object], bool],
    rng: random.Random,
    max_nodes: int = 4000,
    restarts: int = 40,
) -> dict[Coord, object] | None:
    """Places the items of `pool` on `cells` so no two neighbors conflict.

    Randomized backtracking: each cell tries the remaining items in a random order (weighted
    by how many are left, so with no conflicts this is a uniform shuffle). Restarts when a
    branch takes too long. Returns None when it finds nothing.
    """
    for _ in range(restarts):
        result = _try_assign(cells, pool, conflict, rng, max_nodes)
        if result is not None:
            return result
    return None


def _random_tiles(rng: random.Random, rules: BoardRules | None = None) -> dict[Coord, Tile]:
    """Tiles and tokens placed so the checklist holds (or plain shuffled if that is impossible)."""
    rules = rules or BoardRules()
    resources = _assign(
        _CELLS,
        RESOURCES,
        lambda a, b: not rules.allow_adjacent_same_resource and a == b,
        rng,
    )
    if resources is None:
        shuffled = RESOURCES[:]
        rng.shuffle(shuffled)
        resources = dict(zip(_CELLS, shuffled, strict=True))
    land = [c for c in _CELLS if resources[c] != "desert"]

    def numbers_conflict(a: int, b: int) -> bool:
        return (
            (not rules.allow_adjacent_red and a in RED_NUMBERS and b in RED_NUMBERS)
            or (not rules.allow_adjacent_low and a in LOW_NUMBERS and b in LOW_NUMBERS)
            or (not rules.allow_adjacent_same_number and a == b)
        )

    numbers = _assign(land, NUMBERS, numbers_conflict, rng)
    if numbers is None:
        shuffled = NUMBERS[:]
        rng.shuffle(shuffled)
        numbers = dict(zip(land, shuffled, strict=True))
    return {cell: Tile(resources[cell], numbers.get(cell)) for cell in _CELLS}


def generate_board(
    rules: BoardRules | None = None, rng: random.Random | None = None
) -> tuple[Board, GenerationReport]:
    """Shuffles tiles and tokens until the checklist and the fairness level are met.

    When the rules are too strict to be met in MAX_ATTEMPTS shuffles, the board that breaks the
    fewest rules (and is the fairest) is returned and the report says satisfied=False.
    """
    rules = rules or BoardRules()
    rng = rng or random.Random()
    best: tuple[tuple[int, float], dict[Coord, Tile]] | None = None
    chosen: dict[Coord, Tile] | None = None
    attempts = 0
    for attempts in range(1, MAX_ATTEMPTS + 1):  # noqa: B007 - the last value is reported
        tiles = _random_tiles(rng, rules)
        broken = rule_violations(tiles, rules)
        metrics = board_metrics(tiles)
        if not broken and _within_balance(metrics, rules.balance):
            chosen = tiles
            break
        score = (len(broken), _imbalance(metrics))
        if best is None or score < best[0]:
            best = (score, tiles)
    satisfied = chosen is not None
    tiles = chosen if chosen is not None else best[1]
    robber = next(cell for cell, tile in tiles.items() if tile.resource == "desert")
    board = Board(tiles, robber)
    board.ports = place_ports(tiles, rng, rules.shuffle_ports)
    return board, GenerationReport(
        attempts=attempts, satisfied=satisfied, metrics=board_metrics(tiles), rules=rules
    )
