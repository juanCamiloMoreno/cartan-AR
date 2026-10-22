"""Harbors: 9 of them on the coast, four 3:1 and five 2:1 (one per resource)."""

from __future__ import annotations

import math
import random

from light_map.catan.board import RESOURCE_NAMES, Coord, Edge, Tile, edges_of


ANY = "any"  # a 3:1 harbor
# Ring positions (out of the 30 coast edges) of the nine harbors: gaps of 3, 4, 3, 3, 4, ...
PORT_POSITIONS = (0, 3, 7, 10, 13, 17, 20, 23, 27)
PORT_KINDS = (ANY,) * 4 + tuple(RESOURCE_NAMES)
# Fixed order used when the harbors are not shuffled (clockwise from the top left).
STANDARD_ORDER = (ANY, "sheep", ANY, "wheat", "ore", ANY, "brick", ANY, "wood")


def coast_edges(tiles: dict[Coord, Tile]) -> list[Edge]:
    """Edges that have land on one side only, in clockwise order around the island."""
    coast = [
        edge
        for edge in {e for cell in tiles for e in edges_of(cell)}
        if sum(1 for cell in edge if cell in tiles) == 1
    ]

    def angle(edge: Edge) -> float:
        # Axial -> plane for pointy-top hexagons; only the direction around the center matters.
        x = sum(q + r / 2 for q, r in edge) / 2
        y = sum(r for _, r in edge) / 2 * math.sqrt(3) / 2
        return math.atan2(y, x)

    return sorted(coast, key=lambda e: (angle(e), sorted(e)))


def outward_direction(edge: Edge, tiles: dict[Coord, Tile]) -> Coord:
    """Axial direction pointing from the land tile of a coast edge out to the sea."""
    land = next(cell for cell in edge if cell in tiles)
    sea = next(cell for cell in edge if cell not in tiles)
    return sea[0] - land[0], sea[1] - land[1]


def place_ports(
    tiles: dict[Coord, Tile], rng: random.Random, shuffle: bool = True
) -> dict[Edge, str]:
    """Chooses the coast edges of the nine harbors and which kind goes on each."""
    ring = coast_edges(tiles)
    if len(ring) != 30:  # only the standard 19-tile island has the standard harbor frame
        return {}
    offset = rng.randrange(len(ring)) if shuffle else 0
    kinds = list(PORT_KINDS) if shuffle else list(STANDARD_ORDER)
    if shuffle:
        rng.shuffle(kinds)
    return {
        ring[(offset + position) % len(ring)]: kind
        for position, kind in zip(PORT_POSITIONS, kinds, strict=True)
    }
