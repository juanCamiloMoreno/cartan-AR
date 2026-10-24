"""Plays with the mouse as if it were a hand, to try the whole game without projector or camera.

The mouse is a hand with the gesture picked in the right-click menu: it follows the cursor and
goes through exactly the same code as a real hand (rings, holds, buttons, aiming...). Middle click
changes to the next gesture quickly; "Sin mano" takes the hand away.
"""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np

from light_map.core.common_types import GestureType
from light_map.core.scene import HandInput


MOUSE_HANDS_ENV = "LIGHT_MAP_MOUSE_HANDS"

# (gesture, label without accents, what it does in the game); None is "no hand".
MENU_ITEMS: tuple[tuple[GestureType | None, str], ...] = (
    (GestureType.POINTING, "SENALAR  (botones, aim)"),
    (GestureType.CLOSED_FIST, "PUNO  (esquinas, pasar turno)"),
    (GestureType.ROCK, "ROCA  (tirar dados)"),
    (GestureType.VICTORY, "PAZ  (construir)"),
    (GestureType.OPEN_PALM, "PALMA"),
    (GestureType.GUN, "PISTOLA"),
    (GestureType.SHAKA, "SHAKA  (abrir el menu)"),
    (None, "SIN MANO"),
)
MENU_W = 520
ITEM_H = 62
TITLE_H = 54
GOLD = (0, 215, 255)


class MouseHands:
    """Keeps the gesture picked for the mouse and turns the cursor into a HandInput."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.gesture: GestureType | None = GestureType.POINTING
        self.position: tuple[int, int] | None = None
        self.menu_at: tuple[int, int] | None = None
        self._hover: int | None = None
        self._injected = False
        self.fps = 0.0  # frames per second, smoothed
        self._last_frame = 0.0
        self._last_log = 0.0

    # Mouse

    def on_mouse(self, event: int, x: int, y: int, flags: int = 0, param=None) -> None:
        self.position = (int(x), int(y))
        if self.menu_at is not None:
            self._hover = self._item_at(x, y)
        if event == cv2.EVENT_RBUTTONDOWN:
            self.menu_at = self._clamped(x, y)
            self._hover = None
        elif event == cv2.EVENT_LBUTTONDOWN and self.menu_at is not None:
            item = self._item_at(x, y)
            if item is not None:
                self.gesture = MENU_ITEMS[item][0]
            self.menu_at = None
        elif event == cv2.EVENT_MBUTTONDOWN:
            self.cycle()

    def cycle(self) -> None:
        """Next gesture of the menu (skipping "no hand")."""
        gestures = [g for g, _ in MENU_ITEMS if g is not None]
        current = gestures.index(self.gesture) if self.gesture in gestures else -1
        self.gesture = gestures[(current + 1) % len(gestures)]

    # Menu geometry

    def _clamped(self, x: int, y: int) -> tuple[int, int]:
        height = TITLE_H + ITEM_H * len(MENU_ITEMS)
        return (
            max(0, min(int(x), self.width - MENU_W)),
            max(0, min(int(y), self.height - height)),
        )

    def _item_at(self, x: float, y: float) -> int | None:
        if self.menu_at is None:
            return None
        mx, my = self.menu_at
        if not (mx <= x < mx + MENU_W) or y < my + TITLE_H:
            return None
        index = int((y - my - TITLE_H) // ITEM_H)
        return index if 0 <= index < len(MENU_ITEMS) else None

    # Into the app

    def hands(self) -> list[HandInput]:
        """The simulated hand (none while the menu is open or when there is "no hand")."""
        if self.gesture is None or self.position is None or self.menu_at is not None:
            return []
        return [HandInput(self.gesture, self.position, (0.0, 0.0), None)]

    def inject(self, state, now: float) -> None:
        """Puts the simulated hand into the world state (call it every frame before the scenes)."""
        hands = self.hands()
        if hands or self._injected:
            state.update_inputs(hands, now)
        self._injected = bool(hands)

    def tick(self, now: float | None = None) -> None:
        """Counts a frame: keeps the smoothed FPS and logs it every 5 seconds."""
        now = time.perf_counter() if now is None else now
        if self._last_frame:
            instant = 1.0 / max(now - self._last_frame, 1e-6)
            self.fps = instant if self.fps == 0 else 0.9 * self.fps + 0.1 * instant
        self._last_frame = now
        if now - self._last_log >= 5.0:
            self._last_log = now
            logging.info("Projection FPS: %.1f", self.fps)

    def draw(self, image: np.ndarray) -> None:
        """The FPS counter at the top, the hint in the corner and, when open, the right-click menu."""
        self.tick()
        font = cv2.FONT_HERSHEY_SIMPLEX
        label = f"FPS {self.fps:4.1f}"
        color = (
            (80, 230, 80) if self.fps >= 20 else (0, 215, 255) if self.fps >= 10 else (60, 60, 255)
        )
        x = image.shape[1] // 2 + 500
        cv2.putText(image, label, (x, 44), font, 0.95, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(image, label, (x, 44), font, 0.95, color, 2, cv2.LINE_AA)
        hint = "CLIC DERECHO: GESTOS   CLIC CENTRAL: SIGUIENTE"
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(image, hint, (20, image.shape[0] - 16), font, 0.7, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(
            image, hint, (20, image.shape[0] - 16), font, 0.7, (255, 255, 255), 2, cv2.LINE_AA
        )
        if self.menu_at is None:
            return
        mx, my = self.menu_at
        height = TITLE_H + ITEM_H * len(MENU_ITEMS)
        cv2.rectangle(image, (mx, my), (mx + MENU_W, my + height), (35, 28, 28), -1)
        cv2.rectangle(image, (mx, my), (mx + MENU_W, my + height), (255, 255, 255), 3)
        cv2.putText(image, "GESTO DE LA MANO", (mx + 18, my + 38), font, 0.95, GOLD, 2, cv2.LINE_AA)
        for i, (gesture, label) in enumerate(MENU_ITEMS):
            y0 = my + TITLE_H + i * ITEM_H
            if gesture == self.gesture:
                cv2.rectangle(image, (mx + 4, y0), (mx + MENU_W - 4, y0 + ITEM_H), (90, 70, 40), -1)
            if i == self._hover:
                cv2.rectangle(image, (mx + 4, y0), (mx + MENU_W - 4, y0 + ITEM_H), GOLD, 3)
            text = ("> " if gesture == self.gesture else "  ") + label
            cv2.putText(
                image, text, (mx + 18, y0 + 42), font, 0.85, (255, 255, 255), 2, cv2.LINE_AA
            )
