import cv2
import numpy as np

from light_map.catan.layout import hex_corners, tile_center, vertex_position
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

        return [ImagePatch(x=0, y=0, width=self.width, height=self.height, data=buffer)]
