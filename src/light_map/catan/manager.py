"""Owns the Catan Board and publishes the game into WorldState (the only writer)."""

from __future__ import annotations

import json
import logging
import os
import random

from light_map.catan.board import (
    Board,
    Building,
    edge_from_list,
    edge_to_list,
    roll_dice,
    vertex_from_list,
    vertex_to_list,
)
from light_map.catan.layout import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    SIZE,
    edge_endpoints,
    hex_corners,
    sidecar_path,
    tile_center,
    vertex_position,
)
from light_map.catan.view import BuildingView, CatanView, ProducingTile, RoadView
from light_map.state.world_state import WorldState


class CatanManager:
    def __init__(self, board: Board | None = None, rng: random.Random | None = None):
        self.board = board
        self.rng = rng
        self.last_dice: tuple[int, int] | None = None
        self._loaded_from: str | None = None
        self._sidecar: str | None = None

    # Loading and saving

    def load_for_map(self, svg_path: str | None) -> bool:
        """Loads the board saved next to the SVG map. Returns False if there is none."""
        if not svg_path:
            return False
        if svg_path == self._loaded_from and self.board is not None:
            return True
        path = sidecar_path(svg_path)
        if not os.path.exists(path):
            return False
        try:
            with open(path, encoding="utf-8") as f:
                self.board = Board.from_dict(json.load(f))
        except (OSError, ValueError, KeyError) as exc:
            logging.error("CatanManager: could not load %s: %s", path, exc)
            return False
        self._loaded_from = svg_path
        self._sidecar = path
        self.last_dice = None
        return True

    def sync(self, state: WorldState, svg_path: str | None) -> bool:
        """Loads the board for a map and publishes it (or clears the view if there is none)."""
        if self.load_for_map(svg_path):
            self.publish(state)
            return True
        state.catan = None
        return False

    def _save(self) -> None:
        if self._sidecar is None or self.board is None:
            return
        try:
            with open(self._sidecar, "w", encoding="utf-8") as f:
                json.dump(self.board.to_dict(), f, indent=2)
        except OSError as exc:
            logging.error("CatanManager: could not save %s: %s", self._sidecar, exc)

    # Publishing

    def _geometry(self) -> dict:
        tiles = []
        for (q, r), tile in self.board.tiles.items():
            x, y = tile_center(q, r)
            tiles.append(
                {
                    "q": q,
                    "r": r,
                    "resource": tile.resource,
                    "number": tile.number,
                    "x": x,
                    "y": y,
                    "corners": [list(c) for c in hex_corners(q, r)],
                }
            )
        vertices = []
        for vertex in sorted(self.board.all_vertices(), key=vertex_to_list):
            x, y = vertex_position(vertex)
            vertices.append({"id": vertex_to_list(vertex), "x": x, "y": y})
        edges = []
        for edge in sorted(self.board.all_edges(), key=edge_to_list):
            (x1, y1), (x2, y2) = edge_endpoints(edge)
            edges.append({"id": edge_to_list(edge), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return {
            "edges": edges,
            "width": BOARD_WIDTH,
            "height": BOARD_HEIGHT,
            "size": SIZE,
            "tiles": tiles,
            "vertices": vertices,
        }

    def publish(self, state: WorldState) -> CatanView | None:
        board = self.board
        if board is None:
            return None
        total = sum(self.last_dice) if self.last_dice else None
        producing: tuple[ProducingTile, ...] = ()
        payouts: dict[str, dict[str, int]] = {}
        if total is not None:
            producing = tuple(
                ProducingTile(q, r, tile.resource, tile.number)
                for (q, r), tile in board.tiles.items()
                if tile.number == total and (q, r) != board.robber
            )
            payouts = {p: dict(g) for p, g in board.production(total).items()}
        view = CatanView(
            robber=board.robber,
            dice=self.last_dice,
            total=total,
            producing=producing,
            payouts=payouts,
            buildings=tuple(
                BuildingView(v, player, kind.name.lower())
                for v, (player, kind) in board.buildings.items()
            ),
            board=self._geometry(),
            players=tuple(board.players),
            roads=tuple(RoadView(e, player) for e, player in board.roads.items()),
            stats={p: board.player_stats(p) for p in board.players},
        )
        state.catan = view
        return view

    # Game actions

    def roll(self, state: WorldState, dice: tuple[int, int] | None = None) -> CatanView | None:
        """Rolls (or applies physical dice) and publishes which tiles produce."""
        if self.board is None:
            return None
        self.last_dice = dice or roll_dice(self.rng)
        # Production goes straight to the players' hands (fix it by hand if a roll was a mistake).
        self.board.collect(self.board.production(sum(self.last_dice)))
        self._save()
        return self.publish(state)

    def build(self, state: WorldState, player: str, vertex_cells: list[list[int]]) -> None:
        """Places a settlement, or upgrades the player's own settlement to a city."""
        vertex = vertex_from_list(vertex_cells)
        if vertex not in self.board.all_vertices():
            raise ValueError("That vertex is not on the board")
        current = self.board.buildings.get(vertex)
        if current == (player, Building.SETTLEMENT):
            self.board.build(vertex, player, Building.CITY)
        elif current is None:
            self.board.build(vertex, player, Building.SETTLEMENT)
        else:
            raise ValueError("Vertex is already occupied")
        self._save()
        self.publish(state)

    def remove(self, state: WorldState, vertex_cells: list[list[int]]) -> None:
        self.board.remove(vertex_from_list(vertex_cells))
        self._save()
        self.publish(state)

    def move_robber(self, state: WorldState, tile: tuple[int, int]) -> None:
        self.board.move_robber((int(tile[0]), int(tile[1])))
        self._save()
        self.publish(state)

    def toggle_road(self, state: WorldState, player: str, edge_cells: list[list[int]]) -> None:
        """Builds a road, or removes the player's own road from that edge."""
        self.board.toggle_road(edge_from_list(edge_cells), player)
        self._save()
        self.publish(state)

    def add_cards(self, state: WorldState, player: str, resource: str, amount: int) -> None:
        self.board.add_cards(player, resource, int(amount))
        self._save()
        self.publish(state)

    def set_player_count(self, state: WorldState, count: int) -> None:
        self.board.set_player_count(int(count))
        self._save()
        self.publish(state)

    def set_stats_mode(self, state: WorldState, player: str | None, mode: str) -> None:
        """Sets the statistics panel mode ("simple" | "resources" | "toggle") for one player.

        player None (or "all") applies to everybody.
        """
        self.board.set_stats_mode(None if player in (None, "all") else player, mode)
        self._save()
        self.publish(state)
