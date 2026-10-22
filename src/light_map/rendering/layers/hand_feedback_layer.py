import cv2
import numpy as np

import light_map.menu.menu_config as config_vars
from light_map.catan.layout import panel_at
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


class HandFeedbackLayer(Layer):
    """Shows where the camera sees each hand, which gesture it reads and how long a hold has left.

    Holds are tracked here only to draw the progress ring; the actions themselves are decided
    by the scenes.
    """

    def __init__(self, state: WorldState, width: int, height: int):
        super().__init__(state=state, is_static=False)
        self.width = width
        self.height = height
        self._hold_started: dict[tuple[int, str], float] = {}

    def get_current_version(self) -> int:
        if self.state is None:
            return 0
        return max(self.state.hands_version, self.state.catan_version)

    def _hold_for(self, index: int, hand, current_time: float) -> tuple[str, float, float] | None:
        """(what it triggers, hold time, seconds held) while this hand holds an action gesture."""
        action = None
        if hand.gesture == config_vars.CATAN_ROLL_GESTURE:
            action = ("dados", config_vars.CATAN_ROLL_HOLD_TIME)
        elif hand.gesture == config_vars.CATAN_STATS_GESTURE:
            view = self.state.catan if self.state is not None else None
            if isinstance(view, CatanView) and panel_at(
                hand.proj_pos, list(view.players), self.width, self.height
            ):
                action = ("panel", config_vars.CATAN_STATS_HOLD_TIME)
        key = (index, action[0]) if action else None
        # Forget holds that ended.
        for old in [k for k in self._hold_started if k[0] == index and k != key]:
            del self._hold_started[old]
        if key is None:
            return None
        started = self._hold_started.setdefault(key, current_time)
        return action[0], action[1], current_time - started

    def _draw_hand(self, hand, hold) -> tuple[np.ndarray, tuple[int, int]]:
        label, color = GESTURES.get(hand.gesture, ("?", UNKNOWN_COLOR))
        patch = np.zeros((PATCH_H, PATCH_W, 4), dtype=np.uint8)
        center = (PATCH_W // 2, 60)
        cv2.circle(patch, center, RING_RADIUS + 4, (0, 0, 0, 255), 8, cv2.LINE_AA)
        cv2.circle(patch, center, RING_RADIUS, (*color, 255), 5, cv2.LINE_AA)
        cv2.circle(patch, center, 5, (*color, 255), -1, cv2.LINE_AA)
        text = label
        if hold is not None:
            what, needed, held = hold
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

    def _generate_patches(self, current_time: float) -> list[ImagePatch]:
        if self.state is None or not self.state.inputs:
            self._hold_started.clear()
            return []

        patches = []
        for index, hand in enumerate(self.state.inputs):
            hold = self._hold_for(index, hand, current_time)
            patch, center = self._draw_hand(hand, hold)
            px, py = hand.proj_pos
            x = int(min(max(px - center[0], 0), max(self.width - PATCH_W, 0)))
            y = int(min(max(py - center[1], 0), max(self.height - PATCH_H, 0)))
            patches.append(ImagePatch(x=x, y=y, width=PATCH_W, height=PATCH_H, data=patch))
        return patches
