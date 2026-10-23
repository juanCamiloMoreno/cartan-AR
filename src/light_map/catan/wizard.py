"""The guided start of a game: how many play, then the rules of the board.

After these two screens the game itself takes over (dice for the order, a corner for each player
and what goes first), so this class only holds the two screens that come before a game exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from light_map.catan.generator import BALANCE_LEVELS, BoardRules


PLAYERS_STEP = "players"
RULES_STEP = "rules"
GAME_STEP = "game"  # the wizard is over: the game phases show the rest

PLAYER_OPTIONS = (2, 3, 4)

# The checklist as it appears on the table: (rule, label). True means "allowed".
RULE_TOGGLES = (
    ("allow_adjacent_same_resource", "RECURSOS IGUALES JUNTOS"),
    ("allow_adjacent_red", "6 Y 8 JUNTOS"),
    ("allow_adjacent_low", "2 Y 12 JUNTOS"),
    ("allow_adjacent_same_number", "NUMEROS IGUALES JUNTOS"),
    ("shuffle_ports", "PUERTOS AL AZAR"),
)
BALANCE_LABELS = {"random": "LIBRE", "fair": "JUSTO", "very_fair": "MUY JUSTO"}


@dataclass
class Wizard:
    step: str = PLAYERS_STEP
    players: int = 3
    rules: dict = field(default_factory=lambda: BoardRules().to_dict())

    def to_dict(self) -> dict:
        return {"step": self.step, "players": self.players, "rules": dict(self.rules)}

    def press(self, button: str) -> bool:
        """Applies a button. Returns True when the rules were accepted (the game can start)."""
        if self.step == PLAYERS_STEP:
            if not button.startswith("players:") or int(button.split(":")[1]) not in PLAYER_OPTIONS:
                raise ValueError("Choose how many play")
            self.players = int(button.split(":")[1])
            self.step = RULES_STEP
            return False
        if self.step == RULES_STEP:
            if button == "ok":
                return True
            if button == "back":
                self.step = PLAYERS_STEP
                return False
            if button == "balance":
                levels = list(BALANCE_LEVELS)
                self.rules["balance"] = levels[
                    (levels.index(self.rules["balance"]) + 1) % len(levels)
                ]
                return False
            if button.startswith("toggle:") and button[7:] in dict(RULE_TOGGLES):
                name = button[7:]
                self.rules[name] = not self.rules[name]
                return False
        raise ValueError("That button does nothing now")
