import json
import random
from unittest.mock import MagicMock

import pytest

import light_map.menu.menu_config as config_vars
from light_map.action_dispatcher import handle_catan_roll, handle_catan_ui
from light_map.catan import game as g
from light_map.catan.board import Board, edge_vertices
from light_map.catan.layout import panel_rect
from light_map.catan.manager import CatanManager
from light_map.catan.screens import Button, button_under, buttons, screen_kind
from light_map.catan.wizard import Wizard
from light_map.core.app_context import AppContext
from light_map.core.common_types import Action, TimerKey
from light_map.core.scene import HandInput
from light_map.input.gestures import GestureType
from light_map.map.map_scene import ViewingScene
from light_map.rendering.layers.catan_layer import CatanLayer
from light_map.rendering.layers.hand_feedback_layer import HandFeedbackLayer
from light_map.state.world_state import WorldState


W, H = 1920, 1080


def fresh():
    manager = CatanManager(board=Board.random(random.Random(8)), rng=random.Random(2))
    state = WorldState()
    manager.start_wizard(state)
    return manager, state


def app_for(manager):
    app = MagicMock()
    app.catan_manager = manager
    manager.load_for_map = lambda _path: True
    return app


def to_game(manager, state, players=3):
    manager.press(state, f"players:{players}")
    manager.press(state, "ok")


def finish_order(manager, state):
    while manager.board.game.phase == "order":
        manager.order_roll(state, manager.game.current_player, random.randint(1, 6))


# The two screens before the game


def test_the_wizard_starts_asking_how_many_play():
    manager, state = fresh()
    assert state.catan.wizard["step"] == "players"
    assert screen_kind(state.catan) == "players"
    assert [b.id for b in buttons(state.catan, W, H)] == ["players:2", "players:3", "players:4"]


def test_choosing_the_players_opens_the_rules_with_their_defaults():
    manager, state = fresh()
    manager.press(state, "players:4")
    wizard = state.catan.wizard
    assert wizard["step"] == "rules" and wizard["players"] == 4
    ids = [b.id for b in buttons(state.catan, W, H)]
    assert "ok" in ids and "back" in ids and "balance" in ids
    assert any(i.startswith("toggle:") for i in ids)


def test_rules_toggle_and_balance_cycles():
    manager, state = fresh()
    manager.press(state, "players:3")
    before = state.catan.wizard["rules"]["allow_adjacent_red"]
    manager.press(state, "toggle:allow_adjacent_red")
    assert state.catan.wizard["rules"]["allow_adjacent_red"] is (not before)
    levels = []
    for _ in range(3):
        manager.press(state, "balance")
        levels.append(state.catan.wizard["rules"]["balance"])
    assert levels == ["fair", "very_fair", "random"]
    manager.press(state, "back")
    assert state.catan.wizard["step"] == "players"


def test_a_button_that_does_nothing_is_refused():
    manager, state = fresh()
    with pytest.raises(ValueError):
        manager.press(state, "ok")


def test_accepting_the_rules_builds_the_board_and_starts_the_order():
    manager, state = fresh()
    manager.press(state, "players:3")
    manager.press(state, "balance")
    manager.press(state, "ok")
    assert state.catan.wizard is None  # the wizard screens are over
    game = state.catan.game
    assert game["phase"] == "order" and game["wizard"] is True
    assert len(state.catan.players) == 3
    assert screen_kind(state.catan) == "order"
    assert manager.report is not None  # a new board was generated with the rules


# Order, corners, mode


def test_the_order_is_followed_by_the_corners():
    manager, state = fresh()
    to_game(manager, state)
    finish_order(manager, state)
    game = state.catan.game
    assert game["phase"] == "seats" and screen_kind(state.catan) == "seats"
    assert game["current_player"] == game["order"][0]
    assert [b.id for b in buttons(state.catan, W, H)] == [f"seat:{i}" for i in range(4)]


def test_every_player_picks_a_free_corner_and_the_mode_follows():
    manager, state = fresh()
    to_game(manager, state)
    finish_order(manager, state)
    order = list(state.catan.game["order"])
    picks = {order[0]: 2, order[1]: 0, order[2]: 3}
    for player, corner in picks.items():
        assert state.catan.game["current_player"] == player
        manager.press(state, f"seat:{corner}")
        assert f"seat:{corner}" not in [b.id for b in buttons(state.catan, W, H)]
    assert state.catan.game["phase"] == "mode"
    assert manager.board.seats == picks
    corners = list(state.catan.corners)
    for player, corner in picks.items():
        assert corners[corner] == player
    assert corners[1] is None


def test_a_taken_corner_cannot_be_picked_again():
    manager, state = fresh()
    to_game(manager, state)
    finish_order(manager, state)
    manager.press(state, "seat:1")
    with pytest.raises(ValueError, match="taken"):
        manager.press(state, "seat:1")


def ready_for_mode(players=3):
    manager, state = fresh()
    to_game(manager, state, players)
    finish_order(manager, state)
    for corner in range(players):
        manager.press(state, f"seat:{corner}")
    return manager, state


def test_houses_first_goes_to_the_setup_on_the_hidden_board():
    manager, state = ready_for_mode()
    assert [b.id for b in buttons(state.catan, W, H)] == ["map", "houses"]
    manager.press(state, "houses")
    game = state.catan.game
    assert game["phase"] == "setup" and game["hidden"] is True and screen_kind(state.catan) is None


def test_map_first_reveals_and_then_sets_up_on_the_visible_board():
    manager, state = ready_for_mode()
    manager.press(state, "map")
    assert state.catan.game["phase"] == "reveal"
    for _ in range(200):
        if manager.board.game.phase != "reveal":
            break
        manager.reveal_next(state)
    game = state.catan.game
    assert game["phase"] == "setup" and game["hidden"] is False
    assert manager.board.game.reveal_first is False


def test_after_a_map_first_setup_the_game_goes_to_the_dice_without_a_second_reveal():
    manager, state = ready_for_mode(2)
    manager.press(state, "map")
    manager.game.reveal_all()
    board = manager.board
    for _ in range(4):
        player = manager.game.current_player
        vertex = next(
            v
            for v in sorted(board.all_vertices(), key=sorted)
            if all(c in board.tiles for c in v)
            and board.settlement_error(v, player, setup=True) is None
        )
        manager.game.build(player, vertex)
        edge = next(e for e in board.all_edges() if vertex in edge_vertices(e))
        manager.game.build_road(player, edge)
    assert board.game.phase == "roll" and board.game.turn == 1
    assert sum(sum(h.values()) for h in board.hands.values()) > 0  # the second houses were paid


def test_the_game_state_survives_a_save_and_load():
    manager, state = ready_for_mode()
    data = manager.board.to_dict()
    again = Board.from_dict(json.loads(json.dumps(data)))
    assert again.seats == manager.board.seats and again.game.phase == "mode"
    assert again.game.wizard is True


def test_old_phased_games_keep_their_flow():
    manager = CatanManager(board=Board.random(random.Random(8)), rng=random.Random(2))
    state = WorldState()
    manager.new_game(state, 3, phased=True)
    assert screen_kind(state.catan) is None  # no guided screens without the wizard
    finish_order(manager, state)
    assert manager.board.game.phase == "setup"


# The dice of the order and the table corners


def test_rock_during_the_order_rolls_the_die_of_the_player_whose_turn_it_is():
    manager, state = fresh()
    to_game(manager, state)
    first = state.catan.game["current_player"]
    handle_catan_roll(app_for(manager), {}, state)
    assert first in state.catan.game["order_rolls"]


def test_panels_follow_the_chosen_corners():
    manager, state = ready_for_mode()
    corners = list(state.catan.corners)
    layer = CatanLayer(state, MagicMock(), W, H)
    layer.map_system.world_to_screen.side_effect = lambda x, y: (x, y)
    manager.press(state, "houses")
    patches = layer._generate_patches(0.0)
    assert patches and corners[0] is not None


# Reading the hands


@pytest.fixture
def context():
    ctx = MagicMock(spec=AppContext)
    ctx.events = MagicMock()
    ctx.events.has_event.return_value = False
    ctx.notifications = MagicMock()
    ctx.app_config = MagicMock()
    ctx.app_config.projector_ppi = 96.0
    ctx.app_config.width = W
    ctx.app_config.height = H
    ctx.show_tokens = True
    ctx.inspected_token_id = None
    ctx.raw_tokens = []
    ctx.visibility_engine = None
    ctx.map_system = MagicMock()
    ctx.map_system.screen_to_world.side_effect = lambda sx, sy: (sx, sy)
    return ctx


def scene_for(context, state):
    context.state = state
    scene = ViewingScene(context)
    scene._find_target_at_point = lambda _pos: None
    return scene


def hand(gesture, position):
    return [HandInput(gesture, (int(position[0]), int(position[1])), (0.0, 0.0), None)]


def center(button: Button):
    return button.x + button.w / 2, button.y + button.h / 2


def hold_calls(context, key):
    return [c for c in context.events.schedule.call_args_list if c.kwargs.get("key") == key]


def test_pointing_at_a_button_schedules_its_press_and_queues_it(context):
    manager, state = fresh()
    scene = scene_for(context, state)
    three = next(b for b in buttons(state.catan, W, H) if b.id == "players:3")
    scene.update(hand(GestureType.POINTING, center(three)), [], 0.0)
    (call,) = hold_calls(context, TimerKey.CATAN_BUTTON_HOLD)
    delay, callback = call.args
    assert delay == three.hold and callback() == Action.CATAN_BUTTON_REQUEST
    scene.update([], [Action.CATAN_BUTTON_REQUEST], 1.0)
    (queued,) = state.pending_actions
    assert queued["action"] == "CATAN_UI" and json.loads(queued["payload"]) == {
        "button": "players:3"
    }
    handle_catan_ui(app_for(manager), queued, state)
    assert state.catan.wizard["step"] == "rules"


def test_the_wrong_gesture_or_place_presses_nothing(context):
    manager, state = fresh()
    scene = scene_for(context, state)
    three = next(b for b in buttons(state.catan, W, H) if b.id == "players:3")
    scene.update(hand(GestureType.CLOSED_FIST, center(three)), [], 0.0)
    scene.update(hand(GestureType.POINTING, (5, 5)), [], 0.0)
    assert hold_calls(context, TimerKey.CATAN_BUTTON_HOLD) == []


def test_the_fist_on_a_corner_circle_takes_three_seconds(context):
    manager, state = fresh()
    to_game(manager, state)
    finish_order(manager, state)
    scene = scene_for(context, state)
    seat = buttons(state.catan, W, H)[2]
    scene.update(hand(GestureType.CLOSED_FIST, center(seat)), [], 0.0)
    (call,) = hold_calls(context, TimerKey.CATAN_BUTTON_HOLD)
    assert call.args[0] == 3.0
    assert button_under(state.catan, hand(GestureType.CLOSED_FIST, center(seat))[0], W, H) == seat


def test_pass_turn_is_a_five_second_fist_next_to_the_player_in_turn():
    manager, state = ready_for_mode()
    manager.press(state, "houses")
    game = manager.board.game
    game.phase = "main"
    game.order = ["rojo", "azul", "blanco"]
    game.current = 1
    manager.publish(state)
    (end,) = buttons(state.catan, W, H)
    assert end.id == "end_turn" and end.hold == 5.0 and end.gesture == GestureType.CLOSED_FIST
    corner = state.catan.corners.index("azul")
    px, py, pw, ph = panel_rect(corner, W, H)
    assert not (end.x < px + pw and px < end.x + end.w and end.y < py + ph and py < end.y + end.h)
    manager.press(state, "end_turn")
    assert manager.board.game.current == 2


def test_the_reveal_runs_by_itself(context):
    manager, state = ready_for_mode()
    manager.press(state, "map")
    scene = scene_for(context, state)
    scene.update([], [], 0.0)
    scene.update(hand(GestureType.OPEN_PALM, (900, 500)), [], 0.1)
    (call,) = hold_calls(context, TimerKey.CATAN_REVEAL_TICK)
    assert call.args[0] == config_vars.CATAN_REVEAL_STEP
    scene.update([], [Action.CATAN_REVEAL_REQUEST], 0.5)
    assert state.pending_actions[-1]["action"] == "CATAN_REVEAL_NEXT"


def test_pointing_at_a_panel_does_not_toggle_it_on_the_guided_screens(context):
    manager, state = ready_for_mode()
    scene = scene_for(context, state)
    x, y, w, h = panel_rect(0, W, H)
    scene.update(hand(GestureType.POINTING, (x + w // 2, y + h // 2)), [], 0.0)
    assert hold_calls(context, TimerKey.CATAN_STATS_HOLD) == []


# Drawing


def test_every_guided_screen_draws_something_and_covers_the_board():
    manager, state = fresh()
    layer = CatanLayer(state, MagicMock(), W, H)
    layer.map_system.world_to_screen.side_effect = lambda x, y: (x, y)

    def drawn():
        (patch,) = layer._generate_patches(0.0)
        return patch.data

    players = drawn()
    assert players[..., 3].min() == 255  # fully opaque: the board is hidden underneath
    manager.press(state, "players:3")
    rules = drawn()
    assert rules[..., 3].min() == 255
    manager.press(state, "ok")
    order = drawn()
    finish_order(manager, state)
    seats = drawn()
    for first, second in ((players, rules), (rules, order), (order, seats)):
        assert (first != second).any()
    for corner in range(3):
        manager.press(state, f"seat:{corner}")
    mode = drawn()
    assert mode[..., 3].min() == 255


def test_the_player_in_turn_gets_a_big_marker_in_their_corner():
    manager, state = ready_for_mode()
    manager.press(state, "houses")
    layer = CatanLayer(state, MagicMock(), W, H)
    layer.map_system.world_to_screen.side_effect = lambda x, y: (x, y)
    (before,) = layer._generate_patches(0.0)
    assert state.catan.game["phase"] == "setup"
    assert (before.data[..., 3] > 0).sum() > 100000  # a quarter circle of radius 430 is big


def test_the_feedback_layer_shows_the_progress_on_a_button():
    manager, state = fresh()
    layer = HandFeedbackLayer(state, W, H, MagicMock())
    three = next(b for b in buttons(state.catan, W, H) if b.id == "players:3")
    state.inputs = hand(GestureType.POINTING, center(three))
    layer._generate_patches(0.0)
    hold = layer._hold_for(0, state.inputs[0], 0.5)
    assert hold[0] == "boton" and hold[1] == three.hold and hold[2] == pytest.approx(0.5)
    patches = layer._generate_patches(0.5)
    assert any((p.width, p.height) == (three.w, three.h) for p in patches)


def test_the_wizard_object_keeps_its_rules_independent():
    first, second = Wizard(), Wizard()
    first.rules["allow_adjacent_red"] = True
    assert second.rules["allow_adjacent_red"] is False
    assert g.SEATS == "seats" and g.MODE == "mode"


def test_pointing_at_the_panel_in_the_chosen_corner_toggles_that_player(context):
    manager, state = fresh()
    to_game(manager, state)
    finish_order(manager, state)
    first = state.catan.game["current_player"]
    manager.press(
        state, "seat:3"
    )  # the first player takes the corner that is not theirs by default
    for corner in (0, 1):
        manager.press(state, f"seat:{corner}")
    manager.press(state, "houses")
    scene = scene_for(context, state)
    x, y, w, h = panel_rect(3, W, H)
    scene.update(hand(GestureType.POINTING, (x + w // 2, y + h // 2)), [], 0.0)
    assert scene._stats_target == ("stats", first)


def test_the_shaka_is_in_the_mouse_menu():
    from light_map.input.mouse_hands import MENU_ITEMS

    assert GestureType.SHAKA in [gesture for gesture, _ in MENU_ITEMS]


def test_pointing_at_the_exit_button_for_three_seconds_quits(context):
    from light_map.catan.screens import quit_button

    manager, state = fresh()
    scene = scene_for(context, state)
    exit_button = quit_button(W, H)
    scene.update(hand(GestureType.POINTING, center(exit_button)), [], 0.0)
    (call,) = hold_calls(context, TimerKey.CATAN_BUTTON_HOLD)
    assert call.args[0] == 3.0
    scene.update([], [Action.CATAN_BUTTON_REQUEST], 3.0)
    assert state.pending_actions[-1] == {"action": "QUIT"}


def test_the_exit_button_is_drawn_on_the_guided_screens_and_in_the_game():
    from light_map.catan.screens import quit_button

    manager, state = fresh()
    layer = CatanLayer(state, MagicMock(), W, H)
    layer.map_system.world_to_screen.side_effect = lambda x, y: (x, y)
    exit_button = quit_button(W, H)
    probe = (exit_button.y + exit_button.h // 2, exit_button.x + 8)  # inside, left of the text
    (screen,) = layer._generate_patches(0.0)
    assert screen.data[probe[0], probe[1], 3] == 255
    manager.press(state, "players:3")
    manager.press(state, "ok")
    finish_order(manager, state)
    for corner in range(3):
        manager.press(state, f"seat:{corner}")
    manager.press(state, "houses")
    (board,) = layer._generate_patches(0.0)
    assert board.data[probe[0], probe[1], 3] > 0


def test_a_window_closed_with_its_x_counts_as_closed(monkeypatch):
    from light_map.core import display_utils

    window = display_utils.ProjectorWindow.__new__(display_utils.ProjectorWindow)
    window.name, window.closed, window._frames_shown = "projection", False, 0
    monkeypatch.setattr(display_utils.cv2, "getWindowProperty", lambda *_: 0.0)
    assert window.user_closed() is False  # nothing was shown yet
    window._frames_shown = 5
    assert window.user_closed() is True
    monkeypatch.setattr(display_utils.cv2, "getWindowProperty", lambda *_: 1.0)
    assert window.user_closed() is False
