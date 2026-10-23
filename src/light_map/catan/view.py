"""Read-only snapshot of the Catan game, published through WorldState."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from light_map.catan.board import PLAYER_NAMES, edge_to_list, vertex_to_list


PLAYERS = PLAYER_NAMES


@dataclass(frozen=True)
class ProducingTile:
    q: int
    r: int
    resource: str
    number: int


@dataclass(frozen=True)
class BuildingView:
    vertex: frozenset
    player: str
    kind: str  # "settlement" | "city"


@dataclass(frozen=True)
class RoadView:
    edge: frozenset
    player: str


@dataclass(frozen=True)
class CatanView:
    robber: tuple[int, int] | None
    dice: tuple[int, int] | None = None
    total: int | None = None
    producing: tuple[ProducingTile, ...] = ()
    payouts: dict[str, dict[str, int]] | None = None
    buildings: tuple[BuildingView, ...] = ()
    board: dict[str, Any] | None = None
    players: tuple[str, ...] = PLAYERS
    roads: tuple[RoadView, ...] = ()
    stats: dict[str, dict[str, Any]] | None = None
    game: dict[str, Any] | None = None
    generator: dict[str, Any] | None = None
    notice: dict[str, Any] | None = None
    wizard: dict[str, Any] | None = None  # the guided start (players and board rules screens)
    corners: tuple[str | None, ...] = (None, None, None, None)  # who sits in each corner

    def to_dict(self) -> dict[str, Any]:
        return {
            "dice": list(self.dice) if self.dice else None,
            "total": self.total,
            "producing": [
                {"q": t.q, "r": t.r, "resource": t.resource, "number": t.number}
                for t in self.producing
            ],
            "robber": list(self.robber) if self.robber else None,
            "payouts": self.payouts or {},
            "buildings": [
                {"vertex": vertex_to_list(b.vertex), "player": b.player, "kind": b.kind}
                for b in self.buildings
            ],
            "players": list(self.players),
            "roads": [{"edge": edge_to_list(r.edge), "player": r.player} for r in self.roads],
            "stats": self.stats or {},
            "game": self.game,
            "generator": self.generator,
            "notice": self.notice,
            "wizard": self.wizard,
            "corners": list(self.corners),
            "board": self.board,
        }
