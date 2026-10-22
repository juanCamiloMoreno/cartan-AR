import cv2
import numpy as np

from light_map.catan.layout import (
    PANEL_H,
    PANEL_W,
    edge_endpoints,
    hex_corners,
    panel_rect,
    tile_center,
    vertex_position,
)
from light_map.core.common_types import ImagePatch, Layer
from light_map.map.map_system import MapSystem
from light_map.state.world_state import WorldState


HIGHLIGHT_BGR = (0, 215, 255)  # gold
ROBBER_BGR = (30, 30, 30)
PLAYER_BGR = {
    "rojo": (40, 40, 220),
    "azul": (220, 120, 30),
    "blanco": (240, 240, 240),
    "naranja": (0, 140, 255),
}
DEFAULT_PLAYER_BGR = (160, 160, 160)

RESOURCE_BGR = {
    "wood": (50, 125, 46),
    "brick": (43, 87, 194),
    "sheep": (101, 204, 156),
    "wheat": (45, 192, 251),
    "ore": (146, 144, 120),
}
RESOURCE_SHORT = {"wood": "Mad", "brick": "Lad", "sheep": "Ove", "wheat": "Tri", "ore": "Min"}
PANEL_SIMPLE_H = 140
ROAD_THICKNESS = 9

DIE_SIZE = 84
DIE_GAP = 18
DIE_MARGIN = 24
# Pip positions on a 3x3 grid (column, row), by die value.
PIPS = {
    1: [(1, 1)],
    2: [(0, 0), (2, 2)],
    3: [(0, 0), (1, 1), (2, 2)],
    4: [(0, 0), (2, 0), (0, 2), (2, 2)],
    5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
    6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)],
}


def game_banner(game: dict | None) -> str | None:
    """Short ASCII text (OpenCV fonts have no accents) with what the table is waiting for."""
    if not game or game.get("phase") in (None, "free"):
        return None
    phase = game["phase"]
    who = (game.get("current_player") or "").upper()
    if phase == "setup":
        what = "UNA CASA" if game.get("setup_step") == "settlement" else "UN CAMINO"
        return f"PREPARACION: {who} PONE {what}"
    if phase == "roll":
        return f"TURNO DE {who}: TIRA LOS DADOS"
    if phase == "discard":
        pending = ", ".join(f"{p.upper()} {n}" for p, n in (game.get("discards") or {}).items())
        return f"SALIO 7: DESCARTAN {pending}"
    if phase == "robber":
        return f"{who} MUEVE AL LADRON"
    if phase == "steal":
        victims = ", ".join(v.upper() for v in game.get("victims") or [])
        return f"{who} ROBA A: {victims}"
    if phase == "main":
        return f"TURNO DE {who}"
    if phase == "finished":
        return f"{(game.get('winner') or '').upper()} GANO!"
    return None


class CatanLayer(Layer):
    """Highlights the tiles that produce on the last roll and marks the robber."""

    def __init__(self, state: WorldState, map_system: MapSystem, width: int, height: int):
        super().__init__(state=state, is_static=True)
        self.map_system = map_system
        self.width = width
        self.height = height

    def get_current_version(self) -> int:
        if self.state is None:
            return 0
        return max(self.state.catan_version, self.state.viewport_version)

    def _to_screen(self, points: list[tuple[float, float]]) -> np.ndarray:
        return np.array([self.map_system.world_to_screen(x, y) for x, y in points], np.int32)

    def _draw_dice(self, buffer: np.ndarray, dice: tuple[int, int], total: int) -> None:
        """Draws both dice and their total in the top-right corner of the projection."""
        y0 = DIE_MARGIN
        second_x0 = self.width - DIE_MARGIN - DIE_SIZE
        for x0, value in ((second_x0 - DIE_GAP - DIE_SIZE, dice[0]), (second_x0, dice[1])):
            top_left, bottom_right = (x0, y0), (x0 + DIE_SIZE, y0 + DIE_SIZE)
            cv2.rectangle(buffer, top_left, bottom_right, (245, 245, 245, 255), -1)
            cv2.rectangle(buffer, top_left, bottom_right, (20, 20, 20, 255), 3)
            for col, row in PIPS[value]:
                px = x0 + DIE_SIZE * (col + 1) // 4
                py = y0 + DIE_SIZE * (row + 1) // 4
                cv2.circle(buffer, (px, py), 8, (20, 20, 20, 255), -1, cv2.LINE_AA)

        label = f"= {total}"
        origin = (second_x0 - DIE_GAP - DIE_SIZE, y0 + DIE_SIZE + 44)
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(buffer, label, origin, font, 1.5, (20, 20, 20, 255), 8, cv2.LINE_AA)
        cv2.putText(buffer, label, origin, font, 1.5, (255, 255, 255, 255), 3, cv2.LINE_AA)

    @staticmethod
    def _text(img: np.ndarray, text: str, origin: tuple[int, int], scale: float, color) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, text, origin, font, scale, (0, 0, 0, 255), 5, cv2.LINE_AA)
        cv2.putText(img, text, origin, font, scale, color, 2, cv2.LINE_AA)

    def _render_panel(self, player: str, stats: dict, active: bool = False) -> np.ndarray:
        """One player's statistics card. "simple" shows counts, "resources" adds the hand."""
        resources = stats["mode"] == "resources"
        height = PANEL_H if resources else PANEL_SIMPLE_H
        img = np.zeros((height, PANEL_W, 4), dtype=np.uint8)
        color = PLAYER_BGR.get(player, DEFAULT_PLAYER_BGR)
        img[:] = (25, 25, 25, 215)
        cv2.rectangle(img, (0, 0), (PANEL_W - 1, height - 1), (*color, 255), 16 if active else 6)
        cv2.rectangle(img, (18, 16), (42, 40), (*color, 255), -1)
        white = (255, 255, 255, 255)
        self._text(img, player.capitalize(), (54, 38), 0.9, white)
        self._text(img, f"PV {stats['points']}", (PANEL_W - 110, 38), 0.9, HIGHLIGHT_BGR + (255,))
        line = f"Casas {stats['settlements']}  Ciud {stats['cities']}  Cam {stats['roads']}"
        self._text(img, line, (18, 82), 0.62, white)
        self._text(img, f"Cartas {stats['cards']}", (22 if active else 18, 120), 0.7, white)
        if active:
            self._text(img, "TURNO", (PANEL_W - 140, 122), 0.8, HIGHLIGHT_BGR + (255,))
        if resources:
            slot = (PANEL_W - 24) // 5
            for i, (res, label) in enumerate(RESOURCE_SHORT.items()):
                x0 = 12 + i * slot
                cv2.rectangle(img, (x0, 140), (x0 + slot - 8, 218), (*RESOURCE_BGR[res], 255), -1)
                cv2.rectangle(img, (x0, 140), (x0 + slot - 8, 218), (20, 20, 20, 255), 2)
                self._text(img, label, (x0 + 6, 163), 0.5, white)
                self._text(img, str(stats["hand"][res]), (x0 + 18, 205), 0.9, white)
        return img

    def _draw_banner(self, buffer: np.ndarray, view) -> None:
        """What the table is waiting for, centered at the top."""
        text = game_banner(view.game)
        if not text:
            return
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale, thickness = 1.3, 3
        (w, h), baseline = cv2.getTextSize(text, font, scale, thickness)
        x = (self.width - w) // 2
        y = 20 + h + 14
        cv2.rectangle(
            buffer, (x - 24, y - h - 20), (x + w + 24, y + baseline + 14), (20, 20, 20, 225), -1
        )
        cv2.rectangle(
            buffer, (x - 24, y - h - 20), (x + w + 24, y + baseline + 14), (*HIGHLIGHT_BGR, 255), 3
        )
        cv2.putText(buffer, text, (x, y), font, scale, (255, 255, 255, 255), thickness, cv2.LINE_AA)

    def _draw_panels(self, buffer: np.ndarray, view) -> None:
        """Statistics card in each player's corner; top corners are turned to face that seat."""
        for index, player in enumerate(view.players):
            stats = (view.stats or {}).get(player)
            if stats is None:
                continue
            game = view.game or {}
            active = game.get("current_player") == player
            panel = self._render_panel(player, stats, active)
            x, y, _, h = panel_rect(index, self.width, self.height)
            if y < self.height / 2:
                panel = cv2.rotate(panel, cv2.ROTATE_180)
            else:
                y += PANEL_H - panel.shape[0]  # keep the card flush with the bottom edge
            ph, pw = panel.shape[:2]
            buffer[y : y + ph, x : x + pw] = panel

    def _generate_patches(self, current_time: float) -> list[ImagePatch]:
        view = self.state.catan if self.state is not None else None
        if view is None:
            return []

        buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)

        for tile in view.producing:
            poly = self._to_screen(hex_corners(tile.q, tile.r))
            fill = buffer.copy()
            cv2.fillPoly(fill, [poly], (*HIGHLIGHT_BGR, 110), lineType=cv2.LINE_AA)
            buffer = fill
            cv2.polylines(
                buffer, [poly], True, (*HIGHLIGHT_BGR, 255), thickness=6, lineType=cv2.LINE_AA
            )

        for road in view.roads:
            (x1, y1), (x2, y2) = edge_endpoints(road.edge)
            p1, p2 = self._to_screen([(x1, y1), (x2, y2)])
            color = PLAYER_BGR.get(road.player, DEFAULT_PLAYER_BGR)
            cv2.line(
                buffer,
                tuple(int(v) for v in p1),
                tuple(int(v) for v in p2),
                (20, 20, 20, 255),
                ROAD_THICKNESS + 4,
                cv2.LINE_AA,
            )
            cv2.line(
                buffer,
                tuple(int(v) for v in p1),
                tuple(int(v) for v in p2),
                (*color, 255),
                ROAD_THICKNESS,
                cv2.LINE_AA,
            )

        for building in view.buildings:
            cx, cy = (int(v) for v in self._to_screen([vertex_position(building.vertex)])[0])
            color = PLAYER_BGR.get(building.player, DEFAULT_PLAYER_BGR)
            half = 15 if building.kind == "city" else 9
            top_left, bottom_right = (cx - half, cy - half), (cx + half, cy + half)
            cv2.rectangle(buffer, top_left, bottom_right, (*color, 255), -1)
            cv2.rectangle(buffer, top_left, bottom_right, (20, 20, 20, 255), 2)
            if building.kind == "city":
                cv2.rectangle(buffer, (cx - 5, cy - 5), (cx + 5, cy + 5), (20, 20, 20, 255), -1)

        robber_center = self._to_screen([tile_center(*view.robber)])[0]
        cv2.circle(buffer, tuple(int(v) for v in robber_center), 16, (*ROBBER_BGR, 255), -1)
        cv2.circle(buffer, tuple(int(v) for v in robber_center), 16, (255, 255, 255, 255), 2)

        if view.dice is not None and view.total is not None:
            self._draw_dice(buffer, view.dice, view.total)

        self._draw_panels(buffer, view)
        self._draw_banner(buffer, view)

        return [ImagePatch(x=0, y=0, width=self.width, height=self.height, data=buffer)]
