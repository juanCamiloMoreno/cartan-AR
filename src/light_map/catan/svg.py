"""The SVG map Light Map projects for a Catan board (tiles and number tokens)."""

from __future__ import annotations

import cv2

from light_map.catan.board import Coord, Tile
from light_map.catan.layout import BOARD_HEIGHT, BOARD_WIDTH, SIZE, hex_corners, tile_center


COLORS = {
    "wood": "#2e7d32",
    "sheep": "#9ccc65",
    "wheat": "#fbc02d",
    "brick": "#c2572b",
    "ore": "#78909c",
    "desert": "#e6d3a3",
}
DOTS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
K = SIZE / 100
FONT_SIZE = round(28 * K)


def build_svg(tiles: dict[Coord, Tile]) -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{BOARD_WIDTH:.0f}" '
        f'height="{BOARD_HEIGHT:.0f}" viewBox="0 0 {BOARD_WIDTH:.0f} {BOARD_HEIGHT:.0f}">',
        '<rect width="100%" height="100%" fill="#1e88e5"/>',
    ]
    for (q, r), tile in tiles.items():
        res, num = tile.resource, tile.number
        cx, cy = tile_center(q, r)
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in hex_corners(q, r))
        parts.append(
            f'<polygon points="{points}" fill="{COLORS[res]}" stroke="#f5f5f5" stroke-width="3"/>'
        )
        if num is None:
            continue
        color = "#c62828" if num in (6, 8) else "#212121"
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{30 * K:.1f}" fill="#fff8e1" '
            f'stroke="#212121" stroke-width="2"/>'
        )
        # Light Map draws text with cv2.putText, left-aligned (no text-anchor support),
        # so center it manually using the same font and scale as its renderer.
        (tw, th), _ = cv2.getTextSize(str(num), cv2.FONT_HERSHEY_SIMPLEX, FONT_SIZE / 25.0, 1)
        parts.append(
            f'<text x="{cx - tw / 2:.1f}" y="{cy + th / 2 - 3 * K:.1f}" font-family="sans-serif" '
            f'font-size="{FONT_SIZE}" fill="{color}">{num}</text>'
        )
        dots = DOTS[num]
        start = cx - (dots - 1) * 4 * K
        for i in range(dots):
            parts.append(
                f'<circle cx="{start + i * 8 * K:.1f}" cy="{cy + 17 * K:.1f}" '
                f'r="{2 * K:.1f}" fill="{color}"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts)
