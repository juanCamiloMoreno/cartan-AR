"""Geometry shared by the SVG board generator and the projection layer.

All coordinates are in SVG (map) units. Tiles are pointy-top hexagons.
"""

from __future__ import annotations

import math
from pathlib import Path

from light_map.catan.board import edge_vertices


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


def cell_at_world(x: float, y: float) -> tuple[int, int]:
    """Axial (q, r) of the hexagon that contains a point of the board (inverse of tile_center)."""
    r = (y - BOARD_HEIGHT / 2) / (SIZE * 1.5)
    q = (x - BOARD_WIDTH / 2) / (SIZE * math.sqrt(3)) - r / 2
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = round(cx), round(cy), round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return int(rx), int(rz)


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
    first, second = edge_vertices(edge)
    return vertex_position(first), vertex_position(second)


PORT_DISTANCE = SIZE * 0.62  # how far from the coast edge the harbor marker is drawn


def port_anchor(edge, tiles) -> tuple[float, float]:
    """Where the marker of a harbor on a coast edge goes: just outside the edge, in the sea."""
    from light_map.catan.ports import outward_direction

    (x1, y1), (x2, y2) = edge_endpoints(edge)
    land = next(c for c in edge if c in tiles)
    dq, dr = outward_direction(edge, tiles)
    lx, ly = tile_center(*land)
    sx, sy = tile_center(land[0] + dq, land[1] + dr)
    length = math.hypot(sx - lx, sy - ly) or 1.0
    ux, uy = (sx - lx) / length, (sy - ly) / length
    return (x1 + x2) / 2 + ux * PORT_DISTANCE, (y1 + y2) / 2 + uy * PORT_DISTANCE


# Player panels drawn in the corners of the projection (screen pixels).
PANEL_W = 360
PANEL_H = 230  # tallest panel (resources mode); also the hit area for gestures
PANEL_MARGIN = 20
DICE_CLEARANCE = 200  # keeps the top-right panel below the dice
# Seat order: two players sit opposite each other, then the other two corners fill in.
CORNERS = ("bottom_left", "top_right", "top_left", "bottom_right")


BANNER_RESERVE = 110  # screen pixels kept free at the top for the game banner


def fit_board_view(width: int, height: int) -> tuple[float, float, float]:
    """(x, y, zoom) that centers the board and makes it as big as fits between the panels.

    The board sits below the banner strip at the top and between the side panels.
    """
    free_width = width - 2 * (PANEL_W + 2 * PANEL_MARGIN)
    free_height = height - BANNER_RESERVE - PANEL_MARGIN
    zoom = max(0.1, min(free_width / BOARD_WIDTH, free_height / BOARD_HEIGHT))
    x = (width - zoom * BOARD_WIDTH) / 2
    y = BANNER_RESERVE + (free_height - zoom * BOARD_HEIGHT) / 2
    return x, y, zoom


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
