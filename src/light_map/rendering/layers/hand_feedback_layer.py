import cv2
import numpy as np

import light_map.menu.menu_config as config_vars
from light_map.catan.layout import cell_at_world, hex_corners, panel_at, panel_rect
from light_map.catan.view import CatanView
from light_map.core.common_types import GestureType, ImagePatch, Layer
from light_map.state.world_state import WorldState


PATCH_W = 300
PATCH_H = 190
RING_RADIUS = 34

# Label (ASCII only: OpenCV's fonts have no accents) and BGR color for each gesture.
GESTURES = {
    GestureType.OPEN_PALM: ("PALMA", (255, 200, 80)),
    GestureType.CLOSED_FIST: ("PUNO", (120, 120, 255)),
    GestureType.GUN: ("PISTOLA", (80, 220, 255)),
    GestureType.POINTING: ("SENALAR", (120, 255, 120)),
    GestureType.VICTORY: ("PAZ", (255, 120, 255)),
    GestureType.ROCK: ("ROCK", (60, 160, 255)),
    GestureType.SHAKA: ("SHAKA", (255, 255, 120)),
}
UNKNOWN_COLOR = (160, 160, 160)
HIGHLIGHT = (0, 215, 255)  # gold, BGR


class HandFeedbackLayer(Layer):
    """Shows where the camera sees each hand, which gesture it reads and how long a hold has left.

    Holds are tracked here only to draw the progress ring; the actions themselves are decided
    by the scenes.
    """

    def __init__(self, state: WorldState, width: int, height: int, map_system=None):
        super().__init__(state=state, is_static=False)
        self.width = width
        self.height = height
        self.map_system = map_system
        self._hold_started: dict[tuple, float] = {}

    def get_current_version(self) -> int:
        if self.state is None:
            return 0
        return max(self.state.hands_version, self.state.catan_version)

    def _target_of(self, hand) -> tuple[str, object] | None:
        """(what the hold triggers, the target) for a hand that holds an action gesture."""
        if hand.gesture == config_vars.CATAN_ROLL_GESTURE:
            return "dados", None
        if hand.gesture != config_vars.CATAN_STATS_GESTURE:
            return None
        view = self.state.catan if self.state is not None else None
        if not isinstance(view, CatanView):
            return None
        phase = (view.game or {}).get("phase")
        if phase == "robber":
            if self.map_system is None:
                return None
            cell = cell_at_world(*self.map_system.screen_to_world(*hand.proj_pos))
            tiles = {(t["q"], t["r"]) for t in (view.board or {}).get("tiles", [])}
            if cell in tiles and cell != view.robber:
                return "ladron", cell
            return None
        player = panel_at(hand.proj_pos, list(view.players), self.width, self.height)
        if not player:
            return None
        if phase == "steal":
            return ("robar", player) if player in (view.game or {}).get("victims", []) else None
        return "panel", player

    def _hold_for(self, index: int, hand, current_time: float):
        """(what it triggers, hold time, seconds held, target) while a hand holds an action."""
        found = self._target_of(hand)
        key = (index, found[0], found[1]) if found else None
        # Forget holds that ended or moved to another target.
        for old in [k for k in self._hold_started if k[0] == index and k != key]:
            del self._hold_started[old]
        if key is None:
            return None
        needed = (
            config_vars.CATAN_ROLL_HOLD_TIME
            if found[0] == "dados"
            else config_vars.CATAN_STATS_HOLD_TIME
        )
        started = self._hold_started.setdefault(key, current_time)
        return found[0], needed, current_time - started, found[1]

    def _draw_hand(self, hand, hold) -> tuple[np.ndarray, tuple[int, int]]:
        label, color = GESTURES.get(hand.gesture, ("?", UNKNOWN_COLOR))
        patch = np.zeros((PATCH_H, PATCH_W, 4), dtype=np.uint8)
        center = (PATCH_W // 2, 60)
        cv2.circle(patch, center, RING_RADIUS + 4, (0, 0, 0, 255), 8, cv2.LINE_AA)
        cv2.circle(patch, center, RING_RADIUS, (*color, 255), 5, cv2.LINE_AA)
        cv2.circle(patch, center, 5, (*color, 255), -1, cv2.LINE_AA)
        text = label
        if hold is not None:
            what, needed, held, _target = hold
            progress = min(1.0, held / needed)
            done = progress >= 1.0
            arc_color = (80, 230, 80) if done else (255, 255, 255)
            cv2.ellipse(
                patch,
                center,
                (RING_RADIUS + 12, RING_RADIUS + 12),
                -90,
                0,
                360 * progress,
                (*arc_color, 255),
                7,
                cv2.LINE_AA,
            )
            text = f"{label} -> {what}" + (" OK" if done else "")
        font = cv2.FONT_HERSHEY_SIMPLEX
        origin = (10, 140)
        cv2.putText(patch, text, origin, font, 0.85, (0, 0, 0, 255), 6, cv2.LINE_AA)
        cv2.putText(patch, text, origin, font, 0.85, (255, 255, 255, 255), 2, cv2.LINE_AA)
        return patch, center

    def _highlight(self, hold) -> ImagePatch | None:
        """Lights up what the hand is aiming at: the hexagon for the robber, a panel to steal."""
        if hold is None:
            return None
        what, needed, held, target = hold
        progress = min(1.0, held / needed)
        color = (80, 230, 80) if progress >= 1.0 else HIGHLIGHT
        if what == "ladron" and self.map_system is not None:
            points = np.array(
                [self.map_system.world_to_screen(x, y) for x, y in hex_corners(*target)], np.int32
            )
            x0, y0 = points.min(axis=0) - 12
            x1, y1 = points.max(axis=0) + 12
            x0, y0 = max(int(x0), 0), max(int(y0), 0)
            x1, y1 = min(int(x1), self.width), min(int(y1), self.height)
            if x1 <= x0 or y1 <= y0:
                return None
            patch = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
            local = points - np.array([x0, y0], np.int32)
            cv2.fillPoly(patch, [local], (*color, 90), lineType=cv2.LINE_AA)
            cv2.polylines(patch, [local], True, (*color, 255), 10, cv2.LINE_AA)
            return ImagePatch(x=x0, y=y0, width=x1 - x0, height=y1 - y0, data=patch)
        if what in ("robar", "panel"):
            view = self.state.catan
            index = list(view.players).index(target)
            x, y, w, h = panel_rect(index, self.width, self.height)
            patch = np.zeros((h, w, 4), dtype=np.uint8)
            cv2.rectangle(patch, (0, 0), (w - 1, h - 1), (*color, 255), 12)
            return ImagePatch(x=x, y=y, width=w, height=h, data=patch)
        return None

    def _generate_patches(self, current_time: float) -> list[ImagePatch]:
        if self.state is None or not self.state.inputs:
            self._hold_started.clear()
            return []

        patches = []
        for index, hand in enumerate(self.state.inputs):
            hold = self._hold_for(index, hand, current_time)
            highlight = self._highlight(hold)
            if highlight is not None:
                patches.append(highlight)
            patch, center = self._draw_hand(hand, hold)
            px, py = hand.proj_pos
            x = int(min(max(px - center[0], 0), max(self.width - PATCH_W, 0)))
            y = int(min(max(py - center[1], 0), max(self.height - PATCH_H, 0)))
            patches.append(ImagePatch(x=x, y=y, width=PATCH_W, height=PATCH_H, data=patch))
        return patches
