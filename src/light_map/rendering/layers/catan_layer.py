import math
import time

import cv2
import numpy as np

from light_map.catan.layout import (
    PANEL_H,
    PANEL_W,
    SIZE,
    edge_endpoints,
    hex_corners,
    panel_rect,
    tile_center,
    vertex_position,
)
from light_map.catan.screens import buttons, quit_button, screen_kind
from light_map.catan.svg import COLORS, DOTS
from light_map.catan.wizard import BALANCE_LABELS
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
PANEL_SIMPLE_H = 172
ROAD_THICKNESS = 9

DIE_SIZE = 104
DIE_GAP = 20
DIE_MARGIN = 28
PULSE_NS = 100_000_000  # the glow of the producing tiles is redrawn every 0.1 s
DIM_FIRST_SECONDS = 6.0  # how long the board stays dark after a roll
DIM_STRONG, DIM_SOFT = 175, 85
ROLL_TUMBLE = 1.0  # seconds the dice spin on the projection after a throw
ROLL_SHOW = 3.2  # seconds the throw stays big in the middle (the 7 announcement included)
# Pip positions on a 3x3 grid (column, row), by die value.
PIPS = {
    1: [(1, 1)],
    2: [(0, 0), (2, 2)],
    3: [(0, 0), (1, 1), (2, 2)],
    4: [(0, 0), (2, 0), (0, 2), (2, 2)],
    5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
    6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)],
}


def _hex_to_bgr(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return b, g, r


TRADE_CODES = {"wood": "MAD", "brick": "LAD", "sheep": "OVE", "wheat": "TRI", "ore": "MIN"}


def game_banner(game: dict | None) -> str | None:
    """Short ASCII text (OpenCV fonts have no accents) with what the table is waiting for."""
    if not game or game.get("phase") in (None, "free"):
        return None
    phase = game["phase"]
    who = (game.get("current_player") or "").upper()
    if phase == "order":
        return f"QUIEN EMPIEZA: {who} TIRA EL DADO"
    if phase == "reveal":
        return f"REVELANDO EL TABLERO {game.get('reveal_done', 0)}/{game.get('reveal_total', 0)}"
    if phase == "setup":
        what = "UNA CASA" if game.get("setup_step") == "settlement" else "UN CAMINO"
        return f"PREPARACION: {who} PONE {what}"
    if phase == "roll":
        return f"TURNO DE {who}: TIRA LOS DADOS"
    if phase == "discard":
        pending = ", ".join(f"{p.upper()} {n}" for p, n in (game.get("discards") or {}).items())
        return f"SALIO 7: DESCARTAN {pending}"
    if phase == "robber":
        return f"{who} MUEVE AL LADRON: SENALA UN HEXAGONO"
    if phase == "steal":
        victims = ", ".join(v.upper() for v in game.get("victims") or [])
        return f"{who} ROBA A: {victims} (SENALA SU PANEL)"
    if phase == "road_building":
        return f"{who} PONE CAMINOS GRATIS"
    if phase == "main" and game.get("trade"):
        trade = game["trade"]
        give = " + ".join(f"{n} {TRADE_CODES.get(r, r)}" for r, n in trade["give"].items())
        get = " + ".join(f"{n} {TRADE_CODES.get(r, r)}" for r, n in trade["get"].items())
        for_whom = f" (A {trade['to'].upper()})" if trade.get("to") else ""
        return f"{trade['from'].upper()} OFRECE {give} POR {get}{for_whom}"
    if phase == "main":
        return f"TURNO DE {who}"
    if phase == "finished":
        return f"{(game.get('winner') or '').upper()} GANO!"
    return None


class CatanLayer(Layer):
    """Highlights the tiles that produce on the last roll and marks the robber."""

    def __init__(self, state: WorldState, map_system: MapSystem, width: int, height: int):
        super().__init__(state=state, is_static=False)
        self.map_system = map_system
        self.width = width
        self.height = height
        self._producing_key: tuple | None = None
        self._producing_since = 0.0
        self._roll_id: int | None = None
        self._roll_seen = -1e9

    def get_current_version(self) -> int:
        if self.state is None:
            return 0
        version = max(self.state.catan_version, self.state.viewport_version)
        view = self.state.catan
        if view is not None and view.dice is not None:
            roll_id = (view.game or {}).get("roll_id")
            if roll_id != self._roll_id:
                self._roll_id, self._roll_seen = roll_id, time.monotonic()
            if time.monotonic() - self._roll_seen < ROLL_SHOW + 0.2:
                return max(version, time.monotonic_ns() // PULSE_NS * PULSE_NS)
        if view is not None and view.producing:
            # the glow breathes: ask for a redraw a few times per second
            return max(version, time.monotonic_ns() // PULSE_NS * PULSE_NS)
        return version

    def _to_screen(self, points: list[tuple[float, float]]) -> np.ndarray:
        return np.array([self.map_system.world_to_screen(x, y) for x, y in points], np.int32)

    @staticmethod
    def _draw_die(buffer, x0: int, y0: int, size: int, value: int) -> None:
        top_left, bottom_right = (x0, y0), (x0 + size, y0 + size)
        cv2.rectangle(buffer, top_left, bottom_right, (245, 245, 245, 255), -1)
        cv2.rectangle(buffer, top_left, bottom_right, (20, 20, 20, 255), max(3, size // 28))
        for col, row in PIPS[value]:
            center = (x0 + size * (col + 1) // 4, y0 + size * (row + 1) // 4)
            cv2.circle(buffer, center, max(6, size // 10), (20, 20, 20, 255), -1, cv2.LINE_AA)

    def _draw_roll_animation(self, buffer, view) -> None:
        """A new throw: the dice spin in the middle of the screen, then show the result big."""
        age = time.monotonic() - self._roll_seen
        if view.dice is None or view.total is None or age >= ROLL_SHOW:
            return
        w, h = self.width, self.height
        size = 190
        cx, cy = w // 2, h // 2 - 40
        cv2.rectangle(buffer, (cx - 330, cy - 170), (cx + 330, cy + 250), (20, 20, 20, 225), -1)
        cv2.rectangle(buffer, (cx - 330, cy - 170), (cx + 330, cy + 250), (*HIGHLIGHT_BGR, 255), 6)
        tumbling = age < ROLL_TUMBLE
        rng = np.random.default_rng(int(age * 14))
        for slot, final in enumerate(view.dice):
            value = int(rng.integers(1, 7)) if tumbling else final
            jitter = (
                (int(rng.integers(-14, 15)), int(rng.integers(-14, 15))) if tumbling else (0, 0)
            )
            x0 = cx - size - 25 + slot * (size + 50) + jitter[0]
            self._draw_die(buffer, x0, cy - size // 2 - 20 + jitter[1], size, value)
        if tumbling:
            text, color = "TIRANDO...", (255, 255, 255, 255)
        elif view.total == 7:
            text, color = "SALIO 7: LADRON", (60, 60, 255, 255)
        else:
            text, color = f"= {view.total}", (*HIGHLIGHT_BGR, 255)
        self._big_text(buffer, text, (cx, cy + 190), 2.2, color, 6)

    def _draw_dice(self, buffer: np.ndarray, dice: tuple[int, int], total: int) -> None:
        """Draws both dice and their total in the top-right corner of the projection."""
        y0 = DIE_MARGIN + 12
        second_x0 = self.width - DIE_MARGIN - DIE_SIZE - 12
        plate = (second_x0 - DIE_GAP - DIE_SIZE - 20, y0 - 20)
        cv2.rectangle(
            buffer,
            plate,
            (self.width - DIE_MARGIN + 6, y0 + DIE_SIZE + 78),
            (20, 20, 20, 240),
            -1,
        )
        cv2.rectangle(
            buffer,
            plate,
            (self.width - DIE_MARGIN + 6, y0 + DIE_SIZE + 78),
            (*HIGHLIGHT_BGR, 255),
            4,
        )
        for x0, value in ((second_x0 - DIE_GAP - DIE_SIZE, dice[0]), (second_x0, dice[1])):
            top_left, bottom_right = (x0, y0), (x0 + DIE_SIZE, y0 + DIE_SIZE)
            cv2.rectangle(buffer, top_left, bottom_right, (245, 245, 245, 255), -1)
            cv2.rectangle(buffer, top_left, bottom_right, (20, 20, 20, 255), 3)
            for col, row in PIPS[value]:
                px = x0 + DIE_SIZE * (col + 1) // 4
                py = y0 + DIE_SIZE * (row + 1) // 4
                cv2.circle(buffer, (px, py), 8, (20, 20, 20, 255), -1, cv2.LINE_AA)

        label = f"= {total}"
        origin = (second_x0 - DIE_GAP - DIE_SIZE, y0 + DIE_SIZE + 58)
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
        cards = f"Cartas {stats['cards']}  Des {stats.get('dev_cards', 0)}"
        self._text(img, cards, (22 if active else 18, 120), 0.7, white)
        if active:
            self._text(img, "TURNO", (PANEL_W - 140, 122), 0.8, HIGHLIGHT_BGR + (255,))
        # Row of badges: the two bonus cards and the knights played.
        badges = (
            (stats.get("has_longest_road"), "CAMINO+2", 18, 102),
            (stats.get("has_largest_army"), "EJERCITO+2", 110, 214),
        )
        for owned, label, x0, x1 in badges:
            if owned:
                cv2.rectangle(img, (x0, 134), (x1, 164), (*HIGHLIGHT_BGR, 255), -1)
                cv2.putText(
                    img,
                    label,
                    (x0 + 5, 155),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (20, 20, 20, 255),
                    2,
                    cv2.LINE_AA,
                )
        if stats.get("knights"):
            self._text(img, f"Cab {stats['knights']}", (222, 156), 0.55, white)
        if resources:
            slot = (PANEL_W - 24) // 5
            top = PANEL_SIMPLE_H
            for i, (res, label) in enumerate(RESOURCE_SHORT.items()):
                x0 = 12 + i * slot
                box = (x0, top, x0 + slot - 8, top + 78)
                cv2.rectangle(img, box[:2], box[2:], (*RESOURCE_BGR[res], 255), -1)
                cv2.rectangle(img, box[:2], box[2:], (20, 20, 20, 255), 2)
                self._text(img, label, (x0 + 6, top + 23), 0.5, white)
                self._text(img, str(stats["hand"][res]), (x0 + 18, top + 65), 0.9, white)
        return img

    def _draw_revealed_tiles(self, buffer: np.ndarray, view) -> None:
        """While the board is hidden the map shows empty hexagons: paint what is already out."""
        if not (view.game or {}).get("hidden"):
            return
        tiles = (view.board or {}).get("tiles") or []
        ox, oy = self.map_system.world_to_screen(0, 0)
        ux, uy = self.map_system.world_to_screen(100, 0)
        scale = max(0.3, math.hypot(ux - ox, uy - oy) / 100)
        font = cv2.FONT_HERSHEY_SIMPLEX
        k = SIZE / 100
        for tile in tiles:
            resource = tile["resource"]
            if resource == "hidden":
                continue
            poly = self._to_screen(hex_corners(tile["q"], tile["r"]))
            color = _hex_to_bgr(COLORS[resource])
            cv2.fillPoly(buffer, [poly], (*color, 255), lineType=cv2.LINE_AA)
            cv2.polylines(buffer, [poly], True, (245, 245, 245, 255), 3, cv2.LINE_AA)
            number = tile["number"]
            if number is None:
                continue
            cx, cy = (int(v) for v in self.map_system.world_to_screen(tile["x"], tile["y"]))
            radius = int(30 * k * scale)
            cv2.circle(buffer, (cx, cy), radius, (225, 248, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(buffer, (cx, cy), radius, (33, 33, 33, 255), 2, cv2.LINE_AA)
            ink = (40, 40, 198, 255) if number in (6, 8) else (33, 33, 33, 255)
            text = str(number)
            size = 28 * k * scale / 25.0
            (tw, th), _ = cv2.getTextSize(text, font, size, 2)
            cv2.putText(buffer, text, (cx - tw // 2, cy + th // 3), font, size, ink, 2, cv2.LINE_AA)
            dots = DOTS[number]
            start = cx - (dots - 1) * 4 * k * scale
            for i in range(dots):
                dot = (int(start + i * 8 * k * scale), int(cy + 17 * k * scale))
                cv2.circle(buffer, dot, max(2, int(2 * k * scale)), ink, -1, cv2.LINE_AA)

    def _draw_ports(self, buffer: np.ndarray, view) -> None:
        """Harbors: two piers from the coast edge to a marker with the trade ratio."""
        ports = ((view.board or {}).get("ports")) or []
        if not ports:
            return
        ox, oy = self.map_system.world_to_screen(0, 0)
        ux, uy = self.map_system.world_to_screen(100, 0)
        scale = max(0.3, math.hypot(ux - ox, uy - oy) / 100)
        radius = int(min(max(33 * scale, 18), 56))
        font = cv2.FONT_HERSHEY_SIMPLEX
        for port in ports:
            anchor = tuple(int(v) for v in self.map_system.world_to_screen(port["x"], port["y"]))
            for key in (("x1", "y1"), ("x2", "y2")):
                end = tuple(
                    int(v) for v in self.map_system.world_to_screen(port[key[0]], port[key[1]])
                )
                cv2.line(buffer, end, anchor, (30, 30, 30, 255), 9, cv2.LINE_AA)
                cv2.line(buffer, end, anchor, (235, 235, 235, 255), 5, cv2.LINE_AA)
            kind = port["kind"]
            fill = (225, 225, 225) if kind == "any" else RESOURCE_BGR.get(kind, (200, 200, 200))
            cv2.circle(buffer, anchor, radius, (30, 30, 30, 255), -1, cv2.LINE_AA)
            cv2.circle(buffer, anchor, radius - 4, (*fill, 255), -1, cv2.LINE_AA)
            label = "3:1" if kind == "any" else "2:1"
            size = radius / 36
            (tw, th), _ = cv2.getTextSize(label, font, size, 2)
            text_color = (
                (20, 20, 20, 255) if kind in ("any", "wheat", "sheep") else (255, 255, 255, 255)
            )
            offset = th // 2 if kind == "any" else -int(radius * 0.14)
            origin = (anchor[0] - tw // 2, anchor[1] + offset)
            cv2.putText(buffer, label, origin, font, size, text_color, 2, cv2.LINE_AA)
            if kind != "any":
                code = RESOURCE_SHORT[kind]
                (cw, ch), _ = cv2.getTextSize(code, font, size * 0.8, 2)
                cv2.putText(
                    buffer,
                    code,
                    (anchor[0] - cw // 2, anchor[1] + int(radius * 0.62) + ch // 2),
                    font,
                    size * 0.8,
                    text_color,
                    2,
                    cv2.LINE_AA,
                )

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
        for index, player in enumerate(view.corners):
            if player is None:
                continue
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

    # Guided screens: big, simple and obvious

    @staticmethod
    def _big_text(img, text, center, scale, color=(255, 255, 255, 255), thickness=4) -> None:
        """Text centered on a point with a dark outline (ASCII only)."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        (w, h), _ = cv2.getTextSize(text, font, scale, thickness)
        origin = (int(center[0] - w / 2), int(center[1] + h / 2))
        cv2.putText(img, text, origin, font, scale, (0, 0, 0, 255), thickness + 6, cv2.LINE_AA)
        cv2.putText(img, text, origin, font, scale, color, thickness, cv2.LINE_AA)

    def _draw_button(self, buffer, button, fill, text_color=(255, 255, 255, 255)) -> None:
        x, y, w, h = button.x, button.y, button.w, button.h
        if button.shape == "circle":
            center = (x + w // 2, y + h // 2)
            cv2.circle(buffer, center, w // 2, (*fill, 255), -1, cv2.LINE_AA)
            cv2.circle(buffer, center, w // 2, (255, 255, 255, 255), 8, cv2.LINE_AA)
            return
        cv2.rectangle(buffer, (x, y), (x + w, y + h), (*fill, 255), -1)
        cv2.rectangle(buffer, (x, y), (x + w, y + h), (255, 255, 255, 255), 6)

    def _draw_screen(self, buffer, view, kind: str) -> None:
        """A full-screen guide that replaces the board: players, rules, order, seats or mode."""
        w, h = self.width, self.height
        buffer[:] = (24, 18, 18, 255)
        big = self._big_text
        game = view.game or {}
        gold = HIGHLIGHT_BGR + (255,)
        if kind == "players":
            big(buffer, "CUANTOS JUGADORES?", (w // 2, 150), 2.6, gold, 6)
            for button in buttons(view, w, h):
                self._draw_button(buffer, button, (70, 50, 40))
                center = (button.x + button.w // 2, button.y + button.h // 2)
                big(buffer, button.label, center, 9.0, (255, 255, 255, 255), 14)
            big(buffer, "SENALA UN NUMERO CON EL DEDO 1 SEGUNDO", (w // 2, h - 120), 1.6)
        elif kind == "rules":
            big(buffer, "REGLAS DEL TABLERO", (w // 2, 100), 2.4, gold, 6)
            rules = view.wizard["rules"]
            for button in buttons(view, w, h):
                if button.id in ("ok", "back"):
                    fill = (70, 160, 70) if button.id == "ok" else (90, 90, 90)
                    self._draw_button(buffer, button, fill)
                    center = (button.x + button.w // 2, button.y + button.h // 2)
                    big(buffer, button.label, center, 2.4, (255, 255, 255, 255), 6)
                    continue
                self._draw_button(buffer, button, (60, 48, 42))
                cy = button.y + button.h // 2
                big(buffer, button.label, (button.x + 40 + len(button.label) * 17, cy), 1.5)
                if button.id == "balance":
                    value = BALANCE_LABELS.get(rules["balance"], rules["balance"])
                    pill, text = (170, 110, 40), value
                else:
                    pill, text = ((70, 160, 70), "SI") if button.on else ((60, 60, 200), "NO")
                px = button.x + button.w - 150
                cv2.rectangle(buffer, (px - 60, cy - 32), (px + 90, cy + 32), (*pill, 255), -1)
                big(buffer, text, (px + 15, cy), 1.3, (255, 255, 255, 255), 4)
            big(buffer, "SENALA 1 SEGUNDO PARA CAMBIAR", (w // 2, h - 190), 1.2)
        elif kind == "order":
            who = (game.get("current_player") or "").upper()
            color = PLAYER_BGR.get(game.get("current_player"), DEFAULT_PLAYER_BGR)
            big(buffer, "QUIEN EMPIEZA?", (w // 2, 130), 2.6, gold, 6)
            big(buffer, "TURNO", (w // 2, 330), 5.0, (255, 255, 255, 255), 10)
            big(buffer, who, (w // 2, 540), 8.0, (*color, 255), 16)
            big(buffer, "PON LA MANO EN ROCK PARA TIRAR EL DADO", (w // 2, 760), 1.7)
            rolled = game.get("order_rolls") or {}
            for i, (player, value) in enumerate(rolled.items()):
                tone = PLAYER_BGR.get(player, DEFAULT_PLAYER_BGR)
                big(buffer, f"{player.upper()}: {value}", (w // 2, 860 + i * 70), 1.7, (*tone, 255))
        elif kind == "seats":
            who = (game.get("current_player") or "").upper()
            color = PLAYER_BGR.get(game.get("current_player"), DEFAULT_PLAYER_BGR)
            big(buffer, "ELIGE TU ESQUINA", (w // 2, 150), 2.6, gold, 6)
            big(buffer, who, (w // 2, 430), 6.0, (*color, 255), 12)
            big(buffer, "LLEVA EL PUNO A TU ESQUINA 3 SEGUNDOS", (w // 2, 640), 1.6)
            for corner, player in enumerate(view.corners):
                if not player:
                    continue
                x, y, pw, ph = panel_rect(corner, w, h)
                center = (x + pw // 2, y + ph // 2)
                tone = PLAYER_BGR.get(player, DEFAULT_PLAYER_BGR)
                cv2.circle(buffer, center, 130, (*tone, 255), -1, cv2.LINE_AA)
                cv2.circle(buffer, center, 130, (255, 255, 255, 255), 8, cv2.LINE_AA)
                big(buffer, player.upper(), center, 1.6, (20, 20, 20, 255), 4)
            for button in buttons(view, w, h):
                self._draw_button(buffer, button, (70, 50, 40))
                center = (button.x + button.w // 2, button.y + button.h // 2)
                big(buffer, "AQUI", (center[0], center[1] - 20), 1.8)
                big(buffer, "PUNO 3 S", (center[0], center[1] + 40), 1.2)
        elif kind == "mode":
            big(buffer, "QUE VA PRIMERO?", (w // 2, 150), 2.6, gold, 6)
            notes = {
                "map": ("SE REVELA EL MAPA", "Y LUEGO SE PONEN LAS CASAS"),
                "houses": ("SE PONEN LAS CASAS", "Y LUEGO SE REVELA EL MAPA"),
            }
            for button in buttons(view, w, h):
                self._draw_button(buffer, button, (70, 50, 40))
                cx = button.x + button.w // 2
                big(buffer, button.label, (cx, button.y + 110), 1.8, gold, 5)
                first, second = notes[button.id]
                big(buffer, first, (cx, button.y + 230), 1.3)
                big(buffer, second, (cx, button.y + 290), 1.3)
            big(buffer, "SENALA UNA OPCION CON EL DEDO 1 SEGUNDO", (w // 2, h - 110), 1.5)

    def _draw_quit(self, buffer) -> None:
        """A small exit button at the bottom center (point at it for 3 seconds)."""
        button = quit_button(self.width, self.height)
        top_left, bottom_right = (button.x, button.y), (button.x + button.w, button.y + button.h)
        cv2.rectangle(buffer, top_left, bottom_right, (30, 30, 30, 255), -1)
        cv2.rectangle(buffer, top_left, bottom_right, (150, 150, 150, 255), 3)
        center = (button.x + button.w // 2, button.y + button.h // 2 - 8)
        self._big_text(buffer, "SALIR", center, 0.9, (255, 255, 255, 255), 2)
        self._big_text(
            buffer, "SENALA 3 S", (center[0], center[1] + 26), 0.5, (200, 200, 200, 255), 1
        )

    def _draw_turn_corner(self, buffer, view) -> None:
        """A big quarter circle in the corner of the player in turn, and the pass-turn button."""
        game = view.game or {}
        player = game.get("current_player")
        if game.get("phase") in (None, "free", "order", "seats", "mode", "reveal", "finished"):
            return
        if player not in view.corners:
            return
        corner = view.corners.index(player)
        x, y, pw, ph = panel_rect(corner, self.width, self.height)
        right = x > self.width / 2
        bottom = y > self.height / 2
        center = (self.width if right else 0, self.height if bottom else 0)
        angle = {(False, False): 0, (True, False): 90, (True, True): 180, (False, True): 270}[
            (right, bottom)
        ]
        color = PLAYER_BGR.get(player, DEFAULT_PLAYER_BGR)
        cv2.ellipse(
            buffer, center, (430, 430), 0, angle, angle + 90, (*color, 150), -1, cv2.LINE_AA
        )
        cv2.ellipse(
            buffer, center, (430, 430), 0, angle, angle + 90, (*color, 255), 10, cv2.LINE_AA
        )
        label = f"JUEGA {player.upper()}"
        height = 60
        patch = np.zeros((height, pw, 4), dtype=np.uint8)
        self._text(patch, label, (16, 44), 1.4, (255, 255, 255, 255))
        patch[:, :, 3] = np.where(patch[:, :, 3] > 0, 255, 0)
        gap = 14
        for button in buttons(view, self.width, self.height):
            if button.id != "end_turn":
                continue
            ly = button.y - height - gap if bottom else button.y + button.h + gap
            if not bottom:
                patch = cv2.rotate(patch, cv2.ROTATE_180)
            buffer[ly : ly + height, x : x + pw] = patch
            cv2.rectangle(
                buffer,
                (button.x, button.y),
                (button.x + button.w, button.y + button.h),
                (20, 20, 20, 235),
                -1,
            )
            cv2.rectangle(
                buffer,
                (button.x, button.y),
                (button.x + button.w, button.y + button.h),
                (*color, 255),
                8,
            )
            lines = ("PASAR TURNO", "PUNO 5 SEGUNDOS")
            sub = np.zeros((button.h, button.w, 4), dtype=np.uint8)
            self._big_text(sub, lines[0], (button.w // 2, button.h // 2 - 22), 1.2, (255,) * 4, 3)
            self._big_text(sub, lines[1], (button.w // 2, button.h // 2 + 26), 0.9, (255,) * 4, 2)
            if not bottom:
                sub = cv2.rotate(sub, cv2.ROTATE_180)
            mask = sub[:, :, 3] > 0
            region = buffer[button.y : button.y + button.h, button.x : button.x + button.w]
            region[mask] = sub[mask]

    def _draw_roll_band(self, buffer, view) -> None:
        """While everybody waits for the dice: whose turn it is, huge, in the middle."""
        game = view.game or {}
        if game.get("phase") != "roll" or not game.get("current_player"):
            return
        player = game["current_player"]
        color = PLAYER_BGR.get(player, DEFAULT_PLAYER_BGR)
        y0, y1 = self.height // 2 - 150, self.height // 2 + 150
        band = buffer[y0:y1].copy()
        band[:] = (20, 20, 20, 205)
        buffer[y0:y1] = band
        cv2.rectangle(buffer, (0, y0), (self.width, y1), (*color, 255), 10)
        self._big_text(
            buffer, f"TURNO DE {player.upper()}", (self.width // 2, y0 + 100), 3.6, (*color, 255), 8
        )
        self._big_text(
            buffer, "ROCK PARA TIRAR LOS DADOS", (self.width // 2, y0 + 220), 1.8, (255,) * 4, 4
        )

    def _draw_production(self, buffer: np.ndarray, view, now: float) -> None:
        """Darkens the board and lights up (with a soft pulse) the tiles that pay on this roll."""
        key = (view.total, tuple((t.q, t.r) for t in view.producing))
        if key != self._producing_key:
            self._producing_key = key
            self._producing_since = now
        strong = now - self._producing_since < DIM_FIRST_SECONDS
        buffer[:] = (22, 16, 16, DIM_STRONG if strong else DIM_SOFT)
        pulse = 0.5 + 0.5 * math.sin(now * 5.0)
        polys = [self._to_screen(hex_corners(t.q, t.r)) for t in view.producing]
        for poly in polys:
            cv2.fillPoly(buffer, [poly], (0, 0, 0, 0), lineType=cv2.LINE_AA)  # full colors again
        for poly in polys:
            glow = int(60 + 120 * pulse)
            cv2.polylines(buffer, [poly], True, (*HIGHLIGHT_BGR, glow), 26, cv2.LINE_AA)
            cv2.polylines(buffer, [poly], True, (*HIGHLIGHT_BGR, 255), 9, cv2.LINE_AA)
            cv2.polylines(
                buffer, [poly], True, (255, 255, 255, int(120 + 135 * pulse)), 3, cv2.LINE_AA
            )

    def _generate_patches(self, current_time: float) -> list[ImagePatch]:
        view = self.state.catan if self.state is not None else None
        if view is None:
            return []

        buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)

        kind = screen_kind(view)
        if kind:
            self._draw_screen(buffer, view, kind)
            self._draw_quit(buffer)
            return [ImagePatch(x=0, y=0, width=self.width, height=self.height, data=buffer)]

        if view.producing:
            self._draw_production(buffer, view, current_time)

        self._draw_revealed_tiles(buffer, view)
        self._draw_ports(buffer, view)

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

        if view.robber is not None:
            robber_center = self._to_screen([tile_center(*view.robber)])[0]
            cv2.circle(buffer, tuple(int(v) for v in robber_center), 16, (*ROBBER_BGR, 255), -1)
            cv2.circle(buffer, tuple(int(v) for v in robber_center), 16, (255, 255, 255, 255), 2)

        if view.dice is not None and view.total is not None:
            self._draw_dice(buffer, view.dice, view.total)

        self._draw_turn_corner(buffer, view)
        self._draw_panels(buffer, view)
        self._draw_roll_band(buffer, view)
        self._draw_roll_animation(buffer, view)
        self._draw_banner(buffer, view)
        self._draw_quit(buffer)

        return [ImagePatch(x=0, y=0, width=self.width, height=self.height, data=buffer)]
