from unittest.mock import MagicMock

import cv2
import numpy as np

from light_map.core.common_types import GestureType
from light_map.input.mouse_hands import ITEM_H, MENU_ITEMS, MENU_W, TITLE_H, MouseHands


W, H = 1920, 1080


def item_center(mouse, gesture):
    index = next(i for i, (g, _) in enumerate(MENU_ITEMS) if g == gesture)
    mx, my = mouse.menu_at
    return mx + MENU_W // 2, my + TITLE_H + index * ITEM_H + ITEM_H // 2


def test_the_mouse_is_a_pointing_hand_at_the_cursor_by_default():
    mouse = MouseHands(W, H)
    assert mouse.hands() == []  # no cursor seen yet
    mouse.on_mouse(cv2.EVENT_MOUSEMOVE, 300, 200)
    (hand,) = mouse.hands()
    assert hand.gesture == GestureType.POINTING and hand.proj_pos == (300, 200)
    mouse.on_mouse(cv2.EVENT_MOUSEMOVE, 640, 480)
    assert mouse.hands()[0].proj_pos == (640, 480)


def test_right_click_opens_the_menu_and_a_left_click_picks_a_gesture():
    mouse = MouseHands(W, H)
    mouse.on_mouse(cv2.EVENT_RBUTTONDOWN, 400, 300)
    assert mouse.menu_at == (400, 300)
    assert mouse.hands() == []  # the hand waits while the menu is open
    x, y = item_center(mouse, GestureType.ROCK)
    mouse.on_mouse(cv2.EVENT_LBUTTONDOWN, x, y)
    assert mouse.menu_at is None and mouse.gesture == GestureType.ROCK
    mouse.on_mouse(cv2.EVENT_MOUSEMOVE, 500, 500)
    assert mouse.hands()[0].gesture == GestureType.ROCK


def test_clicking_outside_the_menu_closes_it_and_keeps_the_gesture():
    mouse = MouseHands(W, H)
    mouse.gesture = GestureType.CLOSED_FIST
    mouse.on_mouse(cv2.EVENT_RBUTTONDOWN, 100, 100)
    mouse.on_mouse(cv2.EVENT_LBUTTONDOWN, 1500, 900)
    assert mouse.menu_at is None and mouse.gesture == GestureType.CLOSED_FIST


def test_no_hand_takes_the_hand_away():
    mouse = MouseHands(W, H)
    mouse.on_mouse(cv2.EVENT_MOUSEMOVE, 300, 200)
    mouse.on_mouse(cv2.EVENT_RBUTTONDOWN, 300, 200)
    x, y = item_center(mouse, None)
    mouse.on_mouse(cv2.EVENT_LBUTTONDOWN, x, y)
    assert mouse.hands() == []


def test_the_menu_stays_inside_the_screen():
    mouse = MouseHands(W, H)
    mouse.on_mouse(cv2.EVENT_RBUTTONDOWN, W - 10, H - 10)
    mx, my = mouse.menu_at
    assert mx + MENU_W <= W and my + TITLE_H + ITEM_H * len(MENU_ITEMS) <= H


def test_middle_click_goes_to_the_next_gesture_and_wraps_around():
    mouse = MouseHands(W, H)
    seen = [mouse.gesture]
    for _ in range(len([g for g, _ in MENU_ITEMS if g])):
        mouse.on_mouse(cv2.EVENT_MBUTTONDOWN, 10, 10)
        seen.append(mouse.gesture)
    assert seen[0] == seen[-1] and len(set(seen)) == len(seen) - 1


def test_inject_puts_the_hand_in_the_state_and_removes_it_when_gone():
    mouse = MouseHands(W, H)
    state = MagicMock()
    mouse.inject(state, 1.0)
    state.update_inputs.assert_not_called()  # nothing to say before the first move
    mouse.on_mouse(cv2.EVENT_MOUSEMOVE, 50, 60)
    mouse.inject(state, 2.0)
    (hands, now), _ = state.update_inputs.call_args
    assert hands[0].proj_pos == (50, 60) and now == 2.0
    mouse.on_mouse(cv2.EVENT_RBUTTONDOWN, 50, 60)
    mouse.inject(state, 3.0)
    assert state.update_inputs.call_args[0][0] == []  # the menu is open: the hand leaves
    mouse.inject(state, 4.0)
    assert state.update_inputs.call_count == 2  # and it is not reported again


def test_draw_marks_the_hint_and_the_menu():
    mouse = MouseHands(W, H)
    image = np.zeros((H, W, 3), np.uint8)
    mouse.draw(image)
    hint_only = int(image.sum())
    assert hint_only > 0
    mouse.on_mouse(cv2.EVENT_RBUTTONDOWN, 400, 300)
    mouse.draw(image)
    assert int(image.sum()) > hint_only * 10


def test_the_fps_counter_follows_the_frame_rate_and_is_drawn_on_top():
    mouse = MouseHands(W, H)
    for i in range(60):
        mouse.tick(now=1.0 + i * 0.05)  # 20 frames per second
    assert 19 < mouse.fps < 21
    image = np.zeros((H, W, 3), np.uint8)
    mouse.draw(image)
    assert image[:70, W // 2 + 480 :].any()  # the label is in the top strip
