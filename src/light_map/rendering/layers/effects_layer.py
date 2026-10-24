"""Short animations of a dice throw: the dice spinning, the paying tiles glowing and the cards
flying from those tiles to the players who collect them.

They live in their own layer so that redrawing them 60 times a second only touches small patches
instead of the whole board layer.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import cv2
import numpy as np

from light_map.catan.layout import hex_corners, panel_rect, tile_center
from light_map.core.common_types import ImagePatch, Layer
from light_map.map.map_system import MapSystem
from light_map.rendering.layers.catan_layer import (
    HIGHLIGHT_BGR,
    PIPS,
    RESOURCE_BGR,
    RESOURCE_SHORT,
)
from light_map.state.world_state import WorldState


REFRESH_NS = 16_000_000  # about 60 redraws per second while something moves
ROLL_TUMBLE = 1.0  # seconds the dice spin in the middle after a throw
ROLL_SHOW = 1.9  # seconds the throw stays big in the middle, then the cards leave the tiles
ROLL_SHOW_SEVEN = 2.8  # a 7 has no cards to follow: its warning stays a little longer
GLOW_SECONDS = 6.0  # how long the paying tiles keep pulsing
FLIGHT_START = 1.9  # seconds after the throw when the cards leave the tiles
FLIGHT_SECONDS = 0.9
CARD_GAP = 0.13  # seconds between two cards that go to the same player
CARD_W, CARD_H = 46, 64


@dataclass(frozen=True)
class Flight:
    resource: str
    start: tuple[float, float]  # world position of the tile
    player: str
    delay: float  # seconds after FLIGHT_START


def plan_flights(view) -> list[Flight]:
    """One card per settlement (two per city) next to every paying tile, for its owner."""
    tiles = {(t.q, t.r): t for t in view.producing}
    sent: dict[tuple, int] = {}
    flights = []
    for building in view.buildings:
        for cell in building.vertex:
            tile = tiles.get(cell)
            if tile is None:
                continue
            amount = 2 if building.kind == "city" else 1
            for _ in range(amount):
                key = (cell, building.player)
                order = sent.get(key, 0)
                sent[key] = order + 1
                flights.append(
                    Flight(tile.resource, tile_center(*cell), building.player, order * CARD_GAP)
                )
    return flights


def _ease(t: float) -> float:
    return t * t * (3 - 2 * t)


class EffectsLayer(Layer):
    def __init__(self, state: WorldState, map_system: MapSystem, width: int, height: int):
        super().__init__(state=state, is_static=False)
        self.map_system = map_system
        self.width = width
        self.height = height
        self._roll_id: int | None = None
        self._roll_seen = -1e9
        self._flights: list[Flight] = []

    # Timeline

    def _sync(self, view) -> None:
        """Starts the animations when a new throw shows up in the view."""
        roll_id = (view.game or {}).get("roll_id")
        if view.dice is None or roll_id == self._roll_id:
            return
        self._roll_id, self._roll_seen = roll_id, time.monotonic()
        self._flights = plan_flights(view)

    def _age(self) -> float:
        return time.monotonic() - self._roll_seen

    def _last_flight_end(self) -> float:
        if not self._flights:
            return 0.0
        return FLIGHT_START + max(f.delay for f in self._flights) + FLIGHT_SECONDS

    def _active(self) -> bool:
        return self._age() < max(ROLL_SHOW_SEVEN, GLOW_SECONDS, self._last_flight_end()) + 0.1

    def get_current_version(self) -> int:
        if self.state is None:
            return 0
        version = max(self.state.catan_version, self.state.viewport_version)
        view = self.state.catan
        if view is not None:
            self._sync(view)
            if view.dice is not None and self._active():
                return max(version, time.monotonic_ns() // REFRESH_NS * REFRESH_NS)
        return version

    # Drawing

    def _screen(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = self.map_system.world_to_screen(*point)
        return int(x), int(y)

    @staticmethod
    def _text(img, text: str, center: tuple[int, int], scale: float, color, thickness: int) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        (w, h), _ = cv2.getTextSize(text, font, scale, thickness)
        origin = (int(center[0] - w / 2), int(center[1] + h / 2))
        cv2.putText(img, text, origin, font, scale, (0, 0, 0, 255), thickness + 6, cv2.LINE_AA)
        cv2.putText(img, text, origin, font, scale, color, thickness, cv2.LINE_AA)

    @staticmethod
    def _die(img, x0: int, y0: int, size: int, value: int) -> None:
        top_left, bottom_right = (x0, y0), (x0 + size, y0 + size)
        cv2.rectangle(img, top_left, bottom_right, (245, 245, 245, 255), -1)
        cv2.rectangle(img, top_left, bottom_right, (20, 20, 20, 255), max(3, size // 28))
        for col, row in PIPS[value]:
            center = (x0 + size * (col + 1) // 4, y0 + size * (row + 1) // 4)
            cv2.circle(img, center, max(6, size // 10), (20, 20, 20, 255), -1, cv2.LINE_AA)

    def _roll_patch(self, view, age: float) -> ImagePatch | None:
        """The dice spinning in the middle of the screen, then the result (and the 7 warning)."""
        shown = ROLL_SHOW_SEVEN if view.total == 7 else ROLL_SHOW
        if view.dice is None or view.total is None or age >= shown:
            return None
        width, height = 660, 420
        patch = np.zeros((height, width, 4), dtype=np.uint8)
        cv2.rectangle(patch, (0, 0), (width - 1, height - 1), (20, 20, 20, 225), -1)
        cv2.rectangle(patch, (0, 0), (width - 1, height - 1), (*HIGHLIGHT_BGR, 255), 6)
        size = 190
        tumbling = age < ROLL_TUMBLE
        rng = np.random.default_rng(int(age * 14))
        for slot, final in enumerate(view.dice):
            value = int(rng.integers(1, 7)) if tumbling else final
            dx, dy = (
                (int(rng.integers(-14, 15)), int(rng.integers(-14, 15))) if tumbling else (0, 0)
            )
            self._die(patch, 130 + slot * (size + 50) - 25 + dx, 50 + dy, size, value)
        if tumbling:
            text, color = "TIRANDO...", (255, 255, 255, 255)
        elif view.total == 7:
            text, color = "SALIO 7: LADRON", (60, 60, 255, 255)
        else:
            text, color = f"= {view.total}", (*HIGHLIGHT_BGR, 255)
        self._text(patch, text, (width // 2, 345), 2.2, color, 6)
        x = self.width // 2 - width // 2
        y = self.height // 2 - 40 - 170
        return ImagePatch(x=x, y=y, width=width, height=height, data=patch)

    def _glow_patches(self, view, age: float, now: float) -> list[ImagePatch]:
        """A pulsing gold halo around the tiles that pay, for the first seconds after a throw."""
        if age >= GLOW_SECONDS or not view.producing:
            return []
        pulse = 0.5 + 0.5 * math.sin(now * 6.0)
        patches = []
        for tile in view.producing:
            points = np.array([self._screen(c) for c in hex_corners(tile.q, tile.r)], np.int32)
            pad = 24
            x0, y0 = np.maximum(points.min(axis=0) - pad, 0)
            x1 = min(int(points[:, 0].max()) + pad, self.width)
            y1 = min(int(points[:, 1].max()) + pad, self.height)
            if x1 <= x0 or y1 <= y0:
                continue
            patch = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
            local = points - np.array([x0, y0], np.int32)
            cv2.polylines(
                patch, [local], True, (*HIGHLIGHT_BGR, int(70 + 130 * pulse)), 24, cv2.LINE_AA
            )
            cv2.polylines(
                patch, [local], True, (255, 255, 255, int(150 + 105 * pulse)), 4, cv2.LINE_AA
            )
            patches.append(
                ImagePatch(x=int(x0), y=int(y0), width=x1 - x0, height=y1 - y0, data=patch)
            )
        return patches

    def _card_patch(self, flight: Flight, view, age: float) -> ImagePatch | None:
        """One card on its way from the tile to the panel of its player."""
        if flight.player not in view.corners:
            return None
        t = (age - FLIGHT_START - flight.delay) / FLIGHT_SECONDS
        if not 0.0 <= t <= 1.0:
            return None
        sx, sy = self._screen(flight.start)
        px, py, pw, ph = panel_rect(view.corners.index(flight.player), self.width, self.height)
        ex, ey = px + pw // 2, py + ph // 2
        e = _ease(t)
        x = sx + (ex - sx) * e
        y = sy + (ey - sy) * e - 70 * math.sin(math.pi * e)  # a little arc
        scale = 1.0 + 0.35 * math.sin(math.pi * e)
        w, h = int(CARD_W * scale), int(CARD_H * scale)
        patch = np.zeros((h, w, 4), dtype=np.uint8)
        color = RESOURCE_BGR.get(flight.resource, (200, 200, 200))
        cv2.rectangle(patch, (0, 0), (w - 1, h - 1), (*color, 255), -1)
        cv2.rectangle(patch, (0, 0), (w - 1, h - 1), (255, 255, 255, 255), 3)
        cv2.rectangle(patch, (3, 3), (w - 4, h - 4), (20, 20, 20, 255), 1)
        label = RESOURCE_SHORT.get(flight.resource, "?")
        self._text(patch, label, (w // 2, h // 2), 0.5 * scale, (255, 255, 255, 255), 1)
        left, top = int(x - w / 2), int(y - h / 2)
        if left < 0 or top < 0 or left + w > self.width or top + h > self.height:
            return None
        return ImagePatch(x=left, y=top, width=w, height=h, data=patch)

    def _generate_patches(self, current_time: float) -> list[ImagePatch]:
        view = self.state.catan if self.state is not None else None
        if view is None or view.dice is None:
            return []
        self._sync(view)
        age = self._age()
        patches = self._glow_patches(view, age, time.monotonic())
        roll = self._roll_patch(view, age)
        if roll is not None:
            patches.append(roll)
        for flight in self._flights:
            card = self._card_patch(flight, view, age)
            if card is not None:
                patches.append(card)
        return patches
