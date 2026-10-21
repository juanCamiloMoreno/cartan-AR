"""Read-only snapshot of the Catan game, published through WorldState."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from light_map.catan.board import vertex_to_list


PLAYERS = ("rojo", "azul", "blanco", "naranja")


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
class CatanView:
    robber: tuple[int, int]
    dice: tuple[int, int] | None = None
    total: int | None = None
    producing: tuple[ProducingTile, ...] = ()
    payouts: dict[str, dict[str, int]] | None = None
    buildings: tuple[BuildingView, ...] = ()
    board: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dice": list(self.dice) if self.dice else None,
            "total": self.total,
            "producing": [
                {"q": t.q, "r": t.r, "resource": t.resource, "number": t.number}
                for t in self.producing
            ],
            "robber": list(self.robber),
            "payouts": self.payouts or {},
            "buildings": [
                {"vertex": vertex_to_list(b.vertex), "player": b.player, "kind": b.kind}
                for b in self.buildings
            ],
            "players": list(PLAYERS),
            "board": self.board,
        }
