"""Generate a random Catan board as an SVG map for Light Map.

Also writes <name>.board.json next to the SVG so the game logic knows the same board
(tiles, number tokens and harbors).

Usage: python scripts/generate_catan_board.py [--seed N] [--out maps/catan.svg]
           [--allow-same-resource] [--allow-red] [--no-low-adjacent] [--no-same-number]
           [--balance random|fair|very_fair] [--fixed-ports]
"""

import argparse
import json
import random
from pathlib import Path

from light_map.catan.generator import BALANCE_LEVELS, BoardRules, generate_board
from light_map.catan.layout import sidecar_path
from light_map.catan.svg import build_svg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", default="maps/catan.svg")
    parser.add_argument("--no-same-resource", action="store_true", help="no equal neighbors")
    parser.add_argument("--allow-red", action="store_true", help="allow 6 next to 8")
    parser.add_argument("--no-low-adjacent", action="store_true", help="no 2 next to 12")
    parser.add_argument("--no-same-number", action="store_true", help="no equal numbers touching")
    parser.add_argument("--balance", choices=BALANCE_LEVELS, default="random")
    parser.add_argument("--fixed-ports", action="store_true", help="do not shuffle the harbors")
    args = parser.parse_args()
    rules = BoardRules(
        allow_adjacent_same_resource=not args.no_same_resource,
        allow_adjacent_red=args.allow_red,
        allow_adjacent_low=not args.no_low_adjacent,
        allow_adjacent_same_number=not args.no_same_number,
        balance=args.balance,
        shuffle_ports=not args.fixed_ports,
    )
    board, report = generate_board(rules, random.Random(args.seed))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_svg(board.tiles), encoding="utf-8")
    side = Path(sidecar_path(str(out)))
    side.write_text(json.dumps(board.to_dict(), indent=2), encoding="utf-8")
    note = "" if report.satisfied else " (the rules could not all be met; this is the best board)"
    print(f"Wrote {out} and {side} after {report.attempts} attempts{note}")


if __name__ == "__main__":
    main()
