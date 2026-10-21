from unittest.mock import MagicMock

import pytest

import light_map.menu.menu_config as config_vars
from light_map.core.app_context import AppContext
from light_map.core.common_types import Action, TimerKey
from light_map.core.scene import HandInput
from light_map.input.gestures import GestureType
from light_map.map.map_scene import ViewingScene


@pytest.fixture
def context():
    ctx = MagicMock(spec=AppContext)
    ctx.events = MagicMock()
    ctx.events.has_event.return_value = False
    ctx.notifications = MagicMock()
    ctx.app_config = MagicMock()
    ctx.app_config.projector_ppi = 96.0
    ctx.show_tokens = True
    ctx.inspected_token_id = None
    ctx.state = MagicMock()
    ctx.state.pending_actions = []
    return ctx


def hand(gesture):
    return [HandInput(gesture, (100, 100), (0.0, 0.0), None)]


def scheduled_keys(context):
    return [call.kwargs.get("key") for call in context.events.schedule.call_args_list]


def test_roll_gesture_is_not_one_the_menu_or_zoom_already_use():
    used = {
        config_vars.SUMMON_STEP_1_GESTURE,
        config_vars.SUMMON_STEP_2_GESTURE,
        GestureType.POINTING,  # dwell / inspection
        GestureType.CLOSED_FIST,  # pan
    }
    assert config_vars.CATAN_ROLL_GESTURE not in used


def test_holding_the_roll_gesture_schedules_a_roll(context):
    scene = ViewingScene(context)
    scene.update(hand(config_vars.CATAN_ROLL_GESTURE), [], 0.0)

    calls = [
        c
        for c in context.events.schedule.call_args_list
        if c.kwargs.get("key") == TimerKey.CATAN_ROLL_HOLD
    ]
    assert len(calls) == 1
    delay, callback = calls[0].args
    assert delay == config_vars.CATAN_ROLL_HOLD_TIME
    assert callback() == Action.CATAN_ROLL_REQUEST


def test_other_gestures_do_not_schedule_a_roll_and_cancel_a_pending_one(context):
    scene = ViewingScene(context)
    scene.update(hand(GestureType.GUN), [], 0.0)
    assert TimerKey.CATAN_ROLL_HOLD not in scheduled_keys(context)
    context.events.cancel.assert_any_call(TimerKey.CATAN_ROLL_HOLD)


def test_hand_leaving_cancels_the_pending_roll(context):
    scene = ViewingScene(context)
    scene.update([], [], 0.0)
    context.events.cancel.assert_any_call(TimerKey.CATAN_ROLL_HOLD)


def test_no_second_roll_while_waiting_or_cooling_down(context):
    scene = ViewingScene(context)
    for busy in (TimerKey.CATAN_ROLL_HOLD, TimerKey.CATAN_ROLL_COOLDOWN):
        context.events.schedule.reset_mock()
        context.events.has_event.side_effect = lambda key, busy=busy: key == busy
        scene.update(hand(config_vars.CATAN_ROLL_GESTURE), [], 0.0)
        assert TimerKey.CATAN_ROLL_HOLD not in scheduled_keys(context)


def test_the_executed_roll_coming_back_does_not_trigger_another_roll(context):
    # The dispatcher hands the executed "CATAN_ROLL" action back to the scene in the same
    # frame. Treating that as a new request would roll the dice again on every frame.
    scene = ViewingScene(context)
    scene.update([], ["CATAN_ROLL"], 0.0)

    assert context.state.pending_actions == []
    assert TimerKey.CATAN_ROLL_COOLDOWN not in scheduled_keys(context)


def test_roll_request_queues_the_catan_roll_and_starts_the_cooldown(context):
    scene = ViewingScene(context)
    scene.update([], [Action.CATAN_ROLL_REQUEST], 0.0)

    assert context.state.pending_actions == [{"action": "CATAN_ROLL"}]
    calls = [
        c
        for c in context.events.schedule.call_args_list
        if c.kwargs.get("key") == TimerKey.CATAN_ROLL_COOLDOWN
    ]
    assert calls and calls[0].args[0] == config_vars.CATAN_ROLL_COOLDOWN


def test_menu_summoning_still_works(context):
    scene = ViewingScene(context)
    scene.update(hand(config_vars.SUMMON_STEP_1_GESTURE), [], 0.0)
    assert TimerKey.SUMMON_MENU_STEP_1 in scheduled_keys(context)
