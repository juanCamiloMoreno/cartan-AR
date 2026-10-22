import json
import math
import random
import sys
from unittest.mock import MagicMock

import pytest

from light_map.action_dispatcher import handle_catan_new_board
from light_map.catan.board import Board
from light_map.catan.generator import BoardRules, rule_violations
from light_map.catan.layout import BOARD_HEIGHT, BOARD_WIDTH, edge_endpoints
from light_map.catan.manager import CatanManager
from light_map.catan.svg import build_svg
from light_map.state.world_state import WorldState


@pytest.fixture
def table(tmp_path):
    svg = tmp_path / "catan.svg"
    side = tmp_path / "catan.board.json"
    manager = CatanManager(board=Board.random(random.Random(1)), rng=random.Random(2))
    manager._loaded_from = str(svg)
    manager._sidecar = str(side)
    app = MagicMock()
    app.catan_manager = manager
    app.current_map_path = str(svg)
    manager.load_for_map = lambda _path: True
    return app, WorldState(), svg, side


def test_new_board_rewrites_the_svg_and_the_saved_board(table):
    app, state, svg, side = table
    app.catan_manager.new_board(state, {"balance": "fair"})
    saved = json.loads(side.read_text(encoding="utf-8"))
    board = app.catan_manager.board
    assert Board.from_dict(saved).to_dict() == board.to_dict()
    assert len(saved["tiles"]) == 19 and len(saved["ports"]) == 9
    text = svg.read_text(encoding="utf-8")
    assert text.startswith("<svg") and text.count("<polygon") == 19
    assert text == build_svg(board.tiles)


def test_new_board_starts_from_scratch(table):
    app, state, *_ = table
    manager = app.catan_manager
    manager.new_game(state, 3)
    manager.board.add_cards("rojo", "wood", 2)
    manager.new_board(state, None)
    assert manager.board.game.phase == "free"
    assert not manager.board.buildings and not manager.board.roads
    assert not any(manager.board.hands.values())
    assert manager.last_dice is None


def test_the_view_carries_ports_rates_and_the_generation_report(table):
    app, state, *_ = table
    app.catan_manager.new_board(state, {"allow_adjacent_red": False, "balance": "very_fair"})
    data = state.catan.to_dict()
    assert data["generator"]["satisfied"] is True
    assert data["generator"]["rules"]["balance"] == "very_fair"
    assert data["generator"]["metrics"]["avg_spread"] <= 1.0
    ports = data["board"]["ports"]
    assert len(ports) == 9
    assert {p["kind"] for p in ports} >= {"any", "wood", "brick", "sheep", "wheat", "ore"}
    assert data["stats"]["rojo"]["rates"] == {
        r: 4 for r in ("wood", "brick", "sheep", "wheat", "ore")
    }


def test_harbor_markers_sit_in_the_sea_just_outside_the_coast(table):
    app, state, *_ = table
    app.catan_manager.new_board(state, None)
    board = app.catan_manager.board
    center = (BOARD_WIDTH / 2, BOARD_HEIGHT / 2)
    for port in state.catan.board["ports"]:
        edge = frozenset(map(tuple, port["id"]))
        (x1, y1), (x2, y2) = edge_endpoints(edge)
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        anchor = (port["x"], port["y"])
        assert math.dist(anchor, center) > math.dist(mid, center)  # farther from the island
        assert 0 < math.dist(anchor, mid) < 70
        assert 0 <= anchor[0] <= BOARD_WIDTH and 0 <= anchor[1] <= BOARD_HEIGHT
        assert edge in board.ports


def test_dispatcher_generates_with_the_checklist_and_redraws_the_map(table):
    app, state, *_ = table
    payload = {
        "payload": json.dumps(
            {
                "allow_adjacent_same_resource": False,
                "allow_adjacent_red": False,
                "allow_adjacent_low": False,
                "allow_adjacent_same_number": False,
                "balance": "fair",
            }
        )
    }
    handle_catan_new_board(app, payload, state)
    rules = BoardRules(False, False, False, False, balance="fair")
    assert rule_violations(app.catan_manager.board.tiles, rules) == []
    app.load_map.assert_called_once_with(app.current_map_path)


def test_dispatcher_without_payload_uses_the_default_rules(table):
    app, state, *_ = table
    handle_catan_new_board(app, {}, state)
    assert rule_violations(app.catan_manager.board.tiles, BoardRules()) == []
    app.load_map.assert_called_once()


def test_dispatcher_reports_a_bad_rule_and_leaves_the_board_alone(table):
    app, state, *_ = table
    before = app.catan_manager.board.to_dict()
    handle_catan_new_board(app, {"payload": json.dumps({"balance": "perfect"})}, state)
    assert app.catan_manager.board.to_dict() == before
    app.notifications.add_notification.assert_called_once()
    app.load_map.assert_not_called()


def test_the_script_writes_the_svg_and_the_board_with_ports(tmp_path, monkeypatch):
    from scripts import generate_catan_board

    out = tmp_path / "maps" / "mine.svg"
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_catan_board.py", "--seed", "5", "--out", str(out), "--balance", "fair"],
    )
    generate_catan_board.main()
    data = json.loads((tmp_path / "maps" / "mine.board.json").read_text(encoding="utf-8"))
    assert out.exists() and len(data["tiles"]) == 19 and len(data["ports"]) == 9


def test_the_projection_draws_the_harbors(table):
    from light_map.rendering.layers.catan_layer import CatanLayer

    app, state, *_ = table
    manager = app.catan_manager
    manager.board.ports = {}
    manager.publish(state)
    map_system = MagicMock()
    map_system.world_to_screen.side_effect = lambda x, y: (int(x), int(y))
    layer = CatanLayer(state, map_system, 1920, 1080)
    without = layer._generate_patches(0.0)[0].data[..., 3]

    manager.new_board(state, None)
    with_ports = layer._generate_patches(0.0)[0].data[..., 3]
    assert int((with_ports > 0).sum()) > int((without > 0).sum())
    for port in state.catan.board["ports"]:
        x, y = int(port["x"]), int(port["y"])
        assert with_ports[y, x] > 0  # the marker is painted at its anchor
