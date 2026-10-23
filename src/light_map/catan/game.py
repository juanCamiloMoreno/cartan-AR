"""Turn-by-turn Catan rules on top of Board.

Phases: order (a phased game only: everybody rolls a die, the highest starts), seats and mode
(a guided game only: each player picks a corner, then the table picks what comes first),
setup (two
rounds of settlement + road, the second round in reverse order), reveal (a phased game only:
the tiles and then the number tokens appear one by one), roll, discard (after a 7), robber,
steal, main (build, buy and play development cards, trade with the bank or with players,
end turn), road building (two
free roads from a development card) and finished.
"free" is the sandbox mode: no turns and no costs, everything is allowed.

In a phased game the tiles are hidden until the reveal, so the settlements are placed on the
empty board and the cards of the second settlement are paid once the board is revealed.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

from light_map.catan.board import (
    COSTS,
    PIECE_LIMITS,
    RESOURCE_NAMES,
    WIN_POINTS,
    Board,
    Building,
    Coord,
    Edge,
    Vertex,
    players_to_discard,
    roll_dice,
    vertex_from_list,
    vertex_to_list,
)
from light_map.catan.devcards import (
    KNIGHT,
    MONOPOLY,
    PLAYABLE,
    ROAD_BUILDING,
    YEAR_OF_PLENTY,
    DevCards,
)


FREE = "free"
ORDER = "order"
SETUP = "setup"
REVEAL = "reveal"
SEATS = "seats"
MODE = "mode"
ROLL = "roll"
DISCARD = "discard"
ROBBER = "robber"
STEAL = "steal"
MAIN = "main"
ROAD_BUILDING_PHASE = "road_building"
FINISHED = "finished"
PHASES = (
    FREE,
    ORDER,
    SETUP,
    REVEAL,
    SEATS,
    MODE,
    ROLL,
    DISCARD,
    ROBBER,
    STEAL,
    MAIN,
    ROAD_BUILDING_PHASE,
    FINISHED,
)


SPANISH_RESOURCES = {
    "wood": "madera",
    "brick": "arcilla",
    "sheep": "oveja",
    "wheat": "trigo",
    "ore": "mineral",
}


def _cards_text(cards: dict[str, int]) -> str:
    return " + ".join(f"{n} {SPANISH_RESOURCES.get(r, r)}" for r, n in cards.items())


@dataclass
class GameState:
    phase: str = FREE
    order: list[str] = field(default_factory=list)
    current: int = 0
    turn: int = 0
    setup_index: int = 0
    setup_step: str = "settlement"  # "settlement" or "road"
    last_settlement: Vertex | None = None
    discards: dict[str, int] = field(default_factory=dict)
    victims: list[str] = field(default_factory=list)
    winner: str | None = None
    last_dice: tuple[int, int] | None = None
    # Phased game
    phased: bool = False
    hidden: bool = False  # the tiles and tokens are masked until the reveal
    tile_order: list[Coord] = field(default_factory=list)
    number_order: list[Coord] = field(default_factory=list)
    tiles_shown: int = 0
    numbers_shown: int = 0
    pending_payout: list[tuple[str, Vertex]] = field(default_factory=list)
    order_groups: list[list[str]] = field(default_factory=list)
    order_rolls: dict[str, int] = field(default_factory=dict)
    # Guided game
    wizard: bool = False  # the table is guided: after the order come the seats and the mode
    reveal_first: bool = False  # the board is revealed before the settlements are placed
    # Development cards
    resume_phase: str = MAIN  # where the game goes after a knight or a road building card
    free_roads: int = 0
    dev_played: bool = False  # one development card per turn
    bought: list[str] = field(default_factory=list)  # cards bought this turn (not playable yet)
    # Trading between players
    trade: dict | None = None  # the open offer: from, give, get, to, declined
    last_trade: dict | None = None  # the last exchange that happened

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "order": list(self.order),
            "current": self.current,
            "turn": self.turn,
            "setup_index": self.setup_index,
            "setup_step": self.setup_step,
            "last_settlement": (
                vertex_to_list(self.last_settlement) if self.last_settlement else None
            ),
            "discards": dict(self.discards),
            "victims": list(self.victims),
            "winner": self.winner,
            "last_dice": list(self.last_dice) if self.last_dice else None,
            "phased": self.phased,
            "hidden": self.hidden,
            "tile_order": [list(c) for c in self.tile_order],
            "number_order": [list(c) for c in self.number_order],
            "tiles_shown": self.tiles_shown,
            "numbers_shown": self.numbers_shown,
            "pending_payout": [[p, vertex_to_list(v)] for p, v in self.pending_payout],
            "order_groups": [list(group) for group in self.order_groups],
            "order_rolls": dict(self.order_rolls),
            "wizard": self.wizard,
            "reveal_first": self.reveal_first,
            "resume_phase": self.resume_phase,
            "free_roads": self.free_roads,
            "dev_played": self.dev_played,
            "bought": list(self.bought),
            "trade": self.trade,
            "last_trade": self.last_trade,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GameState:
        phase = data.get("phase", FREE)
        last = data.get("last_settlement")
        dice = data.get("last_dice")
        return cls(
            phase=phase if phase in PHASES else FREE,
            order=list(data.get("order", [])),
            current=int(data.get("current", 0)),
            turn=int(data.get("turn", 0)),
            setup_index=int(data.get("setup_index", 0)),
            setup_step=data.get("setup_step", "settlement"),
            last_settlement=vertex_from_list(last) if last else None,
            discards={p: int(n) for p, n in data.get("discards", {}).items()},
            victims=list(data.get("victims", [])),
            winner=data.get("winner"),
            last_dice=(int(dice[0]), int(dice[1])) if dice else None,
            phased=bool(data.get("phased", False)),
            hidden=bool(data.get("hidden", False)),
            tile_order=[(int(c[0]), int(c[1])) for c in data.get("tile_order", [])],
            number_order=[(int(c[0]), int(c[1])) for c in data.get("number_order", [])],
            tiles_shown=int(data.get("tiles_shown", 0)),
            numbers_shown=int(data.get("numbers_shown", 0)),
            pending_payout=[(p, vertex_from_list(v)) for p, v in data.get("pending_payout", [])],
            order_groups=[list(g) for g in data.get("order_groups", [])],
            order_rolls={p: int(n) for p, n in data.get("order_rolls", {}).items()},
            wizard=bool(data.get("wizard", False)),
            reveal_first=bool(data.get("reveal_first", False)),
            resume_phase=data.get("resume_phase", MAIN)
            if data.get("resume_phase") in PHASES
            else MAIN,
            free_roads=int(data.get("free_roads", 0)),
            dev_played=bool(data.get("dev_played", False)),
            bought=list(data.get("bought", [])),
            trade=data.get("trade"),
            last_trade=data.get("last_trade"),
        )


class Game:
    """Applies the turn rules to a Board. Every method raises ValueError when a move is illegal."""

    def __init__(self, board: Board, rng: random.Random | None = None):
        self.board = board
        self.rng = rng or random.Random()

    @property
    def state(self) -> GameState:
        return self.board.game

    @property
    def active(self) -> bool:
        return self.state.phase != FREE

    @property
    def current_player(self) -> str | None:
        state = self.state
        if state.phase == ORDER:
            pending = self.order_pending()
            return pending[0] if pending else None
        if state.phase == SEATS:
            pending = self.seats_pending()
            return pending[0] if pending else None
        if state.phase in (FREE, FINISHED, REVEAL, MODE) or not state.order:
            return None
        if state.phase == SETUP:
            n = len(state.order)
            i = state.setup_index
            return state.order[i if i < n else 2 * n - 1 - i]
        return state.order[state.current]

    # Helpers

    def _require(self, *phases: str) -> None:
        if self.state.phase not in phases:
            raise ValueError(f"Not allowed now (phase: {self.state.phase})")

    def _require_turn(self, player: str) -> None:
        current = self.current_player
        if player != current:
            raise ValueError(f"It is {current}'s turn")

    def _check_win(self) -> None:
        player = self.current_player
        if player and self.board.victory_points(player) >= WIN_POINTS:
            self.state.phase = FINISHED
            self.state.winner = player

    # Starting and leaving a game

    def new_game(self, players: int, phased: bool = False, wizard: bool = False) -> None:
        """Clears the board and starts a game.

        A phased game hides the tiles: first everybody rolls for the turn order, then the
        settlements go on the empty board, and finally the tiles and number tokens are revealed.
        """
        board = self.board
        board.buildings.clear()
        board.roads.clear()
        board.hands.clear()
        board.longest_road_owner = None
        board.seats = {}
        board.dev = DevCards.new(self.rng)
        board.set_player_count(players)
        board.robber = next(
            (c for c, t in board.tiles.items() if t.resource == "desert"), board.robber
        )
        if not phased:
            self.board.game = GameState(
                phase=SETUP,
                order=list(board.players),
                turn=0,
                setup_index=0,
                setup_step="settlement",
            )
            return
        tile_order = list(board.tiles)
        self.rng.shuffle(tile_order)
        self.board.game = GameState(
            phase=ORDER,
            phased=True,
            wizard=wizard,
            hidden=True,
            order_groups=[list(board.players)],
            tile_order=tile_order,
            number_order=self._spiral(),
        )

    def _spiral(self) -> list[Coord]:
        """Cells with a number token, from the outer ring inward starting at a random corner."""
        tiles = self.board.tiles

        def ring(cell: Coord) -> int:
            q, r = cell
            return max(abs(q), abs(r), abs(q + r))

        def angle(cell: Coord) -> float:
            x = cell[0] + cell[1] / 2
            y = cell[1] * math.sqrt(3) / 2
            return math.atan2(y, x)

        order: list[Coord] = []
        shift = self.rng.randrange(12)
        for depth in (2, 1, 0):
            cells = sorted((c for c in tiles if ring(c) == depth), key=angle)
            if cells:
                turn = shift % len(cells)
                order.extend(cells[turn:] + cells[:turn])
        return [c for c in order if tiles[c].number is not None]

    def free_play(self) -> None:
        """Back to the sandbox: no turns, no costs."""
        self.board.game = GameState()

    # Setup

    def _setup_settlement(self, player: str, vertex: Vertex) -> None:
        if self.state.setup_step != "settlement":
            raise ValueError("Place a road next")
        error = self.board.settlement_error(vertex, player, setup=True)
        if error:
            raise ValueError(error)
        self.board.build(vertex, player, Building.SETTLEMENT)
        state = self.state
        state.last_settlement = vertex
        state.setup_step = "road"
        if state.setup_index >= len(state.order):  # second round pays the adjacent tiles
            if state.hidden:
                state.pending_payout.append((player, vertex))  # paid after the reveal
            else:
                self._pay_adjacent_tiles(player, vertex)

    def _setup_road(self, player: str, edge: Edge) -> None:
        state = self.state
        if state.setup_step != "road":
            raise ValueError("Place a settlement first")
        error = self.board.road_error(edge, player, must_touch=state.last_settlement)
        if error:
            raise ValueError(error)
        self.board.toggle_road(edge, player)
        state.last_settlement = None
        state.setup_index += 1
        state.setup_step = "settlement"
        if state.setup_index >= 2 * len(state.order):
            state.current = 0
            if state.hidden:
                state.phase = REVEAL
            else:
                state.phase = ROLL
                state.turn = 1

    def _pay_adjacent_tiles(self, player: str, vertex: Vertex) -> None:
        for resource, amount in self.board.tile_resources_at(vertex).items():
            self.board.add_cards(player, resource, amount)

    # Turn order (phased games)

    def order_pending(self) -> list[str]:
        """Players who still have to roll in the group that is being decided."""
        state = self.state
        if state.phase != ORDER:
            return []
        group = next((g for g in state.order_groups if len(g) > 1), None)
        if group is None:
            return []
        return [p for p in group if p not in state.order_rolls]

    def order_roll(self, player: str, value: int | None = None) -> int:
        """A player rolls one die for the first turn. Ties roll again among the tied players."""
        self._require(ORDER)
        pending = self.order_pending()
        if player not in pending:
            raise ValueError(f"{player} does not have to roll now")
        value = self.rng.randint(1, 6) if value is None else int(value)
        if not 1 <= value <= 6:
            raise ValueError("A die shows 1 to 6")
        state = self.state
        state.order_rolls[player] = value
        if len(pending) > 1:
            return value
        # Everybody in the group rolled: split it by result, highest first.
        index = next(i for i, g in enumerate(state.order_groups) if len(g) > 1)
        group = state.order_groups[index]
        subgroups = []
        for roll in sorted({state.order_rolls[p] for p in group}, reverse=True):
            subgroups.append([p for p in group if state.order_rolls[p] == roll])
        state.order_groups[index : index + 1] = subgroups
        state.order_rolls = {}
        if all(len(g) == 1 for g in state.order_groups):
            state.order = [g[0] for g in state.order_groups]
            state.order_groups = []
            state.setup_index = 0
            state.setup_step = "settlement"
            state.phase = SEATS if state.wizard else SETUP
        return value

    # Seats and mode (guided games)

    def seats_pending(self) -> list[str]:
        """Players, in turn order, who have not picked their corner yet."""
        if self.state.phase != SEATS:
            return []
        return [p for p in self.state.order if p not in self.board.seats]

    def seat(self, player: str, corner: int) -> None:
        """The player sits in a corner of the table (0 to 3); the panel and the turn light go there."""
        self._require(SEATS)
        pending = self.seats_pending()
        if player not in pending:
            raise ValueError(f"{player} already has a corner")
        corner = int(corner)
        if not 0 <= corner < 4:
            raise ValueError("The table has four corners")
        if corner in self.board.seats.values():
            raise ValueError("That corner is taken")
        self.board.seats[player] = corner
        if len(pending) == 1:
            self.state.phase = MODE

    def choose_mode(self, first: str) -> None:
        """ "map" reveals the board first; "houses" places the settlements on the empty board."""
        self._require(MODE)
        state = self.state
        if first == "map":
            state.reveal_first = True
            state.phase = REVEAL
        elif first == "houses":
            state.phase = SETUP
        else:
            raise ValueError("Choose the map or the houses")
        state.setup_index = 0
        state.setup_step = "settlement"

    # Reveal (phased games)

    def visible(self, cell: Coord) -> tuple[str | None, int | None]:
        """(resource, number) of a tile as the players may see it; None means still hidden."""
        tile = self.board.tiles[cell]
        state = self.state
        if not state.hidden:
            return tile.resource, tile.number
        resource = tile.resource if cell in state.tile_order[: state.tiles_shown] else None
        number = tile.number if cell in state.number_order[: state.numbers_shown] else None
        return resource, number

    def reveal_total(self) -> tuple[int, int]:
        """(tiles revealed, tiles to reveal), counting number tokens as one more step each."""
        state = self.state
        return (
            state.tiles_shown + state.numbers_shown,
            len(state.tile_order) + len(state.number_order),
        )

    def reveal_next(self) -> str:
        """Shows the next tile, or once all tiles are out the next number token."""
        self._require(REVEAL)
        state = self.state
        if state.tiles_shown < len(state.tile_order):
            state.tiles_shown += 1
            what = "tile"
        else:
            state.numbers_shown += 1
            what = "number"
        if state.tiles_shown >= len(state.tile_order) and state.numbers_shown >= len(
            state.number_order
        ):
            self._finish_reveal()
        return what

    def reveal_all(self) -> None:
        self._require(REVEAL)
        state = self.state
        state.tiles_shown = len(state.tile_order)
        state.numbers_shown = len(state.number_order)
        self._finish_reveal()

    def _finish_reveal(self) -> None:
        state = self.state
        state.hidden = False
        state.tile_order = []
        state.number_order = []
        state.tiles_shown = state.numbers_shown = 0
        for player, vertex in state.pending_payout:
            self._pay_adjacent_tiles(player, vertex)
        state.pending_payout = []
        state.current = 0
        if state.reveal_first:  # the board is out: now the settlements
            state.reveal_first = False
            state.phase = SETUP
            state.setup_index = 0
            state.setup_step = "settlement"
            return
        state.phase = ROLL
        state.turn = 1

    # Building

    def build(self, player: str, vertex: Vertex) -> None:
        """Places a settlement, or upgrades the player's settlement to a city."""
        self._require(SETUP, MAIN)
        self._require_turn(player)
        if self.state.phase == SETUP:
            self._setup_settlement(player, vertex)
            return
        board = self.board
        if board.buildings.get(vertex) == (player, Building.SETTLEMENT):
            error, kind = board.city_error(vertex, player), "city"
        else:
            error, kind = board.settlement_error(vertex, player), "settlement"
        if error:
            raise ValueError(error)
        board.pay(player, COSTS[kind])
        board.build(vertex, player, Building.CITY if kind == "city" else Building.SETTLEMENT)
        self._check_win()

    def build_road(self, player: str, edge: Edge) -> None:
        self._require(SETUP, MAIN, ROAD_BUILDING_PHASE)
        self._require_turn(player)
        if self.state.phase == SETUP:
            self._setup_road(player, edge)
            return
        if self.state.phase == ROAD_BUILDING_PHASE:
            error = self.board.road_error(edge, player)
            if error:
                raise ValueError(error)
            self.board.toggle_road(edge, player)  # free: the card pays for it
            self.state.free_roads -= 1
            if self.state.free_roads <= 0 or not self._can_place_road(player):
                self._finish_road_building()
            self._check_win()
            return
        error = self.board.road_error(edge, player)
        if error:
            raise ValueError(error)
        self.board.pay(player, COSTS["road"])
        self.board.toggle_road(edge, player)
        self._check_win()

    # Development cards

    def _can_place_road(self, player: str) -> bool:
        board = self.board
        return any(board.road_error(e, player) is None for e in board.all_edges())

    def _finish_road_building(self) -> None:
        self.state.free_roads = 0
        self.state.phase = self._resume()

    def skip_road_building(self, player: str) -> None:
        """Gives up the free roads that are left."""
        self._require(ROAD_BUILDING_PHASE)
        self._require_turn(player)
        self._finish_road_building()

    def buy_dev_card(self, player: str) -> str:
        """Pays sheep + wheat + ore for the top card of the deck. Returns the card."""
        self._require(MAIN)
        self._require_turn(player)
        board = self.board
        if not board.dev.deck:
            raise ValueError("The development card deck is empty")
        board.pay(player, COSTS["dev"])
        card = board.dev.draw(player)
        self.state.bought.append(card)
        self._check_win()  # a victory point card can win right away
        return card

    def play_dev_card(
        self,
        player: str,
        card: str,
        resources: list[str] | None = None,
        resource: str | None = None,
    ) -> None:
        """Plays a card: one per turn, before or after rolling, never one bought this turn."""
        self._require(ROLL, MAIN)
        self._require_turn(player)
        state, board = self.state, self.board
        if card not in PLAYABLE:
            raise ValueError("That card cannot be played")
        if state.dev_played:
            raise ValueError("Only one development card per turn")
        owned = board.dev.hand(player).get(card, 0)
        if owned <= 0:
            raise ValueError(f"{player} does not have that card")
        if owned - state.bought.count(card) <= 0:
            raise ValueError("That card was bought this turn")
        if card == YEAR_OF_PLENTY:
            wanted = list(resources or [])
            if len(wanted) != 2 or any(r not in RESOURCE_NAMES for r in wanted):
                raise ValueError("Choose two resources")
        if card == MONOPOLY and resource not in RESOURCE_NAMES:
            raise ValueError("Choose a resource")

        board.dev.remove(player, card)
        state.dev_played = True
        if card == KNIGHT:
            board.dev.play_knight(player)
            state.resume_phase = state.phase
            state.phase = ROBBER
        elif card == ROAD_BUILDING:
            roads_left = PIECE_LIMITS["road"] - board.piece_count(player, "road")
            if roads_left > 0 and self._can_place_road(player):
                state.free_roads = min(2, roads_left)
                state.resume_phase = state.phase
                state.phase = ROAD_BUILDING_PHASE
        elif card == YEAR_OF_PLENTY:
            for wanted_resource in wanted:
                board.add_cards(player, wanted_resource, 1)
        elif card == MONOPOLY:
            for other in board.players:
                if other == player:
                    continue
                taken = board.hands.get(other, Counter()).get(resource, 0)
                if taken:
                    board.add_cards(other, resource, -taken)
                    board.add_cards(player, resource, taken)
        self._check_win()

    # Turn flow

    def roll(self, dice: tuple[int, int] | None = None) -> int:
        """Rolls (or takes physical dice) for the current player. Returns the total."""
        self._require(ROLL)
        state = self.state
        state.last_dice = dice or roll_dice(self.rng)
        total = sum(state.last_dice)
        if total == 7:
            hands = {p: sum(self.board.hands.get(p, Counter()).values()) for p in state.order}
            state.discards = players_to_discard(hands)
            state.resume_phase = MAIN
            state.phase = DISCARD if state.discards else ROBBER
        else:
            self.board.collect(self.board.production(total))
            state.phase = MAIN
        return total

    def discard(self, player: str, cards: dict[str, int]) -> None:
        """A player with too many cards after a 7 gives up the required number."""
        self._require(DISCARD)
        state = self.state
        if player not in state.discards:
            raise ValueError(f"{player} does not have to discard")
        cards = {r: int(n) for r, n in cards.items() if int(n) > 0}
        if any(r not in RESOURCE_NAMES for r in cards):
            raise ValueError("Unknown resource")
        if sum(cards.values()) != state.discards[player]:
            raise ValueError(f"{player} must discard exactly {state.discards[player]} cards")
        if not self.board.can_afford(player, cards):
            raise ValueError("Not enough cards")
        self.board.pay(player, cards)
        del state.discards[player]
        if not state.discards:
            state.phase = ROBBER

    def move_robber(self, tile: tuple[int, int]) -> None:
        self._require(ROBBER)
        self.board.move_robber(tile)
        mover = self.current_player
        victims = [
            p
            for p in self.board.stealable_players(tile, mover)
            if sum(self.board.hands.get(p, Counter()).values()) > 0
        ]
        self.state.victims = victims
        self.state.phase = STEAL if victims else self._resume()

    def steal(self, victim: str) -> str:
        """Takes one random card from the victim. Returns the resource that was stolen."""
        self._require(STEAL)
        state = self.state
        if victim not in state.victims:
            raise ValueError(f"{victim} cannot be robbed")
        deck = [r for r, n in self.board.hands[victim].items() for _ in range(n)]
        resource = self.rng.choice(deck)
        self.board.add_cards(victim, resource, -1)
        self.board.add_cards(self.current_player, resource, 1)
        state.victims = []
        state.phase = self._resume()
        return resource

    def _resume(self) -> str:
        """The phase to go back to after the robber (roll if a knight was played before rolling)."""
        phase = self.state.resume_phase
        self.state.resume_phase = MAIN
        return phase

    def bank_trade(self, player: str, give: str, get: str) -> None:
        """Trade with the bank at 4:1, or 3:1 / 2:1 with a settlement on a harbor."""
        self._require(MAIN)
        self._require_turn(player)
        if give not in RESOURCE_NAMES or get not in RESOURCE_NAMES or give == get:
            raise ValueError("Choose two different resources")
        self.board.pay(player, {give: self.board.trade_rate(player, give)})
        self.board.add_cards(player, get, 1)

    # Trading between players

    def _clean_cards(self, cards: dict[str, int] | None) -> dict[str, int]:
        if cards is not None and not isinstance(cards, dict):
            raise ValueError("Invalid offer")
        cleaned: dict[str, int] = {}
        for resource, amount in (cards or {}).items():
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                raise ValueError("Invalid offer") from None
            if amount <= 0:
                continue
            if resource not in RESOURCE_NAMES:
                raise ValueError("Unknown resource")
            cleaned[resource] = amount
        return cleaned

    def _open_trade(self) -> dict:
        trade = self.state.trade
        if not trade:
            raise ValueError("There is no open trade offer")
        return trade

    def propose_trade(
        self,
        player: str,
        give: dict[str, int],
        get: dict[str, int],
        to: str | None = None,
    ) -> None:
        """The player in turn offers cards for cards, to everybody or to one player."""
        self._require(MAIN)
        self._require_turn(player)
        state, board = self.state, self.board
        if state.trade:
            raise ValueError("A trade offer is already open")
        give, get = self._clean_cards(give), self._clean_cards(get)
        if not give or not get:
            raise ValueError("Offer at least one card and ask for at least one")
        if set(give) & set(get):
            raise ValueError("You cannot trade a resource for the same resource")
        if not board.can_afford(player, give):
            raise ValueError(f"{player} does not have those cards")
        if to is not None:
            if to == player:
                raise ValueError("You cannot trade with yourself")
            if to not in state.order:
                raise ValueError(f"Unknown player: {to}")
        state.trade = {"from": player, "give": give, "get": get, "to": to, "declined": []}

    def accept_trade(self, player: str) -> None:
        """Another player takes the offer: both hands change at once."""
        self._require(MAIN)
        state, board = self.state, self.board
        trade = self._open_trade()
        if player == trade["from"]:
            raise ValueError("You cannot accept your own offer")
        if player not in state.order:
            raise ValueError(f"Unknown player: {player}")
        if trade["to"] and trade["to"] != player:
            raise ValueError(f"This offer is for {trade['to']}")
        if not board.can_afford(player, trade["get"]):
            raise ValueError(f"{player} does not have those cards")
        if not board.can_afford(trade["from"], trade["give"]):
            state.trade = None  # the offer cannot be honored any more
            raise ValueError(f"{trade['from']} does not have those cards")
        for resource, amount in trade["give"].items():
            board.add_cards(trade["from"], resource, -amount)
            board.add_cards(player, resource, amount)
        for resource, amount in trade["get"].items():
            board.add_cards(player, resource, -amount)
            board.add_cards(trade["from"], resource, amount)
        state.last_trade = {
            "from": trade["from"],
            "to": player,
            "give": trade["give"],
            "get": trade["get"],
        }
        state.trade = None

    def decline_trade(self, player: str) -> None:
        """A player says no; when nobody is left who could accept, the offer closes."""
        self._require(MAIN)
        state = self.state
        trade = self._open_trade()
        if player == trade["from"]:
            raise ValueError("You cannot accept your own offer")
        if player not in state.order:
            raise ValueError(f"Unknown player: {player}")
        if player not in trade["declined"]:
            trade["declined"].append(player)
        others = [p for p in state.order if p != trade["from"]]
        recipients = [trade["to"]] if trade["to"] else others
        if all(p in trade["declined"] for p in recipients):
            state.trade = None

    def cancel_trade(self, player: str) -> None:
        """The player who made the offer takes it back."""
        self._require(MAIN)
        trade = self._open_trade()
        if player != trade["from"]:
            raise ValueError(f"It is {trade['from']}'s offer")
        self.state.trade = None

    def end_turn(self) -> None:
        self._require(MAIN)
        state = self.state
        state.current = (state.current + 1) % len(state.order)
        state.turn += 1
        state.phase = ROLL
        state.last_dice = None
        state.dev_played = False
        state.bought = []
        state.free_roads = 0
        state.trade = None
        state.last_trade = None

    # Description for the dashboard and the projection

    def hint(self) -> str:
        """What the table is waiting for, in Spanish."""
        state = self.state
        who = self.current_player
        if state.phase == FREE:
            return "Modo libre: sin turnos ni costos."
        if state.phase == ORDER:
            rolled = ", ".join(f"{p} {n}" for p, n in state.order_rolls.items())
            pending = ", ".join(self.order_pending())
            tail = f" (ya sacaron: {rolled})" if rolled else ""
            return f"¿Quién empieza? Tira el dado: {pending}{tail}."
        if state.phase == SEATS:
            return f"Elige tu esquina: {who}."
        if state.phase == MODE:
            return "¿Qué va primero: armar el mapa o poner las casas?"
        if state.phase == REVEAL:
            done, total = self.reveal_total()
            return f"Revelando el tablero: {done} de {total}."
        if state.phase == SETUP:
            what = "una casa" if state.setup_step == "settlement" else "un camino"
            return f"Preparación: {who} pone {what}."
        if state.phase == ROLL:
            return f"Turno de {who}: tira los dados."
        if state.phase == DISCARD:
            pending = ", ".join(f"{p} ({n})" for p, n in state.discards.items())
            return f"Salió 7: deben descartar {pending}."
        if state.phase == ROBBER:
            return f"{who} mueve al ladrón."
        if state.phase == STEAL:
            return f"{who} elige a quién robar: {', '.join(state.victims)}."
        if state.phase == ROAD_BUILDING_PHASE:
            return f"{who} pone {state.free_roads} camino(s) gratis."
        if state.phase == MAIN and state.trade:
            trade = state.trade
            for_whom = f" para {trade['to']}" if trade["to"] else ""
            return (
                f"Oferta de {trade['from']}{for_whom}: da {_cards_text(trade['give'])} "
                f"por {_cards_text(trade['get'])}."
            )
        if state.phase == MAIN:
            return f"Turno de {who}: construye, comercia o termina el turno."
        return f"¡{state.winner} ganó con {WIN_POINTS} puntos!"
