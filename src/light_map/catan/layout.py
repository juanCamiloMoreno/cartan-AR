"""Geometry shared by the SVG board generator and the projection layer.

All coordinates are in SVG (map) units. Tiles are pointy-top hexagons.
"""

from __future__ import annotations

import math
from pathlib import Path

from light_map.catan.board import DIRECTIONS, neighbors


SIZE = 70  # hex circumradius; the board fits a 1536x864 screen
PAD = SIZE * 1.2
BOARD_WIDTH = SIZE * math.sqrt(3) * 5 + PAD * 2
BOARD_HEIGHT = SIZE * 1.5 * 4 + SIZE * 2 + PAD * 2


def tile_center(q: int, r: int) -> tuple[float, float]:
    """Center of an axial (q, r) tile on the generated SVG."""
    x = SIZE * math.sqrt(3) * (q + r / 2) + BOARD_WIDTH / 2
    y = SIZE * 1.5 * r + BOARD_HEIGHT / 2
    return x, y


def hex_corners(q: int, r: int, radius: float = SIZE - 2) -> list[tuple[float, float]]:
    cx, cy = tile_center(q, r)
    return [
        (
            cx + radius * math.cos(math.radians(60 * i - 30)),
            cy + radius * math.sin(math.radians(60 * i - 30)),
        )
        for i in range(6)
    ]


def sidecar_path(svg_path: str) -> str:
    """Path of the board description stored next to an SVG map (catan.svg -> catan.board.json)."""
    path = Path(svg_path)
    return str(path.with_name(f"{path.stem}.board.json"))


def vertex_position(vertex) -> tuple[float, float]:
    """Position of a vertex: the mean of the centers of the three tiles that meet there."""
    centers = [tile_center(q, r) for q, r in vertex]
    return (
        sum(x for x, _ in centers) / len(centers),
        sum(y for _, y in centers) / len(centers),
    )


def edge_endpoints(edge) -> tuple[tuple[float, float], tuple[float, float]]:
    """The two vertex positions at the ends of an edge (shared by two adjacent tiles)."""
    a, b = sorted(edge)
    ends = [
        vertex_position(frozenset({a, b, (a[0] + dq, a[1] + dr)}))
        for dq, dr in DIRECTIONS
        if neighbors((a[0] + dq, a[1] + dr), b)
    ]
    return ends[0], ends[1]


# Player panels drawn in the corners of the projection (screen pixels).
PANEL_W = 360
PANEL_H = 230  # tallest panel (resources mode); also the hit area for gestures
PANEL_MARGIN = 20
DICE_CLEARANCE = 200  # keeps the top-right panel below the dice
# Seat order: two players sit opposite each other, then the other two corners fill in.
CORNERS = ("bottom_left", "top_right", "top_left", "bottom_right")


def panel_rect(index: int, width: int, height: int) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the panel of the player sitting at seat `index`."""
    corner = CORNERS[index % len(CORNERS)]
    x = PANEL_MARGIN if corner.endswith("left") else width - PANEL_W - PANEL_MARGIN
    if corner.startswith("bottom"):
        y = height - PANEL_H - PANEL_MARGIN
    else:
        y = PANEL_MARGIN + (DICE_CLEARANCE if corner == "top_right" else 0)
    return x, y, PANEL_W, PANEL_H


def panel_at(point: tuple[float, float], players: list[str], width: int, height: int):
    """The player whose panel contains the screen point, or None."""
    for index, player in enumerate(players):
        x, y, w, h = panel_rect(index, width, height)
        if x <= point[0] <= x + w and y <= point[1] <= y + h:
            return player
    return None
