"""Owns the Catan Board and publishes the game into WorldState (the only writer)."""

from __future__ import annotations

import json
import logging
import os
import random
import time

from light_map.catan.board import (
    COSTS,
    Board,
    Building,
    edge_from_list,
    edge_to_list,
    roll_dice,
    vertex_from_list,
    vertex_to_list,
)
from light_map.catan.game import FREE, Game
from light_map.catan.generator import BoardRules, GenerationReport, generate_board
from light_map.catan.layout import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    SIZE,
    edge_endpoints,
    hex_corners,
    port_anchor,
    sidecar_path,
    tile_center,
    vertex_position,
)
from light_map.catan.svg import build_blank_svg, build_svg
from light_map.catan.view import BuildingView, CatanView, ProducingTile, RoadView
from light_map.state.world_state import WorldState


class CatanManager:
    def __init__(self, board: Board | None = None, rng: random.Random | None = None):
        self.board = board
        self.rng = rng
        self.last_dice: tuple[int, int] | None = None
        self._loaded_from: str | None = None
        self._sidecar: str | None = None
        self.report: GenerationReport | None = None
        self.notice: dict | None = None  # last rejected move, shown on the dashboard
        self.map_dirty = False  # the SVG changed: the app has to reload the map
        self._svg_blank = False

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

    @property
    def game(self) -> Game:
        return Game(self.board, self.rng)

    @property
    def game_active(self) -> bool:
        return self.board is not None and self.board.game.phase != FREE

    @staticmethod
    def _game_view(game: Game) -> dict:
        state = game.state
        return {
            "phase": state.phase,
            "current_player": game.current_player,
            "turn": state.turn,
            "setup_step": state.setup_step,
            "discards": dict(state.discards),
            "victims": list(state.victims),
            "winner": state.winner,
            "hint": game.hint(),
            "costs": COSTS,
            "phased": state.phased,
            "hidden": state.hidden,
            "order": list(state.order),
            "order_rolls": dict(state.order_rolls),
            "order_pending": game.order_pending(),
            "reveal_done": game.reveal_total()[0],
            "reveal_total": game.reveal_total()[1],
        }

    def notify(self, state: WorldState, text: str) -> None:
        """Tells the dashboard why a move was refused (the id changes on every message)."""
        # The clock can be coarse (1 ms on Windows): keep ids strictly increasing.
        previous = self.notice["id"] if self.notice else 0
        self.notice = {"id": max(time.monotonic_ns(), previous + 1), "text": text}
        if self.board is not None:
            self.publish(state)

    # Publishing

    def _geometry(self) -> dict:
        tiles = []
        game = self.game
        for q, r in self.board.tiles:
            x, y = tile_center(q, r)
            resource, number = game.visible((q, r))
            tiles.append(
                {
                    "q": q,
                    "r": r,
                    "resource": resource or "hidden",
                    "number": number,
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
        ports = []
        for edge, kind in self.board.ports.items():
            (x1, y1), (x2, y2) = edge_endpoints(edge)
            ax, ay = port_anchor(edge, self.board.tiles)
            ports.append(
                {
                    "id": edge_to_list(edge),
                    "kind": kind,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "x": ax,
                    "y": ay,
                }
            )
        return {
            "ports": ports,
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
        game = self.game
        dice = game.state.last_dice if game.active else self.last_dice
        total = sum(dice) if dice else None
        producing: tuple[ProducingTile, ...] = ()
        payouts: dict[str, dict[str, int]] = {}
        if total is not None:
            producing = tuple(
                ProducingTile(q, r, tile.resource, tile.number)
                for (q, r), tile in board.tiles.items()
                if tile.number == total and (q, r) != board.robber
            )
            payouts = {p: dict(g) for p, g in board.production(total).items()}
        hidden = game.state.hidden
        view = CatanView(
            robber=None if game.visible(board.robber)[0] is None else board.robber,
            dice=dice,
            total=total,
            producing=producing,
            payouts=payouts,
            buildings=tuple(
                BuildingView(v, player, kind.name.lower())
                for v, (player, kind) in board.buildings.items()
            ),
            board=self._geometry(),
            players=tuple(board.players),
            game=self._game_view(game),
            generator=self.report.to_dict() if self.report and not hidden else None,
            notice=self.notice,
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
        if self.game_active:
            self.game.roll(dice)
        else:
            self.last_dice = dice or roll_dice(self.rng)
            # Production goes straight to the hands (fix it by hand if a roll was a mistake).
            self.board.collect(self.board.production(sum(self.last_dice)))
        self._save()
        return self.publish(state)

    def build(self, state: WorldState, player: str, vertex_cells: list[list[int]]) -> None:
        """Places a settlement, or upgrades the player's own settlement to a city."""
        vertex = vertex_from_list(vertex_cells)
        if vertex not in self.board.all_vertices():
            raise ValueError("That vertex is not on the board")
        if self.game_active:
            self.game.build(player, vertex)
            self._save()
            self.publish(state)
            return
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
        if self.game_active:
            raise ValueError("Pieces cannot be removed during a game")
        self.board.remove(vertex_from_list(vertex_cells))
        self._save()
        self.publish(state)

    def move_robber(self, state: WorldState, tile: tuple[int, int]) -> None:
        target = (int(tile[0]), int(tile[1]))
        if self.game_active:
            self.game.move_robber(target)
        else:
            self.board.move_robber(target)
        self._save()
        self.publish(state)

    def toggle_road(self, state: WorldState, player: str, edge_cells: list[list[int]]) -> None:
        """Builds a road, or (in free mode) removes the player's own road from that edge."""
        if self.game_active:
            self.game.build_road(player, edge_from_list(edge_cells))
        else:
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

    # Turn-based game

    def _write_svg(self, blank: bool) -> None:
        """Rewrites the map file (empty hexagons or the full board) and asks for a reload."""
        if not self._loaded_from or self.board is None:
            return
        svg = build_blank_svg(self.board.tiles) if blank else build_svg(self.board.tiles)
        try:
            with open(self._loaded_from, "w", encoding="utf-8") as f:
                f.write(svg)
        except OSError as exc:
            logging.error("CatanManager: could not write %s: %s", self._loaded_from, exc)
            return
        self._svg_blank = blank
        self.map_dirty = True

    def new_game(self, state: WorldState, players: int, phased: bool = False) -> None:
        """Clears the board and starts a game with the turn rules.

        A phased game also blanks the map: the tiles come out during the reveal.
        """
        self.game.new_game(int(players), bool(phased))
        self.last_dice = None
        if phased:
            self._write_svg(blank=True)
        elif self._svg_blank:
            self._write_svg(blank=False)
        self._save()
        self.publish(state)

    def order_roll(self, state: WorldState, player: str, value: int | None = None) -> None:
        self.game.order_roll(player, None if value in (None, "") else int(value))
        self._save()
        self.publish(state)

    def _after_reveal(self, state: WorldState) -> None:
        if self.board.game.phase != "reveal" and self._svg_blank:
            self._write_svg(blank=False)  # everything is out: the map shows the whole board
        self._save()
        self.publish(state)

    def reveal_next(self, state: WorldState) -> None:
        self.game.reveal_next()
        self._after_reveal(state)

    def reveal_all(self, state: WorldState) -> None:
        self.game.reveal_all()
        self._after_reveal(state)

    def free_play(self, state: WorldState) -> None:
        self.game.free_play()
        if self._svg_blank:
            self._write_svg(blank=False)
        self._save()
        self.publish(state)

    def end_turn(self, state: WorldState) -> None:
        self.game.end_turn()
        self._save()
        self.publish(state)

    def discard(self, state: WorldState, player: str, cards: dict[str, int]) -> None:
        self.game.discard(player, cards)
        self._save()
        self.publish(state)

    def steal(self, state: WorldState, victim: str) -> None:
        self.game.steal(victim)
        self._save()
        self.publish(state)

    def bank_trade(self, state: WorldState, player: str, give: str, get: str) -> None:
        self.game.bank_trade(player, give, get)
        self._save()
        self.publish(state)

    # New board

    def new_board(self, state: WorldState, rules: dict | None = None) -> None:
        """Generates a new board with the given checklist, rewrites the map and starts over."""
        board, report = generate_board(BoardRules.from_dict(rules), self.rng)
        self.board = board
        self.report = report
        self.last_dice = None
        self._write_svg(blank=False)
        self._save()
        self.publish(state)
