import json
import random
from unittest.mock import MagicMock

from light_map.catan.board import Board
from light_map.map.map_config import MapEntry
from light_map.persistence.persistence_service import PersistenceService
from light_map.state.world_state import WorldState


SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="5" height="5"/></svg>'


def load(tmp_path, with_board: bool) -> MapEntry:
    svg = tmp_path / "board.svg"
    svg.write_text(SVG)
    if with_board:
        (tmp_path / "board.board.json").write_text(
            json.dumps(Board.random(random.Random(1)).to_dict())
        )

    app = MagicMock()
    app.state = WorldState()
    app.map_config.data.maps = {}
    app.map_config.get_ppi.return_value = 0
    service = PersistenceService(app)
    service.map_config = app.map_config

    service.load_map(str(svg))
    return app.map_config.data.maps[str(svg)]


def test_catan_map_turns_fog_of_war_off(tmp_path):
    assert load(tmp_path, with_board=True).fow_disabled is True


def test_regular_map_keeps_fog_of_war_setting(tmp_path):
    assert load(tmp_path, with_board=False).fow_disabled is False
