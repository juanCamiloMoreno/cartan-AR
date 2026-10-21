"""Geometry shared by the SVG board generator and the projection layer.

All coordinates are in SVG (map) units. Tiles are pointy-top hexagons.
"""

from __future__ import annotations

import math
from pathlib import Path


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
