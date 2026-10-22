"""Development cards: the deck, the hands and the Largest Army card.

Cards: 14 knights, 5 victory points, 2 road building, 2 year of plenty and 2 monopoly.
A card costs one sheep, one wheat and one ore.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field


KNIGHT = "knight"
VICTORY_POINT = "victory_point"
ROAD_BUILDING = "road_building"
YEAR_OF_PLENTY = "year_of_plenty"
MONOPOLY = "monopoly"

DECK = {KNIGHT: 14, VICTORY_POINT: 5, ROAD_BUILDING: 2, YEAR_OF_PLENTY: 2, MONOPOLY: 2}
PLAYABLE = (KNIGHT, ROAD_BUILDING, YEAR_OF_PLENTY, MONOPOLY)  # a victory point is never played
ARMY_MIN = 3  # knights played to claim the Largest Army card
ARMY_POINTS = 2


@dataclass
class DevCards:
    deck: list[str] = field(default_factory=list)
    hands: dict[str, Counter] = field(default_factory=dict)
    knights: dict[str, int] = field(default_factory=dict)  # knights played by each player
    army_owner: str | None = None

    @classmethod
    def new(cls, rng: random.Random | None = None) -> DevCards:
        """A fresh shuffled deck."""
        cards = [card for card, n in DECK.items() for _ in range(n)]
        (rng or random.Random()).shuffle(cards)
        return cls(deck=cards)

    # Hands

    def hand(self, player: str) -> Counter:
        return self.hands.setdefault(player, Counter())

    def count(self, player: str) -> int:
        return sum(self.hands.get(player, Counter()).values())

    def victory_points(self, player: str) -> int:
        return self.hands.get(player, Counter()).get(VICTORY_POINT, 0)

    def draw(self, player: str) -> str:
        if not self.deck:
            raise ValueError("The development card deck is empty")
        card = self.deck.pop()
        self.hand(player)[card] += 1
        return card

    def remove(self, player: str, card: str) -> None:
        hand = self.hand(player)
        if hand.get(card, 0) <= 0:
            raise ValueError(f"{player} does not have that card")
        hand[card] -= 1

    # Largest army

    def play_knight(self, player: str) -> None:
        self.knights[player] = self.knights.get(player, 0) + 1
        self.refresh_army()

    def refresh_army(self) -> None:
        """The card goes to the first player with 3 knights and only to a strictly bigger army."""
        best = max(self.knights.values(), default=0)
        if best < ARMY_MIN:
            self.army_owner = None
            return
        leaders = [p for p, n in self.knights.items() if n == best]
        if self.army_owner in leaders:
            return
        self.army_owner = leaders[0] if len(leaders) == 1 else self.army_owner

    # Saving

    def to_dict(self) -> dict:
        return {
            "deck": list(self.deck),
            "hands": {p: {c: n for c, n in h.items() if n} for p, h in self.hands.items()},
            "knights": dict(self.knights),
            "army_owner": self.army_owner,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> DevCards:
        data = data or {}
        return cls(
            deck=[c for c in data.get("deck", []) if c in DECK],
            hands={
                p: Counter({c: int(n) for c, n in h.items() if c in DECK and int(n) > 0})
                for p, h in data.get("hands", {}).items()
            },
            knights={p: int(n) for p, n in data.get("knights", {}).items()},
            army_owner=data.get("army_owner"),
        )
