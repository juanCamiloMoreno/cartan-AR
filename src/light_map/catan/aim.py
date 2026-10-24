"""Building by hand: point at a corner or a side of the board, then show "peace" to build there.

The scene (which queues the build) and the feedback layer (which draws the aim) both feed their own
BuildAim with the same hands, so they always agree on what is aimed at.
"""

from __future__ import annotations

from collections.abc import Callable

from light_map.catan.board import edges_of, vertices_of
from light_map.catan.layout import SIZE, edge_endpoints, panel_at, vertex_position
from light_map.catan.screens import screen_kind
from light_map.core.common_types import GestureType


AIM_MEMORY = 4.0  # seconds the aim stays after the finger stops pointing (time to show "peace")
AIM_REACH = SIZE * 0.55  # how far from a corner or side the finger can be and still aim at it
AIM_GESTURE = GestureType.POINTING
BUILD_GESTURE = GestureType.VICTORY

Spot = tuple[str, frozenset]  # ("vertex" | "edge", cells)


def spot_position(spot: Spot) -> tuple[float, float]:
    """World position of a spot (the middle of a side)."""
    kind, cells = spot
    if kind == "vertex":
        return vertex_position(cells)
    (ax, ay), (bx, by) = edge_endpoints(cells)
    return (ax + bx) / 2, (ay + by) / 2


def allowed_kinds(game: dict | None) -> tuple[str, ...]:
    """What the game lets the current player build right now."""
    phase = (game or {}).get("phase")
    if phase == "setup":
        return ("edge",) if (game or {}).get("setup_step") == "road" else ("vertex",)
    if phase == "main":
        return ("vertex", "edge")
    if phase == "road_building":
        return ("edge",)
    return ()


def nearest_spot(world: tuple[float, float], cells, kinds: tuple[str, ...]) -> Spot | None:
    """The corner or side of the board closest to a world point, if the finger is close enough."""
    candidates: list[Spot] = []
    for cell in cells:
        if "vertex" in kinds:
            candidates += [("vertex", v) for v in vertices_of(cell)]
        if "edge" in kinds:
            candidates += [("edge", e) for e in edges_of(cell)]
    best, best_distance = None, AIM_REACH
    for spot in set(candidates):
        x, y = spot_position(spot)
        distance = ((x - world[0]) ** 2 + (y - world[1]) ** 2) ** 0.5
        if distance < best_distance:
            best, best_distance = spot, distance
    return best


def what_it_builds(spot: Spot, view) -> str:
    """ "casa", "ciudad" or "camino": what showing "peace" would build on this spot."""
    kind, cells = spot
    if kind == "edge":
        return "camino"
    current = (view.game or {}).get("current_player")
    for building in view.buildings:
        if (
            building.vertex == cells
            and building.player == current
            and building.kind == "settlement"
        ):
            return "ciudad"
    return "casa"


class BuildAim:
    """Remembers the corner or side the player pointed at until they confirm or let it go."""

    def __init__(self) -> None:
        self.spot: Spot | None = None
        self._seen = 0.0

    def update(
        self,
        hands,
        view,
        screen_to_world: Callable[[float, float], tuple[float, float]],
        screen_size: tuple[int, int],
        now: float,
    ) -> Spot | None:
        """The current aim after looking at this frame's hands (None when nothing is aimed)."""
        kinds = () if screen_kind(view) else allowed_kinds(view.game)
        tiles = [(t["q"], t["r"]) for t in (view.board or {}).get("tiles", [])]
        if not kinds or not tiles:
            self.spot = None
            return None
        for hand in hands:
            if hand.gesture != AIM_GESTURE:
                continue
            if panel_at(hand.proj_pos, list(view.corners), *screen_size):
                continue  # pointing at a player's panel is for the statistics, not for building
            spot = nearest_spot(screen_to_world(*hand.proj_pos), tiles, kinds)
            if spot is not None:
                self.spot, self._seen = spot, now
        if self.spot is not None and (now - self._seen > AIM_MEMORY or self.spot[0] not in kinds):
            self.spot = None
        return self.spot

    def clear(self) -> None:
        self.spot = None


def confirming(hands) -> bool:
    return any(hand.gesture == BUILD_GESTURE for hand in hands)


def build_action(spot: Spot, game: dict | None) -> dict | None:
    """The app action (name and payload) that builds on the spot for the current player."""
    import json

    from light_map.catan.board import edge_to_list, vertex_to_list

    player = (game or {}).get("current_player")
    if not player:
        return None
    kind, cells = spot
    if kind == "vertex":
        payload = {"player": player, "vertex": vertex_to_list(cells)}
        return {"action": "CATAN_BUILD", "payload": json.dumps(payload)}
    payload = {"player": player, "edge": edge_to_list(cells)}
    return {"action": "CATAN_ROAD", "payload": json.dumps(payload)}
