"""The big guided screens of the projection and the buttons on them.

Both the layer that draws the screens and the scene that reads the hands use `buttons`, so what
is drawn is exactly what can be pressed. Every position is in screen pixels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from light_map.catan.layout import panel_rect
from light_map.catan.wizard import PLAYER_OPTIONS, RULE_TOGGLES
from light_map.core.common_types import GestureType


POINT_HOLD = 1.0  # seconds pointing at a button
SEAT_HOLD = 3.0  # seconds with the fist on a corner circle
END_TURN_HOLD = 5.0  # seconds with the fist on the "pass the turn" button
SEAT_RADIUS = 130

# What the whole projection shows instead of the board.
FULL_SCREENS = ("players", "rules", "order", "seats", "mode")


@dataclass(frozen=True)
class Button:
    id: str
    x: int
    y: int
    w: int
    h: int
    label: str
    gesture: GestureType = GestureType.POINTING
    hold: float = POINT_HOLD
    shape: str = "rect"  # "rect" | "circle" (inscribed in the box)
    on: bool | None = None  # the state of a toggle, None for plain buttons

    def contains(self, point: tuple[float, float]) -> bool:
        px, py = point
        if self.shape == "circle":
            return math.hypot(px - (self.x + self.w / 2), py - (self.y + self.h / 2)) <= self.w / 2
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


def screen_kind(view) -> str | None:
    """Which full-screen guide is up: players, rules, order, seats or mode (None: the board)."""
    wizard = getattr(view, "wizard", None)
    if wizard:
        return wizard["step"] if wizard["step"] in ("players", "rules") else None
    phase = (view.game or {}).get("phase")
    if phase in ("order", "seats", "mode") and (view.game or {}).get("wizard"):
        return phase
    return None


def buttons(view, width: int, height: int) -> list[Button]:
    """Every button that can be pressed right now."""
    kind = screen_kind(view)
    game = view.game or {}
    if kind == "players":
        side = 300
        return [
            Button(
                f"players:{n}",
                int(width * (i + 1) / 4 - side / 2),
                height // 2 - side // 2,
                side,
                side,
                str(n),
            )
            for i, n in enumerate(PLAYER_OPTIONS)
        ]
    if kind == "rules":
        rules = view.wizard["rules"]
        row_w, row_h, gap = 1200, 92, 16
        x0 = (width - row_w) // 2
        y0 = 190
        out = [
            Button(
                f"toggle:{name}", x0, y0 + i * (row_h + gap), row_w, row_h, label, on=rules[name]
            )
            for i, (name, label) in enumerate(RULE_TOGGLES)
        ]
        out.append(
            Button(
                "balance", x0, y0 + len(RULE_TOGGLES) * (row_h + gap), row_w, row_h, "EQUILIBRIO"
            )
        )
        bottom = height - 150
        out.append(Button("ok", width // 2 - 220, bottom, 440, 110, "OK"))
        out.append(Button("back", 70, bottom, 260, 110, "ATRAS"))
        return out
    if kind == "mode":
        w, h = 760, 420
        gap = 80
        x0 = (width - 2 * w - gap) // 2
        y = height // 2 - h // 2 + 40
        return [
            Button("map", x0, y, w, h, "1  ARMAR EL MAPA"),
            Button("houses", x0 + w + gap, y, w, h, "2  PONER LAS CASAS"),
        ]
    if kind == "seats":
        taken = {i for i, who in enumerate(view.corners) if who}
        out = []
        for corner in range(4):
            if corner in taken:
                continue
            x, y, pw, ph = panel_rect(corner, width, height)
            cx, cy = x + pw // 2, y + ph // 2
            out.append(
                Button(
                    f"seat:{corner}",
                    cx - SEAT_RADIUS,
                    cy - SEAT_RADIUS,
                    2 * SEAT_RADIUS,
                    2 * SEAT_RADIUS,
                    "AQUI",
                    gesture=GestureType.CLOSED_FIST,
                    hold=SEAT_HOLD,
                    shape="circle",
                )
            )
        return out
    if game.get("phase") == "main" and game.get("current_player") in view.corners:
        corner = view.corners.index(game["current_player"])
        x, y, pw, ph = panel_rect(corner, width, height)
        bh = 110
        by = y - bh - 14 if y > height / 2 else y + ph + 14
        return [
            Button(
                "end_turn",
                x,
                by,
                pw,
                bh,
                "PASAR TURNO",
                gesture=GestureType.CLOSED_FIST,
                hold=END_TURN_HOLD,
            )
        ]
    return []


def button_under(view, hand, width: int, height: int) -> Button | None:
    """The button this hand is pressing: its gesture matches and it is over the button."""
    for button in buttons(view, width, height):
        if hand.gesture == button.gesture and button.contains(hand.proj_pos):
            return button
    return None
